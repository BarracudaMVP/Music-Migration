# План разработки: Music Migration Service

## Концепция

Универсальный сервис переноса музыкальных библиотек между стриминговыми платформами.
Доступен через Telegram-бот и веб-интерфейс. Единый бэкенд обрабатывает задачи от обоих клиентов.

---

## Стек

### Текущий (MVP1–3, реализовано)
- Python 3.12+, aiogram 3.x, aiohttp, aiosqlite
- yandex-music, soundcloud-v2, rapidfuzz, iuliia
- SQLite (локально)

### Целевой (MVP4+)
- **API**: FastAPI + Jinja2 + HTMX (веб-интерфейс без отдельного фронтенда)
- **БД**: PostgreSQL + asyncpg + SQLAlchemy 2.x async + Alembic
- **Очередь задач**: arq (async Redis queue)
- **FSM бота**: aiogram + RedisStorage
- **Кэш / pub-sub**: Redis
- **Контейнеры**: Docker + docker-compose

---

## Архитектура (целевая)

```
┌──────────────────┐     ┌──────────────────┐
│  Telegram Bot    │     │  Web UI          │
│  (aiogram 3.x)   │     │  (Jinja2 + HTMX) │
└────────┬─────────┘     └────────┬─────────┘
         │ HTTP (internal API)    │ HTTP
         └────────────┬───────────┘
                      ▼
         ┌────────────────────────┐
         │    FastAPI Server      │
         │  /api/* + /web/*       │
         │  /admin/*              │
         └──────┬─────────────────┘
                │
        ┌───────┼───────────┐
        ▼       ▼           ▼
  [PostgreSQL] [Redis]  [Redis pub/sub]
                │            │ (progress events)
                ▼            │
     ┌─────────────────┐     │
     │   Worker Pool   │─────┘
     │   (arq workers) │
     └────────┬────────┘
              │
    ┌─────────┼──────────┐
    ▼         ▼          ▼
[YM Adapter] [SC Adapter] [File Adapter]
(RU IP)      (DE proxy)   (CSV/JSON)
```

### Компоненты — отдельные процессы

| Процесс | Хост | Описание |
|---------|------|----------|
| `api` | DE | FastAPI — REST API + веб-интерфейс |
| `bot` | DE | Telegram бот — тонкий клиент к API |
| `worker` | DE | arq worker — выполняет миграции |
| `postgres` | DE | БД |
| `redis` | DE | FSM, очередь, pub/sub |

> Yandex Music: если понадобится RU IP — либо отдельный `worker-ru` на RU-сервере,
> либо SOCKS5 прокси через RU-сервер к основному worker.

---

## Реестр сервисов (Service Registry)

Каждый сервис декларирует свои возможности. Матрица FROM→TO строится автоматически.

```
Capability:
  READ_LIKED_TRACKS      WRITE_LIKED_TRACKS
  READ_PLAYLISTS         WRITE_PLAYLISTS
  READ_LIKED_ARTISTS     WRITE_LIKED_ARTISTS
  EXPORT_FILE            IMPORT_FILE

Сервисы:
  yandex_music:   READ_LIKED_TRACKS, READ_PLAYLISTS, READ_LIKED_ARTISTS
  soundcloud:     WRITE_LIKED_TRACKS, WRITE_PLAYLISTS, WRITE_LIKED_ARTISTS
                  READ_LIKED_TRACKS (в будущем)
  file_csv:       EXPORT_FILE, IMPORT_FILE
  spotify:        (в будущем)
  apple_music:    (в будущем)
```

Матрица направлений (текущая):

```
FROM \ TO     | SoundCloud | File CSV
--------------|------------|----------
Yandex Music  |     ✓      |    ✓
File CSV      |     ✓      |    –
SoundCloud    |     –      |    ✓  (в будущем)
```

### Фазы настройки реестра

1. **Фаза 1** (код): хардкод список адаптеров, capabilities в Python
2. **Фаза 2** (БД): таблица `services` + `service_capabilities`, редактируется в БД
3. **Фаза 3** (admin UI): управление через веб-админку

---

## Структура проекта (целевая)

