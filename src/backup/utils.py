import hashlib
import io
import json
import logging
import re
import shutil
import tarfile
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction

logger = logging.getLogger(__name__)

_progress_lock = threading.Lock()

# Progress is stored on disk (per-task JSON files) so that it is visible
# across multiple Gunicorn workers.  An in-memory dict would be lost the
# moment a polling request lands on a different worker than the one running
# the background thread, causing progress_view to treat the task as
# "completed" prematurely.
_PROGRESS_DIR = Path(tempfile.gettempdir()) / "mes_reports_progress"
_PROGRESS_DIR.mkdir(parents=True, exist_ok=True)


def _progress_file_path(task_id):
    """Return the filesystem path for a given task's progress file."""
    # Sanitise the task_id so it cannot escape the progress directory.
    safe = "".join(c for c in task_id if c.isalnum() or c in ("-", "_"))
    return _PROGRESS_DIR / "{}.json".format(safe)

# Project identifier written into every backup manifest.
# Archives created for a different project will be rejected on restore.
PROJECT_IDENTIFIER = "mes_reports"

# Models managed by the production app — used for clearing, counting, and
# sequence resetting.
PRODUCTION_MODELS = [
    "production.Production",
    "production.FaultAttachment",
    "production.FaultJournal",
    "production.UnitPhoto",
    "production.ControlUnit",
    "production.Lot",
    "production.Station",
    "production.TestDataTranslation",
]


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


def _set_progress(task_id, step, message, total_steps=None, percent=None, status="running"):
    """Store progress on disk so it is visible across Gunicorn workers."""
    if not task_id:
        return
    with _progress_lock:
        data = {
            "step": step,
            "message": message,
            "status": status,
        }
        if total_steps is not None:
            data["total_steps"] = total_steps
        if percent is not None:
            data["percent"] = percent
        path = _progress_file_path(task_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data), encoding="utf-8")
        tmp_path.replace(path)


