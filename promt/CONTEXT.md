# CONTEXT — MES Reports

Контекст проекта для агентов и новых разработчиков. Составлен 2026-11-11.
Рабочее дерево содержит незакоммиченную переработку БД и отчётов (база — `232c0ee`);
актуальное состояние — по `git status` и файлам, а не по последнему коммиту.

Документ описывает: предметную область, архитектуру, поток данных, модели, отчёты,
инварианты и команды проверки. Точные требования к отчётам — в `promt/promt_mes_reports/`,
правила разработки — в `AGENTS.md` (главнее этого файла при расхождениях).

---

## 1. Продукт

Django-приложение для приёма Excel-выгрузок из MES-системы и построения производственных
отчётов по сборочной линии блоков управления двигателем (БУ).

- Единица данных — прохождение станции (010…130) конкретным серийным номером (SN/PCSNo).
- После импорта данные лежат в PostgreSQL; отчёты строятся SQL-запросами и агрегациями.
- 8 отчётов с фильтрами, сводками, сортировкой, диаграммами и экспортом в Excel.
- Просмотр отчётов и экспорт доступны анонимно; изменение данных — только `staff`/superuser.

Станции: `010` подача PCB, `020` FCT1, `030` плазменная очистка, `050` сборка,
`060` стабилизация, `070`高温老化/burn-in, `080` FCT2, `090` прошивка, `100` проверка
прошивки, `110` герметичность, `120` PIN-тест, `130` этикетка. Китайские названия
хранятся в `Station.name_zh`, английские/русские — в `Station.name_en`/`name_ru`;
справочник и seed — в `src/production/stations.py`.

---

## 2. Стек и запуск

| Что | Значение |
|---|---|
| Язык | Python 3.12+ |
| Фреймворк | Django 5.x |
| БД | PostgreSQL 14+ (в Docker — 17) |
| Зависимости | `uv sync --frozen` (pandas, openpyxl, psycopg2-binary, python-dotenv, django-widget-tweaks, gunicorn) |
| Тесты | pytest + pytest-django |
| Настройки | `mes_report3.settings.dev` (по умолчанию в `manage.py`), `prod` — в Docker |

```powershell
uv sync --frozen
uv run python src/manage.py migrate
uv run python src/manage.py runserver
uv run pytest
```

Если `uv` недоступен (нет доступа к `AppData\Local\uv\cache`), использовать venv напрямую:

```powershell
.\.venv\Scripts\python.exe src\manage.py check
.\.venv\Scripts\python.exe -m pytest
```

`.env` читается из `src/` (`BASE_DIR`). Основные переменные: `DJANGO_SECRET_KEY`,
`DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_*`. Часовой пояс жёстко задан
`Europe/Moscow` — отчёты выводят время в нём, а не в поясе браузера.

---

## 3. Карта репозитория

```
src/
  manage.py                 точка входа (settings.dev по умолчанию)
  mes_report3/
    settings/               base.py, dev.py, prod.py
    urls.py                 /admin/, /accounts/, /upload/, /reports/, /health/
    admin_site.py           кастомный MESAdminSite + метрики дашборда
  accounts/                 вход/выход, admin_required (is_staff)
  production/               модели данных, справочник станций, перевод testData, админка
    stations.py             DEFAULT_STATIONS (номер, PositionNo, названия)
    testdata.py             словарь переводов + translate_test_data
  uploads/                  приём Excel, парсер, импорт с дедупликацией
  reports/
    urls.py                 маршруты отчётов и экспорта
    views.py                страницы, фильтры, экспорт в Excel (~1960 строк)
    queries.py              SQL и агрегации (~1185 строк)
    templatetags/           report_tags.py
  backup/                   бэкап/восстановление/очистка (в админке)
  templates/                base, home, reports/reportN.html, admin/backup/*, uploads/*
  static/                   fav_mes.png
tests/                      test_reports.py, test_excel_parser.py, test_settings.py,
                            test_domain.py, _legacy.py (совместимость старых тестов)
docker/                     Dockerfile, docker-compose.yml, nginx, entrypoint.sh
promt/
  promt_mes_reports/        исходные ТЗ (Obsidian)
  plans/                    планы работ 00…04
```

---

## 4. Поток данных

