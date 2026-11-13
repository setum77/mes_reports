"""
Тесты бизнес-логики отчетов.
"""
import warnings
warnings.filterwarnings("ignore")

import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mes_report3.settings.dev")
sys.path.insert(0, "src")
django.setup()

import pytest
from datetime import date, datetime, timedelta
from io import BytesIO
from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpResponseRedirect
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from mes_report3.admin_site import mes_admin_site
from production.admin import LotAdmin, ProductionAdmin
from production.models import ControlUnit, Lot, Production, UnitPhoto
from tests._legacy import (
    LotInfo,
    ManualDefect,
    ProductionRecord,
    SNComment,
    SNPhoto,
)
from reports.queries import (
    report1_orders,
    report2_line_productivity,
    report4_defects,
    report5_repeated_passes,
    report5_summary,
    report6_serial_number,
    report6_summary,
    report7_station130_output,
    report8_stations,
    translate_workstation_name,
)
from reports.views import (
    _report1_summary,
    _report2_period,
    _report2_summary,
    _report5_period,
    _report7_period,
    _report7_summary,
    _report8_period,
    _report8_summary,
    apply_sort,
    get_sort_params,
    SORTABLE_FIELDS,
    REPORT8_COLUMNS,
    REPORT8_CHART_KEYS,
    REPORT8_CHART_STATIONS,
)


