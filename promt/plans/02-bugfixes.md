# 02. План исправления найденных багов (пункт B)

Дата: 2026-11-06
Область: `src/production/`, `src/reports/`, `src/uploads/`
Правило: каждая правка — отдельный атомарный дифф + тест; бизнес-логику расчётов не меняем.

Статус: **B1–B10 выполнены 2026-11-06**, кроме B7 — B7 выполнен по разрешению владельца (правка `AGENTS.md`). Тесты:
`test_admin_manual_defect_search_uses_existing_fields`, `test_report5_repeated_passes_has_no_default_limit`,
`test_report4_view_invalid_period_does_not_crash`, `test_report_exports_invalid_period_do_not_crash`,
`test_report1_export_defaults_to_current_year`, `test_report4_plasma_station_name_is_spelled_correctly`,
`test_report4_manual_defects_not_truncated_to_50`, `test_report8_ng_sns_have_no_extra_spaces`,
`test_report5_repeated_passes_fields_and_comment`. B8 покрыт существующими тестами парсера.

## 0. Сводка

| ID | Дефект | Тип | Приоритет | Файл | Оценка |
|---|---|---|---|---|---|
| B1 | Падение поиска в админке `ManualDefect` | 500 в админке | **P0** | `src/production/admin.py:87` | 15 мин |
| B2 | Отчёт №5 обрезан 50 строками | нарушение ТЗ | **P0** | `src/reports/queries.py:623` | 15 мин |
| B3 | HTTP 500 на некорректных датах периода | 500 на странице | **P0** | `src/reports/views.py:592, 1075, 1349` | 1 ч |
| B4 | Экспорт №1 по умолчанию отдаёт 30 дней | неверное умолчание | P1 | `src/reports/views.py:1070` | 20 мин |
| B5 | Опечатка `Pasma Cleaning` | неверные данные | P1 | `src/reports/queries.py:397` | 10 мин |
| B6 | Ручные браки обрезаны до 50 при `limit=None` | потеря данных | P1 | `src/reports/queries.py:553` | 30 мин |
| B7 | AGENTS.md противоречит коду по обязательным колонкам | документация | P1 | `AGENTS.md` | 20 мин |
| B8 | Дублирующийся импорт и неиспользуемый параметр в парсере | чистота кода | P1 | `src/uploads/excel_parser.py:127, 132` | 20 мин |
| B9 | `ng_sns`: разбор списка SN без `strip()` | устойчивость | P1 | `src/reports/queries.py:1121` | 20 мин |
| B10 | Отчёт №5: время проходов в UTC вместо `TIME_ZONE` | неверные данные | P1 | `src/reports/queries.py` | 30 мин |

Соответствие плану 01: **B2 ≡ R5-1** (одна и та же правка; выполняется в этапе 0, тест — в R5-2).
B5 и B6 касаются отчёта №4 и не пересекаются с переработкой отчёта №5.

## 1. B1 — Падение поиска в админке «Ручной брак» — **P0**

**Симптом.** `/admin/production/manualdefect/?q=<что угодно>` под суперпользователем →
`FieldError: Cannot resolve keyword 'comment' into field` (HTTP 500). Список без поиска работает.

**Причина.** `ManualDefectAdmin.search_fields = ["pcs_no", "production_spec", "lot_number", "comment"]`
(`src/production/admin.py:87`), но поле `comment` удалено из модели миграцией
`0005_remove_manualdefect_comment.py`. Комментарий ручного брака теперь хранится в `SNComment`.

**Проверено.** `ManualDefect._meta.fields` = `id, pcs_no, production_spec, lot_number, entry_date, created_by, created_at` —
поля `comment` нет.

**Правка.**

```python
search_fields = ["pcs_no", "production_spec", "lot_number"]
```

**Тест.** `tests/test_reports.py`:

```python
@pytest.mark.django_db
def test_admin_manual_defect_search_works():
    """Поиск в админке «Ручной брак» не падает (поле comment удалено из модели)."""
    ManualDefect.objects.create(pcs_no="SN-SEARCH", lot_number="LOT-1")
    client = Client()
    client.force_login(User.objects.create_superuser("root", "r@example.com", "pw"))
    response = client.get("/admin/production/manualdefect/", {"q": "SN-SEARCH"})
    assert response.status_code == 200
```

