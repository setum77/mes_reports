"""
Виды (views) для всех отчетов.
"""
from datetime import datetime
from io import BytesIO
from django.utils import timezone as dj_timezone

import openpyxl
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView, CreateView, UpdateView

from accounts.views import admin_required
from production.models import LotInfo, ManualDefect, ProductionRecord, Report5Comment
from reports.queries import (
    get_date_range,
    report1_orders,
    report2_line_productivity,
    report3_monthly_productivity,
    report4_defects,
    report5_repeated_passes,
    report6_serial_number,
)


# ========================
# Сортировка
# ========================

SORTABLE_FIELDS = {
    "report1": ["LOT", "production_spec", "Total", "Production", "Ok",
                 "Diff", "Defect", "start", "finish", "comment"],
    "report2": ["report_date", "fol_hours", "fol_production", "fol_speed",
                 "bol_hours", "bol_production", "bol_speed"],
    "report3": ["report_month", "fol_hours", "fol_production", "fol_speed",
                 "bol_hours", "bol_production", "bol_speed"],
    "report4": ["pcs_no", "production_spec", "lot_number", "entry_date", "comment"],
    "report5": ["pcs_no", "production_spec", "lot_number", "station", "dates", "comment"],
    "report6": ["pcs_no", "lot_number", "production_spec", "subop_no", "workstation_name",
                "created_date", "result", "test_data"],
}


def apply_sort(data, sort_field, sort_dir, allowed_fields):
    """
    Сортирует список словарей по полю. None всегда сортируются в конец.
    """
    if sort_field not in allowed_fields or not isinstance(data, list):
        return data
    reverse = sort_dir == "desc"

    def get_key(item):
        val = item.get(sort_field) if isinstance(item, dict) else None
        if val is None:
            return (0,) if reverse else (1,)
        return (0, val)

    return sorted(data, key=get_key, reverse=reverse)


def get_sort_params(request, report_key):
    """Извлекает и валидирует параметры сортировки из GET-запроса."""
    allowed = SORTABLE_FIELDS[report_key]
    sort_field = request.GET.get("sort", "")
    sort_dir = request.GET.get("dir", "asc")
    if sort_field not in allowed:
        sort_field = ""
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"
    return sort_field, sort_dir


class HomeView(TemplateView):
    template_name = "home.html"


class ReportListView(TemplateView):
    template_name = "reports/report_list.html"


# ========================
# Отчет 1: Сводный (заказы)
# ========================

class Report1View(TemplateView):
    template_name = "reports/report1.html"

    def get(self, request, *args, **kwargs):
        filter_type = request.GET.get("filter", "30d")
        if filter_type == "period":
            s = request.GET.get("start")
            e = request.GET.get("end")
            if s and e:
                start_date = datetime.strptime(s, "%Y-%m-%d").date()
                end_date = datetime.strptime(e, "%Y-%m-%d").date()
            else:
                start_date, end_date = get_date_range("30d")
        else:
            start_date, end_date = get_date_range(filter_type)
        data = report1_orders(start_date, end_date)

        sort_field, sort_dir = get_sort_params(request, "report1")
        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report1"])
            for i, row in enumerate(data, 1):
                row["N"] = i

        return self.render_to_response(self.get_context_data(
            data=data, filter_type=filter_type, start_date=start_date, end_date=end_date,
            sort_field=sort_field, sort_dir=sort_dir,
        ))


@method_decorator(admin_required, name="dispatch")
class LotInfoUpdateView(UpdateView):
    model = LotInfo
    fields = ["plan_total", "comment"]
    template_name = "reports/lot_edit_modal.html"
    slug_field = "lot_number"
    slug_url_kwarg = "lot_number"

    def get_success_url(self):
        return reverse("reports:report1") + "?edited=1"


# ========================
# Отчет 2: Производительность линии
# ========================

