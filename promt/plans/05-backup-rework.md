# 05. Переработка раздела резервного копирования

Дата: 2026-11-13
Основание: `promt/promt_mes_reports/Backup.md` (6 требований)
Статус: **реализовано** 2026-11-13

---

## 1. Цель и границы

Привести раздел `/admin/backup/` к виду: один заголовок, три кнопки, таблица бэкапов;
создание бэкапа — с реальным прогрессом; после создания/восстановления — возврат
в раздел с сообщением о статусе.

В объём входят:

- вёрстка страниц `templates/admin/backup/*`;
- прогресс создания бэкапа и восстановления (включая загрузку архива);
- передача статуса операции на главную страницу раздела;
- удаление неиспользуемых страниц/форм/ссылок;
- тесты.

Не входят:

- изменение формата бэкапа, манифеста и алгоритма `dumpdata`/`loaddata`;
- изменение логики восстановления данных и порядка моделей;
- новые зависимости;
- миграции БД;
- изменение прав доступа (раздел остаётся только для superuser).

---

## 2. Текущее состояние и проблемы

| Где | Проблема |
|---|---|
| `src/templates/admin/backup/index.html:7` | `<h1>{{ title }}</h1>` дублирует `{% block content_title %}` из `django/contrib/admin/templates/admin/base.html:101`. То же в `create.html:6`, `restore_confirm.html:6`, `restore_progress.html:6`, `restore_upload.html:6`, `restore_upload_confirm.html:6`, `wipe.html:6`, `list.html:6`, `restore.html:6`. |
| `src/templates/admin/backup/index.html:18-24` | Дублирует вывод `messages` из `base.html:93`. |
| `src/templates/admin/backup/index.html:10-16` | Пять кнопок; лишние «Список бэкапов» и «Восстановить из бэкапа». |
| `src/templates/admin/backup/list.html` | Список бэкапов вынесен на отдельную страницу, на главной его нет. |
| `src/backup/admin.py:70-81`, `src/templates/admin/backup/create.html` | Создание бэкапа — синхронный POST без прогресса. `create_backup_bg` (`admin.py:83-102`) и `_set_progress` (`utils.py:90-99`) уже есть, но к UI не подключены. |
| `src/backup/utils.py:90-126` | Прогресс хранит только `step/message`; нет `percent/status`. |
| `src/backup/admin.py:104-111` | `progress_view` считает завершением только отсутствие файла. Ошибки (`step=0` без `status`) JS не распознаёт и опрашивает бесконечно. |
| `src/templates/admin/backup/restore_progress.html:63-65`, `restore_upload_confirm.html:77-79` | После завершения идёт редирект на `/admin/backup/`, но сообщение об успехе не передаётся: фоновый поток не имеет `request`. |
| `src/backup/admin.py:148-165`, `113-134`, `167-186` | `restore_view`/`RestoreForm`/`restore.html`, `list_backups_view`/`list.html`, `restore_backup_bg` после переработки не нужны. |

---

## 3. Целевая схема

1. `/admin/backup/` — один h1 «Резервное копирование» (из admin base), описание,
   три кнопки: **«Создать бэкап»**, **«Восстановить из архива»**,
   **«Очистить все данные»**. Под ними — таблица бэкапов:
   имя, время создания, размер, записей, файлы, действия **«Восстановить»** и
   **«Скачать»**, пагинация по 20.
2. «Создать бэкап» → `create.html` (один h1 «Создание бэкапа», без дублей) →
   кнопка запускает `backup_create_bg` → прогресс-бар с процентами и этапами →
   после завершения редирект на `/admin/backup/?task=<id>` → сообщение и таблица
   с новым бэкапом.
3. «Восстановить» в строке таблицы → `restore_confirm` → прогресс →
   редирект на `/admin/backup/?task=<id>` → сообщение и таблица.
4. «Восстановить из архива» → `restore_upload` (inspect + XHR upload) →
   прогресс: 0–50% загрузка файла, 50–100% серверная обработка →
   редирект на `/admin/backup/?task=<id>` → сообщение и таблица.
