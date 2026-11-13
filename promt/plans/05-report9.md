# 05. Отчёт №9 «Журнал неисправностей»

Дата: 2026-11-13
Основание: `promt/promt_mes_reports/09. Журнал неисправностей.md`,
`promt/promt_mes_reports/Описание данных (свойства).md` (раздел «Журнал неисправностей»)
Статус: **согласовано, не начато**

---

## 1. Цель и границы

Реализовать отчёт №9 `/reports/9/` — журнал неисправностей (модель `FaultJournal`
уже существует и заведена в админке, UI отчёта нет).

В объёме:

- страница списка с фильтрами, сортировкой по всем колонкам, поиском;
- разворот строки с полным описанием (без перезагрузки) и отдельная страница
  правки/создания записи;
- загрузка, просмотр, переименование и удаление фотографий/видео на базе общего
  компонента;
- Excel-экспорт **всей таблицы** (без учёта фильтров);
- перевод существующих обработчиков фото (отчёты №4 и №6) на общий компонент;
- тесты.

Не входит:

- импорт журнала из Excel (по ТЗ — «лучше реализовать в архивировании в админке»);
- отображение журнала в отчёте №6 «По SN» (возможное расширение, см. §9);
- изменения логики отчётов №1–№8, кроме перевода фото на общий компонент;
- новые зависимости, миграции (кроме одной, см. §4);
- изменение прав доступа к существующим отчётам.

---

## 2. Согласованные решения

| # | Вопрос | Решение |
|---|---|---|
| 1 | Раскрытие полного описания | Клик/кнопка в строке разворачивает `<tr>` с полным описанием, причиной, мерами, примечанием и галереей фото. Правка — на отдельной странице (форма). |
| 2 | Доступ | Только `staff` (просмотр и правка). Аноним получает 302 на вход. |
| 3 | Единый механизм фото | Новый модуль `src/gallery/`: общие form/upload/rename/delete-view, AJAX JSON и partial для галереи. Отчёты №4 и №6 переводятся на него (шаблон `shared/_photo_viewer_js.html` и `shared/photo_viewer.html` остаются общими). |
| 4 | Связь с Лотом/SN | Структурные поля `FaultJournal.unit` (SN) и `FaultJournal.lot` с автодополнением (выпадающий список с клиентским фильтром). В таблице и полном описании — ссылки на отчёт №6 (SN) и отчёт №1 (лот). Автоссылки по тексту не делаем. |
| 5 | Модель БД | `FaultJournal` расширяется полем `equipment_std` (оборудование из справочника станций) и индексами по `date`, `status`, `station`. Одна миграция `0014`. `FaultAttachment` без изменений. |
| 6 | Фильтры | Типы: `month` (по умолчанию, текущий месяц), `period`, `station`, `all`. Фильтр по станции — отдельный select. Фильтр по оборудованию — select из справочника `Station` (по `equipment_std`). Поиск — `q` по оборудованию, описанию, причине, мерам, примечанию, SN, номеру лота. |
| 7 | Экспорт | `GET /reports/9/export/?<текущие фильтры>` — выгружаются все колонки **отфильтрованной** выборки (период/станция/статус/поиск), без лимита строк. Лист «Сводка» не добавляем. Импорт не реализуется. |
| 8 | Навигация | Кнопка «Журнал» в `base.html` (видна только `staff`) и карточка в `home.html`, `report_list.html`. |
| 9 | Кэш | `Cache-Control: no-store` для HTML страницы №9 (журнал изменяемый, как №4/№6/№8). Excel-экспорт без `no-store` (как у №1). |
| 10 | Форма (важно) | `equipment` — **необязательное** поле с автокомплитом (накопительный список ранее введённых значений + подсказки из справочника `Station`); `equipment_std` — только для фильтра/сортировки, в форме не показывается. `status` — обязательное. Видео не поддерживается (поле `kind` оставляем как есть, UI только фото). |

---

## 3. Текущее состояние и проблемы

