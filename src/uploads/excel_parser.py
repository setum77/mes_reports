"""Парсер Excel-выгрузки MES: проверка колонок, нормализация, дедупликация."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from django.utils import timezone

from production.testdata import translate_test_data


REQUIRED_COLUMNS = [
    "Lot no.",
    "Production spec.",
    "Subop no",
    "subop name",
    "PCSNo",
    "CREATEDATE",
    "result",
    "testData",
]

OPTIONAL_COLUMNS = [
    "opno",
    "op name",
    "Production No.",
    "Production Version",
    "product type",
    "Production Name",
    "SubOPSequence",
    "PositionNo",
    "WorkstationName",
    "User name",
    "working hours",
]

COLUMN_MAP = {
    "Lot no.": "lot_number",
    "Production spec.": "production_spec",
    "Subop no": "subop_no",
    "subop name": "subop_name",
    "PCSNo": "pcs_no",
    "CREATEDATE": "created_date",
    "result": "result",
    "testData": "test_data",
    "opno": "opno",
    "op name": "op_name",
    "Production No.": "production_no",
    "Production Version": "production_version",
    "product type": "product_type",
    "Production Name": "production_name",
    "SubOPSequence": "subop_sequence",
    "PositionNo": "position_no",
    "WorkstationName": "workstation_name",
    "User name": "user_name",
    "working hours": "working_hours",
}


def validate_columns(columns):
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise ValueError(f"Отсутствуют обязательные колонки: {missing}")
    return True


def parse_excel_file(file_path: str | Path) -> list[dict]:
    """Разбирает Excel-выгрузку и возвращает список словарей (без сохранения в БД)."""
    df = pd.read_excel(file_path, sheet_name=0)

    df.columns = [str(c).strip() for c in df.columns]
    validate_columns(df.columns)

    df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})
    df = df.dropna(subset=["created_date"])

    for field in [
        "lot_number",
        "production_spec",
        "pcs_no",
        "subop_name",
        "result",
        "test_data",
        "position_no",
        "workstation_name",
    ]:
        if field not in df.columns:
            df[field] = None
        df[field] = df[field].fillna("").astype(str)

    df["subop_no"] = df["subop_no"].fillna(0).astype(int)
    df["created_date"] = pd.to_datetime(df["created_date"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["created_date"])

    def to_aware(value):
        if value is None or pd.isna(value):
            return None
        if timezone.is_naive(value):
            return timezone.make_aware(value)
        return value

    df["created_date"] = df["created_date"].apply(to_aware)

    records = []
    for row in df.to_dict("records"):
        records.append(
            {
                "lot_number": str(row.get("lot_number", "") or "").strip(),
                "production_spec": str(row.get("production_spec", "") or "").strip(),
                "subop_no": int(row.get("subop_no", 0) or 0),
                "subop_name": str(row.get("subop_name", "") or "").strip(),
                "pcs_no": str(row.get("pcs_no", "") or "").strip(),
                "created_date": row.get("created_date"),
                "result": str(row.get("result", "") or "").strip(),
                "test_data": str(row.get("test_data", "") or "").strip(),
                "opno": str(row.get("opno", "") or "").strip(),
                "op_name": str(row.get("op_name", "") or "").strip(),
                "production_no": str(row.get("production_no", "") or "").strip(),
                "production_version": row.get("production_version"),
                "product_type": str(row.get("product_type", "") or "").strip(),
                "production_name": str(row.get("production_name", "") or "").strip(),
                "subop_sequence": row.get("subop_sequence"),
                "position_no": str(row.get("position_no", "") or "").strip(),
                "workstation_name": str(row.get("workstation_name", "") or "").strip(),
                "user_name": str(row.get("user_name", "") or "").strip(),
                "working_hours": row.get("working_hours"),
            }
        )

    return records


def _ensure_lot(Lot, number, production_spec):
    number = (number or "").strip()
    if not number:
        return None
    lot, created = Lot.objects.get_or_create(
        number=number,
        defaults={"production_spec": production_spec or ""},
    )
    if not created and production_spec and not lot.production_spec:
        lot.production_spec = production_spec
        lot.save(update_fields=["production_spec"])
    return lot


def _ensure_station(Station, number, position_no, name_zh):
    number = int(number or 0)
    if number <= 0:
        number = 0
    station, created = Station.objects.get_or_create(
        number=number,
        defaults={
            "position_no": position_no or "",
            "name_zh": name_zh or "",
            "name_en": name_zh or f"Station {number}",
            "name_ru": name_zh or f"Station {number}",
            "sort_order": number,
        },
    )
    update_fields = []
    if not created:
        if position_no and station.position_no != position_no:
            station.position_no = position_no
            update_fields.append("position_no")
        if name_zh and station.name_zh != name_zh:
            station.name_zh = name_zh
            update_fields.append("name_zh")
        if update_fields:
            station.save(update_fields=update_fields)
    return station


def import_to_database(records: list[dict], file_path: str | Path) -> dict:
    from production.models import ControlUnit, Lot, Production, Station

    before_count = Production.objects.count()

    lot_map = {}
    station_map = {}
    unit_map = {}

    for record in records:
        lot = _ensure_lot(
            Lot, record.get("lot_number"), record.get("production_spec")
        )
        if lot:
            lot_map[record.get("lot_number")] = lot

        station = _ensure_station(
            Station,
            record.get("subop_no"),
            record.get("position_no"),
            record.get("subop_name") or record.get("workstation_name"),
        )
        station_map[record.get("subop_no")] = station

        sn = (record.get("pcs_no") or "").strip()
        if not sn:
            continue
        if sn not in unit_map:
            lot = lot_map.get(record.get("lot_number"))
            unit, created = ControlUnit.objects.get_or_create(
                sn=sn,
                defaults={"lot": lot, "defect": False, "comment": ""},
            )
            if not created and unit.lot_id is None and lot is not None:
                unit.lot = lot
                unit.save(update_fields=["lot"])
            unit_map[sn] = unit

    production_objects = []
    for record in records:
        sn = (record.get("pcs_no") or "").strip()
        unit = unit_map.get(sn)
        station = station_map.get(record.get("subop_no"))
        created_date = record.get("created_date")
        if not unit or not station or not created_date:
            continue
        test_data = record.get("test_data") or ""
        production_objects.append(
            Production(
                unit=unit,
                station=station,
                created_date=created_date,
                result=record.get("result") or "",
                test_data=test_data,
                test_data_ru=translate_test_data(test_data),
            )
        )

    Production.objects.bulk_create(
        production_objects,
        ignore_conflicts=True,
        batch_size=2000,
    )

    after_count = Production.objects.count()
    inserted = after_count - before_count

    return {
        "total": len(records),
        "inserted": inserted,
        "duplicates": len(records) - inserted,
        "before_count": before_count,
        "after_count": after_count,
    }