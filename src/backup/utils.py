import io
import json
import os
import shutil
import tarfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.db import transaction

_progress_lock = threading.Lock()
_progress_store = {}


def _get_backup_root():
    backup_root = getattr(settings, "BACKUP_ROOT", None)
    if backup_root:
        path = Path(backup_root)
    else:
        path = Path(settings.BASE_DIR) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_media_root():
    return Path(settings.MEDIA_ROOT)


def _clear_directory_contents(directory):
    """Clear all contents of a directory without removing the directory itself.
    This avoids 'Device or resource busy' errors when the directory is a mounted volume."""
    if not directory.exists():
        return

    for item in directory.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except (OSError, IOError):
            pass


def _get_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _set_progress(task_id, step, message):
    """Store progress in memory for a task."""
    with _progress_lock:
        _progress_store[task_id] = {"step": step, "message": message}


def get_progress(task_id):
    """Retrieve progress for a task. Returns dict or None."""
    with _progress_lock:
        return _progress_store.get(task_id)


def clear_progress(task_id):
    """Clear progress for a task."""
    with _progress_lock:
        _progress_store.pop(task_id, None)


def create_db_dump(backup_dir):
    """Create a JSON dump of all production app data (excluding auth/sessions)."""
    db_dump_path = backup_dir / "database.json"
    call_command(
        "dumpdata",
        "production",
        "--natural-foreign",
        "--natural-primary",
        "--indent=2",
        output=str(db_dump_path),
    )
    return db_dump_path


def create_media_archive(backup_dir):
    """Create a tar.gz archive of the media directory."""
    media_root = _get_media_root()
    archive_path = backup_dir / "media.tar.gz"

    if not media_root.exists():
        return None

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(media_root, arcname="media")

    return archive_path


def create_full_backup(task_id=None):
    """Create a full backup (DB + media). Returns the backup directory path."""
    backup_root = _get_backup_root()
    timestamp = _get_timestamp()
    backup_dir = backup_root / "backup_{}".format(timestamp)
    backup_dir.mkdir(parents=True, exist_ok=True)

    if task_id:
        _set_progress(task_id, 1, "Создание дампа базы данных...")

    db_dump_path = create_db_dump(backup_dir)

    if task_id:
        _set_progress(task_id, 2, "Архивирование медиафайлов...")

    media_archive_path = create_media_archive(backup_dir)

    if task_id:
        _set_progress(task_id, 3, "Сохранение манифеста...")

    manifest = {
        "timestamp": timestamp,
        "db_dump": db_dump_path.name,
        "media_archive": media_archive_path.name if media_archive_path else None,
        "created_at": timestamp,
    }

    manifest_path = backup_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    if task_id:
        _set_progress(task_id, 4, "Готово!")
        clear_progress(task_id)

    return backup_dir


def list_backups():
    """List all available backups sorted by timestamp (newest first)."""
    backup_root = _get_backup_root()
    backups = []
    for item in backup_root.iterdir():
        if item.is_dir() and item.name.startswith("backup_"):
            manifest_path = item / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    backups.append(
                        {
                            "name": item.name,
                            "path": str(item),
                            "timestamp": manifest.get("timestamp", ""),
                            "created_at": manifest.get("created_at", ""),
                        }
                    )
                except (json.JSONDecodeError, OSError):
                    continue
            else:
                backups.append(
                    {
                        "name": item.name,
                        "path": str(item),
                        "timestamp": item.name.replace("backup_", ""),
                        "created_at": item.name.replace("backup_", ""),
                    }
                )

    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups


def restore_backup(backup_name, restore_db=True, restore_media=True, task_id=None):
    """Restore a backup by name. Returns (success, message)."""
    backup_root = _get_backup_root()
    backup_dir = backup_root / backup_name

    if not backup_dir.exists():
        return False, "Бэкап '{}' не найден.".format(backup_name)

    db_dump_path = backup_dir / "database.json"
    media_archive_path = backup_dir / "media.tar.gz"

    if restore_db and not db_dump_path.exists():
        return False, "Файл database.json не найден в бэкапе."

    if restore_media and not media_archive_path.exists():
        return False, "Файл media.tar.gz не найден в бэкапе."

    try:
        if task_id:
            _set_progress(task_id, 1, "Очистка текущих данных...")

        with transaction.atomic():
            if restore_db:
                if task_id:
                    _set_progress(task_id, 2, "Восстановление базы данных...")
                call_command(
                    "loaddata",
                    str(db_dump_path),
                    verbosity=1,
                )

        if restore_media:
            if task_id:
                _set_progress(task_id, 3, "Восстановление медиафайлов...")
            media_root = _get_media_root()
            _clear_directory_contents(media_root)
            media_root.mkdir(parents=True, exist_ok=True)

            with tarfile.open(media_archive_path, "r:gz") as tar:
                tar.extractall(path=str(media_root.parent))

            extracted_media = media_root.parent / "media"
            if extracted_media.exists() and extracted_media != media_root:
                for item in extracted_media.iterdir():
                    dest = media_root / item.name
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    shutil.move(str(item), str(dest))
                shutil.rmtree(extracted_media, ignore_errors=True)

        if task_id:
            _set_progress(task_id, 4, "Готово!")
            clear_progress(task_id)

        return True, "Бэкап '{}' успешно восстановлен.".format(backup_name)
    except Exception as e:
        if task_id:
            _set_progress(task_id, 0, "Ошибка: {}".format(str(e)))
        return False, "Ошибка при восстановлении: {}".format(str(e))