**Приёмка.** Поиск возвращает строку, ошибок нет. Проверить также `?q=` с пустой строкой и с `lot_number`.

**Риск.** Низкий: удаление поля из кортежа не влияет на отображение и фильтры.

## 2. B2 — Отчёт №5 обрезан 50 строками — **P0**

**Симптом.** На странице отчёта №5 и в экспорте никогда не бывает больше 50 строк, даже если повторов
больше; сводная информация считается по этим 50 строкам.

**Причина.** `report5_repeated_passes(start_date=None, end_date=None, limit=50)` (`src/reports/queries.py:623`).
`Report5View.get` и `Report5ExportView.get` лимит не передают → всегда применяется дефолт.

**Правка.** `limit=None` по умолчанию (см. R5-1 в [01-report5-rework.md](01-report5-rework.md)); параметр сохранить
для обратной совместимости.

**Тест.** R5-2, п.3 — 60 SN × 2 прохода → 60 строк.

**Приёмка.** Число строк на странице и в экспорте совпадает с числом повторов в выбранном периоде.

## 3. B3 — HTTP 500 на некорректных датах периода — **P0**

**Симптом.** `/reports/4/?filter=period&start=abc&end=2026-01-01` → `ValueError: time: format does not match`
и HTTP 500. То же для экспортов `/reports/1/export/` и `/reports/4/export/`. Пользователь видит ошибку
сервера вместо сообщения «Выбран некорректный период».

**Причина.** Три места вызывают `datetime.strptime` без обработки исключения:
`src/reports/views.py:592` (`Report4View`), `:1075` (`Report1ExportView`), `:1349` (`Report4ExportView`).
В остальных отчётах уже используется безопасный `_report7_date` (`src/reports/views.py:107`).

**Правка.** Везде использовать `_report7_date`:

```python
# Report4View
if filter_type == "period":
    start_date = _report7_date(request.GET.get("start"))
    end_date = _report7_date(request.GET.get("end"))
    if start_date is None or end_date is None:
        messages.error(request, "Выбран некорректный период.")
        start_date, end_date = get_date_range("90d")
    elif end_date < start_date:
        messages.error(request, "Дата начала не может быть позже даты окончания.")
        start_date, end_date = get_date_range("90d")
```

Для экспортов — то же без `messages`: при ошибке откат на умолчание своего отчёта
(№4 — `90d`, №1 — текущий год после B4).

**Тесты.**

```python
@pytest.mark.django_db
def test_report4_invalid_period_returns_200():
    response = Client().get("/reports/4/", {"filter": "period", "start": "abc", "end": "2026-01-01"})
    assert response.status_code == 200

@pytest.mark.django_db
def test_report_exports_invalid_period_return_200():
    assert Client().get("/reports/1/export/", {"filter": "period", "start": "x", "end": "y"}).status_code == 200
    assert Client().get("/reports/4/export/", {"filter": "period", "start": "x", "end": "y"}).status_code == 200
```

**Приёмка.** Некорректные даты → 200 + сообщение об ошибке (на странице) или файл с данными за период по умолчанию
(в экспорте). Обратный порядок дат обрабатывается так же.

**Риск.** Низкий; меняется только обработка ошибочного ввода. Валидные даты обрабатываются как раньше.

## 4. B4 — Экспорт отчёта №1: неверное умолчание периода — P1

**Симптом.** Прямой вызов `/reports/1/export/` без параметров отдаёт данные за **30 дней**
(`get_date_range("30d")`), тогда как страница отчёта №1 по умолчанию показывает **текущий год**.
При переходе по кнопке «Экспорт» из интерфейса параметры передаются, поэтому расхождение видно только
при прямом вызове/закладке.

**Причина.** `Report1ExportView.get`: `filter_type = request.GET.get("filter", "30d")` (`src/reports/views.py:1070`).
Для сравнения `Report4ExportView` использует `"90d"` — совпадает с умолчанием своей страницы.

**Правка.** `filter_type = request.GET.get("filter", "year")` и при некорректном периоде — откат на текущий год.

**Тест.** Экспорт без параметров вызывает `report1_orders(1 января текущего года, 31 декабря текущего года)`
(monkeypatch на `views.report1_orders` с записью аргументов).

**Приёмка.** Умолчания страницы и экспорта совпадают для отчётов №1 и №4.

