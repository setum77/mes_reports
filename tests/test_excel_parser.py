"""
Тесты парсинга Excel и дедупликации.
"""
import warnings
warnings.filterwarnings("ignore")

import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mes_report3.settings.dev")
sys.path.insert(0, "src")
django.setup()

import pytest
from io import BytesIO
import pandas as pd
from datetime import datetime
from django.utils import timezone

from production.models import ProductionRecord, LotInfo
from uploads.excel_parser import parse_excel_file, import_to_database, ExcelParseError


def make_excel(df_dict):
    """Создает Excel файл в памяти из словаря."""
    buf = BytesIO()
    df = pd.DataFrame(df_dict)
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf


FULL_COLUMNS = [
    "Lot no.", "opno", "op name", "Production No.", "Production Version",
    "product type", "Production Name", "Production spec.",
    "SubOPSequence", "Subop no", "subop name", "PositionNo",
    "WorkstationName", "PCSNo", "User name", "CREATEDATE",
    "working hours", "result", "testData",
]


def test_parse_valid_excel():
    """Парсинг валидного файла с полным набором колонок."""
    df_data = {
        "Lot no.": ["TEST-LOT-001"],
        "opno": ["LOP-001"],
        "op name": ["Test OP"],
        "Production No.": ["PROD1"],
        "Production Version": [1],
        "product type": ["TYPE1"],
        "Production Name": ["Name1"],
        "Production spec.": ["SPEC-001"],
        "SubOPSequence": [1],
        "Subop no": [10],
        "subop name": ["Station 10"],
        "PositionNo": ["P1"],
        "WorkstationName": ["WS1"],
        "PCSNo": ["PCS001"],
        "User name": ["user1"],
        "CREATEDATE": [datetime(2026, 8, 13, 10, 0, 0)],
        "working hours": [1],
        "result": ["OK"],
        "testData": ["data"],
    }
    buf = make_excel(df_data)
    records = parse_excel_file(buf)
    assert len(records) == 1
    rec = records[0]
    assert rec.lot_number == "TEST-LOT-001"
    assert rec.pcs_no == "PCS001"
    assert rec.subop_no == 10
    assert rec.result == "OK"


def test_parse_missing_required_column():
    """Ошибка при отсутствии обязательного столбца."""
    buf = make_excel({"Lot no.": ["X"]})
    with pytest.raises(ExcelParseError):
        parse_excel_file(buf)


def test_parse_partial_columns():
    """Парсинг файла с упрощенным набором колонок (как table1.xlsx)."""
    df_data = {
        "Lot no.": ["LOT-001"],
        "Production No.": ["P1"],
        "Production spec.": ["SPEC"],
        "Subop no": [10],
        "PCSNo": ["PCS1"],
        "CREATEDATE": [datetime(2026, 8, 13, 10, 0, 0)],
        "result": ["OK"],
    }
    buf = make_excel(df_data)
    records = parse_excel_file(buf)
    assert len(records) == 1
    assert records[0].production_spec == "SPEC"
    assert records[0].subop_name == ""


@pytest.mark.django_db
def test_import_dedup():
    """Дубли не должны создаваться при повторной загрузке."""
    dt = timezone.make_aware(datetime(2026, 8, 13, 10, 0, 0))
    rec1 = ProductionRecord(
        lot_number="LOT-001", subop_no=10, created_date=dt,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    result1 = import_to_database([rec1])
    assert result1["inserted"] == 1
    assert result1["duplicates"] == 0

    rec2 = ProductionRecord(
        lot_number="LOT-001", subop_no=10, created_date=dt,
        pcs_no="PCS1", result="OK", production_spec="SPEC"
    )
    result2 = import_to_database([rec2])
    assert result2["inserted"] == 0
    assert result2["duplicates"] == 1
    assert ProductionRecord.objects.count() == 1


@pytest.mark.django_db
def test_import_lotinfo_created():
    """LotInfo создается при импорте."""
    dt = timezone.make_aware(datetime(2026, 8, 13, 10, 0, 0))
    rec = ProductionRecord(
        lot_number="LOT-002", subop_no=10, created_date=dt,
        pcs_no="PCS2", result="OK", production_spec="SPEC-2"
    )
    import_to_database([rec])
    lot = LotInfo.objects.get(lot_number="LOT-002")
    assert lot.production_spec == "SPEC-2"