| Где | Проблема |
|---|---|
| `src/production/models.py:120` | `FaultJournal` без `equipment_std`, индексов по `date/status/station`. |
| `src/reports/views.py:957–1022` | `SNPhotoUploadView`, `SNPhotoRenameView`, `SNPhotoDeleteView` — синхронные POST, возвращают redirect; нет JSON. Жёстко привязаны к `ControlUnit` и `UnitPhoto`. |
| `src/reports/urls.py:28–30` | URL-ы фото (`sn/<pcs_no>/photo/...`, `photo/<pk>/...`) точечные, не переиспользуемые для `FaultAttachment`. |
| `src/templates/reports/report6.html:146–184, 228–257` | Галерея SN: список превью + модалка загрузки + inline-JS `promptRename`. Дублируется в `report4.html:88–171, 218–249`. |
| `src/templates/shared/_photo_viewer_js.html` | `PhotoViewer`takes `photos: [{url, caption, filename}]` — переиспользуемо как есть. |
| `src/backup/utils.py:43` | `PRODUCTION_MODELS` уже содержит `FaultAttachment`, `FaultJournal` — новых моделей нет, бэкап менять не нужно. |
| `src/production/admin.py` | `FaultJournalAdmin` уже настроен; после добавления полей дополнить `fieldsets`, `list_display`, `list_filter`, `autocomplete_fields`. |
| `src/reports/queries.py` | Данных журнала нет; запрос нужен новый (`report9_faults`), без raw SQL для фильтрации по ORM-связям — достаточно ORM. |

---

## 4. Модель данных

`src/production/models.py` → `FaultJournal`:

```python
equipment_std = models.CharField(
    "Оборудование (станция)", max_length=200, blank=True, default=""
)
```

- `equipment_std` заполняется из `Station.__str__` (например, `020 FCT1`) при выборе
  станции в форме; остаётся свободным текстом, если оборудование не из справочника.
  Это отдельное поле, т.к. существующее `equipment` — свободный текст
  (обязательное, заполняется в админке), и переиспользовать его под справочник нельзя.
- Индексы: `models.Index(fields=["date"])`,
  `models.Index(fields=["status"])`, `models.Index(fields=["station"])`.

`src/production/migrations/0014_faultjournal_equipment_std_indexes.py`:

- `AddField` + `AddIndex` ×3;
- новое поле `blank=True, default=""` — существующие строки не ломаются;
- `makemigrations --check --dry-run` должен быть чистым.

`FaultAttachment` без изменений. Для фото/видео журнала используется `kind`
(`photo` / `video`), уже есть.

---

## 5. Модель прав

`accounts.views.admin_required` (проверяет `is_staff`) ставится на:

- `FaultJournalListView` (Browse only) — `login_required` + `user_passes_test(is_staff)`;
- `FaultJournalCreateView`, `FaultJournalUpdateView`;
- `FaultAttachmentUploadView`, `FaultAttachmentRenameView`, `FaultAttachmentDeleteView`;
- `FaultJournalExportView` (Excel), т.к. экспорт содержит полные тексты и фото-подписи.

HTML страница `/reports/9/` без входа → redirect на `accounts:login` (как у загрузки
Excel). JSON-эндпойнты фото без входа → 403.

---

## 6. Экраны и маршруты

### 6.1. Маршруты (`src/reports/urls.py`)

| URL | View | Имя |
|---|---|---|
| `9/` | `FaultJournalListView` | `report9` |
| `9/export/` | `FaultJournalExportView` | `report9_export` |
| `9/add/` | `FaultJournalCreateView` | `report9_add` |
| `9/<int:pk>/edit/` | `FaultJournalUpdateView` | `report9_edit` |
| `9/<int:pk>/attachment/upload/` | `FaultAttachmentUploadView` | `report9_attachment_upload` |
| `9/<int:pk>/attachment/rename/` | `FaultAttachmentRenameView` | `report9_attachment_rename` |
| `9/<int:pk>/attachment/delete/` | `FaultAttachmentDeleteView` | `report9_attachment_delete` |

