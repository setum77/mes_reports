from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0008_db_rework_copy_data"),
    ]

    operations = [
        migrations.DeleteModel(name="LotInfo"),
        migrations.DeleteModel(name="ManualDefect"),
        migrations.DeleteModel(name="ProductionRecord"),
        migrations.DeleteModel(name="SNComment"),
        migrations.DeleteModel(name="SNPhoto"),
    ]