1. Пользователь (`staff`) загружает Excel в `/upload/`.
2. `uploads.excel_parser.parse_excel_file` разбирает файл через pandas/openpyxl,
   проверяет обязательные колонки, нормализует `subop_no`/`created_date`
   (naive → aware в текущем TIME_ZONE).
3. `import_to_database` последовательно upsert-ит `Lot`, `Station`, `ControlUnit`
   и делает `bulk_create(..., ignore_conflicts=True, batch_size=2000)` для
   `Production`; дубликаты по `(unit, station, created_date)` отбрасываются.
   `defect`/`comment` существующего БУ не перетираются; `test_data_ru` заполняется
   словарём. Внешней транзакции нет.
4. Страницы отчётов: `reports/urls.py` → `ReportNView` (`views.py`) → `reportN_*`
   (`queries.py`, сырой SQL на `django.db.connection`) → шаблон `templates/reports/reportN.html`.
5. Экспорт: `ReportNExportView` (`views.py`, openpyxl) формирует `.xlsx` с теми же
   данными, что и страница (общие хелперы `_reportN_data`).

---

## 5. Модель данных (БД)

### 5.1. Схема

```
Lot 1 ── * ControlUnit 1 ── * Production * ── 1 Station
                    │
                    ├── * UnitPhoto
                    └── * FaultJournal  (unit/lot — опционально)
FaultJournal * ── 1 Station
FaultJournal 1 ── * FaultAttachment
```

`ControlUnit` (БУ) может существовать без записей `Production`: ручной брак/SN,
который ещё не проходил линию. `Production` — только прохождение станции.

### 5.2. Таблицы

| Модель | Поля | Связи/ограничения |
|---|---|---|
| `ControlUnit` | `sn` (unique), `lot` FK, `comment`, `defect`, `entry_date`, `created_by`, `created_at`, `updated_at` | `lot` → `Lot` (`SET_NULL`, nullable); `sn` max_length=100; свойства `pcs_no`, `lot_number`, `production_spec`, `resolved_entry_date` |
| `Lot` | `number` (unique), `production_spec`, `total`, `comment`, `created_at`, `updated_at` | `number` max_length=50; `total` — «Заявленное количество» |
| `Station` | `number` (unique), `position_no`, `name_zh`, `name_en`, `name_ru`, `sort_order`, `is_active` | `number` Integer unique; сортировка `sort_order, number` |
| `Production` | `unit` FK, `station` FK, `created_date`, `result`, `test_data`, `test_data_ru` | `unique_together=(unit, station, created_date)`; индексы `(unit, created_date)`, `(station, created_date)`, `created_date` |
| `TestDataTranslation` | `source` (unique), `target`, `is_active`, `comment` | max_length 255/300/255 |
| `FaultJournal` | `date`, `detected_at`, `station`, `equipment`, `description`, `cause`, `actions_taken`, `resolved_at`, `status`, `note`, `unit`, `lot`, `created_by`, `created_at`, `updated_at` | `status`: `resolved` / `unresolved` / `partial`; `station` `PROTECT`, `unit`/`lot` `SET_NULL`; `duration` — свойство |
| `FaultAttachment` | `journal` FK, `file`, `kind`, `caption`, `uploaded_by`, `uploaded_at` | `kind`: `photo` / `video`; `journal` `CASCADE` |
| `UnitPhoto` | `unit` FK, `image`, `caption`, `uploaded_by`, `uploaded_at` | `unit` `CASCADE`; `image` → `sn_photos/%Y/%m/%d/` |

`Production.unit` — `CASCADE`; `Production.station` — `PROTECT` (станцию с
прохождениями нельзя удалить). `FaultJournal.station` — `PROTECT`.

### 5.3. Производные свойства лота

Не хранятся в БД, считаются в `report1_orders`:

- `Production` — число уникальных БУ, прошедших станцию `10` с `result=OK`;
- `Ok` — число уникальных БУ, прошедших станцию `130` с `result=OK`;
- `Diff = Production − Ok`;
- `start` — минимальный `created_date` станции `10` в лоте;
- `finish` — максимальный `created_date` станции `130` **любого результата**
  (в старом коде ошибочно фильтровался `result='OK'`).

### 5.4. Справочники и перевод testData