Для общего модуля фото (`src/gallery/`) маршруты выносятся в `src/gallery/urls.py`:

| URL | View | Имя |
|---|---|---|
| `photo/unit/<str:pk>/upload/` | `UnitPhotoUploadView` | `unit_photo_upload` |
| `photo/unit/<int:pk>/rename/` | `UnitPhotoRenameView` | `unit_photo_rename` |
| `photo/unit/<int:pk>/delete/` | `UnitPhotoDeleteView` | `unit_photo_delete` |

`reports/urls.py` подключает `gallery` через `include`, старые имена
(`reports:sn_photo_upload` и т.д.) остаются как алиасы (для обратной совместимости
шаблонов №4/№6 в рабочей копии и возможных внешних закладок).

### 6.2. Страница списка (`templates/reports/report9.html`)

Шапка:

- заголовок «Журнал неисправностей»;
- кнопка «Описание отчёта» (modal с `REPORT9_DESCRIPTION`);
- кнопка «Добавить запись» (только staff) → `report9_add`;
- кнопка «Экспорт в Excel» (только staff) → `report9_export`.

Панель фильтров (GET-форма, как в отчётах №2/№4/№5):

- `filter`: `month` (по умолчанию), `period`, `station`, `all`;
- `year` + `month` (select, как в отчёте №5) — для `month`;
- `start` + `end` (date) — для `period`;
- `station` (select из `Station.objects.filter(is_active=True)`, пустое значение — «Все станции»);
- `equipment_std` (select из справочника `Station`, пустое значение — «Все»); фильтрует
  по `equipment_std` (точное совпадение), т.к. `equipment` — свободный текст;
- `equipment` (text, поиск по подстроке в `equipment`);
- `status` (select: все / решена / не решена / частично);
- `q` (text, поиск);
- кнопка «Обновить», кнопка «Сбросить».

Основная таблица (колонки ТЗ + дополнительные, все сортируемые через `sort_link`):

| № | Колонка | Поле для сортировки | Примечание |
|---|---|---|---|
| 1 | Дата | `date` | |
| 2 | Станция | `station__number` | `020 FCT1` |
| 3 | Оборудование | `equipment_std` / `equipment` | |
| 4 | Неисправность | `description` | Первые 150 символов + «…» |
| 5 | Принятые меры | `actions_taken` | Первые 150 символов |
| 6 | Статус | `status` | badge: success / danger / warning |
| 7 | Лот | `lot__number` | ссылка на отчёт №1 при наличии |
| 8 | SN | `unit__sn` | ссылка на отчёт №6 при наличии |
| 9 | Фото | — | счётчик + превью (общий компонент), кнопка «+» (staff) |
| 10 | Автор | `created_by` | |
| 11 | Действия | — | «Развернуть» (chevron), «Редактировать» (pencil, staff) |

- Сортировка по умолчанию: `date` DESC, затем `detected_at` DESC, затем `created_at` DESC
  (как `FaultJournal.Meta.ordering`).
- Разворот строки: `<tr class="fault-detail">` с `id="fault-detail-<pk>"`, скрытый
  через `d-none`; кнопка `.fault-toggle` переключает класс и `aria-expanded`.
  Внутри — полное описание (`white-space: pre-wrap`), причина, меры, примечание,
  длительность, время обнаружения/устранения, галерея фото/видео.
- Если строка не разворачивалась, полное описание загружается из `data-*`-атрибутов
  кнопки (HTML-escaped) — без AJAX, без отдельного endpoint.
- Поиск подсвечивает совпадения в первых 150 символах (по желанию, опционально).

### 6.3. Страница создания/редактирования (`templates/reports/report9_form.html`)

`ModelForm` на `FaultJournal` + `ModelForm` на `FaultAttachment` (для загрузки
одного/нескольких файлов на странице создания/редактирования):

