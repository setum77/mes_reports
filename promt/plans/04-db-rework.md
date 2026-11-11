# 04. Переработка БД и связанных отчётов

Дата составления: 2026-11-11
Основание: `promt/promt_mes_reports/Описание данных (свойства).md`,
`promt/promt_mes_reports/09. Журнал неисправностей.md`, аудит текущего кода
(`src/production`, `src/reports`, `src/uploads`, `src/backup`).
Статус: **реализовано** — БД, импорт, отчёты №1–№8, админка, бэкап и тесты
переведены на новую модель. Отчёт №9 (UI) — отдельным планом после стабилизации.

---

## 1. Цель и границы

Привести модель данных к доменным объектам из ТЗ: **Лот**, **БУ (SN)**, **Станция**,
**Производство**, **Журнал неисправностей**. Убрать дублирование, при котором
`lot_number`, `production_spec`, `workstation_name`, `subop_name`, `position_no`,
`defect` хранятся в каждой записи `ProductionRecord`, а комментарии/фото/брак — в
отдельных таблицах.

В объём входят:

- новые модели и миграция существующих данных;
- импорт Excel под новую схему;
- отчёты №1–№8 (данные, фильтры, экспорт, шаблоны);
- админка, бэкап/восстановление, тесты;
- подготовка схемы для отчёта №9 (модель + админка), без UI отчёта №9.

Не входят:

- сам отчёт №9 (отдельный план после стабилизации БД);
- изменение бизнес-формул FOL/BOL, % NG, скорости (кроме исправлений, явно указанных ниже);
- новые зависимости;
- смена PostgreSQL на другую БД.

---

## 2. Целевая модель

### 2.1. Лот (`LotInfo`, без переименования класса)

| Поле | Тип | Источник |
|---|---|---|
| `lot_number` | CharField, unique | Excel `Lot no.` / админка |
| `production_spec` | CharField | Excel `Production spec.` |
| `plan_total` | PositiveIntegerField, null | «Заявленное количество», админка |
| `comment` | TextField | админ, виден всем |
| `updated_at` | DateTimeField | авто |

Производные свойства (не хранятся в БД, считаются запросом отчёта №1):

- `Production` — уникальные SN, вышедшие со станции 10 со статусом OK;
- `Ok` — уникальные SN, вышедшие со станции 130 со статусом OK;
- `Diff = Production − Ok`;
- `start` — дата/время первого прохода станции 10 в лоте;
- `finish` — дата/время последнего прохода станции 130 **любого статуса** (OK/NG).

> Исправление к текущему коду: сейчас `finish` в `report1_orders` фильтруется
> `result = 'OK'`; по ТЗ фильтр не нужен.

### 2.2. Станция (`Station`) — новая модель

| Поле | Тип | Примечание |
|---|---|---|
| `subop_no` | IntegerField, unique, db_index | номер станции |
| `name_zh` | CharField | из Excel `WorkstationName` (китайский) |
| `name_en` | CharField | словарь/`PositionNo` |
| `name_ru` | CharField | словарь |
| `is_active` | BooleanField, default=True | скрывать устаревшие станции |

Заполняется data-миграцией из существующих `ProductionRecord` + словаря станций.
Импорт новых станций — `get_or_create`; названия `name_en`/`name_ru` можно
редактировать в админке.

### 2.3. БУ (`EngineBlock`) — новая модель

| Поле | Тип | Примечание |
|---|---|---|
| `pcs_no` | CharField, max_length=100, unique, db_index | SN |
| `lot` | FK → `LotInfo`, null=True, on_delete=SET_NULL | лот |
| `production_spec` | CharField, blank=True | снимок из лота / ручной брак |
| `comment` | TextField, default="" | комментарий, виден всем |
| `defect` | BooleanField, default=False | устанавливает админ |
| `entry_date` | DateTimeField, null=True | дата поступления в производство |
| `created_by` | CharField | кто добавил |
| `created_at` / `updated_at` | DateTimeField | аудит |