- `src/production/stations.py`: `DEFAULT_STATIONS` — 12 станций (`10…130`) с
  `position_no` и названиями на трёх языках; `DEFAULT_STATIONS_BY_NUMBER`,
  `STATION_NUMBERS`, `STATION_NUMBERS_IN_REPORT8`.
- `src/production/testdata.py`: `DEFAULT_TEST_DATA_TRANSLATIONS` (35 правил) и
  `translate_test_data()`. Правила загружаются из `TestDataTranslation`
  (`is_active=True`), при пустом справочнике — встроенный список. Замена идёт по
  убыванию длины фрагмента; неизвестные значения остаются в оригинале.
- `Production.test_data_ru` заполняется при импорте; отчёты показывают его,
  fallback — `test_data`.

### 5.5. Миграции и перенос данных

| Миграция | Что делает |
|---|---|
| `0001–0006` | Старая плоская схема (`ProductionRecord`, `LotInfo`, `ManualDefect`, `SNComment`, `SNPhoto`) |
| `0007_db_rework_create_new_models` | Создаёт `Lot`, `Station`, `ControlUnit`, `TestDataTranslation`, `FaultJournal`, `FaultAttachment`, `UnitPhoto`, `Production` (новые таблицы, без переноса данных) |
| `0008_db_rework_copy_data` | Переносит данные: станции (seed + найденные), лоты, БУ (из производства/ручного брака/комментариев/фото), `Production`, фото → `UnitPhoto`, словарь переводов |
| `0009_db_rework_remove_legacy_models` | Удаляет `LotInfo`, `ManualDefect`, `ProductionRecord`, `SNComment`, `SNPhoto` |
| `0010_legacy_report_view` | Создаёт read-only view `production_productionrecord` для старого SQL отчётов (временный слой) |
| `0011_controlunit_created_by` | `ControlUnit.created_by` |
| `0012_controlunit_entry_date` | `ControlUnit.entry_date` |
| `0013_backfill_entry_date` | Заполняет `entry_date` минимальной датой производства |

`makemigrations --check` сейчас не находит изменений. На существующей БД
`migrate` применяет только новые миграции; на чистой — всю цепочку `0001…0013`.

### 5.6. Совместимый view для отчётов

`migrations/0010_legacy_report_view.py` создаёт view `production_productionrecord`
с плоскими колонками (`pcs_no`, `subop_no`, `lot_number`, `production_spec`,
`workstation_name`, `position_no`, `defect` и т.д.), Join-ит `Production`,
`ControlUnit`, `Station`, `Lot`. Он нужен, пока отчёты №1/2/4/5/7/8 используют
старый SQL. Это read-only view: ORM-записи (`ControlUnit`, `UnitPhoto`) идут
через новые модели. После переписывания SQL view можно удалить.

### 5.7. Импорт: Excel → БД

| Excel | Модель/поле |
|---|---|
| `Lot no.` | `Lot.number` |
| `Production spec.` | `Lot.production_spec` |
| `Subop no` | `Station.number` |
| `subop name` / `WorkstationName` | `Station.name_zh` (при создании/обновлении) |
| `PCSNo` | `ControlUnit.sn` |
| `CREATEDATE` | `Production.created_date` (naive → aware в `TIME_ZONE`) |
| `result` | `Production.result` |
| `testData` | `Production.test_data` + `Production.test_data_ru` |

`import_to_database` не создаёт `Production` для БУ без записи; `ControlUnit`
может быть создан отдельно (ручной брак). Дубликаты `Production` отбрасываются
`ignore_conflicts=True`; повторный импорт не меняет `defect`/`comment` существующего БУ.

### 5.8. Админка и бэкап

- `Production` в админке read-only; `ControlUnit`, `Lot`, `Station`,
  `TestDataTranslation`, `FaultJournal`, `FaultAttachment`, `UnitPhoto` — для `staff`.
- `backup/utils.py` `PRODUCTION_MODELS` (порядок удаления при restore):
  `Production`, `FaultAttachment`, `FaultJournal`, `UnitPhoto`, `ControlUnit`,
  `Lot`, `Station`, `TestDataTranslation`.
- `create_db_dump` пишет `database.json` в `UTF-8`; `loaddata` читает его при
  восстановлении. Иначе на Windows `dumpdata` падает с `UnicodeEncodeError` на
  китайских `testData`.

---

