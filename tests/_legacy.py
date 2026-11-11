"""Test-only compatibility shims for the legacy flat model names.

The production schema is normalized (ControlUnit/Station/Production), but the
large report test-suite still creates rows through the old names.  These
classes translate the old keyword arguments to the new models without changing
production code.
"""

from production.models import ControlUnit, Lot, Production, Station, UnitPhoto


def _station(number):
    number = int(number or 0)
    station, _ = Station.objects.get_or_create(
        number=number,
        defaults={
            "position_no": str(number),
            "name_zh": f"Station {number}",
            "name_en": f"Station {number}",
            "name_ru": f"Station {number}",
            "sort_order": number,
        },
    )
    return station


def _lot(number, production_spec=""):
    number = (number or "").strip()
    if not number:
        return None
    lot, _ = Lot.objects.get_or_create(
        number=number,
        defaults={"production_spec": production_spec or ""},
    )
    if production_spec and not lot.production_spec:
        lot.production_spec = production_spec
        lot.save(update_fields=["production_spec"])
    return lot


def _unit(
    sn,
    lot_number="",
    production_spec="",
    defect=False,
    comment="",
    created_by="",
    entry_date=None,
):
    sn = (sn or "").strip()
    if not sn:
        return None
    lot = _lot(lot_number, production_spec)
    unit, created = ControlUnit.objects.get_or_create(
        sn=sn,
        defaults={
            "lot": lot,
            "defect": defect,
            "comment": comment or "",
            "created_by": created_by or "",
            "entry_date": entry_date,
        },
    )
    if created:
        return unit
    update_fields = []
    if unit.lot_id is None and lot is not None:
        unit.lot = lot
        update_fields.append("lot")
    if defect and not unit.defect:
        unit.defect = True
        update_fields.append("defect")
    if comment and not unit.comment:
        unit.comment = comment
        update_fields.append("comment")
    if created_by and not unit.created_by:
        unit.created_by = created_by
        update_fields.append("created_by")
    if entry_date and not unit.entry_date:
        unit.entry_date = entry_date
        update_fields.append("entry_date")
    if update_fields:
        unit.save(update_fields=update_fields)
    return unit


def _production_filter(**kwargs):
    mapped = {}
    for key, value in kwargs.items():
        if key == "pcs_no":
            mapped["unit__sn"] = value
        elif key == "pcs_no__in":
            mapped["unit__sn__in"] = value
        elif key == "defect":
            mapped["unit__defect"] = value
        elif key == "subop_no":
            mapped["station__number"] = value
        elif key == "subop_no__in":
            mapped["station__number__in"] = value
        elif key == "lot_number":
            mapped["unit__lot__number"] = value
        elif key == "lot_number__icontains":
            mapped["unit__lot__number__icontains"] = value
        else:
            mapped[key] = value
    return Production.objects.filter(**mapped)


class ProductionRecord:
    def __init__(self, **kwargs):
        self.id = None
        self.lot_number = kwargs.get("lot_number", "")
        self.production_spec = kwargs.get("production_spec", "")
        self.subop_no = kwargs.get("subop_no")
        self.pcs_no = kwargs.get("pcs_no", "")
        self.created_date = kwargs.get("created_date")
        self.result = kwargs.get("result", "")
        self.test_data = kwargs.get("test_data", "")
        self.defect = kwargs.get("defect", False)
        self.workstation_name = kwargs.get("workstation_name", "")
        self.position_no = kwargs.get("position_no", "")
        self.subop_name = kwargs.get("subop_name", "")

    class objects:
        @staticmethod
        def create(**kwargs):
            obj = ProductionRecord(**kwargs)
            unit = _unit(
                obj.pcs_no,
                obj.lot_number,
                obj.production_spec,
                defect=obj.defect,
            )
            station = _station(obj.subop_no)
            production = Production.objects.create(
                unit=unit,
                station=station,
                created_date=obj.created_date,
                result=obj.result or "",
                test_data=obj.test_data or "",
                test_data_ru=obj.test_data or "",
            )
            obj.id = production.id
            return obj

        @staticmethod
        def bulk_create(items, **kwargs):
            for item in items:
                ProductionRecord.objects.create(**item.__dict__)

        @staticmethod
        def filter(**kwargs):
            return _production_filter(**kwargs)

        @staticmethod
        def get(**kwargs):
            return _production_filter(**kwargs).get()

        @staticmethod
        def count():
            return Production.objects.count()


