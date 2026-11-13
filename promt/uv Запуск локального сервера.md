```bash
cd "D:\asus\doc\@python\mes_reports"
uv sync --frozen
# подготовить библиотеки

uv run python src/manage.py migrate
# подготовить базу данных

uv run python src/manage.py runserver 127.0.0.1:8010
# запустить веб-приложение
```

При твоём способе запуска через `runserver` **обычно достаточно сохранить изменённый Python-файл и обновить страницу в браузере**: Django автоматически перезапускает сервер при изменениях кода. Повторять все три команды каждый раз не нужно. При добавлении новых файлов автоматический перезапуск иногда не срабатывает — тогда перезапусти сервер вручную.[[docs.djangoproject](https://docs.djangoproject.com/en/6.1/ref/django-admin/)]

## 1. Изменился обычный Python-код

Например, ты изменил обработчик запроса в `views.py`:

1. Сохрани файл.
2. Дождись автоматического перезапуска сервера в терминале.
3. Обнови страницу `http://127.0.0.1:8010/`.

Это работает при обычном запуске `runserver`, без параметра `--noreload`.[[docs.djangoproject](https://docs.djangoproject.com/en/6.1/ref/django-admin/)]

Если изменения не подхватились, в терминале, где работает сервер, нажми `Ctrl+C`, затем снова выполни:

```
uv run python src/manage.py runserver 127.0.0.1:8010
```

`Ctrl+C` останавливает текущий сервер; следующая команда запускает его заново.[[docs.djangoproject](https://docs.djangoproject.com/en/6.1/intro/tutorial01/)]

## 2. Изменились модели базы данных — `models.py`

Если ты изменил структуру моделей — например, добавил поле, — одного перезапуска недостаточно. Нужно создать миграции и применить их к базе данных.[[docs.djangoproject](http://docs.djangoproject.com/en/5.2/ref/django-admin/)]

Останови сервер через `Ctrl+C` и выполни:

```
# Создать миграции по изменениям моделей
uv run python src/manage.py makemigrations

# Применить их к базе данных
uv run python src/manage.py migrate

# Снова запустить сервер
uv run python src/manage.py runserver 127.0.0.1:8010
```

Если ты получил обновление проекта, в котором автор уже создал файлы миграций, обычно нужен только `migrate`: повторно создавать миграции не требуется.[[docs.djangoproject](http://docs.djangoproject.com/en/5.2/ref/django-admin/)]

## 3. Изменились зависимости проекта

Если вместе с обновлением изменился `uv.lock`, установи зафиксированные зависимости, затем запусти сервер:[[docs.astral](https://docs.astral.sh/uv/concepts/projects/sync/)][[docs.astral](https://docs.astral.sh/uv/reference/cli/)]

```
# Сначала останови сервер через Ctrl+C

uv sync --frozen
uv run python src/manage.py runserver 127.0.0.1:8010
```

Если изменился только `pyproject.toml`, а `uv.lock` ещё не обновлён, используй:

```
uv sync
```

Без `--frozen` инструмент сможет актуализировать lock-файл. С `--frozen` он использует существующий lock-файл, даже если тот больше не соответствует требованиям проекта.[[docs.astral](https://docs.astral.sh/uv/concepts/projects/sync/)][[docs.astral](https://docs.astral.sh/uv/reference/cli/)]

## Короткая памятка

|Что изменилось|Что делать|
|---|---|
|Существующий Python-код|Сохранить файл → дождаться автоперезапуска → обновить страницу.|
|Добавлены новые файлы, изменения не видны|`Ctrl+C` → снова `runserver`.|
|Структура моделей|`makemigrations` → `migrate`.|
|Получены готовые миграции|`migrate`.|
|Зависимости в `uv.lock`|`uv sync --frozen` → перезапуск сервера.|

Эти действия относятся к твоему локальному серверу разработки. Для рабочего сайта в интернете используется другой способ запуска и перезапуска: Django не рекомендует `runserver` для production.[[docs.djangoproject](https://docs.djangoproject.com/en/6.1/ref/django-admin/)][[docs.djangoproject](http://docs.djangoproject.com/en/5.2/ref/django-admin/)][[docs.astral](https://docs.astral.sh/uv/concepts/projects/sync/)][[docs.djangoproject](https://docs.djangoproject.com/en/6.1/howto/deployment/)]