class Report2View(TemplateView):
    template_name = "reports/report2.html"

    def get(self, request, *args, **kwargs):
        filter_type = request.GET.get("filter", "30d")
        if filter_type == "period":
            s = request.GET.get("start")
            e = request.GET.get("end")
            if s and e:
                start_date = datetime.strptime(s, "%Y-%m-%d").date()
                end_date = datetime.strptime(e, "%Y-%m-%d").date()
            else:
                start_date, end_date = get_date_range("30d")
        else:
            start_date, end_date = get_date_range(filter_type)
        data = report2_line_productivity(start_date, end_date)

        sort_field, sort_dir = get_sort_params(request, "report2")
        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report2"])

        return self.render_to_response(self.get_context_data(
            data=data, filter_type=filter_type, start_date=start_date, end_date=end_date,
            sort_field=sort_field, sort_dir=sort_dir,
        ))


# ========================
# Отчет 3: Сводный по месяцам
# ========================

class Report3View(TemplateView):
    template_name = "reports/report3.html"

    def get(self, request, *args, **kwargs):
        year = request.GET.get("year")
        if year:
            start_date = datetime.strptime(f"{year}-01-01", "%Y-%m-%d").date()
            end_date = datetime.strptime(f"{year}-12-31", "%Y-%m-%d").date()
        else:
            start_date, end_date = get_date_range("year")
        data = report3_monthly_productivity(start_date, end_date)

        sort_field, sort_dir = get_sort_params(request, "report3")
        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report3"])

        return self.render_to_response(self.get_context_data(
            data=data, start_date=start_date, end_date=end_date, year=year or start_date.year,
            years=range(2024, 2027),
            sort_field=sort_field, sort_dir=sort_dir,
        ))


# ========================
# Отчет 4: Брак
# ========================

class Report4View(TemplateView):
    template_name = "reports/report4.html"

    def get(self, request, *args, **kwargs):
        filter_type = request.GET.get("filter", "30d")
        lot_filter = request.GET.get("lot", "")

        if filter_type == "period":
            s = request.GET.get("start")
            e = request.GET.get("end")
            if s and e:
                start_date = datetime.strptime(s, "%Y-%m-%d").date()
                end_date = datetime.strptime(e, "%Y-%m-%d").date()
            else:
                start_date, end_date = get_date_range("30d")
        elif filter_type == "lot":
            start_date, end_date = None, None
        else:
            start_date, end_date = get_date_range(filter_type)

        sort_field, sort_dir = get_sort_params(request, "report4")
        limit = 30 if not lot_filter and not start_date and not sort_field else None
        data = report4_defects(start_date, end_date, limit=limit)

        if lot_filter:
            data = [d for d in data if lot_filter.lower() in (d.get("lot_number") or "").lower()]

        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report4"])

        return self.render_to_response(self.get_context_data(
            data=data, filter_type=filter_type, start_date=start_date, end_date=end_date,
            lot_filter=lot_filter, sort_field=sort_field, sort_dir=sort_dir,
        ))


@method_decorator(admin_required, name="dispatch")
class ManualDefectCreateView(CreateView):
    model = ManualDefect
    fields = ["pcs_no", "production_spec", "lot_number", "entry_date", "reason", "comment"]
    template_name = "reports/defect_form.html"

    def get_success_url(self):
        return reverse("reports:report4") + "?added=1"

    def form_valid(self, form):
        form.instance.created_by = getattr(self.request.user, "username", "admin")
        return super().form_valid(form)


# ========================
# Отчет 5: Повторные проходы
# ========================

class Report5View(TemplateView):
    template_name = "reports/report5.html"

    def get(self, request, *args, **kwargs):
        filter_type = request.GET.get("filter", "30d")
        lot_filter = request.GET.get("lot", "")

        if filter_type == "period":
            s = request.GET.get("start")
            e = request.GET.get("end")
            if s and e:
                start_date = datetime.strptime(s, "%Y-%m-%d").date()
                end_date = datetime.strptime(e, "%Y-%m-%d").date()
            else:
                start_date, end_date = get_date_range("30d")
        elif filter_type == "lot":
            start_date, end_date = None, None
        else:
            start_date, end_date = get_date_range(filter_type)

        sort_field, sort_dir = get_sort_params(request, "report5")
        limit = 50 if not lot_filter and not start_date and not sort_field else None
        data = report5_repeated_passes(start_date, end_date, limit=limit)

        if lot_filter:
            data = [d for d in data if lot_filter.lower() in (d.get("lot_number") or "").lower()]

        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report5"])

        return self.render_to_response(self.get_context_data(
            data=data, filter_type=filter_type, start_date=start_date, end_date=end_date,
            lot_filter=lot_filter, sort_field=sort_field, sort_dir=sort_dir,
        ))