@pytest.mark.django_db
def test_report1_orders():
    """Проверка расчетов Report 1: Production, Ok, Diff."""
    dt1 = timezone.make_aware(datetime(2026, 8, 13, 10, 0, 0))
    dt2 = timezone.make_aware(datetime(2026, 8, 13, 11, 0, 0))
    dt3 = timezone.make_aware(datetime(2026, 8, 19, 12, 0, 0))

    ProductionRecord.objects.create(
        lot_number="LOT-001", subop_no=10, created_date=dt1,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-001", subop_no=10, created_date=dt2,
        pcs_no="PCS2", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-001", subop_no=130, created_date=dt3,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )

    data = report1_orders()
    assert len(data) == 1
    row = data[0]
    assert row["LOT"] == "LOT-001"
    assert row["Production"] == 2
    assert row["Ok"] == 1
    assert row["Diff"] == 1
    assert len(row["defect_sns"]) == 1
    assert row["defect_sns"][0] == "PCS2"


@pytest.mark.django_db
def test_report1_no_data():
    """Отчет 1 с пустой БД."""
    data = report1_orders()
    assert len(data) == 0


@pytest.mark.django_db
def test_report1_orders_lot_info_loaded_in_one_query(django_assert_num_queries):
    """Отчёт №1 не делает отдельный запрос LotInfo на каждый лот (N+1)."""
    dt = timezone.make_aware(datetime(2026, 4, 1, 9, 0))
    ProductionRecord.objects.bulk_create([
        ProductionRecord(
            lot_number=f"LOT-Q{index}", subop_no=10, pcs_no=f"SN-Q{index}",
            created_date=dt, result="OK", production_spec="SPEC",
        )
        for index in range(5)
    ])

    with django_assert_num_queries(2):
        data = report1_orders(date(2026, 4, 1), date(2026, 4, 30))

    assert len(data) == 5


@pytest.mark.django_db
def test_report2_line_productivity():
    """Проверка расчетов Report 2."""
    dt_start = timezone.make_aware(datetime(2026, 8, 13, 10, 0, 0))
    dt_end = timezone.make_aware(datetime(2026, 8, 13, 12, 0, 0))

    ProductionRecord.objects.create(
        lot_number="LOT-001", subop_no=10, created_date=dt_start,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-001", subop_no=50, created_date=dt_end,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )

    from reports.queries import report2_line_productivity
    from datetime import date
    data = report2_line_productivity(date(2026, 8, 13), date(2026, 8, 13))
    assert len(data) == 1
    assert data[0]["fol_hours"] == 2.0
    assert data[0]["fol_production"] == 1
    assert data[0]["has_data"] is True


@pytest.mark.django_db
def test_report2_line_productivity_lot():
    """Фильтр по лоту: учитываются только записи указанного лота."""
    dt_start = timezone.make_aware(datetime(2026, 8, 13, 10, 0, 0))
    dt_end = timezone.make_aware(datetime(2026, 8, 13, 12, 0, 0))

    # Лот LOT-A: PCS1 прошёл станции 010 и 050
    ProductionRecord.objects.create(
        lot_number="LOT-A", subop_no=10, created_date=dt_start,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-A", subop_no=50, created_date=dt_end,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    # Лот LOT-B: PCS2 (должен быть исключён фильтром по лоту)
    ProductionRecord.objects.create(
        lot_number="LOT-B", subop_no=10, created_date=dt_start,
        pcs_no="PCS2", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-B", subop_no=50, created_date=dt_end,
        pcs_no="PCS2", result="OK", production_spec="SPEC"
    )

    data = report2_line_productivity(None, None, lot_number="LOT-A")
    assert len(data) == 1
    assert data[0]["fol_production"] == 1  # только PCS1 из LOT-A
    assert data[0]["fol_hours"] == 2.0
    assert data[0]["has_data"] is True


@pytest.mark.django_db
def test_report5_repeated_passes():
    """Проверка Report 5: БУ с повторными проходами."""
    dt1 = timezone.make_aware(datetime(2026, 8, 13, 10, 0, 0))
    dt2 = timezone.make_aware(datetime(2026, 8, 13, 10, 5, 0))

    ProductionRecord.objects.create(
        lot_number="LOT-001", subop_no=20, created_date=dt1,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-001", subop_no=20, created_date=dt2,
        pcs_no="PCS1", result="NG", production_spec="SPEC"
    )

    from reports.queries import report5_repeated_passes
    from datetime import date
    data = report5_repeated_passes(date(2026, 8, 13), date(2026, 8, 13), limit=50)
    assert len(data) == 1
    assert data[0]["pcs_no"] == "PCS1"
    assert data[0]["station"] == 20


@pytest.mark.django_db
def test_report5_repeated_passes_has_no_default_limit():
    """Отчёт №5 не должен молча ограничивать выборку 50 строками (п.1 ТЗ)."""
    base = timezone.make_aware(datetime(2026, 7, 1, 8, 0, 0))
    records = [
        ProductionRecord(
            lot_number="LOT-MANY",
            subop_no=20,
            pcs_no=f"PCS-{index:03d}",
            created_date=base + timedelta(minutes=index * 2 + attempt),
            result="OK",
            production_spec="SPEC",
        )
        for index in range(60)
        for attempt in range(2)
    ]
    ProductionRecord.objects.bulk_create(records)

    data = report5_repeated_passes(date(2026, 7, 1), date(2026, 7, 1))

    assert len(data) == 60


@pytest.mark.django_db
def test_report5_repeated_passes_fields_and_comment():
    """Отчёт №5: количество проходов, название станции и комментарий из SNComment."""
    dt1 = timezone.make_aware(datetime(2026, 6, 1, 10, 0))
    dt2 = dt1 + timedelta(minutes=10)
    for moment, result in ((dt1, "OK"), (dt2, "NG")):
        ProductionRecord.objects.create(
            lot_number="LOT-R5", subop_no=20, pcs_no="SN-R5",
            created_date=moment, result=result, production_spec="SPEC",
            position_no="20", workstation_name="FCT1",
        )
    SNComment.objects.create(pcs_no="SN-R5", comment="основной комментарий")

    data = report5_repeated_passes(date(2026, 6, 1), date(2026, 6, 30))

    row = next(r for r in data if r["pcs_no"] == "SN-R5")
    assert row["passes_count"] == 2
    assert row["station_name"] == "FCT1"
    assert row["comment"] == "основной комментарий"
    assert row["defect"] is False
    expected_first = timezone.localtime(dt1).strftime("%Y-%m-%d %H:%M:%S")
    expected_second = timezone.localtime(dt2).strftime("%Y-%m-%d %H:%M:%S")
    assert expected_first in row["dates"]
    assert expected_second in row["dates"]


@pytest.mark.django_db
def test_report5_defect_flag_from_production_and_manual():
    """Defect в отчёте №5: флаг ProductionRecord или запись ManualDefect."""
    dt = timezone.make_aware(datetime(2026, 6, 2, 9, 0))
    for pcs_no, flagged in (("SN-R5-FLAG", True), ("SN-R5-MANUAL", False)):
        for offset in (0, 5):
            ProductionRecord.objects.create(
                lot_number="LOT-R5D", subop_no=70, pcs_no=pcs_no,
                created_date=dt + timedelta(minutes=offset), result="OK",
                production_spec="SPEC", defect=flagged,
            )
    ManualDefect.objects.create(pcs_no="SN-R5-MANUAL", lot_number="LOT-R5D")

    data = {
        row["pcs_no"]: row
        for row in report5_repeated_passes(date(2026, 6, 1), date(2026, 6, 30))
    }

    assert data["SN-R5-FLAG"]["defect"] is True
    assert data["SN-R5-MANUAL"]["defect"] is True


def test_report5_summary_counts_by_station():
    """Сводка отчёта №5: количество SN, среднее прохождений, SN с >4 проходами."""
    data = [
        {"station": 20, "station_name": "FCT1", "pcs_no": "A", "passes_count": 2},
        {"station": 20, "station_name": "FCT1", "pcs_no": "B", "passes_count": 5},
        {"station": 20, "station_name": "FCT1", "pcs_no": "C", "passes_count": 4},
        {"station": 70, "station_name": "Oven", "pcs_no": "A", "passes_count": 3},
    ]

    summary = report5_summary(data)

    assert [row["station"] for row in summary] == [20, 70]
    station20 = summary[0]
    assert station20["sn_count"] == 3
    assert station20["avg_passes"] == round(11 / 3, 2)
    assert station20["sns_over_4"] == ["B"]


def test_report5_period_selection():
    """Фильтры отчёта №5: год (по умолчанию), месяц, период, лот и ошибки."""
    today = date.today()

    default = _report5_period(RequestFactory().get("/reports/5/"))
    assert default["filter_type"] == "year"
    assert default["start_date"] == date(today.year, 1, 1)
    assert default["end_date"] == date(today.year, 12, 31)

    month = _report5_period(
        RequestFactory().get("/reports/5/", {"filter": "month", "year": "2026", "month": "3"})
    )
    assert month["start_date"] == date(2026, 3, 1)
    assert month["end_date"] == date(2026, 3, 31)

    period = _report5_period(
        RequestFactory().get(
            "/reports/5/", {"filter": "period", "start": "2026-01-01", "end": "2026-01-31"}
        )
    )
    assert period["start_date"] == date(2026, 1, 1)
    assert period["end_date"] == date(2026, 1, 31)
    assert period["error"] == ""

    invalid = _report5_period(
        RequestFactory().get(
            "/reports/5/", {"filter": "period", "start": "bad", "end": "2026-01-31"}
        )
    )
    assert invalid["error"]
    assert invalid["start_date"] == date(today.year, 1, 1)

    lot = _report5_period(RequestFactory().get("/reports/5/", {"filter": "lot", "lot": "LOT-1"}))
    assert lot["filter_type"] == "lot"
    assert lot["lot_value"] == "LOT-1"
    assert lot["start_date"] is None
    assert lot["end_date"] is None


@pytest.mark.django_db
def test_report5_view_context_has_summary_and_description():
    """Report5View: в контексте есть сводка и описание отчёта, по умолчанию — год."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        response = Client().get("/reports/5/", {"filter": "year", "year": "2026"})
        response.render()

    assert response.status_code == 200
    assert response.context_data["filter_type"] == "year"
    assert isinstance(response.context_data["summary"], list)
    assert response.context_data["report5_description_lines"]


@pytest.mark.django_db
def test_report5_export_has_summary_sheet():
    """Экспорт отчёта №5 содержит основной лист и лист «Сводка» с новыми колонками."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        response = Client().get("/reports/5/export/", {"filter": "year", "year": "2026"})

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), read_only=True)
    assert {"Повторные проходы", "Сводка"} <= set(workbook.sheetnames)
    header = [cell.value for cell in workbook["Повторные проходы"][1]]
    assert header == [
        "№", "Серийный номер", "Лот", "Станция", "Название станции",
        "Дата время", "Defect", "Комментарий",
    ]


@pytest.mark.django_db
def test_report5_lot_filter_applied_in_sql():
    """Фильтр по лоту применяется в SQL (ILIKE), а не только после выборки."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    dt = timezone.make_aware(datetime(2026, 6, 15, 9, 0))
    for lot, pcs_no in (("LOT-SQL-A", "SN-SQL-A"), ("LOT-SQL-B", "SN-SQL-B")):
        for offset in (0, 5):
            ProductionRecord.objects.create(
                lot_number=lot, subop_no=20, pcs_no=pcs_no,
                created_date=dt + timedelta(minutes=offset), result="OK",
                production_spec="SPEC",
            )

    with CaptureQueriesContext(connection) as ctx:
        data = report5_repeated_passes(
            date(2026, 6, 1), date(2026, 6, 30), lot_number="LOT-SQL-A"
        )

    sql_text = " ".join(query["sql"] for query in ctx.captured_queries)
    assert "ILIKE" in sql_text
    assert [row["lot_number"] for row in data] == ["LOT-SQL-A"]


@pytest.mark.django_db
def test_report5_view_passes_lot_to_query(monkeypatch):
    """Report5View передаёт лот в report5_repeated_passes при фильтре «По лоту»."""
    from reports import views

    captured = {}

    def fake_query(start_date=None, end_date=None, limit=None, lot_number=None):
        captured["lot_number"] = lot_number
        return []

    monkeypatch.setattr(views, "report5_repeated_passes", fake_query)

    with override_settings(ALLOWED_HOSTS=["*"]):
        response = Client().get("/reports/5/", {"filter": "lot", "lot": "LOT-XY"})

    assert response.status_code == 200
    assert captured["lot_number"] == "LOT-XY"


@pytest.mark.django_db
def test_report4_last_ok_station_and_sn_comment():
    start = date(2026, 9, 1)
    end = date(2026, 9, 30)
    pcs_no = "SN-REPORT4"

    ProductionRecord.objects.create(
        lot_number="LOT-REPORT4",
        subop_no=10,
        pcs_no=pcs_no,
        created_date=timezone.make_aware(datetime(2026, 9, 1, 8, 0)),
        result="OK",
        production_spec="SPEC-REPORT4",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-REPORT4",
        subop_no=20,
        pcs_no=pcs_no,
        created_date=timezone.make_aware(datetime(2026, 9, 1, 9, 0)),
        result="OK",
        production_spec="SPEC-REPORT4"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-REPORT4",
        subop_no=100,
        pcs_no=pcs_no,
        created_date=timezone.make_aware(datetime(2026, 9, 1, 11, 0)),
        result="OK",
        production_spec="SPEC-REPORT4"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-REPORT4",
        subop_no=120,
        pcs_no=pcs_no,
        created_date=timezone.make_aware(datetime(2026, 9, 1, 10, 0)),
        result="OK",
        production_spec="SPEC-REPORT4"
    )
    SNComment.objects.create(pcs_no=pcs_no, comment="Отчёт 4", created_by="admin")

    data = report4_defects(start, end, defect_filter='in_progress')
    row = next(item for item in data if item["pcs_no"] == pcs_no)

    assert row["last_station"] == "PIN Test"
    assert row["last_station_date"] == timezone.make_aware(datetime(2026, 9, 1, 10, 0))
    assert row["comment"] == "Отчёт 4"


@pytest.mark.django_db
def test_report4_manual_comment_is_used_without_sn_comment():
    pcs_no = "SN-MANUAL-REPORT4"
    ManualDefect.objects.create(
        pcs_no=pcs_no,
        production_spec="SPEC-MANUAL",
        lot_number="LOT-MANUAL",
        created_by="admin",
    )
    SNComment.objects.create(pcs_no=pcs_no, comment="Ручной комментарий", created_by="admin")

    data = report4_defects()
    row = next(item for item in data if item["pcs_no"] == pcs_no)

    assert row["last_station"] == ""
    assert row["comment"] == "Ручной комментарий"


@pytest.mark.django_db
def test_report4_defect_filter_defect_true():
    """defect_filter='defect': ProductionRecord с defect=True + ManualDefect."""
    pcs_no = "SN-DEFECT-FLAG"
    dt = timezone.make_aware(datetime(2026, 9, 1, 10, 0))
    ProductionRecord.objects.create(
        lot_number="LOT", subop_no=10, pcs_no=pcs_no,
        created_date=dt, result="OK", defect=True,
        production_spec="SPEC"
    )
    data = report4_defects(defect_filter="defect")
    row = next((r for r in data if r["pcs_no"] == pcs_no), None)
    assert row is not None
    assert row["pcs_no"] == pcs_no


@pytest.mark.django_db
def test_report4_defect_filter_in_progress_excludes_defect_true():
    """defect_filter='in_progress': только in_progress, не defect=True записи."""
    pcs_no = "SN-INPROGRESS-OK"
    dt_start = timezone.make_aware(datetime(2026, 9, 1, 8, 0))
    dt_mid = timezone.make_aware(datetime(2026, 9, 1, 10, 0))
    ProductionRecord.objects.create(
        lot_number="LOT", subop_no=10, pcs_no=pcs_no,
        created_date=dt_start, result="OK",
        production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT", subop_no=50, pcs_no=pcs_no,
        created_date=dt_mid, result="OK",
        production_spec="SPEC"
    )
    data = report4_defects(defect_filter="in_progress")
    row = next((r for r in data if r["pcs_no"] == pcs_no), None)
    assert row is not None


@pytest.mark.django_db
def test_report4_defect_filter_both_include_manual_defect():
    """defect и in_progress оба включают ManualDefect."""
    pcs_no = "SN-MANUAL-BOTH"
    ManualDefect.objects.create(
        pcs_no=pcs_no, production_spec="SPEC", lot_number="LOT",
        created_by="admin"
    )
    for defect_filter in ("defect", "in_progress"):
        data = report4_defects(defect_filter=defect_filter)
        row = next((r for r in data if r["pcs_no"] == pcs_no), None)
        assert row is not None


@pytest.mark.django_db
def test_report4_defect_filter_in_progress_excludes_completed():
    """defect_filter='in_progress' исключает завершенные SN (прошли 130 OK с defect=True)."""
    pcs_no = "SN-FLAGGED-COMPLETED"
    dt_start = timezone.make_aware(datetime(2026, 9, 1, 8, 0))
    dt_end = timezone.make_aware(datetime(2026, 9, 1, 12, 0))
    ProductionRecord.objects.create(
        lot_number="LOT", subop_no=10, pcs_no=pcs_no,
        created_date=dt_start, result="OK", defect=True,
        production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT", subop_no=130, pcs_no=pcs_no,
        created_date=dt_end, result="OK", defect=True,
        production_spec="SPEC"
    )
    in_progress_data = report4_defects(defect_filter="in_progress")
    assert not any(r["pcs_no"] == pcs_no for r in in_progress_data)
    defect_data = report4_defects(defect_filter="defect")
    assert any(r["pcs_no"] == pcs_no for r in defect_data)


@pytest.mark.django_db
def test_report4_plasma_station_name_is_spelled_correctly():
    """Название станции 30 — Plasma Cleaning (ранее было Pasma)."""
    pcs_no = "SN-PLASMA"
    dt = timezone.make_aware(datetime(2026, 9, 2, 10, 0))
    ProductionRecord.objects.create(
        lot_number="LOT-PLASMA", subop_no=10, pcs_no=pcs_no,
        created_date=dt, result="OK", production_spec="SPEC",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-PLASMA", subop_no=30, pcs_no=pcs_no,
        created_date=dt + timedelta(minutes=5), result="OK", production_spec="SPEC",
    )

    data = report4_defects(date(2026, 9, 1), date(2026, 9, 30), defect_filter="in_progress")

    row = next(r for r in data if r["pcs_no"] == pcs_no)
    assert row["last_station"] == "Plasma Cleaning"


@pytest.mark.django_db
def test_report4_manual_defects_not_truncated_to_50():
    """Ручные браки не обрезаются до 50 строк, если limit не задан."""
    entry = timezone.make_aware(datetime(2026, 9, 10, 12, 0))
    ManualDefect.objects.bulk_create([
        ManualDefect(pcs_no=f"MAN-{index:03d}", lot_number="LOT-MAN", entry_date=entry)
        for index in range(55)
    ])

    data = report4_defects(date(2026, 9, 1), date(2026, 9, 30), defect_filter="defect")

    manual_rows = [row for row in data if row["is_manual"]]
    assert len(manual_rows) == 55


@pytest.mark.django_db
def test_report4_lot_filter_applied_in_sql():
    """Фильтр по лоту в отчёте №4 применяется в SQL (ILIKE)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    dt = timezone.make_aware(datetime(2026, 9, 5, 9, 0))
    for lot, pcs_no in (("LOT-DEF-A", "SN-DEF-A"), ("LOT-DEF-B", "SN-DEF-B")):
        ProductionRecord.objects.create(
            lot_number=lot, subop_no=10, pcs_no=pcs_no,
            created_date=dt, result="OK", production_spec="SPEC", defect=True,
        )

    with CaptureQueriesContext(connection) as ctx:
        data = report4_defects(
            date(2026, 9, 1), date(2026, 9, 30), lot_number="LOT-DEF-A"
        )

    sql_text = " ".join(query["sql"] for query in ctx.captured_queries)
    assert "ILIKE" in sql_text
    assert [row["pcs_no"] for row in data] == ["SN-DEF-A"]


@pytest.mark.django_db
def test_report4_view_passes_lot_to_query(monkeypatch):
    """Report4View передаёт лот в report4_defects, а не фильтрует после выборки."""
    from reports import views

    captured = {}

    def fake_defects(*args, **kwargs):
        captured["lot_number"] = kwargs.get("lot_number")
        return []

    monkeypatch.setattr(views, "report4_defects", fake_defects)

    with override_settings(ALLOWED_HOSTS=["*"]):
        response = Client().get("/reports/4/", {"filter": "year", "lot": "LOT-ZZ"})

    assert response.status_code == 200
    assert captured["lot_number"] == "LOT-ZZ"


@pytest.mark.django_db
def test_report4_view_cache_control_no_store():
    """Report4View: Cache-Control: no-store."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="testuser_report4_cache", defaults={"password": "pass", "is_staff": True}
        )
        dt = timezone.make_aware(datetime(2026, 9, 1, 10, 0))
        ProductionRecord.objects.create(
            lot_number="LOT", subop_no=10, pcs_no="SN-CACHE4",
            created_date=dt, result="OK", defect=True,
            production_spec="SPEC"
        )
        client = Client()
        client.force_login(user)
        response = client.get("/reports/4/")
        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_report4_view_description_lines():
    """Report4View: report4_description_lines в контексте."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="testuser_report4_desc", defaults={"password": "pass", "is_staff": False}
        )
        client = Client()
        client.force_login(user)
        response = client.get("/reports/4/")
        response.render()
        context = response.context_data
        assert context["report4_description_lines"] is not None
        assert len(context["report4_description_lines"]) > 0