- `date` (обязательное, `DateField` с `widget=DateInput(attrs={"type": "date"})`);
- `detected_at` (optional, `DateTimeInput` `type="datetime-local"`);
- `station` (select, `autocomplete_fields`-аналог через `<select>` + JS-фильтр);
- `equipment_std` (text, автозаполняется из `__str__` станции при выборе);
- `equipment` (text, необязательное — свободное описание, если станции нет);
- `description` (обязательное, textarea 5×60);
- `cause` (textarea 3×60);
- `actions_taken` (textarea 3×60);
- `resolved_at` (optional, `datetime-local`);
- `status` (select);
- `note` (textarea 2×60);
- `unit` (SN, `<input list="sn-options">` со списком существующих `ControlUnit.sn`;
  при вводе нового SN — создание `ControlUnit` в `form_valid`);
- `lot` (select с поиском);
- чекбоксы/флажки не добавляются (модель не расширяем).

Кнопки: «Сохранить», «Сохранить и добавить фото», «Отмена». После сохранения —
redirect на `report9` с якорем `#fault-detail-<pk>` (строка разворачивается через
`?open=<pk>`, см. §6.2), сообщение успеха.

### 6.3.1. Автозаполнение и валидация формы

- `equipment` — необязательное текстовое поле с автокомплитом:
  `<input list="equipment-options">` + `<datalist id="equipment-options">`,
  наполняемый из ранее введённых значений `FaultJournal.equipment` (distinct, последние
  50, сортировка по частоте/дате) + подсказки из справочника `Station` (`__str__`).
  Список отдаётся в `context["equipment_options"]`.
- `equipment_std` заполняется автоматически при выборе `station` (JS:
  `station_std_map` из `Station` в `context`) и используется для сортировки/фильтра
  по оборудованию; пользователь может изменить вручную. Поле скрыто в форме
  (`hidden`/`readonly`), чтобы не путать с `equipment`.
- `detected_at` по умолчанию = `date` в 00:00 (если не задано), `resolved_at` — по
  желанию.
- `status` — обязательное; по умолчанию = `unresolved`; при установке `resolved_at`
  и пустом `status` подставляется `resolved` (но форма валидирует, что `status`
  выбран явно).
- `duration` не вводится вручную (свойство модели), отображается только для чтения.
- `created_by` проставляется из `request.user` в `form_valid` (поле уже есть;
  `updated_at` обновляется автоматически).
- Видео: UI не поддерживает загрузку видео; поле `kind` в `FaultAttachment` остаётся
  (на будущее), форма `FaultAttachmentForm` принимает только `image/*`.

### 6.4. Фото/видео (общий компонент `src/gallery/`)

`src/gallery/views.py`:

```python
class BasePhotoUploadView(View):
    model = None            # UnitPhoto / FaultAttachment
    fk_field = None         # "unit" / "journal"
    pk_url_kwarg = None     # "pcs_no" / "pk"
    template_next = None    # куда редиректить при не-AJAX
    ...
    def post(self, request, *args, **kwargs): ...   # JSON при AJAX, redirect иначе
```

- `UnitPhotoUploadView` (`model=UnitPhoto`, `fk_field="unit"`, `pk_url_kwarg="pcs_no"`);
- `FaultAttachmentUploadView` (`model=FaultAttachment`, `fk_field="journal"`, `pk_url_kwarg="pk"`).

Аналогично `BasePhotoRenameView`, `BasePhotoDeleteView` (работают с `pk` объекта
вложения, `model` задаётся в подклассе).

`src/gallery/urls.py` — маршруты выше.

`src/templates/gallery/_gallery.html` — partial:

```html
{% load gallery_tags %}
<div class="photo-gallery" data-gallery="{% if gallery_type == 'unit' %}unit{% else %}journal{% endif}"
     data-owner-key="{{ owner_key }}">
  {% for item in items %}
    <div class="photo-item" data-photo-id="{{ item.id }}">
      <img src="{{ item.thumb_url }}" class="photo-thumb" ...>
      <div class="photo-caption">{{ item.caption|default:item.filename }}</div>
      {% if user.is_staff %}
      <form method="post" action="{% url 'gallery:unit_photo_rename' item.id %}" ...>...</form>
      <form method="post" action="{% url 'gallery:unit_photo_delete' item.id %}" ...>...</form>
      {% endif %}
    </div>
  {% endfor %}
  {% if user.is_staff %}
  <button type="button" class="btn btn-outline-primary btn-sm gallery-add"
          data-bs-toggle="modal" data-bs-target="#galleryUploadModal">+</button>
  {% endif %}
</div>
```

