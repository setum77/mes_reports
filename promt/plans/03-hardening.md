# 03. Техдолг, производительность и безопасность деплоя

Дата: 2026-11-06
Статус: **H1, H2, H3, H5, H6, H7, H9 выполнены** 2026-11-06: LotInfo одним `in_bulk`; `apply_sort` в один
проход; лот в SQL отчёта №4; добавлен `.dockerignore`; суперпользователь создаётся только при заданном
`DJANGO_ADMIN_PASSWORD`; prod требует `DJANGO_SECRET_KEY`; создан `README.md` с запуском, тестами,
Docker и troubleshooting. H4 (решение по модели) и H8 (дедупликация view/export) — не начаты.
Цель: снять узкие места и риски, которые не являются функциональными багами, но мешают развитию проекта.
Все задачи — после закрытия P0/P1 из [02-bugfixes.md](02-bugfixes.md).

## 0. Сводка

| ID | Задача | Приоритет | Файлы | Оценка |
|---|---|---|---|---|
| H1 | Убрать N+1 в `report1_orders` | P2 | `src/reports/queries.py:190` | 1 ч |
| H2 | `apply_sort`: убрать O(n²) | P2 | `src/reports/views.py:69` | 30 мин |
| H3 | Фильтр «По лоту» — в SQL (отчёты №4, №5) | P2 | `src/reports/queries.py`, `views.py` | 3 ч |
| H4 | Решение по мёртвой модели `Report5Comment` | P2 | `production/`, `backup/utils.py`, `admin_site.py`, `tests/` | 1 ч |
| H5 | `.dockerignore` | P2 | корень репозитория | 20 мин |
| H6 | Убрать дефолтный пароль `admin123` | **P2** | `docker/entrypoint.sh:13` | 30 мин |
| H7 | `SECRET_KEY` без дефолта в prod | **P2** | `src/mes_report3/settings/{base,prod}.py` | 20 мин |
| H8 | Дедупликация логики view ↔ export | P3 | `src/reports/views.py` | 2 ч |
| H9 | `README.md` + требование PostgreSQL для тестов | P3 | корень | 1 ч |

## 1. H1 — N+1 в отчёте №1

**Проблема.** `report1_orders` внутри цикла по строкам делает отдельный запрос `LotInfo` на каждый лот
(`src/reports/queries.py:190-191`, анкор `from production.models import LotInfo` внутри `for i, row in enumerate(rows, 1)`).
При 500 лотах — 501 запрос.

**Правка.** Один запрос до цикла:

```python
lot_numbers = [row["lot_number"] for row in rows]
lot_infos = LotInfo.objects.in_bulk(lot_numbers, field_name="lot_number")
...
lot_info = lot_infos.get(row["lot_number"])
```

`LotInfo.lot_number` объявлен `unique=True`, поэтому `in_bulk(field_name=...)` применим.
Импорт `LotInfo` вынести в начало функции (сейчас он внутри цикла).

**Тест.** Существующие `test_report1_orders`, `test_report1_summary`, `test_report1_view_*` должны остаться зелёными.
Дополнительно — фиксация числа запросов через `django_assert_num_queries` (pytest-django):

```python
@pytest.mark.django_db
def test_report1_orders_query_count(django_assert_num_queries):
    # подготовка 5 лотов
    with django_assert_num_queries(1):  # только LotInfo (+ подготовка вне блока)
        report1_orders(date(2026, 1, 1), date(2026, 12, 31))
```

Точное число запросов выяснить при реализации (1 SQL отчёта + 1 `LotInfo`).

**Приёмка.** Число запросов не зависит от количества лотов; результаты идентичны.

## 2. H2 — `apply_sort`: O(n²)

**Проблема.** `apply_sort` (`src/reports/views.py:69-89`) строит `non_none` через
`[item for item in data if item not in none_items]` — сравнение словарей на каждом элементе, O(n²).
Корректность при этом сохраняется (ключ `None` возвращает `(1,)`, поэтому сравнение по значению
не путает строки с `None` и без), поэтому это задача производительности, а не баг.

**Правка.** Один проход:

```python
keyed = [(get_key(item), item) for item in data]
with_values = [(k, item) for k, item in keyed if k[0] != 1]
none_items = [item for k, item in keyed if k[0] == 1]
with_values.sort(key=lambda pair: pair[0], reverse=(sort_dir == "desc"))
return [item for _, item in with_values] + none_items
```

**Тест.** Существующие `test_apply_sort_*` (включая `none_values`) — обязательны; добавить тест на 10 000 строк
(время выполнения не измерять, только корректность и отсутствие рекурсии).

**Приёмка.** Поведение сортировки идентично текущему, включая «None в конец» при `desc`.