@pytest.mark.django_db
def test_report4_view_default_filter_is_90d():
    """Report4View: по умолчанию filter_type='90d'."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="testuser_report4_default", defaults={"password": "pass", "is_staff": True}
        )
        client = Client()
        client.force_login(user)
        response = client.get("/reports/4/")
        response.render()
        assert response.context_data["filter_type"] == "90d"
    pcs_no = "SN-REPORT6-COMMENT"
    ProductionRecord.objects.create(
        lot_number="LOT-REPORT6",
        subop_no=20,
        pcs_no=pcs_no,
        created_date=timezone.make_aware(datetime(2026, 9, 1, 9, 0)),
        result="OK",
        production_spec="SPEC-REPORT6"
    )
    SNComment.objects.create(pcs_no=pcs_no, comment="SN-комментарий", created_by="admin")

    data = report6_serial_number(pcs_no)

    assert data[0]["comment"] == "SN-комментарий"


@pytest.mark.django_db
def test_report4_view_invalid_period_does_not_crash():
    """Report4View: некорректные даты периода не приводят к HTTP 500."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        client = Client()
        for params in (
            {"filter": "period", "start": "abc", "end": "2026-01-01"},
            {"filter": "period", "start": "2026-02-01", "end": "2026-01-01"},
        ):
            response = client.get("/reports/4/", params)
            assert response.status_code == 200


@pytest.mark.django_db
def test_report_exports_invalid_period_do_not_crash():
    """Экспорты отчётов №1 и №4 не падают на некорректных датах периода."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        client = Client()
        for url in ("/reports/1/export/", "/reports/4/export/"):
            for params in (
                {"filter": "period", "start": "not-a-date", "end": "2026-01-01"},
                {"filter": "period", "start": "2026-02-01", "end": "2026-01-01"},
            ):
                response = client.get(url, params)
                assert response.status_code == 200


@pytest.mark.django_db
def test_report4_photos_shown_as_links_with_valid_data_attribute():
    """Report4View: фото отображаются в виде списка ссылок с корректным data-photos (HTML-escaped JSON, not escapejs)."""
    import html as _html
    import json as _json

    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="testuser_report4_photos", defaults={"password": "pass", "is_staff": True}
        )
        client = Client()
        client.force_login(user)

        pcs_no = "SN-REPORT4-PHOTOS"
        dt = timezone.make_aware(datetime(2026, 9, 1, 10, 0))
        ProductionRecord.objects.create(
            lot_number="LOT-PHOTO", subop_no=10, pcs_no=pcs_no,
            created_date=dt, result="OK", defect=True,
            production_spec="SPEC-PHOTO"
        )
        SNPhoto.objects.create(
            pcs_no=pcs_no, image="sn_photos/2026/09/01/photo1.jpg",
            caption="Первая фото", uploaded_by="admin",
        )
        SNPhoto.objects.create(
            pcs_no=pcs_no, image="sn_photos/2026/09/01/photo2.jpg",
            caption="Вторая фото", uploaded_by="admin",
        )
        response = client.get("/reports/4/")
        response.render()
        content = response.content.decode()

        # Фото отображаются как ссылки с именами, а не как "Просмотр (2)"
        assert "Просмотр (2)" not in content
        assert "Первая фото" in content
        assert "Вторая фото" in content

        # data-photos содержит валидный HTML-escaped JSON (а не escapejs с \")
        # Если бы использовался escapejs, в атрибуте были бы \" вместо HTML-сущностей.
        assert 'data-photos="' in content
        # Находим первое вхождение data-photos и извлекаем значение
        idx = content.index('data-photos="')
        start = idx + len('data-photos="')
        end = content.index('"', start)
        raw_photos_attr = content[start:end]
        # Декодируем HTML-сущности (&#34; → ") и проверяем, что это валидный JSON
        decoded = _html.unescape(raw_photos_attr)
        photos_data = _json.loads(decoded)
        assert len(photos_data) == 2
        assert photos_data[0]["caption"] == "Первая фото"
        assert photos_data[1]["caption"] == "Вторая фото"


@pytest.mark.django_db
def test_report6_summary_completed():
    """Summary: SN прошёл станцию 130 с OK → completed=True."""
    pcs_no = "SN-REPORT6-SUMMARY-DONE"
    dt_start = timezone.make_aware(datetime(2026, 9, 15, 10, 0, 0))
    dt_end = timezone.make_aware(datetime(2026, 9, 15, 12, 0, 0))

    ProductionRecord.objects.create(
        lot_number="LOT-DONE", production_spec="SPEC-DONE", subop_no=10,
        pcs_no=pcs_no, created_date=dt_start, result="OK",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-DONE", production_spec="SPEC-DONE", subop_no=130,
        pcs_no=pcs_no, created_date=dt_end, result="OK",
    )
    SNComment.objects.create(pcs_no=pcs_no, comment="Test comment", created_by="admin")

    summary = report6_summary(pcs_no)
    assert summary is not None
    assert summary["pcs_no"] == pcs_no
    assert summary["lot_number"] == "LOT-DONE"
    assert summary["production_spec"] == "SPEC-DONE"
    assert summary["assembly_start"] == dt_start
    assert summary["assembly_end"] == dt_end
    assert summary["completed"] is True
    assert summary["last_station"] == ""
    assert summary["last_station_date"] is None
    assert summary["comment"] == "Test comment"


@pytest.mark.django_db
def test_report6_summary_not_completed():
    """Summary: SN не прошёл станцию 130 с OK → completed=False, last station shown."""
    pcs_no = "SN-REPORT6-SUMMARY-NO"
    dt_start = timezone.make_aware(datetime(2026, 9, 15, 10, 0, 0))
    dt_mid = timezone.make_aware(datetime(2026, 9, 15, 11, 0, 0))

    ProductionRecord.objects.create(
        lot_number="LOT-NO", production_spec="SPEC-NO", subop_no=10,
        pcs_no=pcs_no, created_date=dt_start, result="OK",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-NO", production_spec="SPEC-NO", subop_no=50,
        pcs_no=pcs_no, created_date=dt_mid, result="OK",
    )

    summary = report6_summary(pcs_no)
    assert summary is not None
    assert summary["completed"] is False
    assert summary["assembly_end"] is None
    assert summary["assembly_start"] == dt_start
    assert summary["last_station"]  # имя последней станции
    assert summary["last_station_date"] == dt_mid
    assert summary["last_station_status"] == "OK"


@pytest.mark.django_db
def test_report6_summary_not_completed_last_ng():
    """Summary: last station has NG status → completed=False, last_station_status='NG'."""
    pcs_no = "SN-REPORT6-SUMMARY-NG"
    dt_start = timezone.make_aware(datetime(2026, 9, 15, 10, 0, 0))
    dt_mid = timezone.make_aware(datetime(2026, 9, 15, 11, 0, 0))

    ProductionRecord.objects.create(
        lot_number="LOT-NG", production_spec="SPEC-NG", subop_no=10,
        pcs_no=pcs_no, created_date=dt_start, result="OK",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-NG", production_spec="SPEC-NG", subop_no=50,
        pcs_no=pcs_no, created_date=dt_mid, result="NG",
    )

    summary = report6_summary(pcs_no)
    assert summary is not None
    assert summary["completed"] is False
    assert summary["last_station"]  # имя последней станции
    assert summary["last_station_date"] == dt_mid
    assert summary["last_station_status"] == "NG"


@pytest.mark.django_db
def test_report6_summary_double_passes():
    """Summary: stations passed more than 2 times → double_passes field."""
    pcs_no = "SN-REPORT6-DOUBLE"
    dt_base = timezone.make_aware(datetime(2026, 9, 15, 10, 0, 0))

    ProductionRecord.objects.create(
        lot_number="LOT-DP", production_spec="SPEC-DP", subop_no=10,
        pcs_no=pcs_no, created_date=dt_base, result="OK",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-DP", production_spec="SPEC-DP", subop_no=20,
        pcs_no=pcs_no, created_date=timezone.make_aware(datetime(2026, 9, 15, 11, 0, 0)), result="OK",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-DP", production_spec="SPEC-DP", subop_no=20,
        pcs_no=pcs_no, created_date=timezone.make_aware(datetime(2026, 9, 15, 12, 0, 0)), result="NG",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-DP", production_spec="SPEC-DP", subop_no=20,
        pcs_no=pcs_no, created_date=timezone.make_aware(datetime(2026, 9, 15, 13, 0, 0)), result="OK",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-DP", production_spec="SPEC-DP", subop_no=50,
        pcs_no=pcs_no, created_date=timezone.make_aware(datetime(2026, 9, 15, 14, 0, 0)), result="OK",
    )
    ProductionRecord.objects.create(
        lot_number="LOT-DP", production_spec="SPEC-DP", subop_no=130,
        pcs_no=pcs_no, created_date=timezone.make_aware(datetime(2026, 9, 15, 15, 0, 0)), result="OK",
    )

    summary = report6_summary(pcs_no)
    assert summary is not None
    assert summary["completed"] is True
    assert "20 - 3" in summary["double_passes"]
    assert "50 - 1" not in summary["double_passes"]


@pytest.mark.django_db
def test_report6_summary_missing():
    """Summary: SN не найден → None."""
    assert report6_summary("MISSING-SN") is None
    assert report6_summary("") is None


@pytest.mark.django_db
def test_report6_summary_includes_defect_and_photos():
    """report6_summary: возвращает defect и photos поля."""
    pcs_no = "SN-REPORT6-DEFECT-PHOTOS"
    dt = timezone.make_aware(datetime(2026, 9, 15, 10, 0))
    ProductionRecord.objects.create(
        lot_number="LOT", production_spec="SPEC", subop_no=10,
        pcs_no=pcs_no, created_date=dt, result="OK", defect=True,
    )
    summary = report6_summary(pcs_no)
    assert summary is not None
    assert "defect" in summary
    assert summary["defect"] is True
    assert "photos" in summary
    assert isinstance(summary["photos"], list)


@pytest.mark.django_db
def test_report6_summary_visible_to_anonymous():
    """Report6View: Defect и Фотографии показываются без авторизации, без правки."""
    pcs_no = "SN-REPORT6-ANON"
    dt = timezone.make_aware(datetime(2026, 9, 15, 10, 0))
    ProductionRecord.objects.create(
        lot_number="LOT", production_spec="SPEC", subop_no=10,
        pcs_no=pcs_no, created_date=dt, result="OK",
    )
    SNPhoto.objects.create(
        pcs_no=pcs_no, image="sn_photos/2026/09/01/photo1.jpg",
        caption="Фото 1", uploaded_by="admin",
    )
    response = Client().get(f"/reports/6/?pcs_no={pcs_no}")
    content = response.content.decode()
    assert response.status_code == 200
    assert "Defect (брак)" in content
    assert "Фотографии" in content
    assert "photo-thumb" in content
    assert "/media/sn_photos/2026/09/01/photo1.jpg" in content
    # Без авторизации нет контролов изменения
    assert "Установить брак" not in content
    assert "snPhotoUploadModal" not in content
    assert "/rename/" not in content
    assert "/delete/" not in content


@pytest.mark.django_db
def test_report6_summary_edit_controls_visible_to_staff():
    """Report6View: staff видит контролы правки Defect и фото."""
    user = User.objects.create_user(
        username="report6-anon-staff", password="password", is_staff=True
    )
    pcs_no = "SN-REPORT6-STAFF"
    dt = timezone.make_aware(datetime(2026, 9, 15, 10, 0))
    ProductionRecord.objects.create(
        lot_number="LOT", production_spec="SPEC", subop_no=10,
        pcs_no=pcs_no, created_date=dt, result="OK",
    )
    SNPhoto.objects.create(
        pcs_no=pcs_no, image="sn_photos/2026/09/01/photo1.jpg",
        caption="Фото 1", uploaded_by="admin",
    )
    client = Client()
    client.force_login(user)
    response = client.get(f"/reports/6/?pcs_no={pcs_no}")
    content = response.content.decode()
    assert response.status_code == 200
    assert "Установить брак" in content
    assert "snPhotoUploadModal" in content
    assert "/rename/" in content
    assert "/delete/" in content


@pytest.mark.django_db
def test_report6_set_defect_view_admin_only():
    """SNSetDefectView: только staff, устанавливает defect флаг."""
    user = User.objects.create_user(
        username="report6-editor", password="password", is_staff=True
    )
    pcs_no = "SN-SET-DEFECT"
    dt = timezone.make_aware(datetime(2026, 9, 15, 10, 0))
    ProductionRecord.objects.create(
        lot_number="LOT", production_spec="SPEC", subop_no=10,
        pcs_no=pcs_no, created_date=dt, result="OK",
    )
    client = Client()
    client.force_login(user)
    url = f"/reports/comment/{pcs_no}/defect/"
    response = client.post(url, {"value": "true"})
    assert response.status_code == 302
    assert ProductionRecord.objects.filter(pcs_no=pcs_no, defect=True).exists()


@pytest.mark.django_db
def test_report6_set_defect_view_non_staff_redirect():
    """SNSetDefectView: non-staff перенаправляется на report6."""
    user = User.objects.create_user(
        username="report6-nostaff", password="password", is_staff=False
    )
    pcs_no = "SN-NOSTAFF-DEFECT"
    client = Client()
    client.force_login(user)
    url = f"/reports/comment/{pcs_no}/defect/"
    response = client.post(url, {"value": "true"})
    assert response.status_code == 302
    assert "/reports/6/" in response.url


@pytest.mark.django_db
def test_report6_photo_upload_view_admin_only():
    """SNPhotoUploadView: admin может загрузить фото."""
    user = User.objects.create_user(
        username="report6-photo-upload", password="password", is_staff=True
    )
    pcs_no = "SN-PHOTO-UPLOAD"
    dt = timezone.make_aware(datetime(2026, 9, 15, 10, 0))
    ProductionRecord.objects.create(
        lot_number="LOT", production_spec="SPEC", subop_no=10,
        pcs_no=pcs_no, created_date=dt, result="OK",
    )
    client = Client()
    client.force_login(user)
    url = f"/reports/sn/{pcs_no}/photo/upload/"
    img_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    img_file = (BytesIO(img_content), "test_photo.png")
    response = client.post(url, {"image": img_file, "caption": "Test photo"}, follow=True)
    assert response.status_code == 200
    assert SNPhoto.objects.filter(pcs_no=pcs_no).count() == 1
    assert SNPhoto.objects.get(pcs_no=pcs_no).caption == "Test photo"


@pytest.mark.django_db
def test_report6_photo_rename_view():
    """SNPhotoRenameView: admin может переименовать подпись."""
    user = User.objects.create_user(
        username="report6-photo-rename", password="password", is_staff=True
    )
    pcs_no = "SN-PHOTO-RENAME"
    photo = SNPhoto.objects.create(
        pcs_no=pcs_no, image="test_image.png",
        caption="Old caption", uploaded_by="admin",
    )
    client = Client()
    client.force_login(user)
    url = f"/reports/photo/{photo.pk}/rename/"
    response = client.post(url, {"caption": "New caption"})
    assert response.status_code == 302
    photo.refresh_from_db()
    assert photo.caption == "New caption"


@pytest.mark.django_db
def test_report6_photo_rename_view_not_found():
    """SNPhotoRenameView: not found → redirect на report6 без ошибки."""
    user = User.objects.create_user(
        username="report6-photo-rename-nf", password="password", is_staff=True
    )
    client = Client()
    client.force_login(user)
    url = "/reports/photo/99999/rename/"
    response = client.post(url, {"caption": "New caption"})
    assert response.status_code == 302
    assert "/reports/6/" in response.url


@pytest.mark.django_db
def test_report6_photo_delete_view():
    """SNPhotoDeleteView: admin может удалить фото."""
    user = User.objects.create_user(
        username="report6-photo-delete", password="password", is_staff=True
    )
    pcs_no = "SN-PHOTO-DELETE"
    photo = SNPhoto.objects.create(
        pcs_no=pcs_no, image="test_image.png",
        caption="To delete", uploaded_by="admin",
    )
    client = Client()
    client.force_login(user)
    url = f"/reports/photo/{photo.pk}/delete/"
    response = client.post(url)
    assert response.status_code == 302
    assert not SNPhoto.objects.filter(pk=photo.pk).exists()


@pytest.mark.django_db
def test_report6_view_description_lines():
    """Report6View: report6_description_lines в контексте."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="testuser_report6_desc", defaults={"password": "pass", "is_staff": True}
        )
        client = Client()
        client.force_login(user)
        response = client.get("/reports/6/")
        response.render()
        context = response.context_data
        assert context["report6_description_lines"] is not None
        assert len(context["report6_description_lines"]) > 0