5. Ошибка — красный статус, сообщение, остановка опроса, кнопка
   «Назад в панель управления».
6. Старые URL `backup/list/` и `backup/restore/` — редирект на `backup_index`
   (совместимость). `backup_restore_bg` удаляется.

---

## 4. Задачи

### B1. Убрать дубли заголовков и сообщений

- Удалить `<h1>{{ title }}</h1>` из всех `src/templates/admin/backup/*.html`:
  admin base уже выводит заголовок из `title`.
- Удалить блок `{% if messages %}` из `index.html`: admin base выводит сообщения.
- При правке шаблонов убрать неиспользуемые `{% load i18n widget_tweaks %}`.

**Приёмка.** На каждой странице ровно один видимый `h1`; сообщения выводятся один раз.

### B2. Оставить три кнопки

В `index.html` оставить только:

- `{% url 'mes_admin:backup_create' %}` — «Создать бэкап»;
- `{% url 'mes_admin:backup_restore_upload' %}` — «Восстановить из архива»;
- `{% url 'mes_admin:backup_wipe' %}` — «Очистить все данные».

Удалить ссылки `backup_list` и `backup_restore`.

**Приёмка.** На странице нет кнопок/ссылок «Список бэкапов» и
«Восстановить из бэкапа».

### B3. Таблица бэкапов на главной

- Создать `src/templates/admin/backup/_backup_table.html` на основе `list.html`:
  таблица и пагинация, без `h1` и без ссылки «Назад».
- `index_view` (`admin.py:58-68`):
  - `backups = list_backups()`;
  - `paginator = Paginator(backups, 20)`;
  - `page_obj = paginator.get_page(request.GET.get("page"))`;
  - `backup_infos` — по `get_backup_info(b["name"])` для элементов `page_obj`;
  - передать в контекст `backups=backup_infos`, `page_obj`,
    `backup_count=paginator.count`.
- `index.html`: `{% include "admin/backup/_backup_table.html" %}`.
- `list_backups_view` и `list.html` удалить; URL `backup/list/` заменить на
  редирект `backup_index`.

**Приёмка.** Таблица отображается под кнопками, пагинация работает, есть пустое
состояние «Нет доступных бэкапов.».

### B4. Реальный прогресс создания бэкапа

#### B4.1. Схема прогресса

В `utils.py` расширить `_set_progress` (`utils.py:90-99`):

```python
_set_progress(task_id, step, message, total_steps=None, percent=None, status="running")
```

Файл прогресса получает поля:

```json
{
  "status": "running | completed | error",
  "step": 1,
  "total_steps": 4,
  "percent": 42,
  "message": "..."
}
```

Старые файлы без `status` интерпретируются как `running`, кроме `step == 0` —
как `error`.

Добавить `consume_progress(task_id)` — читает файл и удаляет его (используется
главной страницей, чтобы сообщение показалось один раз).

#### B4.2. Дамп БД

`create_db_dump(backup_dir, task_id=None)` (`utils.py:205-217`):

- до дампа посчитать `total = sum(_get_model_counts().values())`;
- писать дамп через wrapper, который считает вхождения `"model":` в JSON и
  обновляет прогресс 5–55%:

```python
class _DumpProgressWriter:
    def write(self, data):
        self.target.write(data)
        if self.total:
            self.count += data.count('"model":')
            percent = 5 + int(self.count / self.total * 50)
            if percent != self.last_percent:
                self.last_percent = percent
                _set_progress(
                    self.task_id, 1,
                    "Создание дампа БД... {}/{}".format(self.count, self.total),
                    total_steps=4, percent=percent,
                )

    def flush(self):
        self.target.flush()
```

- `call_command("dumpdata", "production", "--natural-foreign",
  "--natural-primary", "--indent=2", stdout=writer)`;
- формат и содержимое `database.json` не меняются.

#### B4.3. Архив медиа

`create_media_archive(backup_dir, task_id=None)` (`utils.py:220-231`):

