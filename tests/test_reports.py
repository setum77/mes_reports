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
from datetime import datetime
from django.utils import timezone

from production.models import ProductionRecord
from reports.queries import (
    report1_orders,
    report2_line_productivity,
    report5_repeated_passes,
    report6_serial_number,
    translate_workstation_name,
)
from reports.views import apply_sort, get_sort_params, SORTABLE_FIELDS


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


def test_translate_workstation_name_by_position():
    assert translate_workstation_name("A110", "气密测试") == "Seal Test"
    assert translate_workstation_name("20", "FCT1") == "FCT1"
    assert translate_workstation_name("unknown", "Unknown") == "Unknown"