@method_decorator(admin_required, name="dispatch")
class Report5CommentFormView(View):
    template_name = "reports/report5_comment_form.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        pcs_no = request.POST.get("pcs_no", "")
        station_no = request.POST.get("station_no")
        comment = request.POST.get("comment", "")
        if pcs_no and station_no:
            try:
                station_no = int(station_no)
                Report5Comment.objects.update_or_create(
                    pcs_no=pcs_no, station_no=station_no,
                    defaults={"comment": comment, "created_by": getattr(request.user, "username", "admin")},
                )
                messages.success(request, "Комментарий сохранен.")
            except ValueError:
                messages.error(request, "Введите корректный номер станции.")
        return redirect("reports:report5")


# ========================
# Отчет 6: Серийный номер
# ========================

class Report6View(TemplateView):
    template_name = "reports/report6.html"

    def get(self, request, *args, **kwargs):
        pcs_no = request.GET.get("pcs_no", "").strip()
        data = report6_serial_number(pcs_no) if pcs_no else []
        exists = ProductionRecord.objects.filter(pcs_no=pcs_no).exists() if pcs_no else None

        if pcs_no and not exists:
            messages.error(request, f'Серийный номер "{pcs_no}" не найден в базе.')

        sort_field, sort_dir = get_sort_params(request, "report6")
        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report6"])

        return self.render_to_response(self.get_context_data(
            data=data, pcs_no=pcs_no, exists=exists,
            sort_field=sort_field, sort_dir=sort_dir,
        ))


# ========================
# Экспорт в Excel
# ========================

class _ExcelExportBase(View):
    """Базовый класс для экспорта в Excel."""

    @staticmethod
    def _excel_value(value):
        """Remove tzinfo from timezone-aware datetimes (Excel unsupported)."""
        if isinstance(value, datetime) and value.tzinfo is not None:
            return dj_timezone.make_naive(value) if value.tzinfo is not None else value
        return value

    def _make_response(self, wb, filename):
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        response = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


@method_decorator(admin_required, name="dispatch")
class Report1ExportView(_ExcelExportBase):
    def get(self, request):
        filter_type = request.GET.get("filter", "30d")
        if filter_type == "period":
            s = request.GET.get("start")
            e = request.GET.get("end")
            if s and e:
                start_date = datetime.strptime(s, "%Y-%m-%d").date()
                end_date = datetime.strptime(e, "%Y-%m-%d").date()
            else:
                start_date, end_date = get_date_range("30d")
        else:
            start_date, end_date = get_date_range(filter_type)
        data = report1_orders(start_date, end_date)

        sort_field, sort_dir = get_sort_params(request, "report1")
        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report1"])
            for i, row in enumerate(data, 1):
                row["N"] = i

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Сводный отчет"
        headers = ["N", "LOT", "Production spec.", "Total", "Production", "Ok", "Diff", "Defect", "start", "finish", "comment"]
        for col, h in enumerate(headers, 1):
            ws.cell(1, col, h)
        for row_num, d in enumerate(data, 2):
            ws.cell(row_num, 1, d["N"])
            ws.cell(row_num, 2, d["LOT"])
            ws.cell(row_num, 3, d["production_spec"])
            ws.cell(row_num, 4, d["Total"])
            ws.cell(row_num, 5, d["Production"])
            ws.cell(row_num, 6, d["Ok"])
            ws.cell(row_num, 7, d["Diff"])
            ws.cell(row_num, 8, d["Defect"])
            ws.cell(row_num, 9, self._excel_value(d["start"]))
            ws.cell(row_num, 10, self._excel_value(d["finish"]))
            ws.cell(row_num, 11, d["comment"])

        return self._make_response(wb, "report1_orders.xlsx")