- до упаковки посчитать суммарный размер файлов `media_root`;
- в `tar.add(media_root, arcname="media", filter=filter)` в `filter` накапливать
  `tarinfo.size` и обновлять прогресс 55–90% не чаще одного изменения процента;
- `filter` обязан возвращать `tarinfo`;
- если медиа нет — сразу выставить 90%.

#### B4.4. Сборка бэкапа

`create_full_backup(task_id=None)` (`utils.py:234-280`):

- этапы: 0–5% — старт, 5–55% — дамп, 55–90% — медиа, 90–100% — манифест и
  контрольная сумма;
- финал: `_set_progress(task_id, 4, "Бэкап '<name>' успешно создан.",
  total_steps=4, percent=100, status="completed")`;
- `clear_progress` при успехе **не вызывать**: файл нужен главной странице для
  сообщения (удаляется через `consume_progress`);
- при исключении: `status="error"`, `percent=0`, сообщение `Ошибка: ...`, `raise`.

#### B4.5. UI создания

- `create.html`: убрать `h1`; форма с `{% csrf_token %}`; кнопка «Создать бэкап»;
  при submit — `fetch` на `backup_create_bg` с `X-CSRFToken`; получить `task_id`
  и вызвать `MesBackupProgress.start(task_id, {minPercent: 0, maxPercent: 100})`;
  fallback без JS — обычный POST на `backup_create` (синхронный, как сейчас).
- `admin.py` `create_backup_bg` (`admin.py:83-102`): thread wrapper с
  `try/except`, начальный `_set_progress(task_id, 0, "Запуск создания бэкапа...")`.

**Приёмка.** Бар движется во время дампа и архивирования; после завершения —
главная страница с сообщением и новой строкой; при ошибке опрос
останавливается, показывается красный статус.

### B5. Статус после операций и общий прогресс-бар

#### B5.1. `progress_view`

`admin.py:104-111`:

- если файла нет — `{"status": "completed", "step": 4, "total_steps": 4,
  "percent": 100, "message": "Готово!"}`;
- если файл есть, но нет `status`: `step == 0` → `error`, иначе `running`;
- вернуть данные как есть.

#### B5.2. Главная страница

`index_view`:

```python
task_id = request.GET.get("task")
if task_id:
    data = get_progress(task_id)
    if data and data.get("status") in ("completed", "error", None):
        consume_progress(task_id)
        if data.get("status") == "error" or data.get("step") == 0:
            messages.error(request, data.get("message", "Ошибка операции."))
        else:
            messages.success(request, data.get("message", "Операция завершена."))
    return redirect("mes_admin:backup_index")
```

Редирект на чистый URL защищает от повторного показа сообщения при F5.

#### B5.3. Общий partial

Создать `src/templates/admin/backup/_progress.html`:

- разметка контейнера прогресса (скрыт, показывается функцией `show`);
- JS `window.MesBackupProgress`:
  - `show()` — показать контейнер;
  - `setProgress(percent, message)` — обновить ширину и текст (0–100);
  - `fail(message)` — красный 100%, «Ошибка», остановить опрос;
  - `start(taskId, {minPercent, maxPercent, totalSteps, redirectUrl})` —
    опрашивать `/admin/backup/progress/<taskId>/`, маппить `data.percent`
    (или `step/total_steps`) в диапазон `minPercent..maxPercent`; при
    `completed` — показать сообщение, через 1.5 с
    `redirectUrl + "?task=" + taskId`; при `error` — `fail`.
- если в partial передан `task_id`, на `DOMContentLoaded` вызвать `start`
  (для `restore_progress` и `restore_upload_confirm`); для `create` и
  `restore_upload` `task_id` не передаётся, страница вызывает `start` сама.

**Приёмка.** После создания/восстановления на главной ровно одно сообщение и
таблица; дублей нет.

### B6. Восстановление из бэкапа и из архива

#### B6.1. Реальный прогресс `loaddata`

`_do_load_data` (`utils.py:347-367`):

