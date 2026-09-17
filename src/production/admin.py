from django.contrib import admin

from mes_report3.admin_site import mes_admin_site

from .models import ProductionRecord, LotInfo, ManualDefect, SNComment, Report5Comment


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


class ProductionRecordAdmin(StaffBusinessModelAdmin):
    list_display = [
        "pcs_no",
        "lot_number",
        "subop_no",
        "created_date",
        "result",
        "production_spec",
    ]
    search_fields = ["pcs_no", "lot_number", "production_spec", "subop_no"]
    list_filter = ["result", "subop_no", "created_date"]
    date_hierarchy = "created_date"
    list_per_page = 100
    readonly_fields = [field.name for field in ProductionRecord._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class LotInfoAdmin(StaffBusinessModelAdmin):
    fieldsets = (
        (None, {
            "fields": ("lot_number", "production_spec"),
        }),
        ("План и комментарий", {
            "fields": ("plan_total", "comment"),
        }),
        ("Служебная информация", {
            "fields": ("updated_at",),
            "classes": ("collapse",),
        }),
    )
    list_display = ["lot_number", "production_spec", "plan_total", "updated_at"]
    search_fields = ["lot_number", "production_spec"]
    list_filter = ["production_spec", "updated_at"]
    list_per_page = 50
    readonly_fields = ["updated_at"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ["updated_at"]
        return ["lot_number", "updated_at"]


class ManualDefectAdmin(StaffBusinessModelAdmin):
    fieldsets = (
        (None, {
            "fields": ("pcs_no", "production_spec", "lot_number", "entry_date"),
        }),
        ("Информация о браке", {
            "fields": ("reason", "comment"),
        }),
        ("Аудит", {
            "fields": ("created_by", "created_at"),
            "classes": ("collapse",),
        }),
    )
    list_display = ["pcs_no", "production_spec", "lot_number", "entry_date", "created_by", "created_at"]
    search_fields = ["pcs_no", "production_spec", "lot_number", "reason", "comment"]
    list_filter = ["production_spec", "lot_number", "entry_date", "created_at", "created_by"]
    list_per_page = 50
    readonly_fields = ["created_by", "created_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user.get_username()
        super().save_model(request, obj, form, change)


class SNCommentAdmin(StaffBusinessModelAdmin):
    fieldsets = (
        (None, {
            "fields": ("pcs_no", "comment"),
        }),
        ("Аудит", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    list_display = ["pcs_no", "created_by", "updated_at"]
    search_fields = ["pcs_no", "comment"]
    list_filter = ["created_at", "updated_at", "created_by"]
    list_per_page = 50
    readonly_fields = ["created_by", "created_at", "updated_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user.get_username()
        super().save_model(request, obj, form, change)


class Report5CommentAdmin(StaffBusinessModelAdmin):
    fieldsets = (
        (None, {
            "fields": ("pcs_no", "station_no", "lot_number"),
        }),
        ("Комментарий", {
            "fields": ("comment",),
        }),
        ("Аудит", {
            "fields": ("created_by", "created_at"),
            "classes": ("collapse",),
        }),
    )
    list_display = ["pcs_no", "station_no", "lot_number", "created_by", "created_at"]
    search_fields = ["pcs_no", "station_no", "lot_number", "comment"]
    list_filter = ["station_no", "lot_number", "created_at", "created_by"]
    list_per_page = 50
    readonly_fields = ["created_by", "created_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user.get_username()
        super().save_model(request, obj, form, change)


mes_admin_site.register(ProductionRecord, ProductionRecordAdmin)
mes_admin_site.register(LotInfo, LotInfoAdmin)
mes_admin_site.register(ManualDefect, ManualDefectAdmin)
mes_admin_site.register(SNComment, SNCommentAdmin)
mes_admin_site.register(Report5Comment, Report5CommentAdmin)
