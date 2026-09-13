from django.urls import path
from uploads import views as upload_views

app_name = "uploads"

urlpatterns = [
    path("", upload_views.UploadHomeView.as_view(), name="upload_home"),
    path("file/", upload_views.UploadFileView.as_view(), name="upload_file"),
    path("success/<int:inserted>/<int:duplicates>/<int:total>/", upload_views.UploadSuccessView.as_view(), name="upload_success"),
]