## 3. H3 — Фильтр «По лоту» в SQL (отчёты №4 и №5)

**Проблема.** При `filter_type == "lot"` отчёты №4 и №5 читают **все** записи за всю историю и фильтруют
по подстроке лота в Python:

- `Report4View.get` / `Report4ExportView.get`: `start_date, end_date = None, None`, затем
  `if lot_filter: data = [d for d in data if lot_filter.lower() in ...]`.
- `Report5View.get` / `Report5ExportView.get`: то же (см. R5-4).

Для сравнения: отчёты №2 и №8 уже передают лот в SQL (`report2_line_productivity(..., lot_number=...)`,
`report8_stations(..., lot_number=...)`).

**Правка.** Добавить необязательный `lot_number` в `report4_defects` и `report5_repeated_passes`,
условие в SQL — с сохранением текущей семантики подстроки:

```sql
AND r.lot_number ILIKE '%' || %s || '%'
```

Для ручных браков в `report4_defects` — `ManualDefect.objects.filter(lot_number__icontains=lot_number)`.
Python-фильтр оставить как страховку (после сужения выборки он дешёвый).

**Важно.** Семантика должна остаться подстрокой (регистронезависимой), иначе изменится поведение.
Если пользователь захочет точное совпадение — это отдельное решение, оформить явно.

**Тесты.** Для каждого отчёта: одинаковый результат при фильтре по полному лоту и по фрагменту;
лота, которого нет, — пустой список; при этом SQL получает параметр (проверить через
`django_assert_num_queries` + `CaptureQueriesContext` — в запросе присутствует `ILIKE`).

**Приёмка.** Отчёт не читает записи других лотов; результаты совпадают с текущими.

## 4. H4 — Мёртвая модель `Report5Comment`

**Состояние.** После переработки отчёта №5 (`Report5CommentFormView` удалён) модель
`Report5Comment` (`src/production/models.py:100`) не используется в UI. При этом она остаётся в:

- `src/production/admin.py:120` (`Report5CommentAdmin`, регистрация);
- `src/backup/utils.py:44` (`PRODUCTION_MODELS`) — используется очисткой и подсчётом строк;
- `src/mes_report3/admin_site.py:47,65,85` — метрика дашборда «report5_comments»;
- `src/templates/admin/index.html:54` — блок дашборда;
- `tests/test_reports.py` (импорт, `model_names`, `report5comment` changelist/add, метрики).

**Вариант A (рекомендуется) — оставить, пометить deprecated.**
- В docstring модели: «Не используется в UI с 2026-11; сохранена для совместимости старых бэкапов».
- Кода не трогаем, тесты не меняем.
- Риск: ноль. Минус: остаётся «мёртвый» раздел в админке.

**Вариант B — удалить полностью.**
- Новая миграция `DeleteModel`, удаление админки, записей в `PRODUCTION_MODELS`, метрик и блока дашборда,
  правка тестов (минимум 7 мест).
- **Существенный риск:** восстановление старых бэкапов идёт через `loaddata` JSON-фикстуры
  (`src/backup/utils.py:367`, `_restore_database`). Если в фикстуре есть записи `production.report5comment`,
  после удаления модели `loaddata` упадёт с ошибкой десериализации. Старые бэкапы станут непригодны.
- Поэтому вариант B допустим только после того, как: (а) принято решение, что старые бэкапы не нужны,
  либо (б) добавлена предварительная фильтрация фикстуры при восстановлении.

**Приёмка.** При варианте A — только docstring; при B — миграции применяются, `pytest` зелёный,
восстановление свежего бэкапа проверено вручную, старые бэкапы — по согласованному решению.

## 5. H5 — `.dockerignore`

**Проблема.** Файла нет. Контекст сборки — корень репозитория: `.venv/` (сотни МБ), `.git/`, `media/` (фото),
`backups/`, `promt/`, `.kilo/`, `.pytest_cache/`. Это замедляет сборку и может «утащить» в образ лишние данные
(`COPY src/` их не копирует, но контекст передаётся целиком).

**Правка.** Создать `.dockerignore`:

```
.git
.gitignore
.venv
venv
__pycache__
*.py[cod]
.pytest_cache
.kilo
promt
media
backups
*.log
.env
.env.*
!docker/.env.example
```

**Приёмка.** `docker build` проходит; `docker build` без `.dockerignore` vs с ним — размер контекста меньше
в разы; `.env` не попадает в образ.

## 6. H6 — Дефолтный пароль администратора — **P2**

**Проблема.** `docker/entrypoint.sh:13-19` создаёт суперпользователя `admin` с паролем
`${DJANGO_ADMIN_PASSWORD:-admin123}`. Если переменная не задана, в проде появляется учётка `admin/admin123`.