@pytest.mark.django_db
def test_report6_view_context_and_recent_sns():
    """Report6View: summary, recent_sns в контексте, Cache-Control: no-store."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="testuser_report6_view", defaults={"password": "pass", "is_staff": True}
        )
        pcs_no = "SN-REPORT6-VIEW"
        dt_start = timezone.make_aware(datetime(2026, 9, 15, 10, 0, 0))
        ProductionRecord.objects.create(
            lot_number="LOT-VIEW", production_spec="SPEC-VIEW", subop_no=10,
            pcs_no=pcs_no, created_date=dt_start, result="OK",
        )

        client = Client()
        client.force_login(user)

        response = client.get(f"/reports/6/?pcs_no={pcs_no}")

        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"
        response.render()
        context = response.context_data
        assert context["exists"] is True
        assert context["summary"] is not None
        assert context["summary"]["pcs_no"] == pcs_no
        assert context["recent_sns"] == ["SN-REPORT6-VIEW"]
        assert "Описание" in response.content.decode() or "report6DescriptionModal" in response.content.decode()
        assert "Сводка" in response.content.decode()
        assert "Последние просмотренные SN" in response.content.decode()
        assert "Редактировать" in response.content.decode()


@pytest.mark.django_db
def test_report6_view_recent_sns_tracking():
    """Report6View: просмотр SN добавляет его в список recent_sns в сессии."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="testuser_report6_recent", defaults={"password": "pass"}
        )
        pcs_no = "SN-REPORT6-RECENT"
        dt_start = timezone.make_aware(datetime(2026, 9, 15, 10, 0, 0))
        ProductionRecord.objects.create(
            lot_number="LOT-RECENT", production_spec="SPEC-RECENT", subop_no=10,
            pcs_no=pcs_no, created_date=dt_start, result="OK",
        )

        client = Client()
        client.force_login(user)

        response = client.get(f"/reports/6/?pcs_no={pcs_no}")
        response.render()
        assert response.context_data["recent_sns"] == ["SN-REPORT6-RECENT"]


@pytest.mark.django_db
def test_sn_comment_edit_view_requires_admin_and_saves_comment():
    user = User.objects.create_user(
        username="report4-editor",
        password="password",
        is_active=True,
        is_staff=True,
    )
    pcs_no = "SN-EDIT-COMMENT"
    ProductionRecord.objects.create(
        lot_number="LOT-EDIT",
        subop_no=10,
        pcs_no=pcs_no,
        created_date=timezone.make_aware(datetime(2026, 9, 1, 8, 0)),
        result="OK",
        production_spec="SPEC-EDIT"
    )
    client = Client()

    response = client.get(f"/reports/comment/{pcs_no}/edit/")
    assert response.status_code == 302

    client.force_login(user)
    response = client.post(
        f"/reports/comment/{pcs_no}/edit/",
        {"comment": "Новый комментарий"},
    )

    assert response.status_code == 302
    assert SNComment.objects.filter(pcs_no=pcs_no).exists()
    assert SNComment.objects.get(pcs_no=pcs_no).comment == "Новый комментарий"
    assert SNComment.objects.get(pcs_no=pcs_no).created_by == "report4-editor"


@pytest.mark.django_db
def test_dedup_on_reimport():
    """Повторная загрузка не создает дублей."""
    dt = timezone.make_aware(datetime(2026, 8, 13, 10, 0, 0))
    records = [
        {
            "lot_number": "LOT-001", "subop_no": 10, "created_date": dt,
            "pcs_no": "PCS1", "result": "OK", "production_spec": "SPEC",
        },
    ]
    from uploads.excel_parser import import_to_database
    result1 = import_to_database(records, "test.xlsx")
    result2 = import_to_database(records, "test.xlsx")
    assert result1["inserted"] == 1
    assert result2["inserted"] == 0
    assert Production.objects.count() == 1


# ========================
# Тесты сортировки
# ========================

def test_apply_sort_ascending():
    """Сортировка по возрастанию."""
    data = [
        {"name": "charlie", "val": 3},
        {"name": "alice", "val": 1},
        {"name": "bob", "val": 2},
    ]
    result = apply_sort(data, "val", "asc", ["val", "name"])
    assert [r["val"] for r in result] == [1, 2, 3]


def test_apply_sort_descending():
    """Сортировка по убыванию."""
    data = [
        {"name": "charlie", "val": 3},
        {"name": "alice", "val": 1},
        {"name": "bob", "val": 2},
    ]
    result = apply_sort(data, "val", "desc", ["val", "name"])
    assert [r["val"] for r in result] == [3, 2, 1]


def test_apply_sort_string_field():
    """Сортировка по строковому полю."""
    data = [
        {"name": "zebra"},
        {"name": "apple"},
        {"name": "mango"},
    ]
    result = apply_sort(data, "name", "asc", ["name"])
    assert [r["name"] for r in result] == ["apple", "mango", "zebra"]


def test_apply_sort_none_values():
    """None всегда сортируются в конец."""
    data = [
        {"name": "b"},
        {"name": None},
        {"name": "a"},
    ]
    result = apply_sort(data, "name", "asc", ["name"])
    assert [r["name"] for r in result] == ["a", "b", None]

    result_desc = apply_sort(data, "name", "desc", ["name"])
    assert [r["name"] for r in result_desc] == ["b", "a", None]

    mixed = apply_sort(
        [
            {"name": "B"},
            {"name": None},
            {"name": "a"},
            {"name": 2},
            {"name": 10},
        ],
        "name",
        "asc",
        ["name"],
    )
    assert [r["name"] for r in mixed] == [2, 10, "a", "B", None]


def test_apply_sort_large_list_keeps_none_last():
    """apply_sort обрабатывает большие списки и по-прежнему ставит None в конец."""
    data = [
        {"n": index, "value": None if index % 10 == 0 else index}
        for index in range(5000)
    ]

    result = apply_sort(data, "value", "asc", ["value"])

    values = [item["value"] for item in result]
    assert len(values) == 5000
    assert values[-500:] == [None] * 500
    assert values[:-500] == sorted(values[:-500])


def test_apply_sort_invalid_field():
    """Сортировка по полю неиз списка allowed_fields возвращает данные без изменений."""
    data = [
        {"name": "b"},
        {"name": "a"},
    ]
    result = apply_sort(data, "invalid_field", "asc", ["name"])
    assert result == data


def test_get_sort_params_valid():
    """Валидные параметры сортировки извлекаются корректно."""
    class FakeRequest:
        def __init__(self, get_params):
            self.GET = get_params

    request = FakeRequest({"sort": "LOT", "dir": "desc"})
    sort_field, sort_dir = get_sort_params(request, "report1")
    assert sort_field == "LOT"
    assert sort_dir == "desc"