- `verbosity=3` (при `verbosity=2` Django не выводит `Processed N object(s).`);
- `stdout` — `io.StringIO`-подобный writer, который в `write` ищет
  `Processed (\d+) object` и обновляет прогресс:
  - `restore_backup` — `base_percent=10`, `span_percent=50` (10–60%);
  - `upload_and_restore` — `base_percent=20`, `span_percent=50` (20–70%);
- `total_records` — из `manifest.db_record_count`; для архива без манифеста —
  подсчёт элементов `database.json` либо fallback на этапный прогресс;
- вывод `loaddata` по-прежнему собирается в строку для логов/ошибок.

#### B6.2. Этапы

`restore_backup` (`utils.py:440-500`), `_restore_database`
(`utils.py:370-404`), `_restore_media` (`utils.py:407-437`):

- старт — 5%;
- очистка — 10%;
- `loaddata` — 10–60% (для upload 20–70%);
- медиа — 60–90% (для upload 70–90%);
- финал — 100%, `status="completed"`, сообщение из возврата функции;
- все ранние `return False` (нет бэкапа, битый манифест, нет `database.json`,
  нет медиа) — `status="error"`, `percent=0`, сообщение.

`upload_and_restore` (`utils.py:674-795`), `_restore_database_internal`
(`utils.py:798-827`):

- этапы: 1 — сохранение архива 5%, 2 — распаковка 15%, 3 — БД 20–70%,
  4 — медиа 70–90%, 5 — финал 100%;
- финал/ошибка — `status="completed"`/`"error"`, сообщение;
- `clear_progress` при успехе не вызывать.

#### B6.3. Страницы восстановления

- `restore_confirm.html`: убрать `h1`; cancel → `backup_index`.
- `restore_progress.html`: убрать `h1`; вместо inline-прогресса включить
  `_progress.html` с `task_id` (авто-старт).
- `restore_upload_confirm.html`: убрать `h1`; включить `_progress.html`
  с `task_id` (авто-старт).
- `restore_upload.html`:
  - убрать `h1`;
  - оставить XHR upload и inspect;
  - upload progress 0–50% через `MesBackupProgress.setProgress`;
  - после успешного ответа `restore-upload-bg` вызвать
    `MesBackupProgress.start(taskId, {minPercent: 50, maxPercent: 100})`;
  - ошибки inspect показывать в блоке информации об архиве, а не в скрытом
    прогрессе.
- `download_view` (`admin.py:136-146`): ошибка → `redirect("mes_admin:backup_index")`.

**Приёмка.** Восстановление из строки таблицы и из загруженного архива
показывает реальный прогресс, завершается сообщением на главной; ошибки видны и
не зацикливают опрос.

### B7. Удалить неиспользуемое

- `admin.py`:
  - удалить `list_backups_view`, `restore_view`, `restore_backup_bg`;
  - удалить импорт `RestoreForm`;
  - URL `backup/list/` и `backup/restore/` — `redirect_to_index` (метод
    `BackupViews`, возвращает `redirect("mes_admin:backup_index")`);
  - URL `backup/restore-bg/` удалить.
- `forms.py`: удалить `RestoreForm` (`forms.py:4-19`).
- Удалить `src/templates/admin/backup/list.html` и
  `src/templates/admin/backup/restore.html`.
- Обновить ссылки: `restore_confirm` cancel → `backup_index`; `download_view`
  error → `backup_index`.
- При правке `admin.py` убрать неиспользуемые импорты (`_read_manifest`,
  `PROJECT_IDENTIFIER`, если не используются).

**Приёмка.** `manage.py check` чист; нет битых ссылок; старые URL
`/admin/backup/list/` и `/admin/backup/restore/` открывают главную.

### B8. Тесты и проверка

#### B8.1. `tests/test_backup.py`

- `setUp`: `tempfile.mkdtemp()` + `override_settings(BACKUP_ROOT=..., MEDIA_ROOT=...)`,
  cleanup; `User.objects.create_superuser`, `client.force_login`.
- Главная:
  - `assertContains(response, "<h1>Резервное копирование</h1>", html=True, count=1)`;
  - есть «Создать бэкап», «Восстановить из архива», «Очистить все данные»;
  - нет «Список бэкапов» и «Восстановить из бэкапа»;
  - таблица содержит имя тестового бэкапа и «Скачать».
