from django.db import models
from django.utils import timezone


class ControlUnit(models.Model):
    """Блок управления (БУ). Может существовать без записей производства."""

    sn = models.CharField("Серийный номер БУ", max_length=100, unique=True)
    lot = models.ForeignKey(
        "Lot",
        verbose_name="Лот",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="units",
    )
    comment = models.TextField("Комментарий", blank=True, default="")
    defect = models.BooleanField("Брак (defect)", default=False)
    entry_date = models.DateTimeField(
        "Дата поступления в производство", null=True, blank=True
    )
    created_by = models.CharField("Кто добавил", max_length=100, blank=True, default="")
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Блок управления (БУ)"
        verbose_name_plural = "Блоки управления (БУ)"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.sn

    @property
    def pcs_no(self):
        return self.sn

    @property
    def lot_number(self):
        return self.lot.number if self.lot else ""

    @property
    def production_spec(self):
        return self.lot.production_spec if self.lot else ""

    @property
    def resolved_entry_date(self):
        if self.entry_date:
            return self.entry_date
        first = self.production_records.order_by("created_date").first()
        return first.created_date if first else self.created_at


class Lot(models.Model):
    """Лот производства."""

    number = models.CharField("Лот", max_length=50, unique=True)
    production_spec = models.CharField(
        "Спецификация (Production spec.)", max_length=200, blank=True, default=""
    )
    total = models.PositiveIntegerField(
        "Заявленное количество (total)", blank=True, null=True
    )
    comment = models.TextField("Комментарий", blank=True, default="")
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Лот"
        verbose_name_plural = "Лоты"
        ordering = ["-number"]

    def __str__(self):
        return self.number


class Station(models.Model):
    """Станция производства: номер, PositionNo и названия на трёх языках."""

    number = models.IntegerField("Номер станции (Subop no)", unique=True)
    position_no = models.CharField("PositionNo", max_length=20, blank=True, default="")
    name_zh = models.CharField(
        "Название (китайский)", max_length=200, blank=True, default=""
    )
    name_en = models.CharField(
        "Название (английский)", max_length=200, blank=True, default=""
    )
    name_ru = models.CharField(
        "Название (русский)", max_length=200, blank=True, default=""
    )
    sort_order = models.PositiveIntegerField("Порядок на линии", default=0)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Станция производства"
        verbose_name_plural = "Станции производства"
        ordering = ["sort_order", "number"]

    def __str__(self):
        return f"{self.number:03d} {self.name_en or self.name_ru or self.name_zh}"


class TestDataTranslation(models.Model):
    """Правило перевода фрагмента testData с китайского на русский."""

    source = models.CharField("Китайский фрагмент", max_length=255, unique=True)
    target = models.CharField("Русский перевод", max_length=300)
    is_active = models.BooleanField("Активен", default=True)
    comment = models.CharField("Примечание", max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Перевод testData"
        verbose_name_plural = "Переводы testData"
        ordering = ["source"]

    def __str__(self):
        return f"{self.source} → {self.target}"


class FaultJournal(models.Model):
    """Запись журнала неисправностей."""

    STATUS_RESOLVED = "resolved"
    STATUS_UNRESOLVED = "unresolved"
    STATUS_PARTIAL = "partial"
    STATUS_CHOICES = [
        (STATUS_RESOLVED, "Проблема решена"),
        (STATUS_UNRESOLVED, "Проблема не решена"),
        (STATUS_PARTIAL, "Проблема решена частично"),
    ]

    date = models.DateField("Дата")
    detected_at = models.DateTimeField("Время обнаружения", null=True, blank=True)
    equipment = models.CharField("Оборудование", max_length=200)
    description = models.TextField("Описание неисправности")
    cause = models.TextField("Причина", blank=True, default="")
    actions_taken = models.TextField("Принятые меры", blank=True, default="")
    resolved_at = models.DateTimeField("Время устранения", null=True, blank=True)
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_UNRESOLVED,
    )
    note = models.TextField("Примечание", blank=True, default="")
    unit = models.ForeignKey(
        ControlUnit,
        verbose_name="БУ",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="faults",
    )
    lot = models.ForeignKey(
        Lot,
        verbose_name="Лот",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="faults",
    )
    station = models.ForeignKey(
        Station,
        verbose_name="Станция",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="faults",
    )
    created_by = models.CharField("Кто создал", max_length=100, blank=True, default="")
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Запись журнала неисправностей"
        verbose_name_plural = "Журнал неисправностей"
        ordering = ["-date", "-detected_at", "-created_at"]

    def __str__(self):
        return f"{self.date} — {self.equipment} — {self.status}"

    @property
    def duration(self):
        if not self.resolved_at or not self.detected_at:
            return None
        return self.resolved_at - self.detected_at


class FaultAttachment(models.Model):
    """Фото/видео, приложенное к записи журнала неисправностей."""

    KIND_PHOTO = "photo"
    KIND_VIDEO = "video"
    KIND_CHOICES = [
        (KIND_PHOTO, "Фотография"),
        (KIND_VIDEO, "Видео"),
    ]

    journal = models.ForeignKey(
        FaultJournal,
        verbose_name="Запись журнала",
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField("Файл", upload_to="fault_attachments/%Y/%m/%d/")
    kind = models.CharField(
        "Тип", max_length=10, choices=KIND_CHOICES, default=KIND_PHOTO
    )
    caption = models.CharField("Подпись", max_length=255, blank=True, default="")
    uploaded_by = models.CharField("Кто загрузил", max_length=100, blank=True, default="")
    uploaded_at = models.DateTimeField("Загружено", auto_now_add=True)

    class Meta:
        verbose_name = "Вложение журнала"
        verbose_name_plural = "Вложения журнала"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.caption or self.file.name


class UnitPhoto(models.Model):
    """Фотография, привязанная к БУ."""

    unit = models.ForeignKey(
        ControlUnit,
        verbose_name="БУ",
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.FileField("Фотография", upload_to="sn_photos/%Y/%m/%d/")
    caption = models.CharField("Подпись / имя", max_length=255, blank=True, default="")
    uploaded_by = models.CharField("Кто загрузил", max_length=100, blank=True, default="")
    uploaded_at = models.DateTimeField("Загружено", auto_now_add=True)

    class Meta:
        verbose_name = "Фотография БУ"
        verbose_name_plural = "Фотографии БУ"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.caption or self.image.name

    @property
    def pcs_no(self):
        return self.unit.sn


class Production(models.Model):
    """Прохождение блоком БУ станции производства."""

    unit = models.ForeignKey(
        ControlUnit,
        verbose_name="БУ",
        on_delete=models.CASCADE,
        related_name="production_records",
    )
    station = models.ForeignKey(
        Station,
        verbose_name="Станция",
        on_delete=models.PROTECT,
        related_name="productions",
    )
    created_date = models.DateTimeField(
        "Дата и время прохождения (CREATEDATE)", db_index=True
    )
    result = models.CharField("Результат (result)", max_length=20)
    test_data = models.TextField("Тестовые данные (testData)", blank=True, default="")
    test_data_ru = models.TextField("Тестовые данные (рус.)", blank=True, default="")

    class Meta:
        verbose_name = "Прохождение станции"
        verbose_name_plural = "Прохождения станций"
        ordering = ["created_date"]
        indexes = [
            models.Index(fields=["unit", "created_date"], name="production__unit_id_328638_idx"),
            models.Index(fields=["station", "created_date"], name="production__station_414dd7_idx"),
        ]
        unique_together = ("unit", "station", "created_date")

    def __str__(self):
        return f"{self.unit_id} | {self.station_id} | {self.created_date}"