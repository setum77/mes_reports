"""Перенос данных из плоских таблиц MES в нормализованную схему.

Порядок:
1. Станции: seed + обнаруженные в исторических данных номера.
2. Лоты: LotInfo + лоты из записей производства и ручных браков.
3. БУ: уникальные SN из производства, ручных браков, комментариев и фото.
4. Производство: записи ProductionRecord с FK на БУ и станцию.
5. Фотографии: SNPhoto -> UnitPhoto.
6. Словарь перевода testData.
"""

from django.db import migrations
from django.utils import timezone

from production.stations import DEFAULT_STATIONS
from production.testdata import DEFAULT_TEST_DATA_TRANSLATIONS, translate_test_data


def _batched(items, size=2000):
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def copy_legacy_data(apps, schema_editor):
    OldProduction = apps.get_model("production", "ProductionRecord")
    OldLot = apps.get_model("production", "LotInfo")
    OldDefect = apps.get_model("production", "ManualDefect")
    OldComment = apps.get_model("production", "SNComment")
    OldPhoto = apps.get_model("production", "SNPhoto")

    Station = apps.get_model("production", "Station")
    Lot = apps.get_model("production", "Lot")
    ControlUnit = apps.get_model("production", "ControlUnit")
    Production = apps.get_model("production", "Production")
    UnitPhoto = apps.get_model("production", "UnitPhoto")
    TestDataTranslation = apps.get_model("production", "TestDataTranslation")

    now = timezone.now()

    # 1. Станции.
    for item in DEFAULT_STATIONS:
        Station.objects.update_or_create(
            number=item["number"],
            defaults={
                "position_no": item["position_no"],
                "name_zh": item["name_zh"],
                "name_en": item["name_en"],
                "name_ru": item["name_ru"],
                "sort_order": item["sort_order"],
                "is_active": True,
            },
        )

    stations_by_number = dict(Station.objects.values_list("number", "id"))

    station_rows = (
        OldProduction.objects.values(
            "subop_no", "subop_name", "workstation_name", "position_no"
        ).distinct()
    )
    for row in station_rows.iterator():
        number = row["subop_no"]
        name_zh = row["subop_name"] or row["workstation_name"] or ""
        position_no = row["position_no"] or ""
        name_en = row["workstation_name"] or name_zh
        station = Station.objects.filter(number=number).first()
        if station is None:
            station = Station.objects.create(
                number=number,
                position_no=position_no,
                name_zh=name_zh,
                name_en=name_en,
                name_ru=name_en,
                sort_order=number,
            )
            stations_by_number[number] = station.id
            continue

        changed = False
        if name_zh and station.name_zh != name_zh:
            station.name_zh = name_zh
            changed = True
        if position_no and station.position_no != position_no:
            station.position_no = position_no
            changed = True
        if name_en and station.name_en != name_en:
            station.name_en = name_en
            changed = True
        if changed:
            station.save(update_fields=["name_zh", "position_no", "name_en"])
        stations_by_number[number] = station.id

    # 2. Лоты.
    def ensure_lot(number, spec=""):
        number = (number or "").strip()
        if not number:
            return None
        lot, _ = Lot.objects.get_or_create(
            number=number,
            defaults={"production_spec": spec or ""},
        )
        return lot

    for old_lot in OldLot.objects.all().iterator():
        lot = ensure_lot(old_lot.lot_number, old_lot.production_spec or "")
        if lot is None:
            continue
        Lot.objects.filter(pk=lot.pk).update(
            production_spec=old_lot.production_spec or "",
            total=old_lot.plan_total,
            comment=old_lot.comment or "",
            created_at=old_lot.updated_at,
            updated_at=old_lot.updated_at,
        )

    for number, spec in (
        OldProduction.objects.values_list("lot_number", "production_spec").distinct()
    ):
        ensure_lot(number, spec or "")

    for number, spec in (
        OldDefect.objects.values_list("lot_number", "production_spec").distinct()
    ):
        ensure_lot(number, spec or "")

    # 3. БУ.
    units = {}

    def ensure_unit(sn):
        sn = (sn or "").strip()
        if not sn:
            return None
        return units.setdefault(
            sn,
            {"lot_number": "", "defect": False, "comment": ""},
        )

    for row in OldProduction.objects.values(
        "pcs_no", "lot_number", "defect"
    ).iterator():
        meta = ensure_unit(row["pcs_no"])
        if meta is None:
            continue
        if not meta["lot_number"]:
            meta["lot_number"] = row["lot_number"] or ""
        if row["defect"]:
            meta["defect"] = True

    for row in OldDefect.objects.values("pcs_no", "lot_number").iterator():
        meta = ensure_unit(row["pcs_no"])
        if meta is None:
            continue
        if not meta["lot_number"]:
            meta["lot_number"] = row["lot_number"] or ""
        meta["defect"] = True

    for row in OldComment.objects.values("pcs_no", "comment").iterator():
        meta = ensure_unit(row["pcs_no"])
        if meta is not None:
            meta["comment"] = row["comment"] or ""

    for sn in OldPhoto.objects.values_list("pcs_no", flat=True).distinct():
        ensure_unit(sn)

    unit_ids = {}
    for batch in _batched(units.items()):
        objects = []
        for sn, meta in batch:
            lot = ensure_lot(meta["lot_number"])
            objects.append(
                ControlUnit(
                    sn=sn,
                    lot=lot,
                    defect=meta["defect"],
                    comment=meta["comment"],
                )
            )
        ControlUnit.objects.bulk_create(objects, ignore_conflicts=True, batch_size=2000)
        for sn, unit_id in ControlUnit.objects.filter(
            sn__in=[sn for sn, _ in batch]
        ).values_list("sn", "id"):
            unit_ids[sn] = unit_id

    # 4. Производство.
    production_batch = []
    for row in OldProduction.objects.values(
        "pcs_no", "subop_no", "created_date", "result", "test_data"
    ).iterator():
        unit_id = unit_ids.get(row["pcs_no"])
        station_id = stations_by_number.get(row["subop_no"])
        if not unit_id or not station_id:
            continue
        text = row["test_data"] or ""
        production_batch.append(
            Production(
                unit_id=unit_id,
                station_id=station_id,
                created_date=row["created_date"],
                result=row["result"] or "",
                test_data=text,
                test_data_ru=translate_test_data(text),
            )
        )
        if len(production_batch) >= 2000:
            Production.objects.bulk_create(
                production_batch, ignore_conflicts=True, batch_size=2000
            )
            production_batch = []
    if production_batch:
        Production.objects.bulk_create(
            production_batch, ignore_conflicts=True, batch_size=2000
        )

    # 5. Фотографии.
    photo_batch = []
    for row in OldPhoto.objects.values(
        "pcs_no", "image", "caption", "uploaded_by", "uploaded_at"
    ).iterator():
        unit_id = unit_ids.get(row["pcs_no"])
        if not unit_id:
            continue
        photo_batch.append(
            UnitPhoto(
                unit_id=unit_id,
                image=row["image"],
                caption=row["caption"] or "",
                uploaded_by=row["uploaded_by"] or "",
                uploaded_at=row["uploaded_at"] or now,
            )
        )
        if len(photo_batch) >= 1000:
            UnitPhoto.objects.bulk_create(photo_batch, batch_size=1000)
            photo_batch = []
    if photo_batch:
        UnitPhoto.objects.bulk_create(photo_batch, batch_size=1000)

    # 6. Словарь перевода testData.
    TestDataTranslation.objects.bulk_create(
        [
            TestDataTranslation(source=source, target=target, is_active=True)
            for source, target in DEFAULT_TEST_DATA_TRANSLATIONS
        ],
        ignore_conflicts=True,
        batch_size=1000,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0007_db_rework_create_new_models"),
    ]

    operations = [
        migrations.RunPython(copy_legacy_data, noop),
    ]