**Правка.** Создавать администратора только при явно заданном пароле; иначе — предупреждение в лог и пропуск:

```bash
if [ -n "${DJANGO_ADMIN_PASSWORD}" ]; then
    echo "Creating superuser (if not exists)..."
    uv run python src/manage.py shell -c "..."
else
    echo "DJANGO_ADMIN_PASSWORD is not set — superuser creation skipped."
fi
```

Дополнительно: в `docker/.env.example` (если есть/будет) указать переменную как обязательную для первичного запуска.

**Приёмка.** Без переменной контейнер стартует, суперпользователь не создаётся; с переменной — создаётся.
Проверить на чистом томе `postgres_data`.

**Риск.** Для существующих установок с уже созданным `admin` ничего не меняется.

## 7. H7 — `SECRET_KEY` в продакшене

**Проблема.** `src/mes_report3/settings/base.py:10` задаёт дефолт
`"dev-secret-key-change-in-production"`. В `prod.py` он не проверяется — при незаданной переменной
прод работает с публично известным ключом (подделка сессий/CSRF).

**Правка.** В `prod.py`:

```python
from django.core.exceptions import ImproperlyConfigured

if not os.environ.get("DJANGO_SECRET_KEY"):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production")
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
```

Дефолт в `base.py` оставить (нужен для dev и тестов).

**Тест.** Юнит-тест: импорт `mes_report3.settings.prod` без переменной через `importlib.reload` в изолированном
`monkeypatch.delenv` → `ImproperlyConfigured`. Аккуратно: модуль настроек импортируется один раз, поэтому тест
должен подгружать файл заново и не влиять на остальные тесты (использовать `importlib.util.spec_from_file_location`).

**Приёмка.** `prod` без ключа не стартует; `dev` и тесты не затронуты.

## 8. H8 — Дедупликация view ↔ export

**Проблема.** Разбор периода и подготовка данных дублируются между `Report1View`/`Report1ExportView`,
`Report4View`/`Report4ExportView`, `Report5View`/`Report5ExportView`, `Report7View`/`Report7ExportView`
(после B3 часть кода станет ещё более похожей).

**Правка.** Вынести в хелперы рядом с `_report*_period`:

```python
def _report4_data(request):
    """Возвращает (data, context) для страницы и экспорта отчёта №4."""
```

и использовать в обоих местах. Экспорт при этом получает ровно те же строки, что и страница.

**Приёмка.** Тесты экспорта и страницы проходят без изменений; дублирующихся блоков не осталось.

**Риск.** Рефакторинг без изменения поведения — выполнять после B3/B4 и только с полным прогоном тестов.

## 9. H9 — README и фиксация требований к тестам

**Проблема.** В репозитории нет `README.md`; порядок запуска известен только из `AGENTS.md`.
БД-тесты требуют PostgreSQL, который не поднимается автоматически; в песочнице `uv` может быть недоступен.

**Правка.** Создать `README.md` (кратко): назначение, стек, структура, `.env`, миграции, запуск dev,
Docker, тесты (с обязательным требованием PostgreSQL), список отчётов и прав.
Дополнительно — раздел «Troubleshooting» с двумя пунктами: `uv` и остановленная служба PostgreSQL.

**Приёмка.** Новый разработчик проходит путь «клон → `.env` → миграции → тесты» по README без обращения к коду.

## 10. Порядок выполнения

```
H1 → H2 → H5 → H6 → H7 → R5-4/H3 → H4 (решение) → H8 → H9
```

H1/H2 — изолированные правки с тестами. H5–H7 не трогают приложение. H3 требует согласования семантики лота.
H4 — управленческое решение. H8 — рефакторинг после стабилизации. H9 — в конце, чтобы описать итоговое состояние.

## 11. Валидация

```powershell
$env:DJANGO_SETTINGS_MODULE="mes_report3.settings.dev"; $env:PYTHONPATH="src"
.\.venv\Scripts\python.exe src\manage.py check
.\.venv\Scripts\python.exe -m pytest -q
docker compose -f docker/docker-compose.yml build
```

Для H6/H7 дополнительно — ручная проверка на чистом окружении (без `DJANGO_ADMIN_PASSWORD` и `DJANGO_SECRET_KEY`).

## 12. Критерии завершения

- [ ] H1–H3 не меняют результаты отчётов (подтверждено тестами).
- [ ] H4 — решение зафиксировано в этом файле (A или B) и выполнено.
- [ ] H5–H7 — деплой без дефолтных секретов; сборка Docker проходит.
- [ ] H8 — поведение идентично, дублирование устранено.
- [ ] H9 — README покрывает запуск, тесты и Docker.