## 6. Отчёты

Все пути — от `/reports/`, у каждого есть `N/export/` (Excel). Просмотр и экспорт
доступны без авторизации; `admin_required` стоит только на операциях изменения данных
(правка лота, ручной брак, комментарий SN, фото).

| № | Страница | Фильтры | Содержание |
|---|---|---|---|
| 1 | Сводный по лотам | год (по умолчанию текущий), произвольный период | Лоты: Production (уник. OK на 010), Ok (уник. OK на 130), Diff, брак (SN, если <10), start/finish (без фильтра result), Total/комментарий из `Lot`; сортировка по `start` (старые сверху); сводка сверху |
| 2 | Производительность линии | месяц, год, период, лот | По дням: FOL (010→050) и BOL (060→130) — часы, выпуск, скорость; только дни с непустыми данными; 3 диаграммы; сводка FOL/BOL; `Cache-Control: no-store` |
| 3 | Сводный по месяцам | год | Агрегация данных отчёта 2 по 12 месяцам года (все месяцы, включая пустые); те же блоки FOL/BOL, диаграммы; `Cache-Control: no-store` у HTML и Excel-экспорта |
| 4 | Брак | 30d/месяц/90d/180d/год/период/лот, тип брака | Ручной брак + БУ, не завершившие производство; последняя OK-станция и дата; сводка по этапам; комментарий SN (редактирование — staff); фото |
| 5 | Повторные проходы | год, месяц, период, лот | Станции, пройденные более одного раза; сводка; без жёсткого лимита строк |
| 6 | Отчёт по SN | ввод SN | Карточка SN: сводка, хронология всех прохождений, `testData` на русском, двойные проходы, Defect, фото, комментарий, последние 50 просмотренных SN |
| 7 | Выпуск за период | день, неделя, месяц, произвольный период | Уникальные SN с 130 и `result=OK` (последняя запись по SN); сводка: дней, выпущено, лоты; SN — ссылки на отчёт 6 |
| 8 | По станциям | год, месяц, период, лот | По дням по каждой станции: уник. OK, OK, NG, % NG, списки NG SN; разница FOL = 010−050, BOL = 060−130; график среднего % NG |

Общие механики: `_reportN_period` в `views.py` разбирает и валидирует GET-параметры
(некорректные значения → сообщение и безопасный дефолт); `apply_sort` сортирует список
словарей по белому списку `SORTABLE_FIELDS`; сводка считается по отфильтрованным данным.

---

## 7. Роли и доступ

| Роль | Права |
|---|---|
| Аноним | Просмотр отчётов №1–№8, экспорт в Excel |
| `is_staff` | Загрузка Excel, правка `Lot` (Total/комментарий), ручной брак, комментарии SN, флаг Defect, фото; бизнес-модели в админке (кроме `Production`) |
| `is_superuser` | Пользователи/группы, бэкап/восстановление/очистка |

Декоратор: `accounts.views.admin_required` (`user_passes_test(is_admin)`, `is_staff`).
В Docker суперпользователь `admin` создаётся при наличии `DJANGO_ADMIN_PASSWORD`.

---

## 8. Импорт Excel

Обязательные колонки (`REQUIRED_COLUMNS` в `uploads/excel_parser.py`):

`Lot no.`, `Production spec.`, `Subop no`, `subop name`, `PCSNo`, `CREATEDATE`,
`result`, `testData`.

Дополнительно маппятся: `opno`, `op name`, `Production No.`, `Production Version`,
`product type`, `Production Name`, `SubOPSequence`, `PositionNo`, `WorkstationName`,
`User name`, `working hours`. Строки без `CREATEDATE` отбрасываются. Дедупликация —
`ignore_conflicts=True`, `batch_size=2000`; `import_to_database` последовательно
upsert-ит `Lot`/`Station`/`ControlUnit` и создаёт `Production` (внешней транзакции нет).

---

## 9. Бэкап и восстановление (`src/backup/`)

- Подключается к кастомной админке через `setup_backup_urls` (`/admin/backup/...`),
  доступ только у superuser.
- Полный бэкап: дамп БД (`database.json` в `UTF-8`) + архив медиа + манифест
  (контрольные суммы, идентификатор проекта `mes_reports`, количество моделей,
  список миграций). Файлы — в `BACKUP_ROOT` (`src/backups/` по умолчанию).
