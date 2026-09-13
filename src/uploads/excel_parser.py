"""
Парсер Excel-выгрузок из MES системы.
Конвертирует DataFrame → ProductionRecord с дедупликацией.
"""
import pandas as pd
from django.db import transaction
from django.utils import timezone

EXCEL_COLUMN_MAP = {
    "Lot no.": "lot_number",
    "opno": "opno",
    "op name": "op_name",
    "Production No.": "production_no",
    "Production Version": "production_version",
    "product type": "product_type",
    "Production Name": "production_name",
    "Production spec.": "production_spec",
    "SubOPSequence": "subop_sequence",
    "Subop no": "subop_no",
    "subop name": "subop_name",
    "PositionNo": "position_no",
    "WorkstationName": "workstation_name",
    "PCSNo": "pcs_no",
    "User name": "user_name",
    "CREATEDATE": "created_date",
    "working hours": "working_hours",
    "result": "result",
    "testData": "test_data",
}


class ExcelParseError(Exception):
    """Ошибка парсинга Excel файла."""


REQUIRED_COLUMNS = ["Lot no.", "Subop no", "PCSNo", "CREATEDATE", "result"]


def parse_excel_file(file_path_or_buffer):
    """
    Парсит Excel файл и возвращает список ProductionRecord (unsaved).
    Выбрасывает ExcelParseError при проблемах.
    """
    from production.models import ProductionRecord

    try:
        df = pd.read_excel(
            file_path_or_buffer,
            engine="openpyxl",
            parse_dates=["CREATEDATE"],
        )
    except (ValueError, ImportError):
        df = pd.read_excel(file_path_or_buffer)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ExcelParseError(
            f"В файле отсутствуют обязательные столбцы: {', '.join(missing)}"
        )

    rename_map = {k: v for k, v in EXCEL_COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    df["subop_no"] = pd.to_numeric(df["subop_no"], errors="coerce").fillna(0).astype(int)
    df["created_date"] = pd.to_datetime(df["created_date"], errors="coerce")
    df = df.dropna(subset=["created_date"])
    df["created_date"] = df["created_date"].apply(lambda x: timezone.make_aware(x) if timezone.is_naive(x) else x)

    records = []
    for _, row in df.iterrows():
        rec = ProductionRecord(
            lot_number=row.get("lot_number", "") or "",
            opno=_safe_str(row.get("opno")),
            op_name=_safe_str(row.get("op_name")),
            production_no=_safe_str(row.get("production_no")),
            production_version=_safe_int(row.get("production_version")),
            product_type=_safe_str(row.get("product_type")),
            production_name=_safe_str(row.get("production_name")),
            production_spec=_safe_str(row.get("production_spec")),
            subop_sequence=_safe_int(row.get("subop_sequence")),
            subop_no=int(row["subop_no"]),
            subop_name=_safe_str(row.get("subop_name")),
            position_no=_safe_str(row.get("position_no")),
            workstation_name=_safe_str(row.get("workstation_name")),
            pcs_no=row.get("pcs_no", "") or "",
            user_name=_safe_str(row.get("user_name")),
            created_date=row["created_date"],
            working_hours=_safe_int(row.get("working_hours")),
            result=_safe_str(row.get("result")),
            test_data=_safe_str(row.get("test_data")),
        )
        records.append(rec)

    return records


def _safe_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()


def _safe_int(val):
    if pd.isna(val):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def import_to_database(records, created_by="system"):
    """
    Загружает записи в БД с дедупликацией.
    Возвращает: {total, inserted, duplicates}
    """
    from production.models import ProductionRecord, LotInfo

    total = len(records)
    before_count = ProductionRecord.objects.count()

    from production.models import ProductionRecord, LotInfo

    lots_data = {}

    for rec in records:
        lots_data.setdefault(rec.lot_number, {
            "production_spec": rec.production_spec or "",
        })

    with transaction.atomic():
        for lot_num, lot_data in lots_data.items():
            obj, created = LotInfo.objects.get_or_create(
                lot_number=lot_num,
                defaults={
                    "production_spec": lot_data["production_spec"],
                    "plan_total": None,
                    "comment": "",
                },
            )
            if not created and not obj.production_spec and lot_data["production_spec"]:
                obj.production_spec = lot_data["production_spec"]
                obj.save(update_fields=["production_spec"])

        ProductionRecord.objects.bulk_create(
            records,
            ignore_conflicts=True,
            batch_size=2000,
        )

    after_count = ProductionRecord.objects.count()
    inserted_count = after_count - before_count
    duplicate_count = total - inserted_count

    return {
        "total": total,
        "inserted": inserted_count,
        "duplicates": duplicate_count,
    }
