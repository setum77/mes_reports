---
created: 13.09.2026
tags:
  - docker
  - python
  - gjango
---
Related:  [[ ]]

# mes_reports Laguna S 2.1 free

# Github

### **Быстрая настройка** — если вы уже делали что-то подобное раньше.

[Настройка на рабочем столе](https://desktop.github.com/)  **или**
[HTTPS](https://github.com/setum77/mes_reports.git)
[SSH].(git@github.com:setum77/mes_reports.git)

Для начала [создайте новый файл](https://github.com/setum77/mes_reports/new/main) или [загрузите существующий](https://github.com/setum77/mes_reports/upload) . Мы рекомендуем включать в каждый репозиторий файлы [README](https://github.com/setum77/mes_reports/new/main?readme=1) , [LICENSE](https://github.com/setum77/mes_reports/new/main?filename=LICENSE.md) и [.gitignore](https://github.com/setum77/mes_reports/new/main?filename=.gitignore) .

> [!…или создайте новый репозиторий в командной строке] 
> echo "# mes_reports" >> README.md 
git init 
git add README.md 
git commit -m "first commit" 
git branch -M main 
git remote add origin git@github.com:setum77/mes_reports.git
 git push -u origin main 

 > [!…или отправить изменения в существующий репозиторий из командной строки] 
> git remote add origin git@github.com:setum77/mes_reports.git
 git branch -M main 
git push -u origin main 

# Запуск сервиса

**Локальная разработка:**
```bash
cd D:\tsa\doc\@python\mes_report3
uv run python -m django runserver 127.0.0.1:8000
```

**Через Docker:**
```bash
cd D:\tsa\doc\@python/mes_report3\docker
docker compose up -d
```

## Остановка

**Локальный сервер:** `Ctrl+C` в терминале  
**Docker:** `docker compose down`

## Администрирование

- **Админка:** http://127.0.0.1:8000/admin/
- **Суперпользователь:** `admin` / `admin123`
- **Загрузка Excel-файлов:** http://127.0.0.1:8000/admin/uploads/excelupload/

# Docker

Все изменения запушены на GitHub: https://github.com/setum77/mes_reports

## Пошаговое руководство по установке на OMV (OpenMediaVoult)

### Шаг 1: Подготовка на OMV

1. Подключитесь к OMV по SSH:
```bash
ssh root@192.168.1.99
```

2. Убедитесь, что Docker и Compose установлены:
```bash
docker --version && docker compose version
```

### Шаг 2: Склонируйте проект

На OMV данные обычно хранятся на подключённом диске. Выясните путь к вашему диску:

```bash
df -h
или посмотреть диски внешние
df -h | grep -E "srv|disk"
```

Ищем что-то вроде:
```
/dev/sdb1       293G   59G  220G  21% /srv/dev-disk-by-uuid-9de8f617-6c88-44d4-a00c-1153e0bee794
```


```bash
# 1. Перейдите в каталог вашего диска данных
cd /srv/dev-disk-by-uuid-9de8f617-6c88-44d4-a00c-1153e0bee794

# 2. Создайте каталог для ваших приложений (если ещё нет)
mkdir -p appdata

# 3.0 Установить гит
apt update && apt install -y git

# 3.1 Создать SSH ключ на сервере
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519
(при создании свой пароль на P ввел на русском языке)
cat ~/.ssh/id_ed25519.pub

# 3.2 Добавьте ключ на GitHub: Settings → SSH and GPG keys → New SSH key
# 3.3 Клонируйте по SSH:
git clone git@github.com:setum77/mes_reports.git
Получилось так что создал в корне а не в appdata, 

# 4. Перейдите в каталог проекта
cd mes_reports
```

**Полный путь будет:** `/srv/dev-disk-by-uuid-9de8f617-6c88-44d4-a00c-1153e0bee794/mes_reports`

### Шаг 3: Настройте .env

```bash
cp docker/.env.prod docker/.env
nano docker/.env
```

Убедитесь, что `DJANGO_ALLOWED_HOSTS` содержит IP вашего OMV сервера:
```
DJANGO_ALLOWED_HOSTS=localhost 127.0.0.1 192.168.1.99
```

> **Важно:** `DJANGO_HTTPS` оставьте `false` — приложение доступно по HTTP в локальной сети.

### Шаг 4: Запустите через Docker Compose

```bash
cd docker
docker compose up -d --build
```

> [!warning] 
> с первого раза не получилось. ИИ подправил докер. Пришлось запулить последние изменения git pull. Затем
> cd docker
> cp .env.prod .env
> nano docker/.env -- тут проверил ip
> docker compose up -d --build -- запускать из папки docker


Первый запуск займёт 5-10 минут (сборка образа). Проверьте статус:
```bash
docker compose ps
```

> [!info команда выше выдала такой результат] 
>  NAME           IMAGE                COMMAND                  SERVICE   CREATED         STATUS                           PORTS
> docker-db-1    postgres:17-alpine   "docker-entrypoint.s…"   db        3 minutes ago   Up 3 minutes (healthy)           5432/tcp
> docker-web-1   docker-web           "/app/entrypoint.sh"     web       3 minutes ago   Up 1 second (health: starting)   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp
> 

> [!info] 
> |Столбец|Значение|
|---|---|
|`NAME`|Фактическое имя Docker-контейнера|
|`IMAGE`|Образ, из которого создан контейнер, например `nginx` или `mariadb`|
|`COMMAND`|Команда, которую Docker запускает внутри контейнера|
|`SERVICE`|Имя сервиса из Compose-файла|
|`CREATED`|Когда контейнер был создан|
|`STATUS`|Текущее состояние: `Up`, `Exited`, `Restarting`, `Paused` и т. п.|
|`PORTS`|Какие порты контейнера опубликованы на хосте| 
### Шаг 5: Доступ к приложению

- **Веб-интерфейс:** http://192.168.1.99:8000/
- **Админка:** http://192.168.1.99:8000/admin/
- **Суперпользователь:** `admin` / `admin123`

---

## Через веб-интерфейс OMV (альтернативный способ)

1. Откройте http://192.168.1.99:88/#/system/plugins
2. Найдите плагин **openmediavault-compose** (уже установлен)
3. Перейдите в раздел **Services → Compose → Projects**
4. Нажмите **Add** → **Docker Compose**
5. Укажите:
   - **Name:** `mes_reports`
   - **File path:** `/srv/dev-disk-by-label-data/appdata/mes_reports/docker/docker-compose.yml`
   - **Environment file:** `/srv/dev-disk-by-label-data/appdata/mes_reports/docker/.env`
6. Нажмите **Save** и включите проект

---

## Обновление проекта

1. Подключитесь по SSH
2. Остановите сервис:
```bash
cd /path/to/mes_reports/docker
docker compose down
```
3. Обновите код:
```bash
cd /path/to/mes_reports
git pull
```
4. Перезапустите:
```bash
cd docker
docker compose up -d --build
```

---

## Управление

| Команда | Описание |
|---|---|
| `docker compose logs -f` | Смотреть логи в реальном времени |
| `docker compose restart` | Перезапустить сервис |
| `docker compose down -v` | Полностью удалить (включая БД) |
| `docker compose exec web uv run python src/manage.py migrate` | Применить миграции |
# Была проблема с паролем, после обновлений нужно было обновиться на omv-tum 

Теперь объясню процесс обновления и деплоя на удаленный сервер `omv-tum` (192.168.1.99).

## Текущая конфигурация

- **Git remote:** `git@github.com:setum77/mes_reports.git` (ветка `main`)
- **Деплой:** Docker + docker-compose (файлы в `docker/`)
- **Сервисы:** `db` (PostgreSQL 17) + `web` (Django + gunicorn)
- **Entrypoint** (`docker/entrypoint.sh`): migrations → collectstatic → gunicorn на порту 8000

## Пошаговая инструкция

### 1. Локальные изменения

Внесите правки в код локально, затем закоммитьте и отправьте:

```powershell
cd D:\tsa\doc\@python\mes_report3
git add .
git commit -m "Ваше сообщение о изменениях"
git push origin main
```

### 2. Обновление на удаленном сервере

Подключитесь по SSH к `192.168.1.99` (хост `omv-tum`):

```bash
ssh admin@192.168.1.99
# или пользователь omv-tum, если имя другое
```

### 3. Перейдите в каталог проекта и обновите код

```bash
cd cd /srv/dev-disk-by-uuid-9de8f617-6c88-44d4-a00c-1153e0bee794/mes_reports   # реальный путь к проекту на сервере
git fetch --all
git pull origin main
```

### 4. Пересоберите и перезапустите Docker-контейнеры

```bash
cd docker
docker compose build --no-cache web   # пересобрать образ Django
docker compose up -d                   # перезапустить сервисы
```

`entrypoint.sh` автоматически выполнит:
- `migrate` — применение миграций БД
- `collectstatic` — сбор статических файлов
- `gunicorn` — запуск веб-сервера на порту 8000

### 5. Проверьте статус

```bash
docker compose ps          # статус контейнеров
docker compose logs -f web  # логи веб-приложения
```

Откройте в браузере `http://192.168.1.99:8000/` и проверьте вход `admin` / `admin123`.

## Важно

- Пароль `admin123` хранится в PostgreSQL (`auth_user`), а не в `.env` — он сохранится при пересборке, так как используется том `postgres_data` в `docker-compose.yml`
- Если нужно сбросить пароль админа на сервере:
  ```bash
  cd docker
  docker-compose exec web uv run python src/manage.py changepassword admin
  ```
- Если меняются переменные окружения — правьте `docker/.env` на сервере перед `docker-compose up -d`

### Перезапуск и проверка

``` Powershell
docker compose down
docker compose up -d --build
docker compose ps
docker compose logs -f web
```

### Команды и последствия

| Команда                                 | Контейнеры                   | Сеть           | PostgreSQL volume          | Данные БД              |
| --------------------------------------- | ---------------------------- | -------------- | -------------------------- | ---------------------- |
| `docker compose stop`                   | Остаются, но остановлены     | Остаётся       | Остаётся                   | Сохраняются            |
| `docker compose start`                  | Запускаются снова            | Остаётся       | Остаётся                   | Сохраняются            |
| `docker compose down`                   | Удаляются                    | Удаляется      | Остаётся                   | Сохраняются            |
| `docker compose up -d --build`          | Создаются/запускаются        | Создаётся      | Подключается старый volume | Сохраняются            |
| `docker compose down -v`                | Удаляются                    | Удаляется      | **Удаляется**              | **Удаляются**          |
| `docker volume rm docker_postgres_data` | Не обязательно               | Не обязательно | **Удаляется**              | **Удаляются**          |
| `docker system prune --volumes`         | Может удалить неиспользуемое | Может удалить  | Может удалить              | Возможна потеря данных |

# Пересборка контейнеров - обнуляются ли данные?

> [!note] 
> Допустим я перезагрузил контейнеры командами
docker compose down 
docker compose up -d --build
вся информация из БД тоже обнулится? 

## Короткий ответ

**Нет**, после обычных команд:

```
docker compose down
docker compose up -d --build
```

данные PostgreSQL **не должны обнулиться**, если база подключена к именованному Docker volume. По вашему логу такой volume уже создан:

```
Volume docker_postgres_data Created
```

Значит данные БД, скорее всего, хранятся в volume `docker_postgres_data`, а не внутри файловой системы контейнера. Обычный `docker compose down` удаляет контейнеры и сеть, но не удаляет именованные volumes. При следующем `up` Compose подключит существующий volume к новому контейнеру PostgreSQL.[[docs.docker](https://docs.docker.com/reference/compose-file/volumes/)][[docs.docker](https://docs.docker.com/reference/cli/docker/compose/down/)]

---

## Что происходит с данными

У вас логически схема выглядит так:

```
Контейнер docker-db-1
        │
        │ подключён к
        ▼
Volume docker_postgres_data
        │
        ▼
Файлы PostgreSQL:
таблицы, пользователи, миграции, записи
```

Когда вы выполняете:

```
docker compose down
```

Docker удаляет:

- контейнер `docker-db-1`;
- контейнер `docker-web-1`;
- сеть `docker_default`.

Но **volume `docker_postgres_data` остаётся**.

Затем:

```
docker compose up -d --build
```

создаёт новые контейнеры и подключает старый volume. PostgreSQL видит прежние файлы базы и запускается с теми же данными.

---

## Команды и последствия

|Команда|Контейнеры|Сеть|PostgreSQL volume|Данные БД|
|---|---|---|---|---|
|`docker compose stop`|Остаются, но остановлены|Остаётся|Остаётся|Сохраняются|
|`docker compose start`|Запускаются снова|Остаётся|Остаётся|Сохраняются|
|`docker compose down`|Удаляются|Удаляется|Остаётся|Сохраняются|
|`docker compose up -d --build`|Создаются/запускаются|Создаётся|Подключается старый volume|Сохраняются|
|`docker compose down -v`|Удаляются|Удаляется|**Удаляется**|**Удаляются**|
|`docker volume rm docker_postgres_data`|Не обязательно|Не обязательно|**Удаляется**|**Удаляются**|
|`docker system prune --volumes`|Может удалить неиспользуемое|Может удалить|Может удалить|Возможна потеря данных|

Критически опасная команда для вашей БД:

```
docker compose down -v
```

Параметр:

```
-v
```

или:

```
--volumes
```

означает: удалить именованные и анонимные volumes, подключённые к сервисам Compose. Для PostgreSQL это равнозначно удалению файлов базы.[[docs.docker](https://docs.docker.com/reference/cli/docker/compose/down/)]

---

## Почему это видно по вашему логу

При первом запуске у вас было:

```
✔ Volume docker_postgres_data Created
```

Это хороший признак: Compose создал отдельное постоянное хранилище для PostgreSQL.

Если в `compose.yaml` у вас написано примерно так:

```
services:
  db:
    image: postgres:17-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

то данные сохранятся после:

```
docker compose down
docker compose up -d --build
```

В Docker имя volume автоматически получает префикс имени Compose-проекта. Поэтому:

```
postgres_data:
```

в файле Compose становится:

```
docker_postgres_data
```

где `docker` — вероятное имя проекта, взятое из имени каталога `docker`.

---

## Как проверить, что volume остался

До остановки контейнеров:

```
docker volume ls
```

Найдите строку вида:

```
local    docker_postgres_data
```

После команды:

```
docker compose down
```

повторите:

```
docker volume ls
```

Если строка всё ещё есть:

```
local    docker_postgres_data
```

значит данные PostgreSQL сохранены.

Можно посмотреть подробности:

```
docker volume inspect docker_postgres_data
```

---

## Проверьте путь монтирования PostgreSQL

Для PostgreSQL 17 важно, чтобы volume подключался по правильному пути. Рекомендуемый вариант:

```
services:
  db:
    image: postgres:17-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Для PostgreSQL 17 и ниже монтирование нужно делать именно в:

```
/var/lib/postgresql/data
```

Если подключить volume к неверному уровню каталога, например:

```
- postgres_data:/var/lib/postgresql
```

после пересоздания контейнера PostgreSQL может использовать не тот каталог данных, и будет казаться, что база «обнулилась».[[forums.docker](https://forums.docker.com/t/docker-database-disappears-randomly/149562)]

---

## Как безопасно пересобирать проект

Для обычной разработки используйте:

```
docker compose down
docker compose up -d --build
```

Или обычно достаточно одной команды:

```
docker compose up -d --build
```

Она сама пересоберёт web-образ и пересоздаст нужные контейнеры, если конфигурация изменилась.

Проверка после запуска:

```
docker compose ps
```

Логи базы:

```
docker compose logs -f db
```

Логи Django:

```
docker compose logs -f web
```

---

## Как намеренно очистить БД

Если вам нужно полностью удалить тестовую базу и начать с нуля:

```
docker compose down -v
docker compose up -d --build
```

После этого PostgreSQL создаст новый пустой cluster, а Django при запуске применит миграции заново.

В вашем случае будут удалены как минимум:

```
docker_postgres_data
docker_media_volume
docker_static_volume
```

То есть могут исчезнуть не только данные базы, но и загруженные пользователями файлы из `media_volume`.

---

## Сделайте резервную копию

Перед экспериментами с volumes полезно сделать SQL-дамп:

```
docker compose exec -T db pg_dump \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" > backup.sql
```

Если вы используете конкретные значения, например:

```
POSTGRES_USER: mes_user
POSTGRES_DB: mes_report
```

то команда будет:

```
docker compose exec -T db pg_dump \
    -U mes_user \
    -d mes_report > backup.sql
```

Для восстановления:

```
docker compose exec -T db psql \
    -U mes_user \
    -d mes_report < backup.sql
```

Не храните `backup.sql` в Git, если в нём настоящие рабочие данные или персональная информация.

---

## Итог

Ваши команды:

```
docker compose down
docker compose up -d --build
```

безопасны для БД **при условии**, что не добавлен флаг `-v` и `docker_postgres_data` подключён к `/var/lib/postgresql/data`.

Не используйте без осознанной необходимости:

```
docker compose down -v
```

Потому что именно эта команда удалит volume PostgreSQL и приведёт к потере данных БД.