БУ может существовать без записей `ProductionRecord` (брак до производства).
`SNComment`, `ManualDefect`, `ProductionRecord.defect` после миграции становятся
источниками этих полей и удаляются.

### 2.4. Производство (`ProductionRecord`) — после переработки

Обязательные поля:

- `block` — FK → `EngineBlock` (обычный integer `block_id`);
- `station` — FK → `Station` (обычный integer `station_id`);
- `created_date` — DateTimeField (дата + время из `CREATEDATE`);
- `result` — CharField;
- `test_data` — TextField (оригинал);
- `test_data_ru` — TextField, blank=True (перевод/нормализация).

Технические поля Excel, не описанные в ТЗ, но сохраняемые для трассировки:
`opno`, `op_name`, `production_no`, `production_version`, `product_type`,
`production_name`, `subop_sequence`, `user_name`, `working_hours`, `position_no`.

Удаляются после миграции: `pcs_no`, `subop_no`, `lot_number`,
`production_spec`, `workstation_name`, `subop_name`, `defect` (переезжают в
`EngineBlock`/`Station`). Уникальность: `(block, station, created_date)`.

### 2.5. Медиафайлы (`MediaFile`) — новая единая модель

| Поле | Тип | Примечание |
|---|---|---|
| `block` | FK → `EngineBlock`, null=True | фото/видео по SN |
| `fault` | FK → `FaultLog`, null=True | фото/видео по журналу |
| `file` | FileField, `upload_to="attachments/%Y/%m/%d/"` | файл |
| `kind` | CharField: `photo` / `video` | тип |
| `caption` | CharField | подпись |
| `uploaded_by` | CharField | кто загрузил |
| `uploaded_at` | DateTimeField, auto_now_add | дата |

Ограничение: ровно один владелец (`block` XOR `fault`). Существующие `SNPhoto`
переносятся в `MediaFile` (kind=`photo`), после проверки удаляются. Просмотр —
единый include-шаблон (фото → `img`, видео → `<video controls>`).

### 2.6. Журнал неисправностей (`FaultLog`) — новая модель

| Поле | Тип | Примечание |
|---|---|---|
| `occurred_on` | DateField | «Дата», обязательное |
| `detected_time` | TimeField, null=True | «Время обнаружения», необязательное |
| `station` | FK → `Station` | обязательное |
| `equipment` | CharField, db_index | «Оборудование», подсказки из существующих значений |
| `description` | TextField | описание неисправности |
| `cause` | TextField, blank=True | причина |
| `actions` | TextField, blank=True | принятые меры |
| `resolved_at` | DateTimeField, null=True | время устранения |
| `duration` | DurationField, null=True | вычисляется при сохранении |
| `status` | CharField, choices | `resolved` / `not_resolved` / `partially_resolved`, обязательное |
| `note` | TextField, blank=True | примечание |
| `created_by` / `created_at` / `updated_at` | аудит | |

`duration = resolved_at − (occurred_on + detected_time or 00:00)`, если
`resolved_at` задан. Если время обнаружения не задано, отсчёт от начала суток.

Доступ: создание/редактирование/просмотр — только `is_staff` (админ).
Отчёт №9 (позже) — `admin_required`, экспорт в Excel — полная таблица.

### 2.7. Схема связей

```
LotInfo 1 ── * EngineBlock 1 ── * ProductionRecord * ── 1 Station
                    │                                 │
                    │                                 └── test_data / test_data_ru
                    ├── * MediaFile (photo/video)
                    └── comment / defect / entry_date

FaultLog * ── 1 Station
FaultLog 1 ── * MediaFile
```

---

## 3. Соответствие ТЗ → модель