def wipe_all_data(confirmation_token):
    """
    Wipe all production data. Requires exact token confirmation 'WIPE_ALL_DATA_CONFIRMED'.
    Returns (success, message).
    """
    if confirmation_token != "WIPE_ALL_DATA_CONFIRMED":
        return False, "Неверный токен подтверждения. Введите 'WIPE_ALL_DATA_CONFIRMED'."

    models_to_wipe = [
        "production.ProductionRecord",
        "production.LotInfo",
        "production.ManualDefect",
        "production.SNComment",
        "production.Report5Comment",
        "production.SNPhoto",
    ]

    try:
        with transaction.atomic():
            for model_path in models_to_wipe:
                app_label, model_name = model_path.split(".")
                from django.apps import apps

                model = apps.get_model(app_label, model_name)
                model.objects.all().delete()

        media_root = _get_media_root()
        if media_root.exists():
            for item in media_root.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        return True, "Все данные успешно удалены."
    except Exception as e:
        return False, f"Ошибка при удалении данных: {str(e)}"


def get_backup_info(backup_name):
    """Get detailed info about a specific backup."""
    backup_root = _get_backup_root()
    backup_dir = backup_root / backup_name

    if not backup_dir.exists():
        return None

    info = {
        "name": backup_name,
        "path": str(backup_dir),
        "timestamp": backup_name.replace("backup_", ""),
        "files": [],
        "size": 0,
    }

    for item in backup_dir.iterdir():
        if item.is_file():
            size = item.stat().st_size
            info["files"].append({"name": item.name, "size": size})
            info["size"] += size

    return info


def download_backup(backup_name):
    """Generate a tar.gz archive of a backup directory for download.
    Returns a file-like object with the archive content."""
    backup_root = _get_backup_root()
    backup_dir = backup_root / backup_name

    if not backup_dir.exists():
        return None

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        tar.add(backup_dir, arcname=backup_name)

    buffer.seek(0)
    return buffer


def upload_and_restore(archive_file, task_id=None):
    """Restore from an uploaded tar.gz archive.
    Extracts the archive, looks for database.json and media.tar.gz inside.
    Returns (success, message)."""
    if task_id:
        _set_progress(task_id, 1, "Сохранение загруженного архива...")

    backup_root = _get_backup_root()
    temp_dir = Path(NamedTemporaryFile(delete=False).name + "_restore")
    temp_dir.mkdir(parents=True, exist_ok=True)

    archive_path = temp_dir / "uploaded.tar.gz"
    with open(archive_path, "wb") as f:
        for chunk in archive_file.chunks():
            f.write(chunk)

    try:
        if task_id:
            _set_progress(task_id, 2, "Извлечение архива...")

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=temp_dir)

        db_dump_path = None
        media_archive_path = None

        for item in temp_dir.rglob("database.json"):
            db_dump_path = item
            break
        for item in temp_dir.rglob("media.tar.gz"):
            media_archive_path = item
            break

        if not db_dump_path:
            return False, "В архиве не найден database.json."

        with transaction.atomic():
            if task_id:
                _set_progress(task_id, 3, "Восстановление базы данных...")
            call_command("loaddata", str(db_dump_path), verbosity=1)

        if media_archive_path:
            if task_id:
                _set_progress(task_id, 4, "Восстановление медиафайлов...")
            media_root = _get_media_root()
            _clear_directory_contents(media_root)
            media_root.mkdir(parents=True, exist_ok=True)

            with tarfile.open(media_archive_path, "r:gz") as tar:
                tar.extractall(path=str(media_root.parent))

            extracted_media = media_root.parent / "media"
            if extracted_media.exists() and extracted_media != media_root:
                for item in extracted_media.iterdir():
                    dest = media_root / item.name
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    shutil.move(str(item), str(dest))
                shutil.rmtree(extracted_media, ignore_errors=True)

        if task_id:
            _set_progress(task_id, 5, "Готово!")
            clear_progress(task_id)

        return True, "Восстановление из загруженного архива выполнено успешно."
    except Exception as e:
        if task_id:
            _set_progress(task_id, 0, "Ошибка: {}".format(str(e)))
        return False, "Ошибка при восстановлении: {}".format(str(e))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