- `create.html`: 200, есть `progress-container`/`MesBackupProgress`, нет дубля h1.
- `progress_view`:
  - `_set_progress(task_id, 1, "...", total_steps=4, percent=42)` → JSON
    `status="running"`, `percent=42`;
  - `status="error"` → JSON `status="error"`;
  - отсутствие файла → `status="completed"`, `percent=100`.
- `consume_progress`: после вызова `get_progress(task_id) is None`.
- `index?task=<id>`: сообщение и редирект на чистый URL; повторный GET без
  параметра не показывает сообщение.
- `backup_list`/`backup_restore`: редирект на `backup_index`.
- `restore_progress`, `restore_upload_confirm`, `wipe`: 200.

Полный create/restore в тестах не запускается (долго, меняет БД); прогресс и
статусы проверяются unit-тестами, а создание — интеграционным тестом на пустой
production-БД (`test_create_backup_bg_progress_and_index_message`).

#### B8.2. Команды

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe src\manage.py check
.\.venv\Scripts\python.exe src\manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pytest tests/test_backup.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Полный `pytest` требует PostgreSQL.

#### B8.3. Ручная проверка

В Docker (Gunicorn `--workers 2`) или `runserver`:

1. Открыть `/admin/backup/` — один h1, три кнопки, таблица.
2. «Создать бэкап» — прогресс движется, после завершения главная с сообщением
   и новой строкой.
3. «Восстановить» в строке — прогресс, затем главная с сообщением.
4. «Восстановить из архива» — upload 0–50%, сервер 50–100%, затем главная с
   сообщением.
5. «Очистить все данные» — сообщение на главной.
6. Проверить, что при 2 воркерах прогресс виден (файловое хранилище), а
   сообщение не дублируется.

---

## 5. Изменения по файлам

| Файл | Изменение |
|---|---|
| `src/backup/utils.py` | `_set_progress` (`percent/status/total_steps`), `consume_progress`, прогресс в `create_db_dump`/`create_media_archive`/`create_full_backup`, прогресс `loaddata`, статусы/проценты в `restore_backup`/`upload_and_restore`, уборка старых файлов прогресса (опционально, 24 ч). |
| `src/backup/admin.py` | `index_view` (пагинация, `?task=`, сообщения), `create_backup_bg` (thread wrapper), `progress_view` (нормализация), удаление `list_backups_view`/`restore_view`/`restore_backup_bg`, редиректы `backup_list`/`backup_restore`, обновление `download_view`/`restore_confirm`. |
| `src/backup/forms.py` | Удалить `RestoreForm`. |
| `src/templates/admin/backup/index.html` | Убрать h1 и дубли messages; оставить 3 кнопки; включить `_backup_table.html`. |
| `src/templates/admin/backup/_backup_table.html` | Новый partial: таблица + пагинация. |
| `src/templates/admin/backup/_progress.html` | Новый partial: разметка + `MesBackupProgress`. |
| `src/templates/admin/backup/create.html` | Убрать h1; прогресс; `fetch` на `backup_create_bg`; fallback POST. |
| `src/templates/admin/backup/restore_progress.html` | Убрать h1; `_progress.html` с авто-стартом. |
| `src/templates/admin/backup/restore_upload_confirm.html` | Убрать h1; `_progress.html` с авто-стартом. |
| `src/templates/admin/backup/restore_upload.html` | Убрать h1; общий прогресс; XHR upload 0–50%; `start` после upload. |
| `src/templates/admin/backup/restore_confirm.html` | Убрать h1; cancel → `backup_index`. |
| `src/templates/admin/backup/wipe.html` | Убрать h1. |
| `src/templates/admin/backup/list.html`, `restore.html` | Удалить. |
| `tests/test_backup.py` | Новые тесты. |
| `promt/plans/README.md` | Добавить план 05 в таблицу (опционально, после реализации). |

---

## 6. Порядок реализации

