from django.contrib import admin

from mes_report3.admin_site import mes_admin_site

from .models import (
    ControlUnit,
    FaultAttachment,
    FaultJournal,
    Lot,
    Production,
    Station,
    TestDataTranslation,
    UnitPhoto,
)


class StaffBusinessModelAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff


class ProductionAdmin(StaffBusinessModelAdmin):
    list_display = ["unit", "station", "created_date", "result", "test_data_ru"]
    search_fields = [
        "unit__sn",
        "station__number",
        "station__name_en",
        "station__name_ru",
        "result",
    ]
    list_filter = ["station", "result", "created_date"]
    date_hierarchy = "created_date"
    list_per_page = 100
    readonly_fields = [field.name for field in Production._meta.fields]
    autocomplete_fields = ["unit", "station"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class LotAdmin(StaffBusinessModelAdmin):
    fieldsets = (
        (None, {"fields": ("number", "production_spec", "total", "comment")}),
        ("Служебная информация", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    list_display = ["number", "production_spec", "total", "updated_at"]
    search_fields = ["number", "production_spec"]
    list_filter = ["production_spec", "updated_at"]
    list_per_page = 50
    readonly_fields = ["created_at", "updated_at"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ["created_at", "updated_at"]
        return ["number", "created_at", "updated_at"]


class StationAdmin(StaffBusinessModelAdmin):
    list_display = [
        "number",
        "position_no",
        "name_zh",
        "name_en",
        "name_ru",
        "sort_order",
        "is_active",
    ]
    list_editable = ["name_zh", "name_en", "name_ru", "sort_order", "is_active"]
    search_fields = ["number", "position_no", "name_zh", "name_en", "name_ru"]
    list_filter = ["is_active"]
    list_per_page = 50


class ControlUnitAdmin(StaffBusinessModelAdmin):
    list_display = ["sn", "lot", "production_spec", "defect", "updated_at"]
    search_fields = ["sn", "lot__number", "lot__production_spec", "comment"]
    list_filter = ["defect", "lot"]
    list_per_page = 100
    readonly_fields = ["production_spec", "created_at", "updated_at"]
    autocomplete_fields = ["lot"]

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by:
            obj.created_by = request.user.get_username()
        super().save_model(request, obj, form, change)


class TestDataTranslationAdmin(StaffBusinessModelAdmin):
    list_display = ["source", "target", "is_active", "comment"]
    search_fields = ["source", "target", "comment"]
    list_filter = ["is_active"]
    list_per_page = 100


class FaultJournalAdmin(StaffBusinessModelAdmin):
    list_display = [
        "date",
        "detected_at",
        "station",
        "equipment",
        "status",
        "resolved_at",
        "duration",
        "unit",
    ]
    search_fields = [
        "equipment",
        "description",
        "cause",
        "actions_taken",
        "note",
        "unit__sn",
        "lot__number",
    ]
    list_filter = ["status", "station", "date", "created_by"]
    date_hierarchy = "date"
    list_per_page = 100
    readonly_fields = ["duration", "created_by", "created_at", "updated_at"]
    autocomplete_fields = ["unit", "lot", "station"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user.get_username()
        super().save_model(request, obj, form, change)


class FaultAttachmentAdmin(StaffBusinessModelAdmin):
    list_display = ["journal", "kind", "caption", "uploaded_by", "uploaded_at"]
    search_fields = ["caption", "uploaded_by", "journal__equipment"]
    list_filter = ["kind", "uploaded_at", "uploaded_by"]
    list_per_page = 50
    readonly_fields = ["uploaded_by", "uploaded_at"]
    autocomplete_fields = ["journal"]


class UnitPhotoAdmin(StaffBusinessModelAdmin):
    list_display = ["unit", "caption", "uploaded_by", "uploaded_at"]
    search_fields = ["unit__sn", "caption"]
    list_filter = ["unit", "uploaded_at", "uploaded_by"]
    list_per_page = 50
    readonly_fields = ["uploaded_by", "uploaded_at"]
    autocomplete_fields = ["unit"]


mes_admin_site.register(Production, ProductionAdmin)
mes_admin_site.register(Lot, LotAdmin)
mes_admin_site.register(Station, StationAdmin)
mes_admin_site.register(ControlUnit, ControlUnitAdmin)
mes_admin_site.register(TestDataTranslation, TestDataTranslationAdmin)
mes_admin_site.register(FaultJournal, FaultJournalAdmin)
mes_admin_site.register(FaultAttachment, FaultAttachmentAdmin)
mes_admin_site.register(UnitPhoto, UnitPhotoAdmin)