| Требование ТЗ | Реализация |
|---|---|
| Лот: номер, спец., total, комментарий | `LotInfo` |
| Лот: Production/Ok/Diff/start/finish | запрос отчёта №1 (производные) |
| БУ: SN, лот, спец., комментарий, defect, фото | `EngineBlock` + `MediaFile` |
| БУ без производства (брак до линии) | `EngineBlock` без `ProductionRecord` |
| Станция: номер, китайское/английское/русское имя | `Station` |
| Производство: SN, станция, дата, время, result, testData | `ProductionRecord` + `Station`/`EngineBlock` |
| testData на русском | `test_data_ru` + словарь + fallback |
| Журнал: дата, время, станция, оборудование, описание, фото/видео, причина, меры, устранение, длительность, статус, примечание | `FaultLog` + `MediaFile` |

---

## 4. Миграция

### 4.1. Принцип

Три фазы: **expand → migrate → contract**.

1. **Expand** — новые таблицы и nullable FK; старые поля/таблицы остаются.
2. **Migrate** — data-миграция заполняет новые поля из старых.
3. **Contract** — после проверки отчётов удалить дублирующие поля/модели.

До начала — обязательный бэкап (`/admin/backup/`) и проверка на копии БД.

### 4.2. Шаги

| Шаг | Файл/действие | Содержание |
|---|---|---|
| 0 | Бэкап + ветка | `backup_*`, `git checkout -b db-domain-rework` |
| 1 | `0007_station_engineblock_media.py` | `CreateModel Station`, `EngineBlock`, `MediaFile`, `FaultLog`; `AddField ProductionRecord.block/station/test_data_ru` (nullable); индексы |
| 2 | `0008_migrate_domain_data.py` | `RunPython`: словарь станций → `Station`; `ProductionRecord` → `EngineBlock`; `SNComment` → `EngineBlock.comment`; `ManualDefect`/`defect=True` → `EngineBlock.defect`; `SNPhoto` → `MediaFile`; `test_data_ru = translate_test_data(test_data)`; заполнить `block_id`/`station_id` |
| 3 | `0009_domain_constraints.py` | `AlterField` FK → `null=False`; `UniqueConstraint(block, station, created_date)`; `CheckConstraint` владельца `MediaFile`; `AlterUniqueTogether` старого ключа оставить до contract |
| 4 | Код | парсер, запросы, views, шаблоны, админка, backup, тесты (раздел 5) |
| 5 | Проверка | отчёты №1–№8 на копии БД, полный `pytest` |
| 6 | `0010_remove_legacy_fields.py` | `RemoveField` дублей `ProductionRecord`; `DeleteModel ManualDefect/SNComment/SNPhoto`; удалить старый unique; обновить `PRODUCTION_MODELS` |

### 4.3. Правила data-миграции

- **Станции**: seed 12 известных (`10, 20, 30, 50, 60, 70, 80, 90, 100, 110, 120, 130`)
  с `name_en`/`name_ru`; затем `UPDATE` из `ProductionRecord` (`workstation_name`
  → `name_zh`), не перетирая заполненные `name_en`/`name_ru`.
- **БУ**: `pcs_no` из `ProductionRecord`, `ManualDefect`, `SNComment`, `SNPhoto`.
  Лот — из последней записи производства или `ManualDefect`; если лота нет в
  `LotInfo`, создать. `defect = any(ProductionRecord.defect) or ManualDefect exists`.
  `comment` — из `SNComment`. `entry_date` — из `ManualDefect` или `MIN(created_date)`.
- **Производство**: `block_id` по `pcs_no`, `station_id` по `subop_no`.
- **Фото**: `SNPhoto` → `MediaFile(block=..., kind="photo")`; `uploaded_at`
  сохранить через `update()` (auto_now_add).
- **Идемпотентность**: миграция повторяема, использует `get_or_create`/`update_or_create`.
- **Проверка**: после миграции сравнить counts: `ProductionRecord`, уникальные `pcs_no`,
  `SNComment`, `ManualDefect`, `SNPhoto`; расхождения — до включения нового кода.

### 4.4. Что сохраняем

- Уникальность `(pcs_no, subop_no, created_date)` → `(block, station, created_date)`.
- `ignore_conflicts=True` при импорте.
- Обязательные колонки Excel.
- `Cache-Control: no-store` для отчётов №2/№3 и экспорта №3 (и фактических №4/№6/№8).
- Ссылки/файлы существующих фото (через `MediaFile`).