`src/templates/gallery/_upload_modal.html` — одна модалка на страницу
(`id="galleryUploadModal"`), `action` задаётся через `data-*` у кнопки «+»
(`data-upload-url`).

`src/templates/gallery/_photo_viewer_js.html` — текущий `shared/_photo_viewer_js.html`
переносится сюда; `shared/photo_viewer.html` остаётся как обёртка для обратной
совместимости или удаляется (см. §10).

`src/gallery/templatetags/gallery_tags.py`:

- `photo_items(owner)` — возвращает список словарей
  `{id, url, caption, filename, kind}` для `UnitPhoto` или `FaultAttachment`;
- `photo_thumb_url(item)` — для `UnitPhoto` это `item.image.url`, для
  `FaultAttachment` — `item.file.url` (без генерации thumbnails на лету; если нужен
  thumbnail, используется CSS `max-width/max-height` — как сейчас).

`src/gallery/forms.py`:

- `UnitPhotoForm` (перенесён из `reports/views.py:952`);
- `FaultAttachmentForm` (`file`, `caption`, `kind`).

### 6.5. Экспорт (`FaultJournalExportView`)

- `GET /reports/9/export/` с теми же GET-параметрами, что и страница
  (`filter`, `year`, `month`, `start`, `end`, `station`, `equipment_std`,
  `status`, `q`); экспортируются **все колонки отфильтрованной выборки**,
  без лимита строк;
- `openpyxl.Workbook`, лист «Журнал неисправностей»;
- колонки (полный набор полей записи): `№`, `Дата`, `Время обнаружения`,
  `Станция`, `Оборудование`, `Оборудование (станция)`, `Статус`, `Лот`, `SN`,
  `Неисправность`, `Причина`, `Принятые меры`, `Время устранения`,
  `Длительность`, `Примечание`, `Фото (кол-во)`, `Фото (подписи)`,
  `Кто создал`, `Создано`, `Изменено`;
- данные — `report9_faults(**filters)` (те же фильтры, что и на странице: период,
  станция, оборудование, статус, поиск), **без лимита строк**; сортировка как в
  `Meta.ordering`;
- `Длительность` — `str(duration)` или `""` (как в админке);
- `Фото (подписи)` — `"; ".join( captions )` через `prefetch_related`;
- имя файла `fault_journal_YYYY-MM-DD_HH-MM-SS.xlsx` (через `_ExcelExportBase._make_response`);
- без листа «Сводка» (по согласованию — экспорт только данных).

Если фильтры не заданы, экспортируется текущий месяц (как дефолт страницы), а не
вся таблица.

---

## 7. Файлы

### Новые

| Файл | Назначение |
|---|---|
| `src/gallery/__init__.py` | Пакет. |
| `src/gallery/apps.py` | `GalleryConfig`. |
| `src/gallery/forms.py` | `UnitPhotoForm`, `FaultAttachmentForm`. |
| `src/gallery/urls.py` | Маршруты фото (unit + journal). |
| `src/gallery/views.py` | `UnitPhotoUploadView`, `UnitPhotoRenameView`, `UnitPhotoDeleteView`, `FaultAttachmentUploadView`, `FaultAttachmentRenameView`, `FaultAttachmentDeleteView`. |
| `src/gallery/templatetags/__init__.py` | |
| `src/gallery/templatetags/gallery_tags.py` | `photo_items`, `photo_thumb_url` и др. |
| `src/templates/gallery/_gallery.html` | Partial галереи. |
| `src/templates/gallery/_upload_modal.html` | Модалка загрузки. |
| `src/templates/gallery/_photo_viewer_js.html` | Перенос из `shared/_photo_viewer_js.html` (или re-export). |
| `src/production/migrations/0014_faultjournal_equipment_std_indexes.py` | Миграция. |
| `src/templates/reports/report9.html` | Страница списка. |
| `src/templates/reports/report9_form.html` | Создание/редактирование. |
| `promt/plans/05-report9.md` | Этот план. |