class LotInfo:
    class objects:
        @staticmethod
        def create(**kwargs):
            number = kwargs.pop("lot_number", kwargs.pop("number", ""))
            total = kwargs.pop("plan_total", kwargs.pop("total", None))
            return Lot.objects.create(number=number, total=total, **kwargs)

        @staticmethod
        def get(**kwargs):
            if "lot_number" in kwargs:
                kwargs["number"] = kwargs.pop("lot_number")
            if "plan_total" in kwargs:
                kwargs["total"] = kwargs.pop("plan_total")
            return Lot.objects.get(**kwargs)


class ManualDefect:
    def __init__(self, **kwargs):
        self.pcs_no = kwargs.get("pcs_no", "")
        self.lot_number = kwargs.get("lot_number", "")
        self.production_spec = kwargs.get("production_spec", "")
        self.entry_date = kwargs.get("entry_date")
        self.created_by = kwargs.get("created_by", "")
        self.created_at = kwargs.get("created_at")

    class objects:
        @staticmethod
        def create(**kwargs):
            return _unit(
                kwargs.get("pcs_no"),
                kwargs.get("lot_number", ""),
                kwargs.get("production_spec", ""),
                defect=True,
                created_by=kwargs.get("created_by", ""),
                entry_date=kwargs.get("entry_date"),
            )

        @staticmethod
        def bulk_create(items, **kwargs):
            for item in items:
                _unit(
                    item.pcs_no,
                    item.lot_number,
                    item.production_spec,
                    defect=True,
                    created_by=item.created_by,
                    entry_date=item.entry_date,
                )

        @staticmethod
        def filter(**kwargs):
            mapped = {}
            for key, value in kwargs.items():
                if key == "pcs_no":
                    mapped["sn"] = value
                elif key == "pcs_no__in":
                    mapped["sn__in"] = value
                elif key == "lot_number":
                    mapped["lot__number"] = value
                elif key == "lot_number__icontains":
                    mapped["lot__number__icontains"] = value
                else:
                    mapped[key] = value
            return ControlUnit.objects.filter(**mapped)

        @staticmethod
        def get(**kwargs):
            return ManualDefect.objects.filter(**kwargs).get()


class SNComment:
    def __init__(self, **kwargs):
        self.pcs_no = kwargs.get("pcs_no", "")
        self.comment = kwargs.get("comment", "")
        self.created_by = kwargs.get("created_by", "")

    class objects:
        @staticmethod
        def create(**kwargs):
            return _unit(
                kwargs.get("pcs_no"),
                comment=kwargs.get("comment", ""),
                created_by=kwargs.get("created_by", ""),
            )

        @staticmethod
        def filter(**kwargs):
            mapped = {}
            for key, value in kwargs.items():
                if key == "pcs_no":
                    mapped["sn"] = value
                elif key == "pcs_no__in":
                    mapped["sn__in"] = value
                else:
                    mapped[key] = value
            return ControlUnit.objects.filter(**mapped)

        @staticmethod
        def get(**kwargs):
            return SNComment.objects.filter(**kwargs).get()


class SNPhoto:
    def __init__(self, **kwargs):
        self.pcs_no = kwargs.get("pcs_no", "")
        self.caption = kwargs.get("caption", "")
        self.uploaded_by = kwargs.get("uploaded_by", "")

    class objects:
        @staticmethod
        def create(**kwargs):
            unit = _unit(kwargs.get("pcs_no"))
            return UnitPhoto.objects.create(
                unit=unit,
                image=kwargs.get("image"),
                caption=kwargs.get("caption", ""),
                uploaded_by=kwargs.get("uploaded_by", ""),
            )

        @staticmethod
        def filter(**kwargs):
            mapped = {}
            for key, value in kwargs.items():
                if key == "pcs_no":
                    mapped["unit__sn"] = value
                elif key == "pcs_no__in":
                    mapped["unit__sn__in"] = value
                else:
                    mapped[key] = value
            return UnitPhoto.objects.filter(**mapped)

        @staticmethod
        def get(**kwargs):
            return SNPhoto.objects.filter(**kwargs).get()