@method_decorator(admin_required, name="dispatch")
class Report2ExportView(_ExcelExportBase):
    def get(self, request):
        filter_type = request.GET.get("filter", "30d")
        if filter_type == "period":
            s = request.GET.get("start")
            e = request.GET.get("end")
            if s and e:
                start_date = datetime.strptime(s, "%Y-%m-%d").date()
                end_date = datetime.strptime(e, "%Y-%m-%d").date()
            else:
                start_date, end_date = get_date_range("30d")
        else:
            start_date, end_date = get_date_range(filter_type)
        data = report2_line_productivity(start_date, end_date)

        sort_field, sort_dir = get_sort_params(request, "report2")
        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report2"])

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Производительность"
        headers = ["Дата", "FOL hours", "FOL production", "FOL speed", "BOL hours", "BOL production", "BOL speed"]
        for col, h in enumerate(headers, 1):
            ws.cell(1, col, h)
        for row_num, d in enumerate(data, 2):
            ws.cell(row_num, 1, d["report_date"].strftime("%Y-%m-%d") if hasattr(d["report_date"], "strftime") else str(d["report_date"]))
            ws.cell(row_num, 2, d["fol_hours"])
            ws.cell(row_num, 3, d["fol_production"])
            ws.cell(row_num, 4, d["fol_speed"])
            ws.cell(row_num, 5, d["bol_hours"])
            ws.cell(row_num, 6, d["bol_production"])
            ws.cell(row_num, 7, d["bol_speed"])

        return self._make_response(wb, "report2_line.xlsx")


@method_decorator(admin_required, name="dispatch")
class Report3ExportView(_ExcelExportBase):
    def get(self, request):
        year = request.GET.get("year")
        if year:
            start_date = datetime.strptime(f"{year}-01-01", "%Y-%m-%d").date()
            end_date = datetime.strptime(f"{year}-12-31", "%Y-%m-%d").date()
        else:
            start_date, end_date = get_date_range("year")
        data = report3_monthly_productivity(start_date, end_date)

        sort_field, sort_dir = get_sort_params(request, "report3")
        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report3"])

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Сводный месяцы"
        headers = ["Месяц", "FOL hours", "FOL production", "FOL speed", "BOL hours", "BOL production", "BOL speed"]
        for col, h in enumerate(headers, 1):
            ws.cell(1, col, h)
        for row_num, d in enumerate(data, 2):
            ws.cell(row_num, 1, d["report_month"].strftime("%Y-%m") if hasattr(d["report_month"], "strftime") else str(d["report_month"]))
            ws.cell(row_num, 2, d["fol_hours"])
            ws.cell(row_num, 3, d["fol_production"])
            ws.cell(row_num, 4, d["fol_speed"])
            ws.cell(row_num, 5, d["bol_hours"])
            ws.cell(row_num, 6, d["bol_production"])
            ws.cell(row_num, 7, d["bol_speed"])

        return self._make_response(wb, "report3_monthly.xlsx")


