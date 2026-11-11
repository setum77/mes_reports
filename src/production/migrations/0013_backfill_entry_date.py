from django.db import migrations


def backfill_entry_date(apps, schema_editor):
    ControlUnit = apps.get_model("production", "ControlUnit")
    Production = apps.get_model("production", "Production")
    units = ControlUnit.objects.filter(entry_date__isnull=True)
    for unit in units.iterator():
        first = (
            Production.objects.filter(unit=unit)
            .order_by("created_date")
            .values_list("created_date", flat=True)
            .first()
        )
        if first:
            ControlUnit.objects.filter(pk=unit.pk).update(entry_date=first)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0012_controlunit_entry_date"),
    ]

    operations = [
        migrations.RunPython(backfill_entry_date, noop),
    ]