**Риск.** Низкий, но меняет объём выгрузки для тех, кто открывал URL напрямую. Указать в описании коммита.

## 5. B5 — Опечатка `Pasma Cleaning` — P1

**Симптом.** В отчёте №4 в колонке «Последняя станция» для станции 30 выводится `Pasma Cleaning`.

**Причина.** `REPORT4_STATION_NAMES = {..., 30: "Pasma Cleaning", ...}` (`src/reports/queries.py:397`).
Правильное написание — `Plasma Cleaning` (так же в `STATION_POSITION_TRANSLATIONS` и `STATION_NAME_TRANSLATIONS`).

**Правка.** `30: "Plasma Cleaning",`.

**Тест.** `report4_defects` для SN, прошедшего станции 10 и 30 с OK → `last_station == "Plasma Cleaning"`.
Дополнительно — `REPORT8_COLUMNS`/график используют «Плазма», их не трогаем.

**Приёмка.** В отчёте №4 и его экспорте — правильное название.

**Риск.** Минимальный. Проверить, что существующие тесты не фиксируют старое написание (поиск по `Pasma`).

## 6. B6 — Отчёт №4: ручные браки обрезаются до 50 — P1

**Симптом.** При выборе периода в отчёте №4 (фильтр «Брак») отображается не больше 50 ручных записей
(`ManualDefect`), даже если их больше; экспорт ведёт себя так же. Основная SQL-часть при этом не ограничена.

**Причина.** `report4_defects` (`src/reports/queries.py:553`): `manual_defects = manual_defects.order_by("-created_at")[:50]` —
срез применяется всегда, независимо от аргумента `limit`.

**Правка.**

```python
manual_defects = manual_defects.order_by("-created_at")
if limit:
    manual_defects = manual_defects[:limit]
```

**Тест.** Создать 55 `ManualDefect` с `entry_date` внутри периода, при пустом результате SQL-части
(`defect_filter="defect"`, записей с `defect=True` нет) → `len(data) == 55` при `limit=None`.

**Приёмка.** Количество ручных строк соответствует БД за период; при явном `limit` ограничение работает.

**Риск.** Увеличение размера страницы при большом числе ручных браков; при необходимости — пагинация
(отдельная задача, не в этом плане).

## 7. B7 — AGENTS.md противоречит коду — P1

**Симптом.** `AGENTS.md` перечисляет 5 обязательных колонок Excel:
`Lot no., Subop no, PCSNo, CREATEDATE, result`. Фактически `REQUIRED_COLUMNS`
(`src/uploads/excel_parser.py:36`) требует 8: дополнительно `Production spec.`, `subop name`, `testData`.
Тесты `test_parse_missing_newly_required_column` это фиксируют.

**Причина.** Требования расширялись, документация не обновлялась.

**Правка (только документация).** В `AGENTS.md` заменить список на фактический:

```
- Required Excel columns:
  `Lot no.`, `Production spec.`, `Subop no`, `subop name`, `PCSNo`, `CREATEDATE`, `result`, `testData`
```

**Важно.** `AGENTS.md` — инструкция для агентов; правка выполняется **только после явного подтверждения**
владельца проекта. Альтернатива (не рекомендуется) — ослабить `REQUIRED_COLUMNS`, но это сломает импорт
и тесты, поэтому код парсера не меняем.

**Приёмка.** Список в AGENTS.md совпадает с `REQUIRED_COLUMNS`; тесты парсера не менялись.

## 8. B8 — Чистка `excel_parser.py` — P1

**Симптом.** В `import_to_database` два одинаковых импорта подряд и неиспользуемый параметр.

**Причина.** `src/uploads/excel_parser.py:127` и `:132` — `from production.models import ProductionRecord, LotInfo`
дважды; `created_by` принимается, но нигде не используется (аудит-полей у моделей импорта нет).

**Правка.** Удалить второй импорт; параметр `created_by` оставить (его передаёт `UploadFileView`,
и он часть публичной сигнатуры) и задокументировать в docstring как зарезервированный.

**Тест.** Существующие `test_import_dedup`, `test_import_lotinfo_created` должны остаться зелёными;
дополнительный тест не нужен.

**Приёмка.** Импорт работает, дублей импорта нет, `flake8`-подобных замечаний нет (линтер не вводим).

