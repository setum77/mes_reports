import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0006_delete_report5comment"),
    ]

    operations = [
        migrations.CreateModel(
            name="ControlUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sn", models.CharField(max_length=100, unique=True, verbose_name="Серийный номер БУ")),
                ("comment", models.TextField(blank=True, default="", verbose_name="Комментарий")),
                ("defect", models.BooleanField(default=False, verbose_name="Брак (defect)")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменено")),
            ],
            options={
                "verbose_name": "Блок управления (БУ)",
                "verbose_name_plural": "Блоки управления (БУ)",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="Lot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=50, unique=True, verbose_name="Лот")),
                ("production_spec", models.CharField(blank=True, default="", max_length=200, verbose_name="Спецификация (Production spec.)")),
                ("total", models.PositiveIntegerField(blank=True, null=True, verbose_name="Заявленное количество (total)")),
                ("comment", models.TextField(blank=True, default="", verbose_name="Комментарий")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменено")),
            ],
            options={
                "verbose_name": "Лот",
                "verbose_name_plural": "Лоты",
                "ordering": ["-number"],
            },
        ),
        migrations.CreateModel(
            name="Station",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.IntegerField(unique=True, verbose_name="Номер станции (Subop no)")),
                ("position_no", models.CharField(blank=True, default="", max_length=20, verbose_name="PositionNo")),
                ("name_zh", models.CharField(blank=True, default="", max_length=200, verbose_name="Название (китайский)")),
                ("name_en", models.CharField(blank=True, default="", max_length=200, verbose_name="Название (английский)")),
                ("name_ru", models.CharField(blank=True, default="", max_length=200, verbose_name="Название (русский)")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Порядок на линии")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активна")),
            ],
            options={
                "verbose_name": "Станция производства",
                "verbose_name_plural": "Станции производства",
                "ordering": ["sort_order", "number"],
            },
        ),
        migrations.CreateModel(
            name="TestDataTranslation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(max_length=255, unique=True, verbose_name="Китайский фрагмент")),
                ("target", models.CharField(max_length=300, verbose_name="Русский перевод")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                ("comment", models.CharField(blank=True, default="", max_length=255, verbose_name="Примечание")),
            ],
            options={
                "verbose_name": "Перевод testData",
                "verbose_name_plural": "Переводы testData",
                "ordering": ["source"],
            },
        ),
        migrations.CreateModel(
            name="FaultJournal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(verbose_name="Дата")),
                ("detected_at", models.DateTimeField(blank=True, null=True, verbose_name="Время обнаружения")),
                ("equipment", models.CharField(max_length=200, verbose_name="Оборудование")),
                ("description", models.TextField(verbose_name="Описание неисправности")),
                ("cause", models.TextField(blank=True, default="", verbose_name="Причина")),
                ("actions_taken", models.TextField(blank=True, default="", verbose_name="Принятые меры")),
                ("resolved_at", models.DateTimeField(blank=True, null=True, verbose_name="Время устранения")),
                ("status", models.CharField(choices=[("resolved", "Проблема решена"), ("unresolved", "Проблема не решена"), ("partial", "Проблема решена частично")], default="unresolved", max_length=20, verbose_name="Статус")),
                ("note", models.TextField(blank=True, default="", verbose_name="Примечание")),
                ("created_by", models.CharField(blank=True, default="", max_length=100, verbose_name="Кто создал")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Изменено")),
                ("lot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="faults", to="production.lot", verbose_name="Лот")),
                ("station", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="faults", to="production.station", verbose_name="Станция")),
                ("unit", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="faults", to="production.controlunit", verbose_name="БУ")),
            ],
            options={
                "verbose_name": "Запись журнала неисправностей",
                "verbose_name_plural": "Журнал неисправностей",
                "ordering": ["-date", "-detected_at", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FaultAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to="fault_attachments/%Y/%m/%d/", verbose_name="Файл")),
                ("kind", models.CharField(choices=[("photo", "Фотография"), ("video", "Видео")], default="photo", max_length=10, verbose_name="Тип")),
                ("caption", models.CharField(blank=True, default="", max_length=255, verbose_name="Подпись")),
                ("uploaded_by", models.CharField(blank=True, default="", max_length=100, verbose_name="Кто загрузил")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True, verbose_name="Загружено")),
                ("journal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="production.faultjournal", verbose_name="Запись журнала")),
            ],
            options={
                "verbose_name": "Вложение журнала",
                "verbose_name_plural": "Вложения журнала",
                "ordering": ["-uploaded_at"],
            },
        ),
        migrations.AddField(
            model_name="controlunit",
            name="lot",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="units", to="production.lot", verbose_name="Лот"),
        ),
        migrations.CreateModel(
            name="UnitPhoto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.FileField(upload_to="sn_photos/%Y/%m/%d/", verbose_name="Фотография")),
                ("caption", models.CharField(blank=True, default="", max_length=255, verbose_name="Подпись / имя")),
                ("uploaded_by", models.CharField(blank=True, default="", max_length=100, verbose_name="Кто загрузил")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True, verbose_name="Загружено")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="photos", to="production.controlunit", verbose_name="БУ")),
            ],
            options={
                "verbose_name": "Фотография БУ",
                "verbose_name_plural": "Фотографии БУ",
                "ordering": ["-uploaded_at"],
            },
        ),
        migrations.CreateModel(
            name="Production",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_date", models.DateTimeField(db_index=True, verbose_name="Дата и время прохождения (CREATEDATE)")),
                ("result", models.CharField(max_length=20, verbose_name="Результат (result)")),
                ("test_data", models.TextField(blank=True, default="", verbose_name="Тестовые данные (testData)")),
                ("test_data_ru", models.TextField(blank=True, default="", verbose_name="Тестовые данные (рус.)")),
                ("station", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="productions", to="production.station", verbose_name="Станция")),
                ("unit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_records", to="production.controlunit", verbose_name="БУ")),
            ],
            options={
                "verbose_name": "Прохождение станции",
                "verbose_name_plural": "Прохождения станций",
                "ordering": ["created_date"],
                "indexes": [
                    models.Index(fields=["unit", "created_date"], name="production__unit_id_328638_idx"),
                    models.Index(fields=["station", "created_date"], name="production__station_414dd7_idx"),
                ],
                "unique_together": {("unit", "station", "created_date")},
            },
        ),
    ]