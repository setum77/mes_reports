"""
URL configuration for mes_report3 project.
"""
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User
from django.urls import include, path
from django.http import HttpResponse

from mes_report3.admin_site import SuperuserOnlyAdminMixin, mes_admin_site
from reports.views import HomeView


class SuperuserOnlyUserAdmin(SuperuserOnlyAdminMixin, UserAdmin):
    pass


class SuperuserOnlyGroupAdmin(SuperuserOnlyAdminMixin, GroupAdmin):
    pass


if not mes_admin_site.is_registered(User):
    mes_admin_site.register(User, SuperuserOnlyUserAdmin)
if not mes_admin_site.is_registered(Group):
    mes_admin_site.register(Group, SuperuserOnlyGroupAdmin)


def health(request):
    return HttpResponse("OK")


urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", mes_admin_site.urls),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("upload/", include("uploads.urls", namespace="uploads")),
    path("reports/", include("reports.urls", namespace="reports")),
    path("", HomeView.as_view(), name="home"),
]