```
music-migration/
├── api/                        # FastAPI сервер
│   ├── main.py                 # app init, роутеры
│   ├── deps.py                 # FastAPI dependencies (auth, db session)
│   ├── routes/
│   │   ├── auth.py             # OAuth endpoints (Yandex, Spotify, etc.)
│   │   ├── migrations.py       # POST /migrations, GET /migrations/{id}
│   │   ├── services.py         # GET /services, GET /services/matrix
│   │   ├── reports.py          # GET /migrations/{id}/report (скачать файл)
│   │   └── admin.py            # /admin/* (защищённые)
│   └── templates/              # Jinja2
│       ├── base.html
│       ├── index.html          # выбор FROM/TO, начало миграции
│       ├── migration.html      # прогресс в реальном времени (HTMX polling)
│       ├── report.html         # итоги
│       └── admin/
│           ├── dashboard.html
│           ├── users.html
│           └── migrations.html
│
├── bot/                        # Telegram бот (тонкий клиент)
│   ├── main.py
│   ├── api_client.py           # HTTP клиент к FastAPI
│   ├── states.py
│   └── handlers/
│       ├── start.py
│       ├── auth.py             # OAuth через API
│       ├── migration.py        # запуск задачи через API, polling прогресса
│       └── status.py
│
├── worker/                     # arq workers
│   ├── main.py                 # WorkerSettings, cron
│   └── tasks/
│       ├── migrate.py          # главный пайплайн (FROM→TO)
│       └── export.py           # экспорт в файл
│
├── core/                       # общая бизнес-логика (shared)
│   ├── services/
│   │   ├── base.py             # MusicServiceAdapter (abstract)
│   │   ├── registry.py         # ServiceRegistry
│   │   ├── yandex/
│   │   │   ├── adapter.py      # YandexMusicAdapter
│   │   │   └── client.py       # (существующий)
│   │   ├── soundcloud/
│   │   │   ├── adapter.py      # SoundCloudAdapter
│   │   │   └── client.py       # (существующий)
│   │   └── file/
│   │       └── adapter.py      # FileAdapter (CSV/JSON import+export)
│   ├── matcher.py              # (существующий)
│   ├── crypto.py               # (существующий)
│   └── db/
│       ├── models.py           # SQLAlchemy 2.x models
│       ├── crud.py             # async CRUD
│       └── alembic/            # миграции БД
│
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.bot
│   ├── Dockerfile.worker
│   └── docker-compose.yml
│
├── config.py                   # Pydantic Settings
├── requirements.txt
├── PLAN.md
└── CLAUDE.md
```

---

## Статус разработки

### ✅ Готово (MVP1–3)

- [x] YandexMusicClient — треки, плейлисты, артисты (батчинг по 150, uid fallback)
- [x] SoundCloudClient — search (soundcloud-v2), write (aiohttp), rate limit 429
- [x] Matcher — rapidfuzz + iuliia транслитерация
- [x] Migration pipeline — tracks / playlists / artists (resumable через SQLite)
- [x] Telegram бот — FSM auth, прогресс, /status, сессии в SQLite
- [x] Yandex OAuth 2.0 (Authorization Code flow)
- [x] Шифрование токенов (Fernet)

---

### ✅ MVP4 — Отделение бота от сервера

**Цель**: бот становится тонким клиентом. Вся логика — в API/worker.

