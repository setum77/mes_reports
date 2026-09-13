from django.contrib import admin
from .models import ProductionRecord, LotInfo, ManualDefect, Report5Comment


@admin.register(ProductionRecord)
class ProductionRecordAdmin(admin.ModelAdmin):
    list_display = ["pcs_no", "lot_number", "subop_no", "created_date", "result", "production_spec"]
    list_filter = ["lot_number", "subop_no", "result", "production_spec"]
    search_fields = ["pcs_no", "lot_number", "production_spec"]
    date_hierarchy = "created_date"


@admin.register(LotInfo)
class LotInfoAdmin(admin.ModelAdmin):
    list_display = ["lot_number", "production_spec", "plan_total", "updated_at"]
    search_fields = ["lot_number", "production_spec"]


@admin.register(ManualDefect)
class ManualDefectAdmin(admin.ModelAdmin):
    list_display = ["pcs_no", "production_spec", "lot_number", "entry_date", "created_by", "created_at"]
    search_fields = ["pcs_no", "lot_number"]
    list_filter = ["created_at", "production_spec"]


@admin.register(Report5Comment)
class Report5CommentAdmin(admin.ModelAdmin):
    list_display = ["pcs_no", "station_no", "lot_number", "created_by", "created_at"]
    search_fields = ["pcs_no", "lot_number"]