### Изменяемые

| Файл | Что |
|---|---|
| `src/production/models.py` | `FaultJournal`: `equipment_std`, индексы. |
| `src/production/admin.py` | `FaultJournalAdmin`: `fieldsets`, `list_display`, `list_filter`, `search_fields` (включить `equipment_std`), `autocomplete_fields`. |
| `src/reports/views.py` | Импорт `gallery`; `FaultJournalListView`, `FaultJournalCreateView`, `FaultJournalUpdateView`, `FaultJournalExportView`; удалить `SNPhotoUploadView`, `SNPhotoRenameView`, `SNPhotoDeleteView`, `UnitPhotoForm` (перенесены в `gallery`); добавить `SORTABLE_FIELDS["report9"]`; `REPORT9_DESCRIPTION`. |
| `src/reports/urls.py` | Маршруты 9/9/export/9/add/9/<pk>/edit/; `include("gallery.urls")`; алиасы старых имён фото. |
| `src/reports/queries.py` | `report9_faults(...)` — ORM-запрос со фильтрами, поиском, сортировкой, `select_related`/`prefetch_related` (или оставить в `views.py`, если функция простая — решить по объёму). |
| `src/templates/base.html` | Кнопка «Журнал» (только `staff`) в навигации отчётов. |
| `src/templates/home.html` | Карточка отчёта №9 (видна `staff`; аноним — нет). |
| `src/templates/reports/report_list.html` | Карточка отчёта №9 (аналогично). |
| `src/templates/reports/report4.html` | Заменить inline-галерею на `{% include "gallery/_gallery.html" %}`; заменить `sn_photo_*` URL на `gallery:*` (или оставить алиасы). |
| `src/templates/reports/report6.html` | То же. |
| `src/reports/templatetags/report_tags.py` | Возможно, `json_encode` остаётся; новых тегов не требуется. |
| `tests/test_reports.py` | Новые тесты (см. §8); обновить существующие тесты, если меняются URL-имена фото. |
| `promt/CONTEXT.md` | Добавить отчёт №9, модель прав, `gallery`-модуль, `equipment_std`. |

---

## 8. Тесты

| Область | Тест |
|---|---|
| Модель | `test_fault_journal_defaults` (`equipment_std == ""`); `test_fault_journal_str` |
| Миграция | `test_makemigrations_no_changes` (положительный); `test_0014_fields_and_indexes` (после `migrate`) |
| Права | `test_report9_list_requires_staff` (аноним → redirect, staff → 200); `test_report9_export_requires_staff`; `test_report9_add_requires_staff` |
| Список | `test_report9_default_filter_is_current_month`; `test_report9_period_filter`; `test_report9_station_filter`; `test_report9_status_filter`; `test_report9_search_matches_description`; `test_report9_sort_by_date_desc_default`; `test_report9_cache_control_no_store` |
| Данные | `test_report9_row_fields_and_truncation` (первые 150 символов + «…»); `test_report9_lot_and_sn_links`; `test_report9_photos_count_and_captions`; `test_report9_detail_toggle_renders_full_text` |
| Форма | `test_report9_create_valid`; `test_report9_create_invalid_missing_date`; `test_report9_edit_updates_fields`; `test_report9_equipment_std_autofill_from_station` |
| Фото (журнал) | `test_fault_attachment_upload_staff_only`; `test_fault_attachment_upload_ajax_returns_json`; `test_fault_attachment_rename`; `test_fault_attachment_delete_removes_file` |
| Фото (общий модуль) | `test_unit_photo_upload_via_gallery_staff_only`; `test_unit_photo_upload_ajax_returns_json`; `test_unit_photo_rename_via_gallery`; `test_unit_photo_delete_via_gallery` |
| Регресс №4/№6 | Существующие тесты `test_report4_photos_shown_as_links_with_valid_data_attribute`, `test_report6_photo_*` должны проходить без изменений (или с обновлёнными URL-именами). |
| Экспорт | `test_report9_export_applies_filters` (период/станция/статус); `test_report9_export_headers_and_photos_count`; `test_report9_export_filename_has_timestamp`; `test_report9_export_default_is_current_month` |
| Навигация | `test_home_shows_report9_for_staff`; `test_home_hides_report9_for_anonymous`; `test_base_nav_shows_report9_for_staff` |