- [x] FastAPI сервер — базовая структура (`api/main.py`, роутеры)
- [x] `POST /api/migrations` — создать задачу миграции
- [x] `GET /api/migrations/{id}` — статус и прогресс
- [x] `GET /api/migrations/{id}/report` — скачать файл результатов
- [x] `POST /api/auth/yandex/token` — обменять код на токен
- [x] `POST /api/auth/soundcloud/validate` — проверить SC токен
- [x] `GET/PUT /api/sessions/{user_id}` — сохранить/загрузить сессию
- [x] bot/api_client.py — обёртка над httpx для вызовов к API
- [x] Рефакторинг bot/handlers — убрать прямые вызовы core/*, делать через api_client
- [x] PostgreSQL модели (SQLAlchemy 2.x): users, sessions, migrations, tracks, playlists, artists
- [x] Alembic — первая миграция (initial schema)

---

### ✅ MVP5 — Worker + очередь задач

**Цель**: миграции выполняются в отдельных worker-процессах через Redis.

- [x] arq worker setup (`worker/main.py`, WorkerSettings)
- [x] Task: `run_migration(migration_id)` — читает из БД, выполняет пайплайн
- [x] Redis pub/sub: worker публикует прогресс → API отдаёт через SSE или polling
- [x] `GET /api/migrations/{id}/progress` — endpoint для polling прогресса
- [x] Отмена задачи (`DELETE /api/migrations/{id}`) — arq job abort
- [x] Ограничение параллельных задач (max_jobs в arq, очередь per-user)

---

### ✅ MVP6 — Service Registry

**Цель**: расширяемый реестр источников и назначений.

- [x] `core/services/base.py` — `Capability` Flag enum + `MusicServiceAdapter` ABC
- [x] `core/services/registry.py` — `ServiceRegistry` с `register/all/get/get_matrix`
- [x] `core/services/yandex/adapter.py` — `YandexMusicAdapter` (тонкая обёртка, READ_*)
- [x] `core/services/soundcloud/adapter.py` — `SoundCloudAdapter` (WRITE_*)
- [x] `core/services/file/adapter.py` — `FileAdapter` — export/import CSV/JSON
- [x] `core/db/crud.py` — добавлена `get_all_tracks(migration_id)`
- [x] `GET /api/services` — список доступных сервисов с capabilities
- [x] `GET /api/services/matrix` — матрица FROM→TO для UI
- [x] Регистрация адаптеров в `api/main.py` startup

---

### ✅ MVP7 — Веб-интерфейс (пользователи)

**Цель**: полноценный веб-UI для обычных пользователей.

- [x] Базовый шаблон `base.html` — навигация, Tailwind CDN + HTMX CDN
- [x] `index.html` — выбор FROM/TO из матрицы сервисов
- [x] `auth.html` — Яндекс OAuth (link+paste code) + SC токен
- [x] `progress.html` — HTMX polling каждые 3 сек → `fragments/status.html`
- [x] `result.html` — статистика + кнопки скачать CSV/JSON
- [x] `history.html` — история миграций пользователя (последние 50)
- [x] `GET /migrate/{id}/export` — скачать CSV или JSON через FileAdapter
- [x] `SessionMiddleware` — подписанные cookie-сессии (secret_key в .env)
- [x] Добавлены зависимости: jinja2, python-multipart, itsdangerous
- [ ] Импорт из файла (загрузка CSV/JSON) — отложено на MVP8

---

### ✅ MVP8 — Веб-интерфейс (админка)

**Цель**: мониторинг и управление сервисом.

- [x] Логин-форма `/admin/login` — защита паролем через сессию (`admin_password` в .env)
- [x] Дашборд `/admin/dashboard` — кол-во миграций/пользователей/треков, статусы, последние 10
- [x] Список миграций `/admin/migrations` — фильтр по статусу и user_id
- [x] Детальная страница `/admin/migrations/{id}` — мета + статистика треков + таблица треков с фильтром
- [x] Отмена миграции `POST /admin/migrations/{id}/cancel`
- [x] Перезапуск миграции `POST /admin/migrations/{id}/restart` (через ARQ)
- [x] Список пользователей `/admin/users` — сессии + кол-во миграций
- [x] Реестр сервисов `/admin/services` — адаптеры с capabilities + матрица
- [x] `config.py` — добавлен `admin_password`

---

### ✅ MVP9 — Инфраструктура и деплой

**Цель**: продакшн-деплой на Timeweb Cloud.

#### Docker

- [x] `Dockerfile.api` — FastAPI + uvicorn
- [x] `Dockerfile.bot` — Telegram бот
- [x] `Dockerfile.worker` — arq worker
- [x] `docker-compose.yml` — все сервисы + PostgreSQL + Redis + Nginx
- [x] `.env.example` — полный список переменных окружения
- [x] Health check endpoint `GET /health` → `{"status":"ok","version":"9.0.0"}`

#### Сеть

- [x] Nginx reverse proxy: `nginx/nginx.conf` — proxy_pass → api:8000
- [x] SSL-секция закомментирована с инструкцией certbot
- [ ] RU сервер (Timeweb Cloud, Россия) — опционально:
  - `worker-ru` — если DE воркер не может достучаться до Яндекс Музыки
  - Или: SOCKS5/HTTP прокси с RU-сервера → пробрасывается в DE worker

#### CI/CD (опционально)

- [ ] GitHub Actions: lint (ruff) + build + push images
- [ ] Деплой через docker-compose pull + up

---

### 🔲 MVP10 — Telegram плейлисты (отложено)

> Telegram имеет внутренние плейлисты у пользователя, но API для работы с ними
> не стандартизован. Реализовать в последнюю очередь, когда появится ясность.

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| SoundCloud блокирует по rate limit | sleep(2) + 429 backoff с reset_time |
| Трек не найден (кириллица) | iuliia транслитерация + dual-path scoring |
| Обрыв задачи | arq retry + resumable пайплайн (статусы в БД) |
| Yandex Music недоступен с DE IP | RU worker или SOCKS5 proxy через RU сервер |
| SoundCloud недоступен с RU IP | Воркер работает на DE сервере |
| 20-30 параллельных пользователей | arq max_jobs, connection pool asyncpg, per-user rate limit |
| Истёкший токен во время миграции | Проверка при старте + graceful fail с уведомлением |
| SC токен как cookie — короткий срок | Уведомление за N дней; инструкция по обновлению |

---

## Переменные окружения (целевые)

```env
# API
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/musicmigration
REDIS_URL=redis://redis:6379/0
SECRET_KEY=                    # для подписи сессий/JWT
ADMIN_TOKEN=                   # для /admin/* endpoints

# Bot
TELEGRAM_BOT_TOKEN=
API_BASE_URL=http://api:8000   # внутренний адрес FastAPI
ALLOWED_USERS=                 # пусто = открыт для всех

# Yandex OAuth
YANDEX_CLIENT_ID=
YANDEX_CLIENT_SECRET=

# Encryption
DB_ENCRYPTION_KEY=             # Fernet key

# Worker
SC_RATE_LIMIT_SLEEP=2.0
MATCH_THRESHOLD=75.0
MAX_CONCURRENT_MIGRATIONS=10

# Proxy (если нужен RU IP для Yandex)
YM_PROXY_URL=                  # socks5://user:pass@ru-server:1080 (опционально)
```