def test_get_sort_params_invalid_field():
    """Недопустимое поле сортировки игнорируется."""
    class FakeRequest:
        def __init__(self, get_params):
            self.GET = get_params

    request = FakeRequest({"sort": "invalid_field", "dir": "asc"})
    sort_field, sort_dir = get_sort_params(request, "report1")
    assert sort_field == ""
    assert sort_dir == "asc"


def test_get_sort_params_defaults():
    """Параметры по умолчанию при отсутствии sort и dir."""
    class FakeRequest:
        def __init__(self, get_params):
            self.GET = get_params

    request = FakeRequest({})
    sort_field, sort_dir = get_sort_params(request, "report2")
    assert sort_field == ""
    assert sort_dir == "asc"


def test_sortable_fields_defined():
    """Все отчеты имеют определенные сортируемые поля."""
    assert "report1" in SORTABLE_FIELDS
    assert "report2" in SORTABLE_FIELDS
    assert "report3" in SORTABLE_FIELDS
    assert "report4" in SORTABLE_FIELDS
    assert "report5" in SORTABLE_FIELDS
    assert "report6" in SORTABLE_FIELDS
    assert "LOT" in SORTABLE_FIELDS["report1"]
    assert "report_date" in SORTABLE_FIELDS["report2"]
    assert "report_month" in SORTABLE_FIELDS["report3"]
    assert "pcs_no" in SORTABLE_FIELDS["report4"]
    assert "station" in SORTABLE_FIELDS["report5"]


@pytest.mark.django_db
def test_report1_sort_by_production():
    """Сортировка отчета 1 по полю Production."""
    dt1 = timezone.make_aware(datetime(2026, 8, 13, 10, 0, 0))
    dt2 = timezone.make_aware(datetime(2026, 8, 13, 11, 0, 0))
    dt3 = timezone.make_aware(datetime(2026, 8, 13, 12, 0, 0))
    dt4 = timezone.make_aware(datetime(2026, 8, 19, 12, 0, 0))

    ProductionRecord.objects.create(
        lot_number="LOT-B", subop_no=10, created_date=dt1,
        pcs_no="PCS-B1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-B", subop_no=130, created_date=dt4,
        pcs_no="PCS-B1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-A", subop_no=10, created_date=dt2,
        pcs_no="PCS-A1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-A", subop_no=10, created_date=dt3,
        pcs_no="PCS-A2", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-A", subop_no=130, created_date=dt4,
        pcs_no="PCS-A2", result="OK", production_spec="SPEC"
    )

    data = report1_orders()
    assert len(data) == 2

    sorted_data = apply_sort(data, "Production", "desc", SORTABLE_FIELDS["report1"])
    assert sorted_data[0]["LOT"] == "LOT-A"
    assert sorted_data[1]["LOT"] == "LOT-B"

    for i, row in enumerate(sorted_data, 1):
        row["N"] = i
    assert sorted_data[0]["N"] == 1
    assert sorted_data[1]["N"] == 2


@pytest.mark.django_db
def test_report6_serial_number():
    first = timezone.make_aware(datetime(2026, 9, 15, 10, 0, 0))
    second = timezone.make_aware(datetime(2026, 9, 15, 11, 0, 0))

    ProductionRecord.objects.create(
        lot_number="LOT-001", production_spec="SPEC-001", subop_no=50,
        position_no="50", workstation_name="壳体组装", pcs_no="SN-001",
        created_date=second, result="OK", test_data='{"value": 2}',
    )
    ProductionRecord.objects.create(
        lot_number="LOT-001", production_spec="SPEC-001", subop_no=10,
        position_no="10", workstation_name="PCB投料", pcs_no="SN-001",
        created_date=first, result="OK", test_data='{"value": 1}',
    )
    ProductionRecord.objects.create(
        lot_number="LOT-002", production_spec="SPEC-002", subop_no=10,
        position_no="10", workstation_name="PCB投料", pcs_no="SN-002",
        created_date=first, result="OK", test_data="",
    )

    data = report6_serial_number("SN-001")

    assert [row["created_date"] for row in data] == [first, second]
    assert [row["workstation_name"] for row in data] == ["PCB Loading", "Assembly"]
    assert data[0]["test_data"] == '{"value": 1}'
    assert report6_serial_number("MISSING") == []


@pytest.mark.django_db
def test_report7_station130_output_filters_and_deduplicates():
    start_date = date(2026, 9, 14)
    end_date = date(2026, 9, 20)
    records = [
            ProductionRecord(
                lot_number="LOT-B", subop_no=130, pcs_no="SN-DUP",
                production_spec="SPEC-B", result="OK",
                created_date=timezone.make_aware(datetime(2026, 9, 15, 10, 0)),
            ),
        ProductionRecord(
            lot_number="LOT-B", subop_no=130, pcs_no="SN-DUP",
            production_spec="SPEC-B", result="OK",
            created_date=timezone.make_aware(datetime(2026, 9, 16, 11, 0)),
        ),
        ProductionRecord(
            lot_number="LOT-A", subop_no=130, pcs_no="SN-START",
            production_spec="SPEC-A", result="OK",
            created_date=timezone.make_aware(datetime(2026, 9, 14, 8, 0)),
        ),
        ProductionRecord(
            lot_number="LOT-C", subop_no=130, pcs_no="SN-END",
            production_spec="SPEC-C", result="OK",
            created_date=timezone.make_aware(datetime(2026, 9, 20, 20, 0)),
        ),
        ProductionRecord(
            lot_number="LOT-NG", subop_no=130, pcs_no="SN-NG",
            result="NG", created_date=timezone.make_aware(datetime(2026, 9, 17, 10, 0)),
        ),
        ProductionRecord(
            lot_number="LOT-OTHER", subop_no=129, pcs_no="SN-OTHER",
            result="OK", created_date=timezone.make_aware(datetime(2026, 9, 17, 10, 0)),
        ),
        ProductionRecord(
            lot_number="LOT-OUT", subop_no=130, pcs_no="SN-OUT",
            result="OK", created_date=timezone.make_aware(datetime(2026, 9, 21, 10, 0)),
        ),
    ]
    ProductionRecord.objects.bulk_create(records)

    data = report7_station130_output(start_date, end_date)

    assert [row["pcs_no"] for row in data] == ["SN-END", "SN-DUP", "SN-START"]
    duplicate = next(row for row in data if row["pcs_no"] == "SN-DUP")
    assert duplicate["lot_number"] == "LOT-B"
    assert duplicate["production_spec"] == "SPEC-B"
    assert duplicate["created_date"] == records[1].created_date


class FakeRequest:
    def __init__(self, get_params):
        self.GET = get_params


def test_report7_period_selection():
    week = _report7_period(FakeRequest({"filter": "week", "week": "2026-W38"}))
    assert week["start_date"] == date(2026, 9, 14)
    assert week["end_date"] == date(2026, 9, 20)

    month = _report7_period(FakeRequest({"filter": "month", "year": "2024", "month": "2"}))
    assert month["start_date"] == date(2024, 2, 1)
    assert month["end_date"] == date(2024, 2, 29)

    invalid = _report7_period(
        FakeRequest({"filter": "period", "start": "2026-09-20", "end": "2026-09-14"})
    )
    assert invalid["error"]

    malformed = _report7_period(
        FakeRequest({"filter": "period", "start": "not-a-date", "end": "2026-09-20"})
    )
    assert malformed["error"]
    assert malformed["start_date"] == date.today()
    assert malformed["end_date"] == date.today()

    missing = _report7_period(
        FakeRequest({"filter": "period", "start": "2026-09-14"})
    )
    assert missing["error"]
    assert missing["start_date"] == date.today()
    assert missing["end_date"] == date.today()


def test_report7_summary():
    data = [
        {"pcs_no": "SN-1", "lot_number": "LOT-B"},
        {"pcs_no": "SN-1", "lot_number": "LOT-B"},
        {"pcs_no": "SN-2", "lot_number": "LOT-A"},
    ]
    summary = _report7_summary(data, date(2026, 9, 14), date(2026, 9, 20))
    assert summary == {
        "total_days": 7,
        "released_count": 2,
        "lots": "LOT-A, LOT-B",
    }


def test_report2_period_selection():
    month = _report2_period(FakeRequest({"filter": "month", "year": "2024", "month": "2"}))
    assert month["start_date"] == date(2024, 2, 1)
    assert month["end_date"] == date(2024, 2, 29)

    year = _report2_period(FakeRequest({"filter": "year", "year": "2025"}))
    assert year["start_date"] == date(2025, 1, 1)
    assert year["end_date"] == date(2025, 12, 31)

    period = _report2_period(
        FakeRequest({"filter": "period", "start": "2026-01-03", "end": "2026-01-05"})
    )
    assert period["start_date"] == date(2026, 1, 3)
    assert period["end_date"] == date(2026, 1, 5)

    invalid = _report2_period(
        FakeRequest({"filter": "period", "start": "2026-01-05", "end": "2026-01-03"})
    )
    assert invalid["error"]


def test_report2_period_lot():
    """Фильтр «По лоту» не задаёт диапазон дат, а передаёт номер лота."""
    request = RequestFactory().get("/reports/2/?filter=lot&lot=MO608131-001")
    period = _report2_period(request)

    assert period["filter_type"] == "lot"
    assert period["lot_value"] == "MO608131-001"
    assert period["start_date"] is None
    assert period["end_date"] is None
    assert period["error"] == ""


def test_report2_summary_averages_only_active_days():
    data = [
        {"fol_hours": 2, "fol_production": 10, "fol_speed": 5, "bol_hours": 0, "bol_production": 0, "bol_speed": 0},
        {"fol_hours": 0, "fol_production": 0, "fol_speed": 0, "bol_hours": 4, "bol_production": 12, "bol_speed": 3},
        {"fol_hours": 4, "fol_production": 12, "fol_speed": 3, "bol_hours": 2, "bol_production": 6, "bol_speed": 3},
    ]
    summary = _report2_summary(data, date(2026, 1, 1), date(2026, 1, 3))
    assert summary == {
        "total_days": 3,
        "fol_hours": 6,
        "fol_production": 22,
        "fol_speed": 4,
        "fol_active_days": 2,
        "bol_hours": 6,
        "bol_production": 18,
        "bol_speed": 3,
        "bol_active_days": 2,
    }


def test_report2_view_default_year(monkeypatch):
    import json
    from reports.views import Report2View

    rows = [
        {"report_date": date(2026, 1, 1), "fol_hours": 2, "fol_production": 10, "fol_speed": 5, "bol_hours": 0, "bol_production": 0, "bol_speed": 0, "has_data": True},
        {"report_date": date(2026, 1, 2), "fol_hours": 0, "fol_production": 0, "fol_speed": 0, "bol_hours": 0, "bol_production": 0, "bol_speed": 0, "has_data": False},
    ]
    monkeypatch.setattr("reports.views.report2_line_productivity", lambda start_date, end_date, lot_number=None: rows)

    request = RequestFactory().get("/reports/2/")
    response = Report2View.as_view()(request)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    response.render()
    context = response.context_data
    assert context["filter_type"] == "year"
    assert b'id="year-field"' in response.content
    assert b'name="year"' in response.content
    assert b'class="fol-cell text-primary"' in response.content
    assert b'class="bol-cell text-danger"' in response.content
    assert b'.table .fol-cell { background-color: #eaf6ff; }' in response.content
    assert b'.table .bol-cell { background-color: #fff0f0; }' in response.content
    assert context["start_date"] == date(date.today().year, 1, 1)
    assert context["end_date"] == date(date.today().year, 12, 31)
    assert context["data"] == [rows[0]]
    assert context["table_summary"]["fol_hours"] == 2
    assert context["table_summary"]["fol_production"] == 10
    chart_data = json.loads(context["chart_data"])
    assert chart_data["dates"] == ["2026-01-01"]
    assert chart_data["fol_hours"] == [2.0]
    assert chart_data["fol_production"] == [10.0]
    expected_days = 366 if date.today().year % 4 == 0 else 365
    assert context["summary"]["total_days"] == expected_days


