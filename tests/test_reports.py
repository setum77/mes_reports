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
from datetime import date, datetime
from io import BytesIO
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from openpyxl import load_workbook

from production.models import ProductionRecord
from reports.queries import (
    report1_orders,
    report2_line_productivity,
    report5_repeated_passes,
    report6_serial_number,
    report7_station130_output,
    translate_workstation_name,
)
from reports.views import (
    _report7_period,
    _report7_summary,
    apply_sort,
    get_sort_params,
    SORTABLE_FIELDS,
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
def test_dedup_on_reimport():
    """Повторная загрузка не создает дублей."""
    dt = timezone.make_aware(datetime(2026, 8, 13, 10, 0, 0))
    records = [
        ProductionRecord(
            lot_number="LOT-001", subop_no=10, created_date=dt,
            pcs_no="PCS1", result="OK", production_spec="SPEC"
        ),
    ]
    from uploads.excel_parser import import_to_database
    result1 = import_to_database(records)
    result2 = import_to_database(records)
    assert result1["inserted"] == 1
    assert result2["inserted"] == 0
    assert ProductionRecord.objects.count() == 1


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
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-B", subop_no=130, created_date=dt4,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-A", subop_no=10, created_date=dt2,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-A", subop_no=10, created_date=dt3,
        pcs_no="PCS2", result="OK", production_spec="SPEC"
    )
    ProductionRecord.objects.create(
        lot_number="LOT-A", subop_no=130, created_date=dt4,
        pcs_no="PCS2", result="OK", production_spec="SPEC"
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
            lot_number="LOT-A", subop_no=130, pcs_no="SN-DUP",
            production_spec="SPEC-A", result="OK",
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