---

## 5. Изменения кода

### 5.1. Импорт (`src/uploads/`)

- `excel_parser.py`: возвращает структурированные строки (не `ProductionRecord`),
  с готовыми `lot_number`, `production_spec`, `subop_no`, `pcs_no`, `created_date`,
  `result`, `test_data`, техническими полями.
- `import_to_database`:
  1. `LotInfo` — `bulk_create(ignore_conflicts=True)`, обновить `production_spec` при пустом;
  2. `Station` — `bulk_create` новых, `in_bulk` карта;
  3. `EngineBlock` — `bulk_create` новых, `in_bulk` карта; не перетирать `defect`/`comment`;
  4. `ProductionRecord` — `bulk_create(ignore_conflicts=True, batch_size=2000)`
     с `block_id`/`station_id`/`test_data_ru`;
  5. вернуть `{total, inserted, duplicates}`.
- `test_data_ru`: `production/translations.py` — словарь китайских фрагментов и
  `translate_test_data()`; пока словарь не покрывает значение — возвращается оригинал.
  Добавить management command `translate_test_data` для повторной обработки.

### 5.2. Запросы (`src/reports/queries.py`)

| Функция | Изменение |
|---|---|
| `report1_orders` | `JOIN production_engineblock` для лота/спец.; `finish` — станция 130 без фильтра result; `Production`/`Ok` через `block`/`station`; `LotInfo` для Total/comment |
| `report2_line_productivity` | фильтр лота через `block.lot_number`; остальное без изменений |
| `report3_monthly_productivity` | без изменений (обёртка над report2) |
| `report4_defects` | `defect` — из `EngineBlock`; «незавершённые» — через `block`/`station`; ручные — `EngineBlock` без записей; комментарий/фото — из `EngineBlock`/`MediaFile`; имя последней станции — `Station.name_en` |
| `report5_repeated_passes` | `JOIN block/station`; имя станции — `Station`; комментарий/`defect` — `EngineBlock` |
| `report6_serial_number` | записи по `block`; `station.name_en`; `test_data_ru` (fallback `test_data`) |
| `report6_summary` | `EngineBlock` (комментарий/`defect`/запись), `Station`, `MediaFile` |
| `report7_station130_output` | `JOIN block` для lot/spec |
| `report8_stations` | фильтр лота через `block`; группировка по `station_id`; при необходимости подписи из `Station` |

Удалить/переписать `STATION_NAME_TRANSLATIONS`, `STATION_POSITION_TRANSLATIONS`,
`translate_workstation_name`, `REPORT4_STATION_NAMES` — источник истины `Station`.

### 5.3. Views (`src/reports/views.py`)

- `Report1View`/`_report1_data` — без изменений по фильтрам; данные из нового запроса.
- `Report2/3/5/7/8` — фильтр лота передаётся как раньше; проверить, что `lot`
  валидируется по `LotInfo`.
- `Report4View`:
  - `defect_filter='defect'` — `EngineBlock.defect=True`;
  - `in_progress` — станция 10 OK, нет 130 OK;
  - ручные — `EngineBlock` без `ProductionRecord`.
- `ManualDefectCreateView` → `EngineBlockCreateView` (URL можно оставить
  `/defect/add/`): форма `pcs_no`, `lot`, `production_spec`, `entry_date`, `comment`;
  если БУ существует — обновить `defect=True`/дату, иначе создать.
- `SNCommentEditView` — читает/пишет `EngineBlock.comment`.
- `SNSetDefectView` — `EngineBlock.defect`.
- `SNPhotoUpload/Rename/Delete` → `MediaFile` (`kind` определяется по content type
  или полю формы); сохранить существующие URL.
- `Report6View` — existence/`recent_sns` через `EngineBlock`; комментарии — из `EngineBlock`.
- Экспорт: `Report4ExportView`, `Report6ExportView` — новые поля/названия станций.

### 5.4. Админка (`src/production/admin.py`, `mes_report3/admin_site.py`)

