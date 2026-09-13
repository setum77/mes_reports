"""
URL configuration for mes_report3 project.
"""
from django.contrib import admin
from django.urls import include, path
from django.http import HttpResponse

from reports.views import HomeView


def health(request):
    return HttpResponse("OK")


urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("upload/", include("uploads.urls", namespace="uploads")),
    path("reports/", include("reports.urls", namespace="reports")),
    path("", HomeView.as_view(), name="home"),
]
