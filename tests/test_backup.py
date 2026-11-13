import io
import json
import time

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from backup.utils import (
    _DumpProgressWriter,
    _LoadProgressWriter,
    _progress_file_path,
    _set_progress,
    clear_progress,
    consume_progress,
    get_progress,
)


def _make_backup(root, name="backup_20260101_120000", records=10):
    backup_dir = root / name
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "project": "mes_reports",
        "timestamp": "20260101_120000",
        "created_at": "20260101_120000",
        "django_version": "5.0",
        "db_dump": "database.json",
        "db_checksum": "a" * 64,
        "db_record_count": records,
        "model_counts": {"production.Production": records},
        "media_archive": None,
        "migration_list": [],
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (backup_dir / "database.json").write_text("[]", encoding="utf-8")
    return backup_dir


def _login_superuser():
    user = User.objects.create_superuser(
        username="backup-admin",
        password="backup-password",
        email="backup@example.com",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_backup_index_single_h1_three_buttons_and_table(tmp_path):
    _make_backup(tmp_path)
    client = _login_superuser()

    with override_settings(
        BACKUP_ROOT=str(tmp_path),
        MEDIA_ROOT=str(tmp_path / "media"),
        ALLOWED_HOSTS=["*"],
    ):
        response = client.get("/admin/backup/")
        content = response.content.decode()

    assert response.status_code == 200
    assert content.count("<h1>Резервное копирование</h1>") == 1
    assert "Создать бэкап" in content
    assert "Восстановить из архива" in content
    assert "Очистить все данные" in content
    assert "Список бэкапов" not in content
    assert "Восстановить из бэкапа" not in content
    assert "backup_20260101_120000" in content
    assert "Скачать" in content


@pytest.mark.django_db
def test_backup_create_page_single_h1_and_progress(tmp_path):
    client = _login_superuser()

    with override_settings(
        BACKUP_ROOT=str(tmp_path),
        MEDIA_ROOT=str(tmp_path / "media"),
        ALLOWED_HOSTS=["*"],
    ):
        response = client.get("/admin/backup/create/")
        content = response.content.decode()

    assert response.status_code == 200
    assert content.count("<h1>Создание бэкапа</h1>") == 1
    assert "backup-progress-container" in content
    assert "MesBackupProgress" in content


@pytest.mark.django_db
def test_progress_view_running_completed_and_error(tmp_path):
    client = _login_superuser()
    task_id = "progress-test-task"

    with override_settings(ALLOWED_HOSTS=["*"]):
        _set_progress(task_id, 1, "Работает", total_steps=4, percent=42)
        data = client.get("/admin/backup/progress/{}/".format(task_id)).json()
        assert data["status"] == "running"
        assert data["percent"] == 42
        assert data["total_steps"] == 4

        _set_progress(
            task_id,
            0,
            "Ошибка",
            total_steps=4,
            percent=0,
            status="error",
        )
        data = client.get("/admin/backup/progress/{}/".format(task_id)).json()
        assert data["status"] == "error"

        clear_progress(task_id)
        data = client.get("/admin/backup/progress/{}/".format(task_id)).json()
        assert data["status"] == "completed"
        assert data["percent"] == 100
        assert data["message"] == "Готово!"


def test_consume_progress_reads_and_removes_file():
    task_id = "consume-test-task"
    _set_progress(task_id, 1, "Работает", total_steps=4, percent=10)

    data = consume_progress(task_id)

    assert data is not None
    assert data["percent"] == 10
    assert get_progress(task_id) is None


def test_progress_file_path_is_sanitised():
    path = _progress_file_path("../evil")
    assert path.parent.name == "mes_reports_progress"


def test_dump_progress_writer_counts_models():
    task_id = "dump-writer-test"
    target = io.StringIO()
    writer = _DumpProgressWriter(target, task_id, 10)

    writer.write('{"model": "production.production", "pk": 1}')

    data = get_progress(task_id)
    assert data is not None
    assert data["percent"] == 10
    assert data["message"] == "Создание дампа БД... 1/10"
    assert '"model":' in target.getvalue()
    clear_progress(task_id)


def test_load_progress_writer_parses_loaddata_lines():
    task_id = "load-writer-test"
    writer = _LoadProgressWriter(task_id, 10, 10, 50, 2, 4)

    writer.write("\rProcessed 5 object(s).")

    data = get_progress(task_id)
    assert data is not None
    assert data["percent"] == 35
    assert data["message"] == "Восстановление базы данных... 5/10"
    clear_progress(task_id)


@pytest.mark.django_db
def test_index_consumes_task_and_shows_message_once(tmp_path):
    _make_backup(tmp_path)
    client = _login_superuser()
    task_id = "index-message-task"

    with override_settings(
        BACKUP_ROOT=str(tmp_path),
        MEDIA_ROOT=str(tmp_path / "media"),
        ALLOWED_HOSTS=["*"],
    ):
        _set_progress(
            task_id,
            4,
            "Бэкап создан",
            total_steps=4,
            percent=100,
            status="completed",
        )

        response = client.get("/admin/backup/?task={}".format(task_id))
        assert response.status_code == 302
        assert response.url == "/admin/backup/"

        follow = client.get(response.url)
        content = follow.content.decode()
        assert "Бэкап создан" in content
        assert get_progress(task_id) is None

        repeat = client.get("/admin/backup/")
        repeat_content = repeat.content.decode()
        assert repeat_content.count("Бэкап создан") == 0


@pytest.mark.django_db
def test_old_list_and_restore_urls_redirect_to_index(tmp_path):
    client = _login_superuser()

    with override_settings(
        BACKUP_ROOT=str(tmp_path),
        MEDIA_ROOT=str(tmp_path / "media"),
        ALLOWED_HOSTS=["*"],
    ):
        for url in ("/admin/backup/list/", "/admin/backup/restore/"):
            response = client.get(url)
            assert response.status_code == 302
            assert response.url == "/admin/backup/"


@pytest.mark.django_db
def test_create_backup_bg_progress_and_index_message(tmp_path):
    client = _login_superuser()

    with override_settings(
        BACKUP_ROOT=str(tmp_path),
        MEDIA_ROOT=str(tmp_path / "media"),
        ALLOWED_HOSTS=["*"],
    ):
        response = client.post("/admin/backup/create-bg/")
        assert response.status_code == 200
        task_id = response.json()["task_id"]

        data = None
        for _ in range(100):
            data = client.get(
                "/admin/backup/progress/{}/".format(task_id)
            ).json()
            if data.get("status") in ("completed", "error"):
                break
            time.sleep(0.2)

        assert data is not None
        assert data["status"] == "completed", data
        assert data["percent"] == 100

        response = client.get("/admin/backup/?task={}".format(task_id))
        assert response.status_code == 302
        follow = client.get(response.url)
        assert "успешно создан" in follow.content.decode()
        assert get_progress(task_id) is None

        backups = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith("backup_")]
        assert backups


@pytest.mark.django_db
def test_restore_and_upload_pages_render(tmp_path):
    _make_backup(tmp_path)
    client = _login_superuser()

    with override_settings(
        BACKUP_ROOT=str(tmp_path),
        MEDIA_ROOT=str(tmp_path / "media"),
        ALLOWED_HOSTS=["*"],
    ):
        response = client.get(
            "/admin/backup/restore/backup_20260101_120000/"
        )
        assert response.status_code == 200

        response = client.get(
            "/admin/backup/restore-progress/backup_20260101_120000/some-task/"
        )
        assert response.status_code == 200

        response = client.get(
            "/admin/backup/restore-upload-confirm/some-task/"
        )
        assert response.status_code == 200

        response = client.get("/admin/backup/restore-upload/")
        assert response.status_code == 200

        response = client.get("/admin/backup/wipe/")
        assert response.status_code == 200