@method_decorator(admin_required, name="dispatch")
class Report4ExportView(_ExcelExportBase):
    def get(self, request):
        filter_type = request.GET.get("filter", "30d")
        lot_filter = request.GET.get("lot", "")

        if filter_type == "period":
            s = request.GET.get("start")
            e = request.GET.get("end")
            if s and e:
                start_date = datetime.strptime(s, "%Y-%m-%d").date()
                end_date = datetime.strptime(e, "%Y-%m-%d").date()
            else:
                start_date, end_date = get_date_range("30d")
        elif filter_type == "lot":
            start_date, end_date = None, None
        else:
            start_date, end_date = get_date_range(filter_type)

        sort_field, sort_dir = get_sort_params(request, "report4")
        limit = 30 if not lot_filter and not start_date and not sort_field else None
        data = report4_defects(start_date, end_date, limit=limit)
        if lot_filter:
            data = [d for d in data if lot_filter.lower() in (d.get("lot_number") or "").lower()]

        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report4"])

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Брак"
        headers = ["№", "Серийный номер", "Production spec.", "Лот", "Дата поступления в производство", "Комментарий"]
        for col, h in enumerate(headers, 1):
            ws.cell(1, col, h)
        for row_num, d in enumerate(data, 2):
            ws.cell(row_num, 1, row_num - 1)
            ws.cell(row_num, 2, d["pcs_no"])
            ws.cell(row_num, 3, d["production_spec"])
            ws.cell(row_num, 4, d["lot_number"] or "")
            ws.cell(row_num, 5, self._excel_value(d["entry_date"]))
            ws.cell(row_num, 6, d.get("comment", ""))

        return self._make_response(wb, "report4_defects.xlsx")


@method_decorator(admin_required, name="dispatch")
class Report5ExportView(_ExcelExportBase):
    def get(self, request):
        filter_type = request.GET.get("filter", "30d")
        lot_filter = request.GET.get("lot", "")

        if filter_type == "period":
            s = request.GET.get("start")
            e = request.GET.get("end")
            if s and e:
                start_date = datetime.strptime(s, "%Y-%m-%d").date()
                end_date = datetime.strptime(e, "%Y-%m-%d").date()
            else:
                start_date, end_date = get_date_range("30d")
        elif filter_type == "lot":
            start_date, end_date = None, None
        else:
            start_date, end_date = get_date_range(filter_type)

        sort_field, sort_dir = get_sort_params(request, "report5")
        limit = 50 if not lot_filter and not start_date and not sort_field else None
        data = report5_repeated_passes(start_date, end_date, limit=limit)
        if lot_filter:
            data = [d for d in data if lot_filter.lower() in (d.get("lot_number") or "").lower()]

        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report5"])

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Повторные проходы"
        headers = ["№", "Серийный номер", "Production spec.", "Лот", "Станция", "Дата время", "Комментарий"]
        for col, h in enumerate(headers, 1):
            ws.cell(1, col, h)
        for row_num, d in enumerate(data, 2):
            ws.cell(row_num, 1, row_num - 1)
            ws.cell(row_num, 2, d["pcs_no"])
            ws.cell(row_num, 3, d["production_spec"])
            ws.cell(row_num, 4, d["lot_number"] or "")
            ws.cell(row_num, 5, d["station"])
            ws.cell(row_num, 6, d["dates"])
            ws.cell(row_num, 7, d.get("comment", ""))

        return self._make_response(wb, "report5_repeats.xlsx")


class Report6ExportView(_ExcelExportBase):
    def get(self, request):
        pcs_no = request.GET.get("pcs_no", "").strip()
        data = report6_serial_number(pcs_no) if pcs_no else []
        if pcs_no and not data:
            return redirect("reports:report6")

        sort_field, sort_dir = get_sort_params(request, "report6")
        if sort_field:
            data = apply_sort(data, sort_field, sort_dir, SORTABLE_FIELDS["report6"])

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Отчет по SN"
        headers = [
            "PCSNo", "Lot no.", "Production spec.", "Subop no",
            "WorkstationName", "CREATEDATE", "result", "testData",
        ]
        for col, header in enumerate(headers, 1):
            ws.cell(1, col, header)
        for row_num, d in enumerate(data, 2):
            ws.cell(row_num, 1, d["pcs_no"])
            ws.cell(row_num, 2, d["lot_number"])
            ws.cell(row_num, 3, d["production_spec"])
            ws.cell(row_num, 4, d["subop_no"])
            ws.cell(row_num, 5, d["workstation_name"])
            ws.cell(row_num, 6, self._excel_value(d["created_date"]))
            ws.cell(row_num, 7, d["result"])
            ws.cell(row_num, 8, d["test_data"])

        return self._make_response(wb, f"report6_{pcs_no}.xlsx")
