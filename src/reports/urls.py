from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportListView.as_view(), name="list"),
    path("1/", views.Report1View.as_view(), name="report1"),
    path("2/", views.Report2View.as_view(), name="report2"),
    path("3/", views.Report3View.as_view(), name="report3"),
    path("4/", views.Report4View.as_view(), name="report4"),
    path("5/", views.Report5View.as_view(), name="report5"),
    path("6/", views.Report6View.as_view(), name="report6"),
    path("7/", views.Report7View.as_view(), name="report7"),
    path("1/export/", views.Report1ExportView.as_view(), name="report1_export"),
    path("2/export/", views.Report2ExportView.as_view(), name="report2_export"),
    path("3/export/", views.Report3ExportView.as_view(), name="report3_export"),
    path("4/export/", views.Report4ExportView.as_view(), name="report4_export"),
    path("5/export/", views.Report5ExportView.as_view(), name="report5_export"),
    path("6/export/", views.Report6ExportView.as_view(), name="report6_export"),
    path("7/export/", views.Report7ExportView.as_view(), name="report7_export"),
    path("lot/<str:lot_number>/edit/", views.LotInfoUpdateView.as_view(), name="lot_edit"),
    path("defect/add/", views.ManualDefectCreateView.as_view(), name="defect_add"),
    path("comment/<str:pcs_no>/edit/", views.SNCommentEditView.as_view(), name="sn_comment_edit"),
    path("report5/comment/", views.Report5CommentFormView.as_view(), name="report5_comment"),
]