- `ProductionRecordAdmin` — read-only, `list_display` через `block__pcs_no`,
  `station__subop_no`; `search_fields` по `block__pcs_no`, `station__name_*`.
- `LotInfoAdmin` — без изменений.
- Новые: `StationAdmin` (staff), `EngineBlockAdmin` (staff; `defect`, `comment`),
  `MediaFileAdmin` (staff; фото/видео), `FaultLogAdmin` (staff; фильтры/поиск).
- Удалить регистрации `ManualDefect`, `SNComment`, `SNPhoto` после contract.
- `get_dashboard_metrics`: `ManualDefect` → `EngineBlock.defect`; добавить
  `FaultLog` (открытые проблемы), если нужно.
- `get_report_links`: пункт «Журнал» добавить на этапе отчёта №9.

### 5.5. Шаблоны

- `report4.html`, `report5.html`, `report6.html`: названия станций из `Station`,
  `test_data_ru`, единый include медиа.
- `shared/photo_viewer.html` / `_photo_viewer_js.html`: поддержать `kind=video`
  (`<video controls>`), один вызов для SN и `FaultLog`.
- `defect_form.html`, `sn_comment_form.html`: минимальные правки под новые поля.
- `report9.html` — отложено до отдельного плана.

### 5.6. Backup (`src/backup/utils.py`)

- `PRODUCTION_MODELS` обновить и упорядочить по зависимостям:
  `ProductionRecord`, `MediaFile`, `FaultLog`, `EngineBlock`, `LotInfo`, `Station`.
- В переходный период (expand/contract) включить старые модели, затем удалить.
- `dumpdata/loaddata` — без изменений; проверить `manifest` counts и восстановление
  на тестовой БД.
- `_reset_sequences` — для моделей с `BigAutoField`; `Station`/`EngineBlock` имеют
  `id`, последовательности сбросить.

### 5.7. Тесты (`tests/`)

- Обновить фикстуры: создавать `Station` + `EngineBlock` + `LotInfo`, затем
  `ProductionRecord` с FK.
- Добавить:
  - constraints: unique `(block, station, created_date)`, `MediaFile` XOR;
  - `Station` seed/translation;
  - `translate_test_data`;
  - импорт: новый файл → БД, повторный импорт без дублей;
  - отчёты №1–№8 на новых полях (в т.ч. `finish` без OK, ручной брак без записей);
  - `MediaFile` для отчётов №4/№6;
  - backup manifest count.
- Сохранить `test_apply_sort*`, `test_get_sort_params*` без изменений.
- Целевой результат: `uv run pytest` зелёный; `manage.py check` без ошибок.

---

## 6. Отчёты: сводка изменений

| № | Что меняется | Риск |
|---|---|---|
| 1 | Данные через `block`/`station`; `finish` без `result='OK'`; фильтр лота через `LotInfo` | средний: SQL CTE |
| 2 | фильтр лота через `block`; остальное без изменений | низкий |
| 3 | без изменений (агрегация report2) | низкий |
| 4 | `EngineBlock.defect`, ручные БУ без записей, `Station.name_en`, `MediaFile` | высокий: логика брака |
| 5 | `block`/`station`, комментарий/`defect` из БУ | средний |
| 6 | `EngineBlock`, `test_data_ru`, `MediaFile` | высокий: карточка SN |
| 7 | `block` для lot/spec | низкий |
| 8 | `block` для фильтра лота, `station_id` для группировки | средний: SQL pivot |

---

## 7. Порядок выполнения

### Фаза A. Подготовка (P0)

- [ ] Бэкап БД, ветка `db-domain-rework`.
- [ ] Baseline: `manage.py check`, `pytest` (зафиксировать зелёный статус).
- [ ] Согласовать решения из раздела 9.

### Фаза B. Схема и данные (P0)

- [ ] `0007`: модели `Station`, `EngineBlock`, `MediaFile`, `FaultLog`; nullable FK.
- [ ] `0008`: data-миграция (станции, БУ, комментарии, брак, фото, `test_data_ru`).
- [ ] `0009`: NOT NULL + constraints.
- [ ] Проверка counts и ручной сверки на копии БД.

