from datetime import datetime

import pytest
from django.utils import timezone

from production.models import ControlUnit, FaultJournal, Lot, Station
from production.stations import DEFAULT_STATIONS
from production.testdata import translate_test_data


@pytest.mark.django_db
def test_station_seed_has_twelve_stations():
    for item in DEFAULT_STATIONS:
        station = Station.objects.get(number=item["number"])
        assert station.name_en == item["name_en"]
        assert station.name_ru == item["name_ru"]


@pytest.mark.django_db
def test_control_unit_entry_date_prefers_manual_value():
    lot = Lot.objects.create(number="LOT-DOMAIN")
    manual = timezone.make_aware(datetime(2026, 1, 2, 8, 0))
    unit = ControlUnit.objects.create(
        sn="SN-DOMAIN", lot=lot, entry_date=manual, defect=True
    )
    assert unit.resolved_entry_date == manual


def test_translate_test_data_uses_dictionary():
    assert translate_test_data("刷写成功") == "Прошивка успешна"
    assert translate_test_data("unknown") == "unknown"


@pytest.mark.django_db
def test_fault_journal_duration():
    station = Station.objects.create(number=999, name_en="Test")
    detected = timezone.make_aware(datetime(2026, 1, 1, 8, 0))
    resolved = timezone.make_aware(datetime(2026, 1, 1, 10, 30))
    journal = FaultJournal.objects.create(
        date=detected.date(),
        detected_at=detected,
        station=station,
        equipment="TEST",
        description="test",
        resolved_at=resolved,
        status=FaultJournal.STATUS_RESOLVED,
    )
    assert journal.duration.total_seconds() == 2.5 * 3600