def test_report2_export_includes_summary_and_charts(monkeypatch):
    from types import SimpleNamespace
    from reports.views import Report2ExportView

    rows = [
        {"report_date": date(2026, 1, 1), "fol_hours": 2, "fol_production": 10, "fol_speed": 5, "bol_hours": 0, "bol_production": 0, "bol_speed": 0, "has_data": True},
        {"report_date": date(2026, 1, 2), "fol_hours": 0, "fol_production": 0, "fol_speed": 0, "bol_hours": 0, "bol_production": 0, "bol_speed": 0, "has_data": False},
        {"report_date": date(2026, 1, 3), "fol_hours": 4, "fol_production": 12, "fol_speed": 3, "bol_hours": 2, "bol_production": 6, "bol_speed": 3, "has_data": True},
    ]
    monkeypatch.setattr("reports.views.report2_line_productivity", lambda start_date, end_date, lot_number=None: rows)

    request = RequestFactory().get("/reports/2/export/", {"filter": "period", "start": "2026-01-01", "end": "2026-01-03"})
    request.user = SimpleNamespace(is_authenticated=True)
    response = Report2ExportView.as_view()(request)

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    assert workbook.sheetnames == ["Производительность", "Сводка", "Диаграммы"]

    sheet = workbook["Производительность"]
    assert sheet["A2"].value == "2026-01-01"
    assert sheet["A3"].value == "2026-01-03"
    assert sheet.max_row == 3

    summary = workbook["Сводка"]
    assert summary["B2"].value == "01.01.2026 — 03.01.2026"
    assert summary["B3"].value.date() == date(2026, 1, 1)
    assert summary["B4"].value.date() == date(2026, 1, 3)
    assert summary["B5"].value == 3
    assert summary["B7"].value == "FOL"
    assert summary["C7"].value == "BOL"
    assert summary["B8"].value == 6
    assert summary["C8"].value == 2
    assert summary["B9"].value == 22
    assert summary["C9"].value == 6
    assert summary["B10"].value == 4
    assert summary["C10"].value == 3
    assert summary["B11"].value == 2
    assert summary["C11"].value == 1

    charts = workbook["Диаграммы"]._charts
    assert len(charts) == 3
    assert all(len(chart.series) == 2 for chart in charts)


def test_report2_view_lot_filter(monkeypatch):
    """Вью с фильтром «По лоту» передаёт номер лота в запрос и отображает поле лота."""
    from reports.views import Report2View

    rows = [
        {"report_date": date(2026, 8, 13), "fol_hours": 2, "fol_production": 10, "fol_speed": 5,
         "bol_hours": 0, "bol_production": 0, "bol_speed": 0, "has_data": True},
    ]
    captured = {}

    def fake_query(start_date, end_date, lot_number=None):
        captured["lot_number"] = lot_number
        return rows

    monkeypatch.setattr("reports.views.report2_line_productivity", fake_query)

    request = RequestFactory().get("/reports/2/?filter=lot&lot=MO608131-001")
    response = Report2View.as_view()(request)

    assert response.status_code == 200
    assert captured["lot_number"] == "MO608131-001"
    response.render()
    content = response.content.decode()
    assert 'value="lot" selected' in content
    assert 'id="lot-field"' in content
    assert 'name="lot"' in content
    assert 'value="MO608131-001"' in content
    assert "Фильтр: По лоту" in content


@pytest.mark.django_db
def test_report7_export_is_available_to_regular_user():
    user = User.objects.create_user(username="operator", password="password")
    client = Client()
    client.force_login(user)
    ProductionRecord.objects.create(
        lot_number="LOT-001", subop_no=130, pcs_no="SN-001",
        production_spec="SPEC-001", result="OK",
        created_date=timezone.make_aware(datetime(2026, 9, 15, 10, 30)),
    )

    response = client.get("/reports/7/export/", {"filter": "day", "day": "2026-09-15"})

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")
    workbook = load_workbook(BytesIO(response.content), read_only=True)
    assert workbook.sheetnames == ["Сводка", "Выпуск"]
    assert workbook["Выпуск"]["A1"].value == "PCSNo - Серийный номер"
    assert workbook["Выпуск"]["A2"].value == "SN-001"
    assert workbook["Сводка"]["B3"].value == 1


def test_translate_workstation_name_by_position():
    assert translate_workstation_name("A110", "气密测试") == "Seal Test"
    assert translate_workstation_name("20", "FCT1") == "FCT1"
    assert translate_workstation_name("unknown", "Unknown") == "Unknown"


def test_report1_period_types_constant():
    """Проверка константы доступных типов периодов для отчета 1."""
    from reports.views import REPORT1_PERIOD_TYPES
    assert REPORT1_PERIOD_TYPES == {"year", "period"}


@pytest.mark.django_db
def test_report1_view_year_filter():
    """Проверка отчета 1 через Client с фильтром по году."""
    from django.test import Client, override_settings
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user, _ = User.objects.get_or_create(username="testuser_report1_year", defaults={"password": "testpass"})

    with override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"]):
        client = Client()
        client.force_login(user)

        # Тест: год по умолчанию (текущий)
        response = client.get("/reports/1/")
        assert response.status_code == 200
        assert "Сводный отчет" in response.content.decode()

        # Тест: конкретный год
        response = client.get("/reports/1/?filter=year&year=2025")
        assert response.status_code == 200
        assert "Сводный отчет" in response.content.decode()

        # Тест: некорректный год (должен вернуть текущий год с ошибкой)
        response = client.get("/reports/1/?filter=year&year=not-a-year")
        assert response.status_code == 200
        # Должно отображаться сообщение об ошибке


def test_report1_summary():
    data = [
        {"LOT": "LOT-A", "Production": 2, "Ok": 1, "Diff": 1},
        {"LOT": "LOT-B", "Production": 3, "Ok": 0, "Diff": 3},
        {"LOT": "LOT-C", "Production": 0, "Ok": 0, "Diff": 0},
    ]

    summary = _report1_summary(data, date(2026, 9, 14), date(2026, 9, 20))

    assert summary == {
        "total_days": 7,
        "released_lots": 1,
        "production_total": 5,
        "ok_total": 1,
        "diff_total": 4,
    }


@pytest.mark.django_db
def test_report1_view_period_summary_context(monkeypatch):
    from django.test import Client, override_settings

    user, _ = User.objects.get_or_create(
        username="testuser_report1_summary", defaults={"password": "testpass"}
    )
    rows = [
        {"LOT": "LOT-A", "Production": 2, "Ok": 1, "Diff": 1},
        {"LOT": "LOT-B", "Production": 3, "Ok": 0, "Diff": 3},
        {"LOT": "LOT-C", "Production": 0, "Ok": 0, "Diff": 0},
    ]
    monkeypatch.setattr("reports.views.report1_orders", lambda start_date, end_date: rows)

    with override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"]):
        client = Client()
        client.force_login(user)
        response = client.get(
            "/reports/1/?filter=period&start=2026-09-14&end=2026-09-16"
        )
        response.render()

    assert response.status_code == 200
    assert response.context_data["summary"] == {
        "total_days": 3,
        "released_lots": 1,
        "production_total": 5,
        "ok_total": 1,
        "diff_total": 4,
    }
    content = response.content.decode()
    assert "Всего дней" in content
    assert "Выпущено лотов" in content
    assert "Запущено в производство" in content
    assert "Выпущено" in content
    assert "Не прошло сборку" in content


@pytest.mark.django_db
def test_report1_view_period_filter():
    """Проверка отчета 1 через Client с фильтром по произвольному периоду."""
    from django.test import Client, override_settings
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user, _ = User.objects.get_or_create(username="testuser_report1_period", defaults={"password": "testpass"})

    with override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"]):
        client = Client()
        client.force_login(user)

        # Тест: валидный период
        response = client.get("/reports/1/?filter=period&start=2026-01-01&end=2026-01-31")
        assert response.status_code == 200
        assert "Сводный отчет" in response.content.decode()

        # Тест: некорректная дата начала
        response = client.get("/reports/1/?filter=period&start=not-a-date&end=2026-01-31")
        assert response.status_code == 200
        # Должно отображаться сообщение об ошибке

        # Тест: конец раньше начала
        response = client.get("/reports/1/?filter=period&start=2026-01-31&end=2026-01-01")
        assert response.status_code == 200
        # Должно отображаться сообщение об ошибке


@pytest.mark.django_db
def test_report1_defect_threshold(monkeypatch):
    """Проверка порога Diff < 10 для отображения SN в defect_sns."""
    from django.test import Client, override_settings
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user, _ = User.objects.get_or_create(username="testuser_report1_defect", defaults={"password": "testpass"})

    # Подготовка строк с разным defect_count
    rows_9 = [{
        "LOT": "LOT-9",
        "production_spec": "SPEC",
        "Total": 10,
        "Production": 10,
        "Ok": 1,
        "Diff": 9,
        "Defect": "SN1, SN2, SN3, SN4, SN5, SN6, SN7, SN8, SN9",
        "defect_sns": ["SN1", "SN2", "SN3", "SN4", "SN5", "SN6", "SN7", "SN8", "SN9"],
        "start": None,
        "finish": None,
        "comment": "",
    }]
    rows_10 = [{
        "LOT": "LOT-10",
        "production_spec": "SPEC",
        "Total": 10,
        "Production": 10,
        "Ok": 0,
        "Diff": 10,
        "Defect": "SN не прошедших сборку более 10 штук",
        "defect_sns": [],
        "start": None,
        "finish": None,
        "comment": "",
    }]

    def mock_orders_9(start_date, end_date):
        return rows_9

    def mock_orders_10(start_date, end_date):
        return rows_10

    with override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"]):
        client = Client()
        client.force_login(user)

        # Diff = 9 -> defect_sns populated
        monkeypatch.setattr("reports.views.report1_orders", mock_orders_9)
        response = client.get("/reports/1/")
        response.render()
        assert response.status_code == 200
        data = response.context_data["data"]
        assert len(data) == 1
        assert data[0]["defect_sns"] == ["SN1", "SN2", "SN3", "SN4", "SN5", "SN6", "SN7", "SN8", "SN9"]
        assert data[0]["Defect"] == "SN1, SN2, SN3, SN4, SN5, SN6, SN7, SN8, SN9"

        # Diff = 10 -> defect_sns empty, Defect message
        monkeypatch.setattr("reports.views.report1_orders", mock_orders_10)
        response = client.get("/reports/1/")
        response.render()
        assert response.status_code == 200
        data = response.context_data["data"]
        assert len(data) == 1
        assert data[0]["defect_sns"] == []
        assert data[0]["Defect"] == "SN не прошедших сборку более 10 штук"