- Восстановление: проверка манифеста → очистка production-моделей (`Production`,
  `FaultAttachment`, `FaultJournal`, `UnitPhoto`, `ControlUnit`, `Lot`, `Station`,
  `TestDataTranslation`) → сброс sequences → `loaddata` → восстановление медиа. Долгие
  операции выполняются в фоновом потоке, прогресс — в файле (in-memory хранилище не
  подходит: gunicorn запускается с `--workers 2`, воркеры не разделяют память).
- Есть загрузка архива с inspect/подтверждением и полная очистка данных (`wipe`).

---

## 10. Инварианты и соглашения

Не нарушать без явного решения владельца:

1. Уникальность `Production (unit, station, created_date)`.
2. `ControlUnit.sn`, `Lot.number`, `Station.number`, `TestDataTranslation.source` — unique.
3. `Production.station` и `FaultJournal.station` — `PROTECT`; `Production.unit` — `CASCADE`;
   `ControlUnit.lot`, `FaultJournal.unit/lot` — `SET_NULL`.
4. Импорт только через `bulk_create(..., ignore_conflicts=True)`.
5. Обязательные колонки Excel — без изменений.
6. `Cache-Control: no-store` как минимум для HTML отчётов №2 и №3 и Excel-экспорта №3
   (в текущем коде также для HTML отчётов №4, №6, №8).
7. Новые зависимости не добавляются.
8. Изменения — минимальные и точечные; unrelated-рефакторинг не делать.
9. Комментарии в коде и объяснения — на русском.
10. `Production` в админке остаётся read-only.
11. Время — в `TIME_ZONE = Europe/Moscow` (не UTC и не пояс браузера).
12. Дамп БД пишется в `UTF-8`; `production_productionrecord` — только read-only view.

---

## 11. Проверка

```powershell
# Конфигурация
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe src\manage.py check

# Состояние схемы и миграций
.\.venv\Scripts\python.exe src\manage.py showmigrations production
.\.venv\Scripts\python.exe src\manage.py migrate --plan
.\.venv\Scripts\python.exe src\manage.py makemigrations --check --dry-run

# Узкий прогон
.\.venv\Scripts\python.exe -m pytest tests/test_reports.py -q

# Полный прогон (нужен PostgreSQL; pytest-django создаёт test_mes_report,
# роли требуется CREATEDB)
uv run pytest
```

В `tests/` 122 теста (включая 4 доменных теста в `test_domain.py`). БД-тесты требуют
запущенного PostgreSQL (`start`/`stop` в корне переводят службу `postgresql-x64-17`).

---

## 12. Куда смотреть при типовых задачах

| Задача | Файлы |
|---|---|
| Новый/изменённый отчёт | `reports/queries.py` (данные), `reports/views.py` (фильтры, экспорт), `templates/reports/reportN.html`, `reports/urls.py`, `templates/base.html`/`home.html` (ссылки) |
| Фильтр периода | `_reportN_period`/`_reportN_data` в `views.py`; частая причина 500 — необработанный разбор дат |
| Экспорт Excel | `ReportNExportView` в `views.py`; для №2/№3 — листы сводки и диаграмм |
| Импорт/колонки | `uploads/excel_parser.py`, `uploads/forms.py`, `uploads/views.py` |
| Модели/админка/миграции | `production/models.py`, `production/admin.py`, `production/stations.py`, `production/testdata.py`, `production/migrations/`, `mes_report3/admin_site.py` |
| Бэкап | `backup/utils.py`, `backup/admin.py`, `templates/admin/backup/*` |
| Доступ | `accounts/views.py`, `production/admin.py` |

---

## 13. Документация и история

- `README.md` — установка, Docker, переменные окружения, troubleshooting.
- `AGENTS.md` — правила разработки для агентов (приоритет над этим файлом).
- `promt/promt_mes_reports/` — исходные ТЗ по отчётам и данные (включая `*.xlsx/csv`).
- `promt/plans/00-roadmap.md` … `04-db-rework.md` — планы доработок со статусами.
- История: `git log --oneline`; ключевые этапы — переработка отчёта №5, исправления
  P0/P1, hardening (H1–H9), рефакторинг общей логики, переработка БД (`0007–0013`).