1. B1, B2, B3 — вёрстка главной и таблицы (без изменения бэкенда).
2. B7 — удалить мёртвые страницы/ссылки, обновить редиректы.
3. B4.1, B5.1, B5.2, B5.3 — схема прогресса, `progress_view`, главная, partial.
4. B4.2–B4.5 — прогресс создания бэкапа и UI.
5. B6.1–B6.3 — прогресс восстановления и страницы.
6. B8 — тесты и проверка.

---

## 7. Риски и решения

| Риск | Решение |
|---|---|
| Gunicorn `--workers 2`: прогресс в памяти не виден другому воркеру | Прогресс уже на диске; новые поля `percent/status` тоже в файле. |
| `loaddata` с `verbosity=3` может замедлить восстановление | Вывод только в stdout, не в консоль; влияние минимально. |
| `tar.add(..., filter=...)` с `nonlocal` и обновлением прогресса | Обновлять не чаще 1% и возвращать `tarinfo`; иначе файл будет пропущен. |
| `dumpdata` wrapper может исказить JSON | Wrapper только считает вхождения и делегирует запись; содержимое файла не меняется. |
| Старые файлы прогресса без `status` | `progress_view`/`index_view` нормализуют: `step=0` → error, иначе running. |
| Бэкап/восстановление прервано перезапуском воркера | Вне объёма: прогресс останется на последнем этапе; пользователь может повторить. Опционально — таймаут/индикация «задача прервана». |
| Остаются файлы прогресса после завершения | `consume_progress` удаляет файл при открытии главной; дополнительно — уборка файлов старше 24 ч. |
| Удаление `list.html`/`restore.html` ломает прямые ссылки | URL `backup/list/` и `backup/restore/` остаются как редиректы на `backup_index`. |

---

## 8. Результат реализации (2026-11-13)

Выполнено:

- B1 — дубли `h1` и `messages` убраны; на всех страницах раздела заголовок
  выводится только из admin base.
- B2 — на главной оставлены три кнопки: «Создать бэкап», «Восстановить из
  архива», «Очистить все данные».
- B3 — таблица бэкапов вынесена в `_backup_table.html` и выводится на главной
  с пагинацией по 20.
- B4 — прогресс создания бэкапа: дамп БД (5–55%, подсчёт сериализованных
  объектов), архив медиа (55–90%, по размеру файлов), манифест (90–100%);
  финальный статус `completed` с именем бэкапа.
- B5 — общий partial `_progress.html` с `MesBackupProgress`; `progress_view`
  отдаёт `status/percent`; главная страница принимает `?task=`, показывает
  сообщение и удаляет файл прогресса.
- B6 — прогресс восстановления: `loaddata` запускается с `verbosity=3`, вывод
  парсится на `Processed N object(s).`; для восстановления из бэкапа 10–60%,
  для архива 20–70%; медиа и финал; ошибки получают `status="error"`.
- B7 — удалены `list_backups_view`, `restore_view`, `restore_backup_bg`,
  `RestoreForm`, `list.html`, `restore.html`; старые URL `backup/list/` и
  `backup/restore/` ведут на `backup_index`.
- B8 — добавлен `tests/test_backup.py` (11 тестов).

Изменённые файлы:

- `src/backup/admin.py`
- `src/backup/forms.py`
- `src/backup/utils.py`
- `src/templates/admin/backup/index.html`
- `src/templates/admin/backup/_backup_table.html` (новый)
- `src/templates/admin/backup/_progress.html` (новый)
- `src/templates/admin/backup/create.html`
- `src/templates/admin/backup/restore_confirm.html`
- `src/templates/admin/backup/restore_progress.html`
- `src/templates/admin/backup/restore_upload.html`
- `src/templates/admin/backup/restore_upload_confirm.html`
- `src/templates/admin/backup/wipe.html`
- `tests/test_backup.py` (новый)
- удалены `list.html`, `restore.html`

Проверка:

```powershell
uv run --extra dev python src\manage.py check
uv run --extra dev python src\manage.py makemigrations --check --dry-run
uv run --extra dev python -m pytest -q
```

Результат: `System check identified no issues`, `No changes detected`,
`133 passed`.