### Фаза C. Код (P0)

- [ ] Импорт/парсер.
- [ ] `queries.py` — отчёты 1–8.
- [ ] `views.py` — фильтры, брак, комментарии, фото.
- [ ] Шаблоны + единый медиа-вьюер.
- [ ] Админка + dashboard.
- [ ] Backup.
- [ ] Тесты.

### Фаза D. Contract и стабилизация (P1)

- [ ] Полный `pytest`, ручная проверка отчётов на копии БД.
- [ ] `0010`: удалить legacy-поля/модели.
- [ ] Обновить `README`/`CONTEXT.md`/`AGENTS.md`.
- [ ] Коммит (по запросу владельца).

### Фаза E. Отчёт №9 (P2, отдельный план)

- [ ] `05-report9.md`: UI, фильтры, поиск, экспорт, редактирование, медиа.
- [ ] Модель/админка уже готовы после фазы B.

---

## 8. Проверка

```powershell
# Статическая проверка
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe src\manage.py check

# Миграции
.\.venv\Scripts\python.exe src\manage.py migrate --plan
.\.venv\Scripts\python.exe src\manage.py migrate

# Тесты (нужен PostgreSQL)
.\.venv\Scripts\python.exe -m pytest tests/test_reports.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Ручной чек-лист на копии БД:

- [ ] отчёт 1: `finish` у лота с NG на 130 не пустой; `Production/Ok/Diff` сходятся;
- [ ] отчёт 4: ручной брак без записей производства виден; `defect` из БУ;
- [ ] отчёт 6: SN без производства открывается; фото/видео; `test_data_ru`;
- [ ] отчёты 2/3/5/7/8: фильтр лота, суммы и диаграммы совпадают с baseline;
- [ ] повторный импорт не создаёт дублей;
- [ ] бэкап/восстановление на тестовой БД проходит.

---

## 9. Решения, требующие подтверждения

1. **Имя класса лота**: оставить `LotInfo` (рекомендуется, меньше диффа) или
   переименовать в `Lot`?
2. **Медиа**: единая `MediaFile` (рекомендуется) или `SNPhoto` + отдельный
   `FaultLogMedia`?
3. **Contract**: удалять legacy-поля/модели сразу после проверки (рекомендуется)
   или оставить на один релиз для отката?
4. **testData на русском**: словарь + fallback (рекомендуется) или только ручной
   перевод в админке?
5. **Журнал**: доступ `is_staff` (рекомендуется) или только `is_superuser`?
6. **Видео**: поддерживать сразу (`<video>`) или только фото на первом этапе?

---

## 10. Риски

| Риск | Влияние | Мера |
|---|---|---|
| Потеря/искажение данных при миграции | высокое | бэкап, `RunPython` idempotency, сверка counts, contract отдельно |
| Дубли `ProductionRecord` при `bulk_create` | среднее | `ignore_conflicts=True`, уникальный constraint |
| Расхождение `EngineBlock.lot` и `ProductionRecord.lot_number` | среднее | data-миграция по последней записи; проверка |
| Старые бэкапы не содержат новые модели | среднее | бэкапы создаются после миграции; совместимость не гарантируется |
| Тесты (~111 функций) массово ломаются | среднее | обновить фикстуры одним этапом, узкий прогон |
| `test_data_ru` не переводит реальные значения | низкое | fallback на оригинал, словарь пополняется по факту |

---

## 11. Definition of Done

- [ ] `manage.py check` без ошибок.
- [ ] `pytest` зелёный.
- [ ] Все отчёты №1–№8 открываются и экспортируются на реальных данных.
- [ ] Нет обращений к удалённым полям (`ProductionRecord.pcs_no` и т.п.) в коде.
- [ ] Бэкап/восстановление работает на новой схеме.
- [ ] Документация (`CONTEXT.md`, `AGENTS.md`) обновлена.