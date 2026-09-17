from django.db import models
from django.utils import timezone


class ProductionRecord(models.Model):
    """
    Сырой запись из выгрузки MES системы.
    Каждая запись = одно прохождение станции БУ.
    """
    lot_number = models.CharField("Номер лота", max_length=50, db_index=True)
    opno = models.CharField("opno", max_length=50, blank=True, null=True)
    op_name = models.CharField("Название операции", max_length=200, blank=True, null=True)
    production_no = models.CharField("Номер производства", max_length=100, blank=True, null=True)
    production_version = models.IntegerField("Версия производства", blank=True, null=True)
    product_type = models.CharField("Тип продукта", max_length=100, blank=True, null=True)
    production_name = models.CharField("Название производства", max_length=200, blank=True, null=True)
    production_spec = models.CharField("Спецификация", max_length=200, blank=True, null=True)
    subop_sequence = models.IntegerField("Порядковый номер субоперации", blank=True, null=True)
    subop_no = models.IntegerField("Номер станции", db_index=True)
    subop_name = models.CharField("Название станции", max_length=200, blank=True, null=True)
    position_no = models.CharField("Номер позиции", max_length=50, blank=True, null=True)
    workstation_name = models.CharField("Имя станции", max_length=200, blank=True, null=True)
    pcs_no = models.CharField("Серийный номер БУ", max_length=100, db_index=True)
    user_name = models.CharField("Имя пользователя", max_length=100, blank=True, null=True)
    created_date = models.DateTimeField("Дата и время прохождения", db_index=True)
    working_hours = models.IntegerField("Рабочие часы", blank=True, null=True)
    result = models.CharField("Результат", max_length=20, blank=True, null=True)
    test_data = models.TextField("Тестовые данные", blank=True, null=True)

    class Meta:
        verbose_name = "Запись производства"
        verbose_name_plural = "Записи производства"
        unique_together = ("pcs_no", "subop_no", "created_date")
        ordering = ["created_date"]
        indexes = [
            models.Index(fields=["pcs_no", "subop_no"]),
        ]

    def __str__(self):
        return f"{self.pcs_no} | станция {self.subop_no} | {self.created_date}"


class LotInfo(models.Model):
    """
    Метаданные лота с редактируемыми полями (Total, comment — для отчета 1).
    """
    lot_number = models.CharField("Номер лота", max_length=50, unique=True)
    production_spec = models.CharField("Спецификация", max_length=200, blank=True, null=True)
    plan_total = models.PositiveIntegerField("Плановое количество (Total)", null=True, blank=True)
    comment = models.TextField("Комментарий", blank=True, default="")
    updated_at = models.DateTimeField("Дата изменения", auto_now=True)

    class Meta:
        verbose_name = "Информация о лоте"
        verbose_name_plural = "Информация о лотах"
        ordering = ["-lot_number"]

    def __str__(self):
        return self.lot_number


class ManualDefect(models.Model):
    """
    Ручные записи о браке (для отчета 4).
    Созданы администратором и сохраняются навсегда.
    """
    pcs_no = models.CharField("Серийный номер БУ", max_length=100)
    production_spec = models.CharField("Спецификация", max_length=200, blank=True, null=True)
    lot_number = models.CharField("Номер лота", max_length=50, blank=True, null=True)
    entry_date = models.DateTimeField("Дата поступления в производство", blank=True, null=True)
    reason = models.TextField("Причина брака", blank=True)
    comment = models.TextField("Комментарий", blank=True, default="")
    created_by = models.CharField("Кто добавил", max_length=100, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Ручной брак"
        verbose_name_plural = "Ручные браки"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.pcs_no} (брак)"


class SNComment(models.Model):
    pcs_no = models.CharField("Серийный номер БУ", max_length=100, unique=True)
    comment = models.TextField("Комментарий", blank=True, default="")
    created_by = models.CharField("Кто добавил", max_length=100, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Комментарий SN"
        verbose_name_plural = "Комментарии SN"
        ordering = ["-updated_at"]

    def __str__(self):
        return self.pcs_no


class Report5Comment(models.Model):
    """
    Комментарии для отчета 5 (повторные проходы станций).
    """
    pcs_no = models.CharField("Серийный номер БУ", max_length=100)
    station_no = models.IntegerField("Номер станции")
    lot_number = models.CharField("Номер лота", max_length=50, blank=True, null=True)
    comment = models.TextField("Комментарий", blank=True, default="")
    created_by = models.CharField("Кто добавил", max_length=100, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Комментарий отчета 5"
        verbose_name_plural = "Комментарии отчета 5"
        ordering = ["-created_at"]
        unique_together = ("pcs_no", "station_no")

    def __str__(self):
        return f"{self.pcs_no} | станция {self.station_no}"