@pytest.mark.django_db
def test_report1_default_sort_by_start(monkeypatch):
    """Проверка сортировки по умолчанию по start asc."""
    from django.test import Client, override_settings
    from django.contrib.auth import get_user_model
    from datetime import datetime
    from django.utils import timezone

    User = get_user_model()
    user, _ = User.objects.get_or_create(username="testuser_report1_sort", defaults={"password": "testpass"})

    # Две строки с разными start датами
    row_later = {
        "LOT": "LOT-LATER",
        "production_spec": "SPEC",
        "Total": 5,
        "Production": 5,
        "Ok": 5,
        "Diff": 0,
        "Defect": "",
        "defect_sns": [],
        "start": timezone.make_aware(datetime(2026, 9, 15, 12, 0, 0)),
        "finish": None,
        "comment": "",
    }
    row_earlier = {
        "LOT": "LOT-EARLIER",
        "production_spec": "SPEC",
        "Total": 5,
        "Production": 5,
        "Ok": 5,
        "Diff": 0,
        "Defect": "",
        "defect_sns": [],
        "start": timezone.make_aware(datetime(2026, 9, 10, 8, 0, 0)),
        "finish": None,
        "comment": "",
    }
    rows = [row_later, row_earlier]  # порядок в моке: позже, раньше

    def mock_orders(start_date, end_date):
        return rows

    with override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"]):
        client = Client()
        client.force_login(user)
        monkeypatch.setattr("reports.views.report1_orders", mock_orders)
        response = client.get("/reports/1/")
        response.render()
        assert response.status_code == 200
        data = response.context_data["data"]
        # После сортировки по start asc первым должен быть LOT-EARLIER
        assert data[0]["LOT"] == "LOT-EARLIER"
        assert data[1]["LOT"] == "LOT-LATER"
        # N должно быть перенумеровано
        assert data[0]["N"] == 1
        assert data[1]["N"] == 2


def test_report1_comment_no_truncate():
    """Проверка, что комментарий не обрезается в шаблоне (юнит-тест шаблона не требуется, проверяем логику)."""
    # Этот тест больше документационный, так как урезание убрано в шаблоне.
    pass


@pytest.mark.django_db
def test_report1_export_is_available_to_regular_user():
    """Обычный авторизованный пользователь может экспортировать отчет №1 в Excel."""
    with override_settings(ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"]):
        user, _ = User.objects.get_or_create(
            username="operator", defaults={"password": "password"}
        )
        client = Client()
        client.force_login(user)

        response = client.get("/reports/1/export/")

        assert response.status_code == 200
        assert response["Content-Type"].startswith("application/vnd.openxmlformats")
        workbook = load_workbook(BytesIO(response.content), read_only=True)
        assert workbook.sheetnames == ["Сводный отчет"]


@pytest.mark.django_db
def test_report1_export_defaults_to_current_year(monkeypatch):
    """Экспорт №1 без параметров использует текущий год, как и страница отчёта."""
    from reports import views

    captured = {}

    def fake_orders(start, end):
        captured["start"] = start
        captured["end"] = end
        return []

    monkeypatch.setattr(views, "report1_orders", fake_orders)

    with override_settings(ALLOWED_HOSTS=["*"]):
        response = Client().get("/reports/1/export/")

    assert response.status_code == 200
    today = date.today()
    assert captured["start"] == date(today.year, 1, 1)
    assert captured["end"] == date(today.year, 12, 31)


@pytest.mark.django_db
def test_report1_export_order_matches_page(monkeypatch):
    """Экспорт №1 сортирует по умолчанию так же, как страница (start asc)."""
    from reports import views

    rows = [
        {
            "N": 1, "LOT": "LOT-NEW", "production_spec": "S", "Total": 1,
            "Production": 1, "Ok": 0, "Diff": 1, "Defect": "", "defect_sns": [],
            "start": datetime(2026, 5, 2, 9, 0), "finish": None, "comment": "",
        },
        {
            "N": 2, "LOT": "LOT-OLD", "production_spec": "S", "Total": 1,
            "Production": 1, "Ok": 0, "Diff": 1, "Defect": "", "defect_sns": [],
            "start": datetime(2026, 5, 1, 9, 0), "finish": None, "comment": "",
        },
    ]
    monkeypatch.setattr(
        views, "report1_orders", lambda start, end: [dict(row) for row in rows]
    )

    with override_settings(ALLOWED_HOSTS=["*"]):
        page = Client().get("/reports/1/")
        page.render()
        export = Client().get("/reports/1/export/")

    assert [row["LOT"] for row in page.context_data["data"]] == ["LOT-OLD", "LOT-NEW"]

    workbook = load_workbook(BytesIO(export.content), read_only=True)
    sheet = workbook["Сводный отчет"]
    exported = [sheet.cell(row, 2).value for row in range(2, 4)]
    assert exported == ["LOT-OLD", "LOT-NEW"]


@pytest.mark.parametrize(
    ("report_number", "view_name", "query_name"),
    [
        (1, "Report1ExportView", "report1_orders"),
        (2, "Report2ExportView", "report2_line_productivity"),
        (3, "Report3ExportView", "report2_line_productivity"),
        (4, "Report4ExportView", "report4_defects"),
        (5, "Report5ExportView", "report5_repeated_passes"),
        (6, "Report6ExportView", "report6_serial_number"),
        (7, "Report7ExportView", "report7_station130_output"),
        (8, "Report8ExportView", "report8_stations"),
    ],
)
def test_report_exports_available_to_anonymous(monkeypatch, report_number, view_name, query_name):
    """Все отчёты можно экспортировать в Excel без авторизации."""
    from django.contrib.auth.models import AnonymousUser
    from reports import views

    monkeypatch.setattr(views, query_name, lambda *args, **kwargs: [])
    view = getattr(views, view_name)
    request = RequestFactory().get(f"/reports/{report_number}/export/")
    request.user = AnonymousUser()

    response = view.as_view()(request)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")


# ========================
# Тесты отчёта 8: По станциям
# ========================

@pytest.mark.django_db
def test_report8_ng_sns_have_no_extra_spaces():
    """Список NG SN разбирается без лишних пробелов после запятой."""
    dt = timezone.make_aware(datetime(2026, 5, 5, 9, 0))
    for pcs_no in ("SN-NG-1", "SN-NG-2"):
        ProductionRecord.objects.create(
            lot_number="LOT-NG", subop_no=20, pcs_no=pcs_no,
            created_date=dt, result="NG", production_spec="SPEC",
        )

    data = report8_stations(date(2026, 5, 1), date(2026, 5, 31))

    assert data[0]["station_20_ng_sns"] == ["SN-NG-1", "SN-NG-2"]


def test_report8_columns_count():
    """Отчёт 8: 36 столбцов в таблице (1 Дата + 35 столбцов по станциям)."""
    assert len(REPORT8_COLUMNS) == 36
    assert REPORT8_COLUMNS[0][0] == "report_date"
    assert REPORT8_COLUMNS[-1][0] == "bol_diff"


def test_report8_period_default_year():
    """По умолчанию фильтр «Год» — последний календарный год."""
    today = date.today()
    request = RequestFactory().get("/reports/8/")

    period = _report8_period(request)

    assert period["filter_type"] == "year"
    assert period["year_value"] == today.year - 1
    assert period["start_date"] == date(today.year - 1, 1, 1)
    assert period["end_date"] == date(today.year - 1, 12, 31)
    assert period["error"] == ""


def test_report8_period_month():
    """Фильтр «Месяц» задаёт корректный диапазон."""
    request = RequestFactory().get("/reports/8/?filter=month&year=2024&month=2")

    period = _report8_period(request)

    assert period["filter_type"] == "month"
    assert period["start_date"] == date(2024, 2, 1)
    assert period["end_date"] == date(2024, 2, 29)


def test_report8_period_lot():
    """Фильтр «По лоту» не задаёт диапазон дат."""
    request = RequestFactory().get("/reports/8/?filter=lot&lot=MO608131-001")

    period = _report8_period(request)

    assert period["filter_type"] == "lot"
    assert period["lot_value"] == "MO608131-001"
    assert period["start_date"] is None
    assert period["end_date"] is None
    assert period["error"] == ""


def test_report8_period_invalid_year():
    """Некорректный год мягко откатывается на последний календарный год (как в отчётах 2/3)."""
    today = date.today()
    request = RequestFactory().get("/reports/8/?filter=year&year=not-a-year")

    period = _report8_period(request)

    assert period["filter_type"] == "year"
    assert period["year_value"] == today.year - 1
    assert period["start_date"] == date(today.year - 1, 1, 1)
    assert period["end_date"] == date(today.year - 1, 12, 31)


def test_report8_period_period_invalid_range():
    """Конец раньше начала — ошибка."""
    request = RequestFactory().get("/reports/8/?filter=period&start=2026-09-20&end=2026-09-14")

    period = _report8_period(request)

    assert period["error"]


def test_report8_summary_totals_and_averages():
    """Сводка: суммы для счётчиков, среднее для %."""
    data = [
        {"report_date": date(2026, 1, 1),
         "station_020_ok": 10, "station_020_ng": 1, "station_020_pct": 10.0, "station_020_ng_sns": [],
         "station_080_ok": 10, "station_080_ng": 0, "station_080_pct": 0.0, "station_080_ng_sns": [],
         "fol_diff": 2, "bol_diff": -1},
        {"report_date": date(2026, 1, 2),
         "station_020_ok": 10, "station_020_ng": 3, "station_020_pct": 30.0, "station_020_ng_sns": ["SN-003"],
         "station_080_ok": 10, "station_080_ng": 1, "station_080_pct": 10.0, "station_080_ng_sns": [],
         "fol_diff": 0, "bol_diff": -1},
    ]
    summary = _report8_summary(data)

    assert summary["station_020_ok"] == 20
    assert summary["station_020_ng"] == 4
    assert summary["station_020_pct"] == round((10.0 + 30.0) / 2, 2)
    assert summary["station_080_pct"] == round((0.0 + 10.0) / 2, 2)
    assert summary["fol_diff"] == 2
    assert summary["bol_diff"] == -2
    assert summary["station_020_ng_sns"] == []


def test_report8_view_default_year(monkeypatch):
    """Вью по умолчанию отображает последний год и устанавливает Cache-Control: no-store."""
    import json
    from reports.views import Report8View

    rows = [
        {"report_date": date(2026, 1, 1),
         "station_010_ok": 8, "station_020_ok": 10, "station_020_ng": 2, "station_020_pct": 20.0,
         "station_020_ng_sns": ["SN-001", "SN-002"],
         "station_030_ok": 7, "station_050_ok": 6, "fol_diff": 2,
         "station_060_ok": 5, "station_070_ok": 5,
         "station_080_ok": 10, "station_080_ng": 0, "station_080_pct": 0.0, "station_080_ng_sns": [],
         "station_090_ok": 10, "station_090_ng": 1, "station_090_pct": 10.0, "station_090_ng_sns": ["SN-003"],
         "station_100_ok": 10, "station_100_ng": 0, "station_100_pct": 0.0, "station_100_ng_sns": [],
         "station_110_ok": 10, "station_110_ng": 0, "station_110_pct": 0.0, "station_110_ng_sns": [],
         "station_120_ok": 10, "station_120_ng": 0, "station_120_pct": 0.0, "station_120_ng_sns": [],
         "station_130_ok": 10, "station_130_ng": 0, "station_130_pct": 0.0, "station_130_ng_sns": [],
         "bol_diff": 5},
    ]
    monkeypatch.setattr("reports.views.report8_stations", lambda start, end, lot=None: rows)

    request = RequestFactory().get("/reports/8/")
    response = Report8View.as_view()(request)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    response.render()
    context = response.context_data
    assert context["filter_type"] == "year"
    assert context["year_value"] == date.today().year - 1
    assert b"report8DescriptionModal" in response.content
    chart_data = json.loads(context["chart_data"])
    # Диаграмма: динамика % NG по дням — одна линия на каждую станцию.
    assert len(chart_data["dates"]) == 1
    assert len(chart_data["datasets"]) == 7
    expected_labels = ["FCT1", "FCT2", "Прошивка", "Проверка прошивки",
                       "Герметичность", "PIN", "Этикетка"]
    assert [ds["label"] for ds in chart_data["datasets"]] == expected_labels
    # Каждая серия содержит значение для каждой даты и задан цвет.
    assert all(len(ds["data"]) == 1 for ds in chart_data["datasets"])
    assert all("color" in ds for ds in chart_data["datasets"])
    assert len({ds["color"] for ds in chart_data["datasets"]}) == 7  # цвета разные
    # NG SN ссылка на отчёт 6
    assert b'href="/reports/6/?pcs_no=SN-001"' in response.content
    # Цвета: station_020_pct > 0 → красный, station_080_pct == 0 → зелёный
    assert b"pct-ng" in response.content
    assert b"pct-zero" in response.content
    # Фильтр «Год» по умолчанию: выпадающий список лет отображается и активен.
    content = response.content.decode()
    assert 'id="year-field"' in content
    assert 'name="year"' in content
    assert 'value="year" selected' in content
    assert content.count('value="20') >= 3  # несколько лет в списке
    # Регрессия: JS не должен скрывать year-field при выборе «Год» (старый cascade-баг).
    assert "month: ['month-field', 'year-field']" not in content
    assert "fieldFilters" in content


def test_report8_export_available_to_anonymous(monkeypatch):
    """Экспорт отчёта 8 доступен анонимным пользователям."""
    from django.contrib.auth.models import AnonymousUser
    from reports.views import Report8ExportView

    monkeypatch.setattr("reports.views.report8_stations", lambda *a, **kw: [])
    request = RequestFactory().get("/reports/8/export/")
    request.user = AnonymousUser()

    response = Report8ExportView.as_view()(request)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")
    workbook = load_workbook(BytesIO(response.content))
    assert "По станциям" in workbook.sheetnames


def test_report8_export_includes_daily_chart(monkeypatch):
    """Экспорт отчёта 8 содержит дневную диаграмму «Средний % NG по дням» с 7 линиями."""
    from datetime import date
    from django.contrib.auth.models import AnonymousUser
    from reports.views import Report8ExportView

    rows = [
        {"report_date": date(2026, 1, 1),
         "station_020_pct": 20.0, "station_080_pct": 0.0, "station_090_pct": 10.0,
         "station_100_pct": 0.0, "station_110_pct": 5.0, "station_120_pct": 0.0,
         "station_130_pct": 0.0},
        {"report_date": date(2026, 1, 2),
         "station_020_pct": 30.0, "station_080_pct": 0.0, "station_090_pct": 0.0,
         "station_100_pct": 15.0, "station_110_pct": 0.0, "station_120_pct": 25.0,
         "station_130_pct": 0.0},
    ]
    monkeypatch.setattr("reports.views.report8_stations", lambda *a, **kw: rows)

    request = RequestFactory().get(
        "/reports/8/export/", {"filter": "period", "start": "2026-01-01", "end": "2026-01-02"}
    )
    request.user = AnonymousUser()
    response = Report8ExportView.as_view()(request)

    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    assert "Сводка" in workbook.sheetnames

    summary = workbook["Сводка"]
    charts = summary._charts
    assert len(charts) == 1
    line_chart = charts[0]
    # openpyxl хранит заголовок диаграммы как объект Title после перезагрузки.
    title_text = str(line_chart.title)
    assert "Средний % NG по дням" in title_text, title_text
    assert len(line_chart.series) == 7

    # Заголовки столбцов дневной диаграммы — подписи NG-типов.
    expected_labels = ["FCT1", "FCT2", "Прошивка", "Проверка прошивки",
                       "Герметичность", "PIN", "Этикетка"]
    assert [summary.cell(12, col).value for col in range(2, 2 + len(expected_labels))] == expected_labels

    # Даты находятся в столбце A, начиная с заголовка в строке 12.
    assert summary.cell(12, 1).value == "Дата"
    assert summary.cell(13, 1).value == "2026-01-01"
    assert summary.cell(14, 1).value == "2026-01-02"

    # Каждая серия окрашена в свой цвет (7 разных цветов).
    solid_fills = [s.graphicalProperties.line.solidFill for s in line_chart.series]
    assert all(solid_fills)
    assert len(set(solid_fills)) == 7


@pytest.mark.django_db
def test_admin_dashboard_includes_report8():
    """Админ-дашборд содержит ссылку на отчёт 8."""
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="admin_report8",
            defaults={"is_active": True, "is_staff": True, "is_superuser": False},
        )
        user.is_active = True
        user.is_staff = True
        user.is_superuser = False
        user.save()

        client = Client()
        client.force_login(user)
        response = client.get("/admin/")

        assert response.status_code == 200
        assert "Отчёт 8: По станциям" in response.content.decode()
        assert reverse("reports:report8") in response.content.decode()


    with override_settings(ALLOWED_HOSTS=["*"]):
        anonymous_client = Client()
        anonymous_response = anonymous_client.get("/admin/")
        assert anonymous_response.status_code == 302
        assert "/admin/login/" in anonymous_response["Location"]

        user, _ = User.objects.get_or_create(
            username="admin_regular",
            defaults={"is_active": True, "is_staff": False, "is_superuser": False},
        )
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.save()

        client = Client()
        client.force_login(user)
        response = client.get("/admin/")
        assert response.status_code == 302
        assert "/admin/login/" in response["Location"]


