# MES Reports

Django-приложение для загрузки выгрузок из MES-системы и построения производственных отчётов
по сборочной линии блоков управления двигателем (БУ).

Данные — прохождения станций (010…130) конкретными серийными номерами (SN). Из Excel-выгрузки
записи попадают в PostgreSQL, откуда строятся 8 отчётов с фильтрами, сводками и экспортом в Excel.

## Отчёты

| № | URL | Что показывает |
|---|---|---|
| 1 | `/reports/1/` | Сводный по заказам: лоты, план/факт, брак, ссылки на SN |
| 2 | `/reports/2/` | Производительность линии по дням: FOL/BOL, часы, выпуск, скорость |
| 3 | `/reports/3/` | То же по месяцам выбранного года |
| 4 | `/reports/4/` | Брак: ручные записи и БУ, не завершившие производство |
| 5 | `/reports/5/` | Повторные проходы станций + сводка по станциям |
| 6 | `/reports/6/` | Карточка SN: сводка, хронология, фото, комментарий |
| 7 | `/reports/7/` | Выпуск за период: уникальные SN со станции 130 со статусом OK |
| 8 | `/reports/8/` | Качество по станциям: OK/NG/% NG, разницы FOL/BOL, график |

Просмотр отчётов и экспорт в Excel доступны без авторизации. Изменение данных — только администраторам.

## Стек

- Python 3.12+, Django 5.2, PostgreSQL 14+
- pandas + openpyxl (разбор и экспорт Excel), psycopg2, python-dotenv, django-widget-tweaks
- gunicorn + nginx (в Docker), pytest + pytest-django (тесты)

## Структура

```
src/
  manage.py            точка входа
  mes_report3/         настройки: base.py, dev.py, prod.py
  accounts/            вход/выход, декоратор admin_required
  production/          модели данных и админка
  uploads/             приём Excel и импорт с дедупликацией
  reports/             queries.py (SQL и агрегации), views.py (страницы и экспорт)
  templates/           шаблоны (Bootstrap 5, Chart.js)
tests/                 pytest-тесты
docker/                Dockerfile, docker-compose, nginx
promt/                 ТЗ (promt_mes_reports) и планы работ (plans)
```

## Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) для зависимостей
- PostgreSQL **14+** (рекомендуется 17 — как в Docker-образе)

## Быстрый старт

1. Установить зависимости:

   ```bash
   uv sync --frozen
   ```

2. Создать роль и базу (кодировка обязательно UTF-8):

   ```sql
   CREATE ROLE mes_user LOGIN PASSWORD 'mes_pass' CREATEDB;
   CREATE DATABASE mes_report
       OWNER mes_user
       ENCODING 'UTF8'
       LC_COLLATE 'C'
       LC_CTYPE 'C'
       TEMPLATE template0;
   ```

   `CREATEDB` нужен pytest-django для создания тестовой базы `test_mes_report`.

3. Скопировать переменные окружения (необязательно — по умолчанию совпадают с шагом 2):

   ```bash
   cp .env.example src/.env
   ```

   Файл `.env` читается из `src/` (там находится `BASE_DIR`).

4. Применить миграции и создать администратора:

   ```bash
   uv run python src/manage.py migrate
   uv run python src/manage.py createsuperuser
   ```

5. Запустить сервер разработки:

   ```bash
   uv run python src/manage.py runserver
   ```

   Настройки по умолчанию — `mes_report3.settings.dev` (их подставляет `manage.py`).
   Загружать выгрузки можно после входа: раздел «Загрузка Excel» (`/upload/`).

## Тесты

```bash
uv run pytest
```

Тесты, работающие с БД, требуют запущенного PostgreSQL: pytest-django создаёт и удаляет
базу `test_mes_report`, поэтому у роли должно быть право `CREATEDB`.

## Docker

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Стек: `db` (PostgreSQL 17), `web` (gunicorn), `nginx` (публикует `127.0.0.1:8000`).
При старте контейнер применяет миграции, собирает статику и запускает gunicorn.

Обязательные переменные в `docker/.env`:

| Переменная | Назначение |
|---|---|
| `DJANGO_SECRET_KEY` | без неё prod-настройки не запускаются |
| `DJANGO_ADMIN_PASSWORD` | пароль создаваемого суперпользователя `admin`; без неё пользователь не создаётся |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | доступ к контейнерной БД |

Данные БД и медиафайлы хранятся в томах `postgres_data` и `media_volume`, поэтому пересборка образа
их не удаляет.

## Переменные окружения

| Переменная | По умолчанию | Комментарий |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev-ключ | в prod обязательна |
| `DJANGO_DEBUG` | `True` (dev) | в prod по умолчанию `False` |
| `DJANGO_ALLOWED_HOSTS` | `localhost 127.0.0.1` | список через пробел |
| `DJANGO_HTTPS` | `false` | включает SSL-redirect и secure-cookies |
| `POSTGRES_DB` | `mes_report` | |
| `POSTGRES_USER` | `mes_user` | |
| `POSTGRES_PASSWORD` | `mes_pass` | |
| `POSTGRES_HOST` | `localhost` | в compose — `db` |
| `POSTGRES_PORT` | `5432` | |

## Роли и доступ

- **Анонимно** — просмотр отчётов №1–№8 и экспорт в Excel.
- **staff** (`is_staff`) — загрузка Excel, правка плана и комментария лота, ручной брак,
  комментарии SN, флаг Defect, фотографии; бизнес-модели в админке (кроме `Production` — только чтение).
- **superuser** — пользователи и группы, резервное копирование/восстановление/очистка данных.

## Troubleshooting

**`uv: failed to open ... AppData\Local\uv\cache`** — нет доступа к кешу uv (бывает в песочницах).
Используйте интерпретатор из виртуального окружения:

```powershell
.\.venv\Scripts\python.exe src\manage.py check
.\.venv\Scripts\python.exe -m pytest
```

**`OperationalError: connection ... refused`** — не запущен PostgreSQL:

```powershell
Get-Service postgresql-x64-17
net start postgresql-x64-17
```

**Порт 8000 занят** (`docker`/nginx уже слушает) — запустите dev-сервер на другом порту:

```powershell
.\.venv\Scripts\python.exe src\manage.py runserver 127.0.0.1:8001
```

**Кракозябры в комментариях** — база создана не в UTF-8. Проверка:

```sql
SELECT datname, pg_encoding_to_char(encoding) FROM pg_database;
```

**Время в отчёте отличается от ожидаемого** — отчёты выводят время в `TIME_ZONE`
(`Europe/Moscow`), а не в поясе браузера.

## Документация

- `AGENTS.md` — правила разработки для агентов и обязательные инварианты.
- `promt/promt_mes_reports/` — исходные ТЗ по отчётам (Obsidian).
- `promt/plans/` — планы работ: `00-roadmap.md`, `01-report5-rework.md`, `02-bugfixes.md`, `03-hardening.md`.
