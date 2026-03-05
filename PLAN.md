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

### 🔲 MVP4 — Отделение бота от сервера

**Цель**: бот становится тонким клиентом. Вся логика — в API/worker.

- [ ] FastAPI сервер — базовая структура (`api/main.py`, роутеры)
- [ ] `POST /api/migrations` — создать задачу миграции
- [ ] `GET /api/migrations/{id}` — статус и прогресс
- [ ] `GET /api/migrations/{id}/report` — скачать файл результатов
- [ ] `POST /api/auth/yandex/token` — обменять код на токен
- [ ] `POST /api/auth/soundcloud/validate` — проверить SC токен
- [ ] `GET/PUT /api/sessions/{user_id}` — сохранить/загрузить сессию
- [ ] bot/api_client.py — обёртка над httpx для вызовов к API
- [ ] Рефакторинг bot/handlers — убрать прямые вызовы core/*, делать через api_client
- [ ] PostgreSQL модели (SQLAlchemy 2.x): users, sessions, migrations, tracks, playlists, artists
- [ ] Alembic — первая миграция (initial schema)

---

### 🔲 MVP5 — Worker + очередь задач

**Цель**: миграции выполняются в отдельных worker-процессах через Redis.

- [ ] arq worker setup (`worker/main.py`, WorkerSettings)
- [ ] Task: `run_migration(migration_id)` — читает из БД, выполняет пайплайн
- [ ] Redis pub/sub: worker публикует прогресс → API отдаёт через SSE или polling
- [ ] `GET /api/migrations/{id}/progress` — endpoint для polling прогресса
- [ ] Отмена задачи (`DELETE /api/migrations/{id}`) — arq job abort
- [ ] Ограничение параллельных задач (max_jobs в arq, очередь per-user)

---

### 🔲 MVP6 — Service Registry

**Цель**: расширяемый реестр источников и назначений.

- [ ] `core/services/base.py` — абстрактный `MusicServiceAdapter`
  ```python
  class MusicServiceAdapter:
      id: str
      name: str
      capabilities: set[Capability]
      async def get_liked_tracks(self, session) -> list[Track]: ...
      async def like_track(self, session, track_id) -> bool: ...
      # и т.д.
  ```
- [ ] `core/services/registry.py` — `ServiceRegistry.get_matrix()` → FROM→TO матрица
- [ ] Перенести YandexMusicClient → `YandexMusicAdapter(MusicServiceAdapter)`
- [ ] Перенести SoundCloudClient → `SoundCloudAdapter(MusicServiceAdapter)`
- [ ] `FileAdapter` — экспорт в CSV/JSON, импорт из CSV/JSON
- [ ] `GET /api/services` — список доступных сервисов с capabilities
- [ ] `GET /api/services/matrix` — матрица FROM→TO для UI
- [ ] Настройка через код (Фаза 1); схема БД для Фазы 2 (таблица `services`)

---

### 🔲 MVP7 — Веб-интерфейс (пользователи)

**Цель**: полноценный веб-UI для обычных пользователей.

- [ ] Базовый шаблон (base.html) — навигация, стили (Tailwind CDN или simple CSS)
- [ ] Главная страница: выбор FROM / TO (из матрицы сервисов)
- [ ] Auth flow: кнопка «войти через Яндекс», ввод SC токена
- [ ] Страница прогресса — HTMX polling каждые 3 сек → обновление без перезагрузки
- [ ] Страница результатов — статистика + скачать отчёт
- [ ] История миграций пользователя
- [ ] Импорт из файла (загрузка CSV/JSON)
- [ ] Экспорт в файл (скачать CSV/JSON)

---

### 🔲 MVP8 — Веб-интерфейс (админка)

**Цель**: мониторинг и управление сервисом.

- [ ] Дашборд: активные миграции, очередь, нагрузка на воркеры
- [ ] Список пользователей, их сессий, миграций
- [ ] Лог миграций с фильтрацией
- [ ] Управление реестром сервисов (включить/выключить, capabilities)
- [ ] Просмотр not_found треков для любой миграции
- [ ] Принудительная отмена/перезапуск задачи
- [ ] Защита: HTTP Basic или внутренний токен

---

### 🔲 MVP9 — Инфраструктура и деплой

**Цель**: продакшн-деплой на Timeweb Cloud.

#### Docker

- [ ] `Dockerfile.api` — FastAPI + gunicorn/uvicorn
- [ ] `Dockerfile.bot` — Telegram бот
- [ ] `Dockerfile.worker` — arq worker
- [ ] `docker-compose.yml` — все сервисы + PostgreSQL + Redis
- [ ] `.env.example` — полный список переменных окружения
- [ ] Health check endpoints (`/health` для API, воркера)

#### Сеть

- [ ] DE сервер (Timeweb Cloud, Германия):
  - `api`, `bot`, `worker`, `postgres`, `redis`
  - SoundCloud доступен без ограничений
- [ ] RU сервер (Timeweb Cloud, Россия) — опционально:
  - `worker-ru` — если DE воркер не может достучаться до Яндекс Музыки
  - Или: SOCKS5/HTTP прокси с RU-сервера → пробрасывается в DE worker
- [ ] Nginx reverse proxy: SSL termination, `/` → api, статика
- [ ] Certbot (Let's Encrypt) для SSL

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