def get_progress(task_id):
    """Retrieve progress for a task from disk. Returns dict or None."""
    if not task_id:
        return None
    with _progress_lock:
        path = _progress_file_path(task_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None


def clear_progress(task_id):
    """Clear progress for a task by removing its file."""
    if not task_id:
        return
    with _progress_lock:
        path = _progress_file_path(task_id)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass


def consume_progress(task_id):
    """Read a task's progress and remove its file (used once by the index page)."""
    data = get_progress(task_id)
    if data is not None:
        clear_progress(task_id)
    return data


class _DumpProgressWriter:
    """File-like wrapper that counts serialized objects during dumpdata."""

    def __init__(self, target, task_id, total_records):
        self.target = target
        self.task_id = task_id
        self.total_records = total_records
        self.count = 0
        self.last_percent = -1

    def write(self, data):
        self.target.write(data)
        if self.total_records:
            self.count += data.count('"model":')
            percent = min(55, 5 + int(self.count / self.total_records * 50))
            if percent != self.last_percent:
                self.last_percent = percent
                _set_progress(
                    self.task_id,
                    1,
                    "Создание дампа БД... {}/{}".format(self.count, self.total_records),
                    total_steps=4,
                    percent=percent,
                )
        return len(data)

    def flush(self):
        self.target.flush()


class _LoadProgressWriter(io.StringIO):
    """StringIO that parses loaddata progress lines and updates progress."""

    def __init__(self, task_id, total_records, base_percent, span_percent, step, total_steps):
        super().__init__()
        self.task_id = task_id
        self.total_records = total_records
        self.base_percent = base_percent
        self.span_percent = span_percent
        self.step = step
        self.total_steps = total_steps
        self.last_percent = -1

    def write(self, s):
        result = super().write(s)
        if self.total_records:
            matches = re.findall(r"Processed (\d+) object", s)
            if matches:
                processed = int(matches[-1])
                percent = self.base_percent + int(processed / self.total_records * self.span_percent)
                percent = min(percent, self.base_percent + self.span_percent)
                if percent != self.last_percent:
                    self.last_percent = percent
                    _set_progress(
                        self.task_id,
                        self.step,
                        "Восстановление базы данных... {}/{}".format(processed, self.total_records),
                        total_steps=self.total_steps,
                        percent=percent,
                    )
        return result


def _get_production_models():
    """Return list of (app_label, model) pairs for production models."""
    models = []
    for model_path in PRODUCTION_MODELS:
        app_label, model_name = model_path.split(".")
        model = apps.get_model(app_label, model_name)
        models.append(model)
    return models


def _clear_production_data(model_counts=None):
    """Delete all records from production models and reset PostgreSQL sequences.

    Args:
        model_counts: Optional dict of model label -> count, used for logging.
    """
    models = _get_production_models()
    for model in models:
        label = model._meta.label
        count = model.objects.count()
        if count:
            model.objects.all().delete()
            logger.info("Cleared %d records from %s", count, label)

    # Reset PostgreSQL sequences so that auto-incrementing PKs don't collide
    # with explicit PKs loaded from the fixture.
    _reset_sequences(models)


def _reset_sequences(models):
    """Reset auto-increment sequences for the given models to start at 1."""
    with connection.cursor() as cursor:
        for model in models:
            seq_name = f"{model._meta.db_table}_id_seq"
            cursor.execute(
                "SELECT relname FROM pg_class WHERE relname = %s", [seq_name]
            )
            if cursor.fetchone():
                try:
                    cursor.execute(
                        f"ALTER SEQUENCE {seq_name} RESTART WITH 1"
                    )
                    logger.info("Reset sequence %s to 1", seq_name)
                except Exception as e:
                    logger.warning("Could not reset sequence %s: %s", seq_name, e)


def _compute_file_checksum(filepath):
    """Compute SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _get_model_counts():
    """Return dict of model label -> record count for all production models."""
    counts = {}
    for model in _get_production_models():
        counts[model._meta.label] = model.objects.count()
    return counts


def _read_manifest(backup_dir):
    """Read and return the manifest.json from a backup directory.
    Returns None if manifest is missing or invalid."""
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def create_db_dump(backup_dir, task_id=None):
    """Create a UTF-8 JSON dump of all production app data."""
    db_dump_path = backup_dir / "database.json"
    total_records = sum(_get_model_counts().values())
    with open(db_dump_path, "w", encoding="utf-8") as dump_file:
        writer = _DumpProgressWriter(dump_file, task_id, total_records)
        call_command(
            "dumpdata",
            "production",
            "--natural-foreign",
            "--natural-primary",
            "--indent=2",
            stdout=writer,
        )
    return db_dump_path


def create_media_archive(backup_dir, task_id=None):
    """Create a tar.gz archive of the media directory."""
    media_root = _get_media_root()
    archive_path = backup_dir / "media.tar.gz"

    if not media_root.exists():
        return None

    total_size = 0
    for item in media_root.rglob("*"):
        try:
            if item.is_file():
                total_size += item.stat().st_size
        except OSError:
            continue

    processed_size = 0
    last_percent = -1

    def _filter(tarinfo):
        nonlocal processed_size, last_percent
        if tarinfo.isfile():
            processed_size += tarinfo.size
            if total_size:
                fraction = processed_size / total_size
                percent = min(90, 55 + int(fraction * 35))
                if percent != last_percent:
                    last_percent = percent
                    _set_progress(
                        task_id,
                        2,
                        "Архивирование медиафайлов... {}%".format(int(fraction * 100)),
                        total_steps=4,
                        percent=percent,
                    )
        return tarinfo

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(media_root, arcname="media", filter=_filter)

    if task_id and last_percent < 90:
        _set_progress(
            task_id,
            2,
            "Архивирование медиафайлов...",
            total_steps=4,
            percent=90,
        )

    return archive_path


def create_full_backup(task_id=None):
    """Create a full backup (DB + media). Returns the backup directory path."""
    backup_root = _get_backup_root()
    timestamp = _get_timestamp()
    backup_dir = backup_root / "backup_{}".format(timestamp)
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        if task_id:
            _set_progress(task_id, 1, "Создание дампа базы данных...", total_steps=4, percent=5)

        db_dump_path = create_db_dump(backup_dir, task_id=task_id)

        if task_id:
            _set_progress(task_id, 2, "Архивирование медиафайлов...", total_steps=4, percent=55)

        media_archive_path = create_media_archive(backup_dir, task_id=task_id)

        if task_id:
            _set_progress(task_id, 3, "Сохранение манифеста...", total_steps=4, percent=92)

        # Build a manifest with rich metadata so that backups can be validated
        # on restore.
        model_counts = _get_model_counts()
        db_checksum = _compute_file_checksum(db_dump_path)

        import django
        manifest = {
            "project": PROJECT_IDENTIFIER,
            "timestamp": timestamp,
            "created_at": timestamp,
            "django_version": django.get_version(),
            "db_dump": db_dump_path.name,
            "db_checksum": db_checksum,
            "db_record_count": sum(model_counts.values()),
            "model_counts": model_counts,
            "media_archive": media_archive_path.name if media_archive_path else None,
            "migration_list": _get_migration_info(),
        }

        manifest_path = backup_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        if task_id:
            _set_progress(
                task_id,
                4,
                "Бэкап '{}' успешно создан.".format(backup_dir.name),
                total_steps=4,
                percent=100,
                status="completed",
            )

        return backup_dir
    except Exception as exc:
        if task_id:
            _set_progress(
                task_id,
                0,
                "Ошибка: {}".format(str(exc)),
                total_steps=4,
                percent=0,
                status="error",
            )
        raise


def _get_migration_info():
    """Return a list of applied migrations for the production app."""
    from django.db.migrations.recorder import MigrationRecorder

    recorder = MigrationRecorder(connection)
    migrations = []
    for migration in recorder.applied_migrations():
        if migration[0] == "production":
            migrations.append(migration[1])
    return sorted(migrations)


def list_backups():
    """List all available backups sorted by timestamp (newest first)."""
    backup_root = _get_backup_root()
    backups = []
    for item in backup_root.iterdir():
        if item.is_dir() and item.name.startswith("backup_"):
            manifest_path = item / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
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


def _validate_backup_manifest(backup_dir):
    """Validate that a backup directory has a valid manifest for this project.
    Returns (is_valid, manifest_or_error_message).
    """
    manifest = _read_manifest(backup_dir)
    if manifest is None:
        return False, "Манифест manifest.json не найден или повреждён."

    project = manifest.get("project")
    if project != PROJECT_IDENTIFIER:
        return False, (
            "Архив предназначен для другого проекта (project='{}'). "
            "Ожидается '{}'.".format(project, PROJECT_IDENTIFIER)
        )

    return True, manifest


def _do_load_data(
    db_dump_path,
    task_id=None,
    total_records=None,
    base_percent=10,
    span_percent=50,
    step=2,
    total_steps=4,
):
    """Run loaddata and return (success, message, output_str).

    loaddata manages its own transaction — do NOT wrap it in
    transaction.atomic() because that prevents proper rollback on
    IntegrityError in PostgreSQL with large datasets.
    """
    if task_id and total_records:
        try:
            total_records = int(total_records)
        except (TypeError, ValueError):
            total_records = None
    else:
        total_records = None

    if task_id and total_records:
        stdout = _LoadProgressWriter(
            task_id,
            total_records,
            base_percent,
            span_percent,
            step,
            total_steps,
        )
    else:
        stdout = io.StringIO()

    try:
        call_command(
            "loaddata",
            str(db_dump_path),
            verbosity=3,
            stdout=stdout,
        )
        logger.info("[load_data] loaddata stdout: %s", stdout.getvalue()[-2000:])
        return True, "", stdout.getvalue()
    except Exception as e:
        logger.error("[load_data] loaddata failed: %s", str(e))
        logger.info("[load_data] loaddata stdout before error: %s", stdout.getvalue()[-4000:])
        return False, str(e), stdout.getvalue()


def _restore_database(db_dump_path, task_id=None, total_records=None):
    """Clear production data and load the fixture via loaddata.

    This function intentionally does NOT wrap loaddata in an outer
    transaction.atomic() — loaddata manages its own transaction.
    Wrapping it causes PostgreSQL to leave loaded rows in the database
    even when loaddata raises an IntegrityError.
    """
    if task_id:
        _set_progress(task_id, 1, "Очистка текущих данных...", total_steps=4, percent=10)

    # Clear existing data first — loaddata only INSERTs, it does not DELETE.
    _clear_production_data()

    if task_id:
        _set_progress(task_id, 2, "Восстановление базы данных...", total_steps=4, percent=10)

    success, error_or_output, output = _do_load_data(
        db_dump_path,
        task_id=task_id,
        total_records=total_records,
        base_percent=10,
        span_percent=50,
        step=2,
        total_steps=4,
    )

    if not success:
        return False, "Ошибка загрузки данных: {}".format(error_or_output)

    # Verify that data was actually loaded.
    pr_model = apps.get_model("production", "production")
    loaded_count = pr_model.objects.count()
    total_counts = _get_model_counts()
    logger.info(
        "[restore_database] Loaded counts: %s", json.dumps(total_counts)
    )

    if loaded_count == 0:
        return False, "Данные не загружены: таблица Production пуста после loaddata."

    if task_id:
        _set_progress(task_id, 2, "База данных восстановлена.", total_steps=4, percent=60)

    return True, "База данных восстановлена. Записей: {}".format(loaded_count)


def _restore_media(
    media_archive_path,
    task_id=None,
    media_step=3,
    total_steps=4,
    base_percent=60,
    span_percent=30,
):
    """Restore media files from a tar.gz archive."""
    if task_id:
        _set_progress(
            task_id,
            media_step,
            "Восстановление медиафайлов...",
            total_steps=total_steps,
            percent=base_percent,
        )

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
        _set_progress(
            task_id,
            media_step,
            "Медиафайлы восстановлены.",
            total_steps=total_steps,
            percent=base_percent + span_percent,
        )


def restore_backup(backup_name, restore_db=True, restore_media=True, task_id=None):
    """Restore a backup by name. Returns (success, message)."""
    backup_root = _get_backup_root()
    backup_dir = backup_root / backup_name

    if not backup_dir.exists():
        msg = "Бэкап '{}' не найден.".format(backup_name)
        if task_id:
            _set_progress(task_id, 0, msg, total_steps=4, percent=0, status="error")
        return False, msg

    # Validate manifest — check project identifier and archive integrity.
    is_valid, manifest_or_msg = _validate_backup_manifest(backup_dir)
    if not is_valid:
        msg = str(manifest_or_msg)
        if task_id:
            _set_progress(task_id, 0, msg, total_steps=4, percent=0, status="error")
        return False, msg

    manifest = manifest_or_msg
    logger.info("[restore_backup] Manifest: project=%s, db_dump=%s, media_archive=%s",
                manifest.get("project"), manifest.get("db_dump"),
                manifest.get("media_archive"))

    db_dump_path = backup_dir / manifest.get("db_dump", "database.json")

    if restore_db and not db_dump_path.exists():
        msg = "Файл {} не найден в бэкапе.".format(db_dump_path.name)
        if task_id:
            _set_progress(task_id, 0, msg, total_steps=4, percent=0, status="error")
        return False, msg

    # Determine whether media archive exists in this backup.
    has_media = manifest.get("media_archive") is not None
    if restore_media and has_media:
        media_archive_path = backup_dir / manifest["media_archive"]
        if not media_archive_path.exists():
            msg = "Файл {} не найден в бэкапе.".format(manifest["media_archive"])
            if task_id:
                _set_progress(task_id, 0, msg, total_steps=4, percent=0, status="error")
            return False, msg
    else:
        media_archive_path = None
        if restore_media and not has_media:
            logger.info("[restore_backup] Media archive not present in backup, skipping media restore")

    try:
        if task_id:
            _set_progress(
                task_id,
                1,
                "Восстановление из бэкапа '{}': {} записей...".format(
                    backup_name, manifest.get("db_record_count", "?")),
                total_steps=4,
                percent=5,
            )

        if restore_db:
            success, msg = _restore_database(
                db_dump_path,
                task_id=task_id,
                total_records=manifest.get("db_record_count"),
            )
            if not success:
                if task_id:
                    _set_progress(task_id, 0, "Ошибка: {}".format(msg), total_steps=4, percent=0, status="error")
                return False, msg

        if restore_media and media_archive_path:
            _restore_media(media_archive_path, task_id)

        success_message = "Бэкап '{}' успешно восстановлен.".format(backup_name)
        if task_id:
            _set_progress(
                task_id,
                4,
                success_message,
                total_steps=4,
                percent=100,
                status="completed",
            )

        return True, success_message
    except Exception as e:
        if task_id:
            _set_progress(task_id, 0, "Ошибка: {}".format(str(e)), total_steps=4, percent=0, status="error")
        return False, "Ошибка при восстановлении: {}".format(str(e))


def wipe_all_data(confirmation_token):
    """
    Wipe all production data. Requires exact token confirmation 'WIPE_ALL_DATA_CONFIRMED'.
    Returns (success, message).
    """
    if confirmation_token != "WIPE_ALL_DATA_CONFIRMED":
        return False, "Неверный токен подтверждения. Введите 'WIPE_ALL_DATA_CONFIRMED'."

    models = _get_production_models()

    try:
        with transaction.atomic():
            for model in models:
                count = model.objects.count()
                if count:
                    model.objects.all().delete()
                    logger.info("Wiped %d records from %s", count, model._meta.label)

        # Reset sequences AFTER the transaction commits.
        _reset_sequences(models)

        media_root = _get_media_root()
        if media_root.exists():
            _clear_directory_contents(media_root)

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

    # Read manifest for richer info
    manifest = _read_manifest(backup_dir)
    if manifest:
        info["manifest"] = manifest

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


def inspect_uploaded_archive(archive_file):
    """Read the manifest from an uploaded tar.gz archive and return info dict.

    Used to display archive metadata on the restore-upload page **before**
    the actual restore starts, mirroring the info shown on the restore-confirm
    page for server-side backups.

    Args:
        archive_file: A file-like object (Django UploadedFile or BytesIO)
                      containing a tar.gz archive.

    Returns:
        dict with keys: project, timestamp, created_at, django_version,
        db_dump, db_checksum, db_checksum_short, db_record_count,
        model_counts, media_archive, migration_list, archive_name,
        archive_size, files.
        Returns dict with 'error' key on failure.
    """
    archive_name = getattr(archive_file, "name", "archive.tar.gz")

    # Determine size without consuming the file pointer.
    archive_size = 0
    if hasattr(archive_file, "size"):
        archive_size = archive_file.size
    else:
        current_pos = archive_file.tell()
        archive_file.seek(0, 2)
        archive_size = archive_file.tell()
        archive_file.seek(current_pos)

    result = {
        "archive_name": archive_name,
        "archive_size": archive_size,
    }

    try:
        archive_file.seek(0)
        with tarfile.open(fileobj=archive_file, mode="r:gz") as tar:
            members = tar.getmembers()
            file_infos = []
            for m in members:
                if m.isfile():
                    file_infos.append({"name": m.name, "size": m.size})
            result["files"] = file_infos

            # Find and read manifest.json
            manifest = None
            for m in members:
                if m.name.endswith("manifest.json") and m.isfile():
                    f = tar.extractfile(m)
                    if f:
                        manifest = json.loads(f.read().decode("utf-8"))
                    break

            if manifest:
                db_checksum = manifest.get("db_checksum", "")
                result.update({
                    "project": manifest.get("project", "—"),
                    "timestamp": manifest.get("timestamp", "—"),
                    "created_at": manifest.get("created_at", "—"),
                    "django_version": manifest.get("django_version", "—"),
                    "db_dump": manifest.get("db_dump", "—"),
                    "db_checksum": db_checksum,
                    "db_checksum_short": db_checksum[:16] if db_checksum else "—",
                    "db_record_count": manifest.get("db_record_count", "—"),
                    "model_counts": manifest.get("model_counts", {}),
                    "media_archive": manifest.get("media_archive", None),
                    "migration_list": manifest.get("migration_list", []),
                })
            else:
                result.update({
                    "project": "—",
                    "timestamp": "—",
                    "created_at": "—",
                    "django_version": "—",
                    "db_dump": "—",
                    "db_checksum": "—",
                    "db_checksum_short": "—",
                    "db_record_count": "—",
                    "model_counts": {},
                    "media_archive": None,
                    "migration_list": [],
                    "warning": "Манифест manifest.json не найден в архиве",
                })
    except tarfile.TarError as e:
        result["error"] = "Не удалось прочитать архив: {}".format(str(e))
    except (json.JSONDecodeError, OSError) as e:
        result["error"] = "Ошибка при чтении манифеста: {}".format(str(e))
    finally:
        archive_file.seek(0)

    return result


def upload_and_restore(archive_file, task_id=None):
    """Restore from an uploaded tar.gz archive.
    Extracts the archive, looks for database.json and media.tar.gz inside.
    Returns (success, message)."""
    if task_id:
        _set_progress(task_id, 1, "Сохранение загруженного архива...", total_steps=5, percent=5)

    logger.info("[upload_and_restore] task_id=%s archive_name=%s archive_size=%s",
                task_id, getattr(archive_file, "name", "?"), getattr(archive_file, "size", "?"))

    temp_dir = Path(tempfile.mkdtemp(prefix="mes_restore_"))

    archive_path = temp_dir / "uploaded.tar.gz"
    with open(archive_path, "wb") as f:
        if hasattr(archive_file, "chunks"):
            # Django UploadedFile
            for chunk in archive_file.chunks():
                f.write(chunk)
        else:
            # Generic file-like object (e.g., BytesIO)
            while True:
                chunk = archive_file.read(8192)
                if not chunk:
                    break
                f.write(chunk)

    try:
        if task_id:
            _set_progress(task_id, 2, "Извлечение архива...", total_steps=5, percent=15)

        logger.info("[upload_and_restore] archive saved to %s, size=%d", archive_path, archive_path.stat().st_size)

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

        logger.info("[upload_and_restore] db_dump_path=%s media_archive_path=%s", db_dump_path, media_archive_path)

        if not db_dump_path:
            msg = "В архиве не найден database.json."
            logger.error("[upload_and_restore] database.json not found in archive")
            if task_id:
                _set_progress(task_id, 0, "Ошибка: {}".format(msg), total_steps=5, percent=0, status="error")
            return False, msg

        db_size = db_dump_path.stat().st_size
        logger.info("[upload_and_restore] database.json size=%d bytes", db_size)

        with open(db_dump_path, "r", encoding="utf-8") as f:
            db_preview = f.read()[:500]
        logger.info("[upload_and_restore] database.json preview: %s", db_preview)

        # Validate manifest inside the uploaded archive (if present).
        manifest = None
        for item in temp_dir.rglob("manifest.json"):
            try:
                manifest = json.loads(item.read_text(encoding="utf-8"))
                break
            except (json.JSONDecodeError, OSError):
                pass

        if manifest:
            logger.info("[upload_and_restore] manifest: %s", json.dumps(manifest)[:500])
            project = manifest.get("project")
            if project and project != PROJECT_IDENTIFIER:
                msg = (
                    "Архив предназначен для другого проекта (project='{}'). "
                    "Ожидается '{}'.".format(project, PROJECT_IDENTIFIER)
                )
                logger.error("[upload_and_restore] archive is for project '%s', expected '%s'",
                             project, PROJECT_IDENTIFIER)
                if task_id:
                    _set_progress(task_id, 0, "Ошибка: {}".format(msg), total_steps=5, percent=0, status="error")
                return False, msg
            if task_id:
                _set_progress(
                    task_id,
                    2,
                    "Архив проверен: project={}, {} записей".format(
                        project or "неизвестно", manifest.get("db_record_count", "?")),
                    total_steps=5,
                    percent=15,
                )
        else:
            logger.info("[upload_and_restore] no manifest.json found in archive, proceeding without validation")

        total_records = manifest.get("db_record_count") if manifest else None

        # Count records before restore for logging.
        pr_model_class = apps.get_model("production", "production")
        prod_count_before = pr_model_class.objects.count()
        logger.info("[upload_and_restore] records BEFORE loaddata: %d", prod_count_before)

        # Restore database (includes clearing existing data + loaddata).
        if task_id:
            _set_progress(task_id, 3, "Восстановление базы данных...", total_steps=5, percent=20)

        success, msg = _restore_database_internal(db_dump_path, task_id, total_records)
        if not success:
            if task_id:
                _set_progress(task_id, 0, "Ошибка: {}".format(msg), total_steps=5, percent=0, status="error")
            return False, msg

        # Restore media (if present in the archive).
        if media_archive_path:
            _restore_media(
                media_archive_path,
                task_id,
                media_step=4,
                total_steps=5,
                base_percent=70,
                span_percent=20,
            )

        # Count records after restore.
        prod_count_after = pr_model_class.objects.count()
        logger.info("[upload_and_restore] records AFTER loaddata: %d", prod_count_after)

        success_message = "Восстановление из загруженного архива выполнено успешно."
        if task_id:
            _set_progress(
                task_id,
                5,
                success_message,
                total_steps=5,
                percent=100,
                status="completed",
            )

        logger.info("[upload_and_restore] restore completed successfully")
        return True, success_message
    except Exception as e:
        logger.exception("[upload_and_restore] error: %s", str(e))
        if task_id:
            _set_progress(task_id, 0, "Ошибка: {}".format(str(e)), total_steps=5, percent=0, status="error")
        return False, "Ошибка при восстановлении: {}".format(str(e))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _restore_database_internal(db_dump_path, task_id=None, total_records=None):
    """Internal database restore used by upload_and_restore.
    Same logic as _restore_database but without the manifest validation
    (which is done by the caller).

    Uses step 3 for the database restore phase, matching the step schema
    of upload_and_restore (1=save archive, 2=extract, 3=db restore,
    4=media, 5=done).
    """
    if task_id:
        _set_progress(task_id, 3, "Очистка текущих данных...", total_steps=5, percent=20)
    _clear_production_data()

    if task_id:
        _set_progress(task_id, 3, "Восстановление базы данных (loaddata)...", total_steps=5, percent=20)

    success, error_or_output, output = _do_load_data(
        db_dump_path,
        task_id=task_id,
        total_records=total_records,
        base_percent=20,
        span_percent=50,
        step=3,
        total_steps=5,
    )
    if not success:
        return False, "Ошибка загрузки данных: {}".format(error_or_output)

    pr_model = apps.get_model("production", "production")
    loaded_count = pr_model.objects.count()
    if loaded_count == 0:
        return False, "Данные не загружены: таблица Production пуста после loaddata."

    total_counts = _get_model_counts()
    logger.info("[_restore_database_internal] Loaded counts: %s", json.dumps(total_counts))

    if task_id:
        _set_progress(task_id, 3, "База данных восстановлена.", total_steps=5, percent=70)

    return True, "База данных восстановлена. Записей: {}".format(loaded_count)