**Риск.** Нулевой.

## 9. B9 — `ng_sns` без `strip()` — P1

**Симптом.** При формировании списка SN с NG в отчёте №8
(`src/reports/queries.py:1121-1123`) строка `STRING_AGG(DISTINCT pcs_no, ', ')` разбивается по `","`
без обрезки пробелов. Сейчас незаметно (номера без пробелов), но при появлении пробелов в `pcs_no`
ссылки в шаблоне и экспорт получат значение с ведущим пробелом.

**Правка.**

```python
row[f"station_{station}_ng_sns"] = (
    [s.strip() for s in (r["ng_sns"] or "").split(",") if s.strip()]
    if r["ng_sns"] else []
)
```

**Тест.** Юнит-тест на `report8_stations` с SN, содержащим пробел после запятой в агрегате, либо прямой тест
разбора (проще — проверить, что `ng_sns` не содержит элементов с ведущими пробелами для двух SN).

**Приёмка.** Список NG SN в таблице и экспорте без лишних пробелов; ссылки на отчёт №6 корректны.

**Риск.** Нулевой.

## 9.1. B10 — время проходов в отчёте №5 выводилось в UTC — P1

**Найдено** при написании тестов R5-2 (2026-11-06).

**Симптом.** В отчёте №5 и его экспорте время проходов отличалось от остальных отчётов на величину
смещения `TIME_ZONE`: при `TIME_ZONE = "Europe/Moscow"` проход в 10:00 показывался как `07:00`.

**Причина.** `STRING_AGG(TO_CHAR(rr.created_date, 'YYYY-MM-DD HH24:MI:SS'))` в
`report5_repeated_passes` рендерил timestamp в часовом поясе сессии PostgreSQL. При `USE_TZ = True`
Django держит сессию в UTC, а остальные отчёты выводят время через шаблоны с `localtime` → в `TIME_ZONE`.

**Правка.**

```sql
STRING_AGG(
    TO_CHAR(rr.created_date AT TIME ZONE %s, 'YYYY-MM-DD HH24:MI:SS'),
    ', ' ORDER BY rr.created_date
) as dates,
```

`%s` — `settings.TIME_ZONE`; параметр добавлен в правильном порядке:
`params = date_params + [settings.TIME_ZONE] + date_params`.

**Тест.** `test_report5_repeated_passes_fields_and_comment` сравнивает строки с
`timezone.localtime(...)`, а не с захардкоженным временем.

**Приёмка.** Время в отчёте №5 совпадает с временем в отчётах №4/№6/№8 для того же прохода.

## 10. Не является багом (зафиксировано, чтобы не «чинить» зря)

- `apply_sort` (`src/reports/views.py:87`) — корректна, но O(n²) из-за `item not in none_items`; вынесено в H2.
- `inserted_count = after_count - before_count` (`src/uploads/excel_parser.py:162`) — неточно только при
  параллельных импортах; для текущего однопользовательского сценария приемлемо (H-план не включает).
- `Report5Comment` — не баг, а мёртвый код после переработки отчёта №5; решение в H4.

## 11. Порядок и валидация

1. B1 (админка) — 15 мин, тест отдельный.
2. B2/B3 — 1 ч, тесты отдельные.
3. B4, B5, B6 — 1 ч.
4. B8, B9 — 40 мин.
5. B7 — после подтверждения.

```powershell
$env:DJANGO_SETTINGS_MODULE="mes_report3.settings.dev"; $env:PYTHONPATH="src"
.\.venv\Scripts\python.exe src\manage.py check
.\.venv\Scripts\python.exe -m pytest tests/test_reports.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_excel_parser.py -q
```

**Условие запуска БД-тестов:** PostgreSQL должен быть запущен (`postgresql-x64-17`). Сейчас служба остановлена —
это первое действие перед выполнением плана.

## 12. Критерии завершения плана B

- [ ] Все пункты B1–B9 закрыты или явно отложены с причиной.
- [ ] Для B1–B6 и B9 есть тесты, падающие до правки.
- [ ] Полный `pytest` зелёный.
- [ ] `git log` содержит отдельные коммиты (минимум: «fix admin search», «fix period parsing», «fix report5 limit + tests»).
- [ ] Ни одна правка не затронула инварианты из README планов.
