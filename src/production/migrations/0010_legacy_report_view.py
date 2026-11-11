"""Read-only compatibility view for legacy report SQL.

The application schema is normalized (Production/Station/ControlUnit), but the
existing report queries still reference the historical flat table.  This view
keeps those queries working while they are migrated to the new model.  It is
not a Django model and is safe to drop once report SQL is rewritten.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0009_db_rework_remove_legacy_models"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE VIEW production_productionrecord AS
            SELECT
                p.id,
                COALESCE(l.number, '') AS lot_number,
                p.created_date,
                p.result,
                p.test_data,
                u.defect,
                u.sn AS pcs_no,
                s.number AS subop_no,
                s.name_zh AS subop_name,
                s.position_no,
                s.name_zh AS workstation_name,
                COALESCE(l.production_spec, '') AS production_spec
            FROM production_production p
            JOIN production_controlunit u ON u.id = p.unit_id
            JOIN production_station s ON s.id = p.station_id
            LEFT JOIN production_lot l ON l.id = u.lot_id
            """,
            reverse_sql="DROP VIEW IF EXISTS production_productionrecord",
        ),
    ]