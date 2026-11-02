import uuid

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import FileResponse, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path

from backup.forms import RestoreForm, UploadRestoreForm, WipeConfirmForm
from backup.utils import (
    PROJECT_IDENTIFIER,
    _read_manifest,
    _set_progress,
    create_full_backup,
    download_backup,
    get_progress,
    get_backup_info,
    inspect_uploaded_archive,
    list_backups,
    restore_backup,
    upload_and_restore,
    wipe_all_data,
)


class BackupViews:
    """Class-based backup views that can be registered on the admin site."""

    def get_urls(self):
        custom_urls = [
            path("backup/", self.admin_site.admin_view(self.index_view), name="backup_index"),
            path("backup/create/", self.admin_site.admin_view(self.create_backup), name="backup_create"),
            path("backup/create-bg/", self.admin_site.admin_view(self.create_backup_bg), name="backup_create_bg"),
            path("backup/progress/<str:task_id>/", self.admin_site.admin_view(self.progress_view), name="backup_progress"),
            path("backup/list/", self.admin_site.admin_view(self.list_backups_view), name="backup_list"),
            path("backup/download/<str:backup_name>/", self.admin_site.admin_view(self.download_view), name="backup_download"),
            path("backup/restore/", self.admin_site.admin_view(self.restore_view), name="backup_restore"),
            path("backup/restore-bg/<str:backup_name>/", self.admin_site.admin_view(self.restore_backup_bg), name="backup_restore_bg"),
            path("backup/restore-upload/", self.admin_site.admin_view(self.restore_upload_view), name="backup_restore_upload"),
            path("backup/restore-upload-inspect/", self.admin_site.admin_view(self.restore_upload_inspect), name="backup_restore_upload_inspect"),
            path("backup/restore-upload-bg/<str:task_id>/", self.admin_site.admin_view(self.restore_upload_bg), name="backup_restore_upload_bg"),
            path("backup/restore-upload-confirm/<str:task_id>/", self.admin_site.admin_view(self.restore_upload_confirm), name="backup_restore_upload_confirm"),
            path("backup/restore/<str:backup_name>/", self.admin_site.admin_view(self.restore_confirm), name="backup_restore_confirm"),
            path("backup/restore-progress/<str:backup_name>/<str:task_id>/", self.admin_site.admin_view(self.restore_progress), name="backup_restore_progress"),
            path("backup/wipe/", self.admin_site.admin_view(self.wipe_view), name="backup_wipe"),
        ]
        return custom_urls

    def _is_superuser(self, request):
        return request.user.is_active and request.user.is_superuser

    def _check_superuser(self, request):
        if not self._is_superuser(request):
            return redirect("admin:login")
        return None

    def index_view(self, request):
        if not self._is_superuser(request):
            return redirect("admin:login")

        backups = list_backups()
        context = self.admin_site.each_context(request)
        context.update({
            "title": "Резервное копирование",
            "backup_count": len(backups),
        })
        return TemplateResponse(request, "admin/backup/index.html", context)

    def create_backup(self, request):
        if not self._is_superuser(request):
            return redirect("admin:login")

        if request.method == "POST":
            backup_dir = create_full_backup()
            messages.success(request, "Бэкап успешно создан: {}".format(backup_dir.name))
            return redirect("mes_admin:backup_index")

        context = self.admin_site.each_context(request)
        context.update({"title": "Создание бэкапа"})
        return TemplateResponse(request, "admin/backup/create.html", context)

    def create_backup_bg(self, request):
        if not self._is_superuser(request):
            return redirect("admin:login")

        task_id = str(uuid.uuid4())

        # Set initial progress so the first poll doesn't see None (which
        # progress_view interprets as "completed").
        _set_progress(task_id, 0, "Запуск создания бэкапа...")

        import threading

        thread = threading.Thread(
            target=create_full_backup,
            kwargs={"task_id": task_id},
        )
        thread.daemon = True
        thread.start()

        return JsonResponse({"task_id": task_id})

    def progress_view(self, request, task_id):
        if not self._is_superuser(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        progress = get_progress(task_id)
        if progress is None:
            return JsonResponse({"status": "completed", "step": 4, "message": "Готово!"})
        return JsonResponse(progress)

    def list_backups_view(self, request):
        if not self._is_superuser(request):
            return redirect("admin:login")

        backups = list_backups()
        paginator = Paginator(backups, 20)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        backup_infos = []
        for b in page_obj:
            info = get_backup_info(b["name"])
            if info:
                backup_infos.append(info)

        context = self.admin_site.each_context(request)
        context.update({
            "title": "Список бэкапов",
            "backups": backup_infos,
            "page_obj": page_obj,
        })
        return TemplateResponse(request, "admin/backup/list.html", context)

    def download_view(self, request, backup_name):
        if not self._is_superuser(request):
            return redirect("admin:login")

        archive = download_backup(backup_name)
        if archive is None:
            messages.error(request, "Бэкап '{}' не найден.".format(backup_name))
            return redirect("mes_admin:backup_list")

        response = FileResponse(archive, as_attachment=True, filename="{}.tar.gz".format(backup_name))
        return response

    def restore_view(self, request):
        if not self._is_superuser(request):
            return redirect("admin:login")

        if request.method == "POST":
            form = RestoreForm(request.POST)
            if form.is_valid():
                backup_name = form.cleaned_data["backup_name"]
                return redirect("mes_admin:backup_restore_confirm", backup_name=backup_name)
        else:
            form = RestoreForm()

        context = self.admin_site.each_context(request)
        context.update({
            "title": "Восстановление из бэкапа",
            "form": form,
        })
        return TemplateResponse(request, "admin/backup/restore.html", context)

    def restore_backup_bg(self, request, backup_name):
        if not self._is_superuser(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        task_id = str(uuid.uuid4())

        # Set initial progress so the first poll doesn't see None (which
        # progress_view interprets as "completed").
        _set_progress(task_id, 0, "Запуск восстановления...")

        import threading

        thread = threading.Thread(
            target=restore_backup,
            kwargs={"backup_name": backup_name, "restore_db": True, "restore_media": True, "task_id": task_id},
        )
        thread.daemon = True
        thread.start()

        return JsonResponse({"task_id": task_id})

    def restore_upload_view(self, request):
        if not self._is_superuser(request):
            return redirect("admin:login")

        if request.method == "POST":
            form = UploadRestoreForm(request.POST, request.FILES)
            if form.is_valid():
                task_id = str(uuid.uuid4())

                # Read file content into memory before starting the thread.
                archive_file = form.cleaned_data["archive"]

                # Inspect the archive to display its info on the confirm page.
                archive_info = inspect_uploaded_archive(archive_file)
                archive_file.seek(0)  # Reset for reading

                file_content = archive_file.read()
                # Store archive info in session for the confirm page (non-JS fallback).
                if "error" not in archive_info:
                    request.session["restore_upload_archive_info"] = archive_info

                # Set initial progress so the first poll doesn't see None (which
                # progress_view interprets as "completed").
                _set_progress(task_id, 0, "Запуск восстановления...")

                import io
                import threading

                thread = threading.Thread(
                    target=upload_and_restore,
                    kwargs={"archive_file": io.BytesIO(file_content), "task_id": task_id},
                )
                thread.daemon = True
                thread.start()

                return redirect("mes_admin:backup_restore_upload_confirm", task_id=task_id)
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, "{}: {}".format(field, error))
                return redirect("mes_admin:backup_restore_upload")
        else:
            form = UploadRestoreForm()

        context = self.admin_site.each_context(request)
        context.update({
            "title": "Восстановление из загруженного архива",
            "form": form,
        })
        return TemplateResponse(request, "admin/backup/restore_upload.html", context)

    def restore_upload_confirm(self, request, task_id):
        if not self._is_superuser(request):
            return redirect("admin:login")

        archive_info = request.session.pop("restore_upload_archive_info", None)

        context = self.admin_site.each_context(request)
        context.update({
            "title": "Восстановление из загруженного архива",
            "task_id": task_id,
            "archive": archive_info,
        })
        return TemplateResponse(request, "admin/backup/restore_upload_confirm.html", context)

    def restore_upload_inspect(self, request):
        """Inspect an uploaded archive and return its manifest info as JSON.

        Called via AJAX when the user selects a file on the restore-upload
        page, so archive metadata can be displayed before the restore starts.
        """
        if not self._is_superuser(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        if request.method != "POST" or "archive" not in request.FILES:
            return JsonResponse({"error": "Архив не передан в запросе"}, status=400)

        archive = request.FILES["archive"]
        info = inspect_uploaded_archive(archive)

        if "error" in info:
            return JsonResponse(info, status=400)

        return JsonResponse(info)

    def restore_upload_bg(self, request, task_id):
        import io
        import logging
        logger = logging.getLogger(__name__)

        if not self._is_superuser(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)

        archive = request.FILES.get("archive")
        if not archive:
            logger.warning("[restore_upload_bg] No archive file in request, task_id=%s", task_id)
            return JsonResponse({"error": "No file uploaded"}, status=400)

        # Read file content into memory before starting the thread.
        # Django's UploadedFile temp files are cleaned up when the request
        # ends, which happens right after we return the response — before
        # the background thread has a chance to read them.
        file_content = archive.read()
        logger.info("[restore_upload_bg] Read archive into memory: name=%s size=%d, task_id=%s",
                    getattr(archive, "name", "?"), len(file_content), task_id)

        # Set initial progress so the first poll doesn't see None (which
        # progress_view interprets as "completed").
        _set_progress(task_id, 0, "Запуск восстановления...")

        import threading

        thread = threading.Thread(
            target=upload_and_restore,
            kwargs={"archive_file": io.BytesIO(file_content), "task_id": task_id},
        )
        thread.daemon = True
        thread.start()

        return JsonResponse({"status": "started"})

    def restore_confirm(self, request, backup_name):
        if not self._is_superuser(request):
            return redirect("admin:login")

        if request.method == "POST":
            task_id = str(uuid.uuid4())

            # Set initial progress so the first poll doesn't see None (which
            # progress_view interprets as "completed").
            _set_progress(task_id, 0, "Запуск восстановления...")

            import threading

            thread = threading.Thread(
                target=restore_backup,
                kwargs={"backup_name": backup_name, "restore_db": True, "restore_media": True, "task_id": task_id},
            )
            thread.daemon = True
            thread.start()

            return redirect("mes_admin:backup_restore_progress", backup_name=backup_name, task_id=task_id)

        backup_info = get_backup_info(backup_name)
        if not backup_info:
            messages.error(request, "Бэкап '{}' не найден.".format(backup_name))
            return redirect("mes_admin:backup_list")

        context = self.admin_site.each_context(request)
        context.update({
            "title": "Подтверждение восстановления: {}".format(backup_name),
            "backup": backup_info,
        })
        return TemplateResponse(request, "admin/backup/restore_confirm.html", context)

    def restore_progress(self, request, backup_name, task_id):
        if not self._is_superuser(request):
            return redirect("admin:login")

        backup_info = get_backup_info(backup_name)
        manifest = backup_info.get("manifest", {}) if backup_info else {}

        context = self.admin_site.each_context(request)
        context.update({
            "title": "Восстановление: {}".format(backup_name),
            "backup_name": backup_name,
            "task_id": task_id,
            "manifest": manifest,
        })
        return TemplateResponse(request, "admin/backup/restore_progress.html", context)

    def wipe_view(self, request):
        if not self._is_superuser(request):
            return redirect("admin:login")

        if request.method == "POST":
            form = WipeConfirmForm(request.POST)
            if form.is_valid():
                confirmation = form.cleaned_data["confirmation"]
                success, message = wipe_all_data(confirmation)
                if success:
                    messages.success(request, message)
                else:
                    messages.error(request, message)
                return redirect("mes_admin:backup_index")
        else:
            form = WipeConfirmForm()

        context = self.admin_site.each_context(request)
        context.update({
            "title": "Полное удаление данных",
            "form": form,
        })
        return TemplateResponse(request, "admin/backup/wipe.html", context)


def setup_backup_urls(admin_site):
    """Patch the admin site to include backup URLs under /admin/backup/."""
    backup_views = BackupViews()
    backup_views.admin_site = admin_site

    original_get_urls = admin_site.get_urls

    def patched_get_urls():
        urls = original_get_urls()
        custom_urls = backup_views.get_urls()
        return custom_urls + urls

    admin_site.get_urls = patched_get_urls
    admin_site.backup_views = backup_views