@pytest.mark.django_db
def test_admin_index_preserves_redirect_response(monkeypatch):
    redirect_response = HttpResponseRedirect("/admin/login/")
    monkeypatch.setattr(
        "django.contrib.admin.sites.AdminSite.index",
        lambda self, request, extra_context=None: redirect_response,
    )

    request_users = (
        AnonymousUser(),
        User(is_active=True, is_staff=False, is_superuser=False),
    )
    for request_user in request_users:
        request = RequestFactory().get("/admin/")
        request.user = request_user
        assert mes_admin_site.index(request) is redirect_response


@pytest.mark.django_db
def test_admin_staff_sees_business_models_but_not_auth_models():
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="admin_staff",
            defaults={"is_active": True, "is_staff": True, "is_superuser": False},
        )
        user.is_active = True
        user.is_staff = True
        user.is_superuser = False
        user.save()

        client = Client()
        client.force_login(user)
        response = client.get("/admin/")

        assert response.status_code == 200
        app_list = response.context["app_list"]
        model_names = {
            model["object_name"]
            for app in app_list
            for model in app["models"]
        }
        assert {"Production", "Lot", "ControlUnit"} <= model_names
        assert "User" not in model_names
        assert "Group" not in model_names
        assert not any(app["app_label"] == "auth" for app in app_list)


@pytest.mark.django_db
def test_admin_superuser_sees_auth_models():
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="admin_super",
            defaults={"is_active": True, "is_staff": True, "is_superuser": True},
        )
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.save()

        client = Client()
        client.force_login(user)
        response = client.get("/admin/")

        assert response.status_code == 200
        auth_app = next(app for app in response.context["app_list"] if app["app_label"] == "auth")
        model_names = {model["object_name"] for model in auth_app["models"]}
        assert {"User", "Group"} <= model_names


@pytest.mark.django_db
def test_admin_manual_defect_search_uses_existing_fields():
    """Поиск в админке «Ручной брак» не падает: поля comment у модели больше нет."""
    ManualDefect.objects.create(pcs_no="SN-ADMIN-SEARCH", lot_number="LOT-ADMIN-SEARCH")

    with override_settings(ALLOWED_HOSTS=["*"]):
        user = User.objects.create_superuser("admin_search", "search@example.com", "pw")
        client = Client()
        client.force_login(user)
        response = client.get("/admin/production/controlunit/", {"q": "SN-ADMIN-SEARCH"})

    assert response.status_code == 200
    assert "SN-ADMIN-SEARCH" in response.content.decode()


@pytest.mark.django_db
def test_admin_production_record_is_read_only_for_staff():
    request = RequestFactory().get("/admin/")
    request.user = User(is_active=True, is_staff=True, is_superuser=False)
    model_admin = ProductionAdmin(Production, mes_admin_site)

    assert model_admin.has_view_permission(request)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)


@pytest.mark.django_db
def test_admin_lot_number_is_editable_on_create_and_read_only_on_change():
    request = RequestFactory().get("/admin/")
    request.user = User(is_active=True, is_staff=True, is_superuser=False)
    model_admin = LotAdmin(Lot, mes_admin_site)

    assert "number" not in model_admin.get_readonly_fields(request, obj=None)
    lot = Lot(number="LOT-ADMIN")
    assert "number" in model_admin.get_readonly_fields(request, obj=lot)


@pytest.mark.django_db
def test_admin_audit_fields_are_set_on_create():
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="admin_audit",
            defaults={"is_active": True, "is_staff": True, "is_superuser": False},
        )
        user.is_active = True
        user.is_staff = True
        user.is_superuser = False
        user.save()

        client = Client()
        client.force_login(user)
        defect_pcs_no = f"ADMIN-DEFECT-{user.pk}"
        lot = Lot.objects.create(number="LOT-ADMIN")

        defect_response = client.post(
            "/admin/production/controlunit/add/",
            {
                "sn": defect_pcs_no,
                "lot": lot.pk,
                "defect": "on",
                "_save": "Save",
            },
        )
        assert defect_response.status_code == 302
        defect = ManualDefect.objects.get(pcs_no=defect_pcs_no)
        assert defect.created_by == user.username
        assert defect.created_at is not None


@pytest.mark.django_db
def test_admin_dashboard_has_links_and_aggregate_metrics():
    with override_settings(ALLOWED_HOSTS=["*"]):
        user, _ = User.objects.get_or_create(
            username="admin_dashboard",
            defaults={"is_active": True, "is_staff": True, "is_superuser": False},
        )
        user.is_active = True
        user.is_staff = True
        user.is_superuser = False
        user.save()

        LotInfo.objects.create(
            lot_number="LOT-DASHBOARD",
            production_spec="SPEC-DASHBOARD",
            plan_total=25,
        )
        ProductionRecord.objects.create(
            lot_number="LOT-DASHBOARD",
            subop_no=17,
            pcs_no="SN-DASHBOARD",
            created_date=timezone.now(),
            result="OK",
            production_spec="SPEC-DASHBOARD",
        )
        ManualDefect.objects.create(
            pcs_no="SN-DASHBOARD-DEFECT",
            production_spec="SPEC-DASHBOARD",
            lot_number="LOT-DASHBOARD",
            created_by="seed",
        )

        client = Client()
        client.force_login(user)
        response = client.get("/admin/")

        assert response.status_code == 200
        content = response.content.decode()
        metrics = response.context["dashboard_metrics"]
        assert metrics["lots"]["total"] >= 1
        assert metrics["lots"]["plan_total"] >= 25
        assert metrics["production_records"]["total"] >= 1
        assert metrics["production_records"]["recent"] >= 1
        assert metrics["manual_defects"]["total"] >= 1
        assert metrics["manual_defects"]["recent"] >= 1

        for label in (
            "Лоты",
            "Записи производства",
            "Ручной брак",
            "Отчёт 1: Сводный",
            "Отчёт 7: Выпуск",
            "Загрузка Excel",
        ):
            assert label in content
        assert "План: 25" in content
        assert "За 7 дней:" in content
        for url_name in (
            "mes_admin:production_lot_changelist",
            "mes_admin:production_production_changelist",
            "mes_admin:production_controlunit_changelist",
            "reports:report1",
            "reports:report7",
            "uploads:upload_home",
        ):
            assert reverse(url_name) in content
