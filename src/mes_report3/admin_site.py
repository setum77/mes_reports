from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.db.models import Count, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone


class SuperuserOnlyAdminMixin:
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser


class MESAdminSite(AdminSite):
    site_header = "MES Reports Admin"
    site_title = "Администрирование MES Reports"
    index_title = "Управление MES Reports"
    index_template = "admin/index.html"

    def index(self, request, extra_context=None):
        response = super().index(request, extra_context)
        context_data = getattr(response, "context_data", None)
        if context_data is not None:
            context_data.update(
                {
                    "dashboard_metrics": self.get_dashboard_metrics(),
                    "report_links": self.get_report_links(),
                    "upload_url": reverse("uploads:upload_home"),
                }
            )
        return response

    def get_dashboard_metrics(self):
        from production.models import LotInfo, ManualDefect, ProductionRecord, Report5Comment

        now = timezone.now()
        recent_cutoff = now - timedelta(days=7)
        production = ProductionRecord.objects.aggregate(
            total=Count("id"),
            recent=Count("id", filter=Q(created_date__gte=recent_cutoff)),
            latest=Max("created_date"),
        )
        lots = LotInfo.objects.aggregate(
            total=Count("id"),
            plan_total=Coalesce(Sum("plan_total"), Value(0)),
        )
        manual_defects = ManualDefect.objects.aggregate(
            total=Count("id"),
            recent=Count("id", filter=Q(created_at__gte=recent_cutoff)),
            latest=Max("created_at"),
        )
        comments = Report5Comment.objects.aggregate(
            total=Count("id"),
            recent=Count("id", filter=Q(created_at__gte=recent_cutoff)),
            latest=Max("created_at"),
        )
        return {
            "lots": {
                "total": lots["total"],
                "plan_total": lots["plan_total"],
            },
            "production_records": {
                "total": production["total"],
                "recent": production["recent"],
                "latest": production["latest"],
            },
            "manual_defects": {
                "total": manual_defects["total"],
                "recent": manual_defects["recent"],
                "latest": manual_defects["latest"],
            },
            "report5_comments": {
                "total": comments["total"],
                "recent": comments["recent"],
                "latest": comments["latest"],
            },
            "recent_days": 7,
        }

    def get_report_links(self):
        report_names = (
            ("reports:report1", "Отчёт 1: Сводный"),
            ("reports:report2", "Отчёт 2: Производительность"),
            ("reports:report3", "Отчёт 3: Месяцы"),
            ("reports:report4", "Отчёт 4: Брак"),
            ("reports:report5", "Отчёт 5: Повторные проходы"),
            ("reports:report6", "Отчёт 6: Серийный номер"),
            ("reports:report7", "Отчёт 7: Выпуск"),
        )
        return [
            {"url": reverse(url_name), "label": label}
            for url_name, label in report_names
        ]


mes_admin_site = MESAdminSite(name="mes_admin")
