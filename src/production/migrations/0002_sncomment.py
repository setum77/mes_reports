from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("production", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SNComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("pcs_no", models.CharField(max_length=100, unique=True, verbose_name="Серийный номер БУ")),
                ("comment", models.TextField(blank=True, default="", verbose_name="Комментарий")),
                ("created_by", models.CharField(blank=True, max_length=100, verbose_name="Кто добавил")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменено")),
            ],
            options={
                "verbose_name": "Комментарий SN",
                "verbose_name_plural": "Комментарии SN",
                "ordering": ["-updated_at"],
            },
        ),
    ]