Обновить `tests/test_reports.py` (или вынести в `tests/test_report9.py` и
`tests/test_gallery.py` — чище, но больше файлов; рекомендуется вынести).

---

## 9. Открытые вопросы / будущие расширения

- Импорт журнала из Excel — возможен позже через админку (как `uploads` для
  производства).
- Видео в `FaultAttachment.kind = video` — сейчас отображается как файл-ссылка;
  dedicated `<video>`-плеер не делаем (по ТЗ «насчёт видео пока не знаю»).
- Пагинация списка: журнал может быть большим; сейчас — без лимита (как отчёты №4/№5),
  при >1000 записей добавить `LIMIT`/`OFFSET` или `Paginator`.
- Добавление дополнительных полей (`is_important` и т.п.) — по мере необходимости,
  отдельной миграцией.

---

## 10. Порядок выполнения

| Шаг | Содержание | Прибл. время |
|---|---|---|
| 1 | `gallery`-модуль: `apps.py`, `forms.py`, `urls.py`, `views.py`, `templatetags`; тесты модуля. | 2 ч |
| 2 | Перенос `shared/_photo_viewer_js.html` → `gallery/_photo_viewer_js.html`; шаблоны `gallery/_gallery.html`, `gallery/_upload_modal.html`. | 1 ч |
| 3 | Перевод `report4.html` и `report6.html` на `gallery`; обновление тестов. | 1.5 ч |
| 4 | Миграция `0014` + `FaultJournalAdmin` + `makemigrations --check`. | 30 мин |
| 5 | `report9_faults` (queries/views), `SORTABLE_FIELDS["report9"]`, `REPORT9_DESCRIPTION`, блок «Неисправности» в `report6.html` (обратная ссылка из журнала в карточку SN). | 2 ч |
| 6 | `report9.html` (фильтры, таблица, sort, toggle, badges, галерея). | 2 ч |
| 7 | `report9_form.html` + `FaultJournalCreateView`/`UpdateView` + автозаполнение `equipment_std`/`unit`/`lot`. | 2 ч |
| 8 | `FaultJournalExportView` + тесты. | 1 ч |
| 9 | Навигация (`base.html`, `home.html`, `report_list.html`) + тесты. | 30 мин |
| 10 | Полный `pytest`, `check`, `makemigrations --check`, ручная проверка в браузере. | 1 ч |
| 11 | Обновление `CONTEXT.md`, `AGENTS.md` (если требуется), коммит. | 30 мин |

Итого: ~13 ч.

---

## 11. Критерии готовности

- [ ] `manage.py check` — без замечаний.
- [ ] `makemigrations --check --dry-run` — чисто.
- [ ] `pytest` — все тесты зелёные (включая новые и регресс №4/№6).
- [ ] Аноним не видит `/reports/9/` и не может ничего делать с фото журнала.
- [ ] `staff` видит журнал, фильтрует, ищет, сортирует, разворачивает строки,
      создаёт/редактирует записи, загружает/переименовывает/удаляет фото.
- [ ] Excel-экспорт выгружает отфильтрованную выборку (период/станция/оборудование/
      статус/поиск), без лимита строк, и открывается без предупреждений.
- [ ] Отчёты №4 и №6 используют общий `gallery` (нет дублирующихся
      `SNPhotoUploadView` и т.п. в `reports/views.py`).
- [ ] `CONTEXT.md` обновлён.