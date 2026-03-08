# MM — Music Migration

Универсальный сервис переноса музыкальных библиотек между стриминговыми платформами.
Доступен через Telegram-бот и веб-интерфейс. Единый бэкенд обрабатывает задачи от обоих клиентов.

---

## Стек

- **API**: FastAPI + Jinja2 + HTMX
- **БД**: PostgreSQL + SQLAlchemy 2.x async + Alembic
- **Очередь**: arq (Redis)
- **Бот**: aiogram 3.x
- **Инфра**: Docker + docker-compose + Nginx
- **Прокси**: Dante SOCKS5 на RU сервере (для Яндекс Музыки)

---

## Архитектура

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
(RU proxy)   (EU server)  (CSV/JSON)
```

---

## Реестр сервисов

```
Capability:
  READ_LIKED_TRACKS      WRITE_LIKED_TRACKS
  READ_PLAYLISTS         WRITE_PLAYLISTS
  READ_LIKED_ARTISTS     WRITE_LIKED_ARTISTS
  EXPORT_FILE            IMPORT_FILE

Сервисы (сейчас):
  yandex_music:   READ_LIKED_TRACKS, READ_PLAYLISTS, READ_LIKED_ARTISTS, EXPORT_TRACKS
  soundcloud:     WRITE_LIKED_TRACKS, WRITE_PLAYLISTS, WRITE_LIKED_ARTISTS, EXPORT_TRACKS
  file_csv:       EXPORT_FILE, IMPORT_FILE
  spotify:        READ_LIKED_TRACKS, READ_PLAYLISTS, READ_LIKED_ARTISTS, EXPORT_TRACKS

Сервисы (после MM-38, MM-39):
  yandex_music:   + WRITE_LIKED_TRACKS, WRITE_PLAYLISTS
  spotify:        + WRITE_LIKED_TRACKS, WRITE_PLAYLISTS
```

```
Матрица переносов (сейчас):
FROM \ TO     | SoundCloud | File CSV  | Яндекс Музыка | Spotify
--------------|------------|-----------|---------------|--------
Яндекс Музыка |     ✓      |    ✓      |       –       |    –
Spotify       |     ✓      |    ✓      |       –       |    –
File CSV      |     ✓      |    –      |       –       |    –
SoundCloud    |     –      |    ✓      |       –       |    –

Матрица переносов (после MM-38 + MM-39):
FROM \ TO     | SoundCloud | File CSV  | Яндекс Музыка | Spotify
--------------|------------|-----------|---------------|--------
Яндекс Музыка |     ✓      |    ✓      |       –       |  ✓ MM-39
Spotify       |     ✓      |    ✓      |   ✓ MM-38     |    –
File CSV      |     ✓      |    –      |   ✓ MM-38     |  ✓ MM-39
SoundCloud    |     –      |    ✓      |   ✓ MM-38     |  ✓ MM-39
```

---

## Задачи

### ✅ MM-1 — Ядро (треки, плейлисты, артисты)
- [x] YandexMusicClient — треки, плейлисты, артисты (батчинг по 150, uid fallback)
- [x] SoundCloudClient — search + write, rate limit 429
- [x] Matcher — rapidfuzz + iuliia транслитерация
- [x] Migration pipeline — resumable через БД (pending/liked/not_found/error)
- [x] Шифрование токенов (Fernet)

---

### ✅ MM-2 — Telegram бот (базовый)
- [x] FSM auth: Yandex OAuth + SoundCloud токен
- [x] Прогресс миграции, /status, /cancel
- [x] Сессии в SQLite

---

### ✅ MM-3 — FastAPI + разделение бота от сервера
- [x] FastAPI сервер — роутеры, deps
- [x] POST /api/migrations, GET /api/migrations/{id}
- [x] POST /api/auth/yandex/token, POST /api/auth/soundcloud/validate
- [x] GET/PUT /api/sessions/{user_id}
- [x] bot/api_client.py — бот как тонкий клиент
- [x] PostgreSQL модели (SQLAlchemy 2.x) + Alembic

---

### ✅ MM-4 — Worker + очередь задач
- [x] arq worker, WorkerSettings
- [x] run_migration job — читает из БД, выполняет пайплайн
- [x] Redis pub/sub прогресс → polling endpoint
- [x] Отмена задачи (arq job abort)
- [x] Ограничение параллельных задач

---

### ✅ MM-5 — Service Registry
- [x] Capability Flag enum + MusicServiceAdapter ABC
- [x] ServiceRegistry — register/all/get/matrix
- [x] YandexMusicAdapter, SoundCloudAdapter, FileAdapter
- [x] GET /api/services, GET /api/services/matrix

---

### ✅ MM-6 — Веб-интерфейс (пользователи)
- [x] base.html, index.html, auth.html, progress.html, result.html, history.html
- [x] HTMX polling прогресса
- [x] Экспорт CSV/JSON
- [x] SessionMiddleware (cookie-сессии)

---

### ✅ MM-7 — Веб-интерфейс (админка)
- [x] /admin/login, /admin/dashboard, /admin/migrations, /admin/users, /admin/services
- [x] Отмена и перезапуск миграции
- [x] Детальная страница миграции с таблицей треков

---

### ✅ MM-8 — Инфраструктура и деплой
- [x] Dockerfile.api/bot/worker + docker-compose.yml
- [x] Nginx reverse proxy
- [x] entrypoint.sh — alembic upgrade head перед стартом
- [x] healthcheck для api, .dockerignore
- [x] RU сервер — Dante SOCKS5 прокси → YM_PROXY_URL
- [x] EU сервер — полный стек запущен

---

### 🔲 MM-9 — SSL / HTTPS
- [ ] Домен → A-запись на EU сервер
- [ ] certbot + Let's Encrypt через docker
- [ ] Раскомментировать SSL-секцию в nginx/nginx.conf
- [ ] Редирект HTTP → HTTPS

---

### 🔲 MM-10 — CI/CD и среды
- [ ] GitHub Actions: lint (ruff) + build + deploy
- [ ] Разделение конфигов: .env.local / .env.prod
- [ ] Деплой: ssh → git pull → docker compose up --build -d

---

### ✅ MM-11 — Улучшенный поиск треков
- [x] split_artists(): feat./ft./&/x/при уч./при участии → несколько запросов параллельно
- [x] Дедупликация кандидатов по sc_id
- [x] Fallback: title-only поиск если пул кандидатов пустой
- [x] _SEARCH_LIMIT 5 → 10

---

### ✅ MM-12 — Список треков и статусы (веб)
- [x] GET /migrate/{id}/tracks — таблица с фильтрацией и пагинацией
- [x] Фильтр по статусу: Все / Перенесены / Не найдены / Ошибки / В очереди
- [x] Пагинация по 50 треков (get_tracks_page в crud.py)
- [x] Ссылка «Список треков» на странице result.html

---

### ✅ MM-13 — Обновление Telegram бота
- [x] Inline-кнопка [Отключиться от миграции] в прогресс-сообщении
- [x] Финальное сообщение с кнопками: [Ненайденные треки N] [Открыть в браузере] [Новая миграция]
- [x] Callback migration:not_found:{id} → первые 30 треков + ссылка на полный список
- [x] Callback migration:new → запуск нового /migrate
- [x] /status → кнопка [Открыть в браузере] (ссылка на /migrate/{id}/tracks)
- [x] api_client.get_not_found_tracks() — вызывает /api/reports/{id}/not-found

---

### ✅ MM-14 — Импорт из файла
- [x] GET /import — страница загрузки файла
- [x] POST /import/preview (HTMX) — парсинг, предпросмотр первых 20 строк, авто-маппинг колонок
- [x] POST /import/start — запуск переноса с выбранными колонками
- [x] FileAdapter: get_columns(), preview_tracks(), detect_column_mapping(), import_tracks(artist_col, title_col)
- [x] migrate_from_file_tracks() — пайплайн без YM, через _run_pending_loop
- [x] run_file_migration_job — ARQ-задача (tracks передаются как list[dict])
- [x] Ссылка «Импорт» в навигации

---

### ✅ MM-15 — Ролевая модель
- [x] Поле role ('user' | 'admin') в UserSession модели
- [x] Alembic-миграция: add_user_role (a1b2c3d4e5f6)
- [x] _is_admin() проверяет сессионный пароль ИЛИ роль admin в БД
- [x] POST /admin/users/{user_id}/set-role — смена роли
- [x] users.html: колонка «Роль» + кнопки «Сделать admin» / «Снять admin»
- [x] set_user_role() в crud.py, экспортирован из core/db

---

### ✅ MM-16 — Безопасность и rate limiting
- [x] Rate limit: 10 переносов/час per user_id через Redis (check_migration_rate_limit в deps.py)
  - Применяется к POST /migrate и POST /import/start
- [x] Брутфорс защита /admin/login: 5 попыток → блокировка 15 мин по IP (in-memory)
  - _is_locked_out / _record_fail / _reset_attempts в admin.py
- [x] AllowedUsersWebMiddleware: проверяет ALLOWED_USERS для числовых (Telegram) user_id из сессии
  - Добавлен в api/middleware.py, зарегистрирован до SessionMiddleware (innermost)

---

### ✅ MM-17 — Уведомления
- [x] `worker/notifications.py`: `notify_telegram()` — httpx напрямую к Bot API, пропускает `web_*` user_id
- [x] `run_migration_job`: Telegram-уведомление при успехе (статистика + ссылка) и при ошибке
- [x] `run_file_migration_job`: аналогичные уведомления
- [x] Уведомление приходит **сразу** после завершения задачи в worker (не delayed)
- [ ] ~~check_sc_tokens_job~~ — удалено: нет смысла уведомлять об истёкшем токене, пользователь может уже не нуждаться в сервисе

> **Веб-аналог уведомлений:** отсутствует целенаправленно. Веб-пользователь видит результат через HTMX-поллинг (каждые 3 с) на странице `/migrate/{id}`. Если закрыл браузер — результат доступен в истории.

---

### ✅ MM-18 — Улучшение интерфейса (веб)

> Только веб-интерфейс. Telegram-бот не менялся — у него нативная Telegram UI.

- [x] **Мобильная адаптация**: hamburger-меню в nav, responsive grid (sm:grid-cols-*), flex-wrap везде
- [x] **Редизайн**: rounded-2xl карточки, тени (shadow-sm), stat cards с цветовым кодированием
- [x] **Анимации прогресса**:
  - Indeterminate shimmer-полоса (CSS @keyframes) пока перенос идёт
  - Filled progress bar с цветом по % успеха при завершении
  - Пульсирующая цветная точка рядом со статусом
  - Slide-in анимация при загрузке страницы
  - SVG-спиннер на начальной загрузке
- [x] **Страницы**: base, index, progress, status fragment, result, history, auth, tracks, import, import_preview
- [x] **index.html**: radio-выбор режима (только треки / треки + плейлисты + артисты), передаётся в `mode` → worker
- [x] **auth.html**: step indicator (кружки 1→2 с зелёной галочкой)
- [x] **history.html**: status badges с фоновым цветом, chevron, пустое состояние с иконкой
- [x] `api/routes/web.py`: `start_migrate` принимает `mode: str = Form("full")`

---

### ✅ MM-19 — Централизованное логирование
- [x] `core/logger.py` — `setup_logger(service)`: stderr colored sink + stdout JSON sink (`serialize=True`); `service` вшит в каждую запись через `extra`
- [x] `api/main.py` — `setup_logger("api")` при старте (раньше не вызывался)
- [x] `run_worker.py` — `setup_logger("worker")` перед `run_worker()`
- [x] `bot/main.py` — уже вызывал `setup_logger()`, обновлён на `setup_logger("bot")`
- [x] Docker log rotation на всех сервисах в `docker-compose.yml` (`json-file`, `max-size: 20m`, `max-file: 5`)
- [x] `docker-compose.monitoring.yml` — отдельный opt-in стек: Loki 2.9 + Promtail 2.9 + Grafana 10.2
- [x] `monitoring/loki/config.yml` — Loki local filesystem storage
- [x] `monitoring/promtail/config.yml` — docker_sd_configs (читает через `/var/run/docker.sock`), парсит loguru JSON, промотирует `service`/`log_level`/`migration_id` в Loki labels
- [x] `monitoring/grafana/provisioning/datasources/loki.yml` — auto-provision Loki datasource

**Запуск мониторинга:**
```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```
Grafana: http://localhost:3000 (admin / $GRAFANA_PASSWORD)

**Фильтрация в Grafana (LogQL):**
```logql
{service="worker"} |= "migration_id"          # все логи воркера
{log_level="ERROR"}                             # только ошибки
{service="api"} | json | migration_id="42"     # конкретная миграция
```

---

### ✅ MM-20 — Тесты и ревью
- [x] Покрытие тестами ключевых пайплайнов
- [x] Integration tests (API + DB)
- [x] Нагрузочное тестирование (20 параллельных запросов через asyncio.gather)
- [x] Кодревью и рефакторинг

---

### ✅ MM-21 — Мультиязычность
- [x] `core/i18n.py` — каталог строк `_S[key][lang]`, `t(key, lang)`, `detect_lang_web()`, `detect_lang_tg()`
- [x] Alembic миграция `d1e2f3a4b5c6` — поле `lang TEXT NOT NULL DEFAULT 'ru'` в `user_sessions`
- [x] `core/db/models.py` — поле `lang: Mapped[str]`
- [x] `core/db/crud.py` — `save_user_lang(user_id, lang)`, `load_user_session()` возвращает `lang`
- [x] **Веб**: `api/routes/web.py` — `_render()` инжектит `lang` и `t()` во все шаблоны, `GET /set-lang` сохраняет выбор в сессии + БД
- [x] **Веб**: все шаблоны переведены — base, index, auth, progress, result, history, tracks, import, export, fragments/status
- [x] **Веб**: кнопка EN↔RU в навигации (desktop + mobile hamburger)
- [x] **Веб**: автоопределение по `Accept-Language` → приоритет: сессия → заголовок → "ru"
- [x] **Бот**: `bot/handlers/start.py` — определение языка из `language_code`, `/language` команда, выбор языка при первом старте если `language_code is None`
- [x] **Бот**: все хендлеры переведены — start, auth, migration, status
- [x] **Бот**: lang хранится в FSM state + персистируется в БД при сохранении сессии
- [x] **Worker**: `worker/notifications.py` — `migration_done_text(lang=)`, `migration_failed_text(lang=)` принимают язык
- [x] **Worker**: `worker/tasks.py` — `_get_user_lang(user_id)` достаёт lang из БД перед отправкой уведомления
- [x] 133 теста проходят без изменений

---

### ✅ MM-22 — Spotify
- [x] `SpotifyAdapter` в ServiceRegistry (`READ_LIKED_TRACKS | READ_PLAYLISTS | READ_LIKED_ARTISTS`)
- [x] `core/spotify/models.py` — SpotifyTrack, SpotifyPlaylist, SpotifyArtist
- [x] `core/spotify/oauth.py` — Authorization Code Flow: `get_auth_url()`, `exchange_code()`, `refresh_access_token()`, CSRF state
- [x] `core/spotify/client.py` — `SpotifyClient`: `get_liked_tracks()`, `get_playlists()`, `get_followed_artists()`, pagination
- [x] `core/services/spotify/adapter.py` — SpotifyAdapter зарегистрирован в startup
- [x] `config.py` — `spotify_client_id`, `spotify_client_secret`, `spotify_redirect_uri`
- [x] Alembic миграция `c3d4e5f6a7b8` — добавлено поле `spotify_token TEXT NULL` в `user_sessions`
- [x] `core/db/models.py` — `spotify_token: Mapped[str | None]`
- [x] `core/db/crud.py` — `save_spotify_token()` (upsert только spotify_token), `load_user_session()` возвращает `spotify_token`
- [x] `migration/spotify_tracks.py` — `migrate_spotify_tracks()` + `run_spotify_migration()`: Spotify → SC (reuse `_run_pending_loop`)
- [x] `worker/tasks.py` — `run_spotify_migration_job()` ARQ задача
- [x] `worker/main.py` — `run_spotify_migration_job` в `functions`
- [x] `api/routes/web.py` — `GET /auth/spotify` (redirect), `GET /auth/spotify/callback` (CSRF state check, exchange, save), обновлён `start_migrate` для `from_service=spotify`
- [x] `api/templates/auth.html` — секция Spotify (кнопка OAuth, статус подключения), показывается только если `spotify_enabled`

**Настройка Spotify app (developer.spotify.com):**
1. Create app → Redirect URI: `{API_BASE_URL}/auth/spotify/callback`
2. Scopes: `user-library-read`, `playlist-read-private`, `user-follow-read`
3. Client ID + Client Secret → в `.env` как `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` / `SPOTIFY_REDIRECT_URI`

**Ограничения MVP:**
- Spotify → SoundCloud: только треки (mode=tracks; плейлисты TODO в следующей итерации)
- Refresh token не сохраняется — при истечении access_token нужна повторная авторизация
- Spotify UI скрыт если `SPOTIFY_CLIENT_ID` не задан

**Экспорт Spotify → File (дополнение к MM-22):**
- [x] `SpotifyAdapter`: добавить `Capability.EXPORT_TRACKS` + `session_token_key = "spotify_token"`
- [x] `core/export.py`: `export_library()` уже работает через adapter — достаточно добавить capability
- [x] `fetch_liked_tracks()` реализован в SpotifyAdapter (возвращает `[{artist, title}]`)

---

### 🔲 MM-23 — Telegram плейлисты (отложено)

> API не стандартизован. Реализовать когда появится ясность.

---

### ✅ MM-24 — Экспорт треков в файл (standalone)

> Отдельный поток: экспортировать треки из источника (YM / SoundCloud) в CSV/JSON файл без запуска переноса.
> Полезно для бэкапа библиотеки или ручного редактирования перед импортом.

- [x] GET /export — страница выбора источника и формата
- [x] POST /export/start — авторизация источника + скачивание файла (Response с Content-Disposition)
- [x] `Capability.EXPORT_TRACKS` — новый флаг в `core/services/base.py`; `session_token_key` на адаптере
- [x] `core/export.py` — `export_library(service_id, token, fmt)` + `exportable_services()`
- [x] `YandexMusicAdapter`: `EXPORT_TRACKS` capability + `fetch_liked_tracks(token)` → `[{artist, title}]`
- [x] Формат совместим с /import (колонки artist, title)
- [x] Ссылка «Экспорт» в nav (desktop + mobile)

---

### ✅ MM-28 — Экспорт SoundCloud → File

> Экспортировать лайкнутые треки из SoundCloud в CSV/JSON файл.
> Логика аналогична MM-24 (YM → File) — достаточно добавить capability в адаптер.

- [x] `SoundCloudAdapter`: добавить `Capability.EXPORT_TRACKS` + `session_token_key = "soundcloud_token"`
- [x] `SoundCloudAdapter`: реализовать `fetch_liked_tracks(token)` → `[{artist, title}]` (через `SoundCloudClient.get_liked_tracks()`)
- [x] `/export` показывает SoundCloud как источник (шаблон динамический — подхватывает автоматически)
- [x] `SoundCloudClient.get_liked_tracks()` — новый метод: GET `/me/track_likes` с пагинацией через `next_href`

---

### 🔲 MM-26 — Монетизация (после завершения всего функционала)

> Реализовать только когда продукт стабилен и есть реальные пользователи.

**Базовая модель (freemium):**
- [ ] 1 успешный перенос в день бесплатно (сброс в полночь UTC)
- [ ] Безлимитный план — подписка (месяц / год)
- [ ] Подписка хранится в БД: таблица `subscriptions` (user_id, plan, expires_at)
- [ ] Проверка лимита перед запуском — учитывает план пользователя

**Дополнительные идеи:**
- [ ] Пробный период 7 дней при первой регистрации
- [ ] Ограничение по кол-ву треков на бесплатном плане (напр. до 200 треков за раз)
- [ ] Реферальная программа: пригласи друга → +7 дней бесплатно обоим
- [ ] Поддержка платёжных систем: Telegram Stars (нативно в боте), ЮKassa (RU), Stripe (EU)
- [ ] Webhook от платёжной системы → активация подписки в БД
- [ ] Уведомление за 3 дня до истечения подписки (через бота и email)
- [ ] История платежей в личном кабинете (веб + бот)
- [ ] Admin: статистика по подпискам, MRR, активные пользователи

---

### ✅ MM-29 — PostgreSQL only (убрать SQLite)

> Alembic остаётся — он нужен для управления схемой PostgreSQL. Убираем только SQLite-специфику.

- [x] `aiosqlite` убран из `requirements.txt` → перенесён в `requirements-dev.txt`
- [x] Создан `requirements-dev.txt` (aiosqlite + pytest для локальной разработки)
- [x] `render_as_batch=True` убран из `alembic/env.py`
- [x] `db_path` и SQLite дефолт убраны из `config.py` (DATABASE_URL теперь требует явного задания)
- [x] `init_db()` удалён — схема управляется через `alembic upgrade head`
- [x] Вызовы `init_db()` удалены из api/main.py, migration/tracks.py, migration/spotify_tracks.py
- [x] `_dialect_insert()` сохраняет SQLite fallback только для in-memory тестовых фикстур
- [x] 133 теста проходят

---

### ✅ MM-34 — Файрвол на уровне провайдера (Timeweb Cloud)

> Whitelist-режим: только указанный трафик разрешён, остальное блокируется.

**RU сервер:**
- [x] TCP 22 — от всех (SSH)
- [x] TCP 1080 — только с 72.56.68.207 (EU сервер, SOCKS5)
- [x] Проверено: port 1080 закрыт с посторонних IP, прокси работает с EU

**EU сервер:**
- [x] TCP 22 — от всех (SSH)
- [x] TCP 80 — от всех (HTTP → nginx)
- [x] TCP 443 — от всех (HTTPS → nginx)
- [x] Проверено: SSH, 80, 443 доступны

---

### 🔲 MM-33 — YouTube Music интеграция

> Двунаправленная интеграция: чтение через `ytmusicapi` (unofficial, cookies), запись через YouTube Data API v3 (official, OAuth).
> YouTube Data API v3 поддерживает лайки, плейлисты, подписки на каналы официально.

**Архитектура:**
- **Чтение** (`ytmusicapi`, cookie-based): `get_liked_tracks()`, `get_playlists()`, `get_followed_artists()`
- **Запись** (YouTube Data API v3, OAuth): `like_track()` (`videos.rate`), `create_playlist()` (`playlists.insert`), `add_to_playlist()` (`playlistItems.insert`), `follow_artist()` (`subscriptions.insert`)
- Auth разделена: cookies для чтения, OAuth для записи

**Read (YT → другие сервисы):**
- [ ] `core/youtube/client.py` — `YouTubeMusicClient`: `get_liked_tracks()`, `get_playlists()`, `get_followed_artists()` (через `ytmusicapi`)
- [ ] `core/youtube/models.py` — `YTTrack`, `YTPlaylist`, `YTArtist`
- [ ] `core/services/youtube/adapter.py` — `YouTubeMusicAdapter`: `READ_LIKED_TRACKS | READ_PLAYLISTS | READ_LIKED_ARTISTS | EXPORT_TRACKS`
- [ ] Auth (чтение): cookie/headers JSON из браузера — аналогично SC токену

**Write (другие → YT):**
- [ ] `core/youtube/api_client.py` — `YouTubeAPIClient`: `like_track()`, `create_playlist()`, `add_to_playlist()`, `follow_channel()` (через YouTube Data API v3)
- [ ] Auth (запись): Google OAuth 2.0 (scopes: `youtube.force-ssl`)
- [ ] `core/services/youtube/adapter.py` — добавить `WRITE_LIKED_TRACKS | WRITE_PLAYLISTS | WRITE_LIKED_ARTISTS`
- [ ] ServiceRegistry matrix: * → YouTube (треки, плейлисты, артисты)
- [ ] `worker/tasks.py` — `run_youtube_migration_job` ARQ задача

**Web:**
- [ ] `api/routes/web.py` — YouTube в auth flow: отдельные секции для cookies (чтение) и OAuth (запись)
- [ ] ServiceRegistry matrix обновить: YT → SC/File, YM/Spotify/SC → YT

**Риски:**
- `ytmusicapi` — scraping, может сломаться при изменении YT
- YouTube Data API v3 — квоты (10 000 units/day по умолчанию); лайк = 50 units, создание плейлиста = 50 units
- Поиск треков: в YT нет прямого аналога "найти песню по artist+title" — нужен `search()` через ytmusicapi или YouTube Search API

---

### ✅ MM-35 — Текущий трек в прогрессе и логах

**Воркер / пайплайн:**
- [x] `migration/tracks.py` — `logger.info(f"[{i}/{total}] ▶ {track_str}")` перед каждым треком; `progress_callback` вызывается на каждом треке
- [x] `worker/tasks.py` — `_make_progress_callback(redis, migration_id)` → пишет `migration_current_track:{id}` в Redis (TTL 86400s) для всех трёх job типов
- [x] `migration/spotify_tracks.py` — `run_spotify_migration()` принимает и пробрасывает `progress_callback`

**Веб:**
- [x] `api/routes/web.py` — `status_fragment` читает `migration_current_track:{id}` из Redis, передаёт `current_track` в шаблон
- [x] `api/templates/fragments/status.html` — строка «♪ Сейчас: {track}» под прогресс-баром (HTMX обновляет каждые 3 с)

**REST API + Telegram бот:**
- [x] `api/routes/migrations.py` — `GET /api/migrations/{id}` включает `current_track` из Redis
- [x] `bot/handlers/migration.py` — poll-цикл добавляет `♪ {current_track}` к тексту прогресса
- [x] `core/i18n.py` — ключ `status_current_track` (ru/en)

---

### ✅ MM-36 — Выбор сервиса в Telegram боте

> Сейчас бот жёстко захардкожен на YM → SC. Нужно добавить выбор источника и приёмника через inline-кнопки.

**Источники (FROM):** Яндекс Музыка, Spotify *(TO всегда SoundCloud на данном этапе)*

**Реализация:**
- [x] `/migrate` теперь сначала показывает inline-кнопки выбора источника (Яндекс Музыка / Spotify)
- [x] FSM state `AuthFlow.selecting_from` — хранит выбор до перехода к авторизации
- [x] `bot/handlers/auth.py` — `_show_from_selection()`, `on_select_from_ym()`, `on_select_from_spotify()`
- [x] Если выбран Spotify и токен есть в сессии → показываем подтверждение для Spotify
- [x] Если выбран Spotify и токена нет → сообщение с ссылкой на веб-интерфейс
- [x] `bot/handlers/migration.py` — передаёт `from_service` и `spotify_token` в API
- [x] `bot/api_client.py` — `start_migration()` принимает `from_service`, `spotify_token`
- [x] `api/routes/migrations.py` — `StartMigrationRequest` маршрутизирует на `run_migration_job` или `run_spotify_migration_job`
- [x] i18n: `bot_select_from`, `bot_service_yandex`, `bot_service_spotify`, `bot_spotify_no_token`, `bot_confirm_spotify`, `bot_migration_started_spotify`

---

### 🔲 MM-37 — Настройка Spotify приложения

> Без `SPOTIFY_CLIENT_ID / SECRET / REDIRECT_URI` Spotify в веб-интерфейсе скрыт и не работает.
> Задача — зафиксировать процесс настройки и убедиться что всё задокументировано.

- [ ] Создать Spotify app на developer.spotify.com
- [ ] Прописать Redirect URI: `{API_BASE_URL}/auth/spotify/callback`
- [ ] Scopes для READ (уже): `user-library-read`, `playlist-read-private`, `user-follow-read`
- [ ] Scopes для WRITE *(после MM-39)*: + `user-library-modify`, `playlist-modify-private`, `playlist-modify-public`
- [ ] Добавить в `.env` на EU сервере: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`
- [ ] Проверить что кнопка Spotify появляется на `/auth` в веб-интерфейсе

---

### 🔲 MM-38 — Яндекс Музыка WRITE (лайки + плейлисты)

> Библиотека `yandex-music` поддерживает запись — можно переносить треки В Яндекс Музыку.
> Открывает направления: SC → YM, Spotify → YM, File → YM.

**YandexMusicClient (новые методы):**
- [ ] `like_track(track_id)` → `client.users_likes_tracks_add([track_id])` *(или батчем)*
- [ ] `create_playlist(title)` → `client.users_playlists_create(title, visibility='private')`
- [ ] `add_tracks_to_playlist(playlist_kind, tracks)` → `client.users_playlists_change(kind, diff)`
- [ ] `search_tracks(query)` — уже есть в YM API, нужен метод для поиска на YM по artist+title

**YandexMusicAdapter:**
- [ ] Добавить `WRITE_LIKED_TRACKS | WRITE_PLAYLISTS`
- [ ] Matcher: fuzzy-поиск результатов YM аналогично SC (rapidfuzz + транслитерация)

**Пайплайн:**
- [ ] `migration/yandex_tracks.py` — `migrate_to_yandex(sc_client_or_tracks, ym_client, migration_id)` — переиспользует `_run_pending_loop` логику
- [ ] `worker/tasks.py` — `run_yandex_migration_job`

**ServiceRegistry matrix после MM-38:**
```
SC → YM ✓, Spotify → YM ✓, File → YM ✓
```

**Риски:**
- `yandex-music` — неофициальная библиотека, методы write могут меняться
- Поиск на YM: качество результатов под вопросом — нужно тестировать matcher

---

### 🔲 MM-39 — Spotify WRITE (лайки + плейлисты)

> Официальный Spotify API поддерживает запись. Открывает направления: YM → Spotify, SC → Spotify, File → Spotify.

**SpotifyClient (новые методы):**
- [ ] `like_track(track_id)` → `PUT /me/tracks?ids={id}`
- [ ] `search_tracks(query)` → `GET /search?type=track` (для поиска по artist+title)
- [ ] `create_playlist(title)` → `POST /users/{user_id}/playlists`
- [ ] `add_tracks_to_playlist(playlist_id, track_uris)` → `POST /playlists/{id}/tracks`

**SpotifyAdapter:**
- [ ] Добавить `WRITE_LIKED_TRACKS | WRITE_PLAYLISTS`
- [ ] Дополнительные OAuth scopes: `user-library-modify`, `playlist-modify-private`, `playlist-modify-public`
- [ ] `save_user_id(token)` — нужен `user_id` для создания плейлиста (`GET /me`)

**Пайплайн:**
- [ ] `migration/spotify_write.py` — перенос треков В Spotify (поиск + лайк/добавление в плейлист)
- [ ] `worker/tasks.py` — `run_spotify_write_job`

**ServiceRegistry matrix после MM-39:**
```
YM → Spotify ✓, SC → Spotify ✓, File → Spotify ✓
```

**Важно:** refresh token нужно начать сохранять (сейчас не сохраняется — MM-22 limitation). Без него токен истекает через 1 час.

---

### ✅ MM-32 — Читаемые логи в Docker

- [x] Убрать дублирование: `LOG_FORMAT` env var переключает режим (`pretty` | `json`)
- [x] `pretty` (default) — один sink: stderr, colored (локальная разработка)
- [x] `json` — один sink: stdout, newline-delimited JSON (Docker/Promtail)
- [x] `docker-compose.yml` — `LOG_FORMAT=json` прописан для api/bot/worker
- [x] `config.py` — `log_format` поле; `CLAUDE.md` — задокументировано

---

### 🔲 MM-40 — Динамическая оценка времени переноса

> Вместо хардкода «5000 треков ≈ 3–4 часа» — показывать живую оценку на основе реального количества треков.
> Файловые миграции всё равно проходят через SC rate limit, поэтому оценка применима и к ним.

**Формула:** `SC_RATE_LIMIT_SLEEP` (сек) + ~1 сек на поиск + ~0.5 сек overhead ≈ **3–4 сек/трек**
- Консервативная оценка: `ceil(track_count * 3.5 / 60)` минут
- До 60 мин — показываем в минутах; больше — в часах и минутах

**Места отображения:**
- [ ] `core/i18n.py` — хелпер `format_eta(track_count, sc_rate_limit_sleep)` → локализованная строка
- [ ] Бот, экран подтверждения YM (`_show_confirmation`) — добавить строку `⏱ Примерно N мин`
- [ ] Бот, экран подтверждения Spotify (`_show_confirmation_spotify`) — то же самое
- [ ] Веб, страница `/migrate` (confirmation template) — добавить `⏱ Примерно N мин`
- [ ] `bot_confirm`, `bot_confirm_spotify` i18n-ключи — добавить `{eta}` placeholder
- [ ] Убрать хардкод «5000 треков ≈ 3–4 часа» из `bot_confirm_spotify`

---

### ✅ MM-41 — Spotify i18n в веб-интерфейсе

> В `auth.html` использовались ключи без перевода в `core/i18n.py`.

- [x] `auth_spotify_hint` — «Нажми кнопку ниже, чтобы войти через Spotify» (ru/en)
- [x] `auth_spotify_btn` — «Подключить Spotify» (ru/en)
- [x] `auth_source_label` — «Откуда переносить» (ru/en) — тоже отсутствовал
- [x] `auth_dest_label` — «Куда переносить» (ru/en) — тоже отсутствовал
- [x] Проверены все `t('...')` вызовы в templates/ — других пропущенных ключей нет

---

### 🔲 MM-30 — README

- [ ] Описание сервиса (что делает, кому нужен)
- [ ] Инструкция по запуску через docker-compose (prod)
- [ ] Переменные окружения (.env)
- [ ] Telegram-бот — как найти, команды
- [ ] Веб-интерфейс — разделы и функции
- [ ] FAQ: как получить токены, что делать если трек не найден

---

### ✅ MM-31 — Управление доступом к веб-интерфейсу

> Возможность запустить только бэкенд + бот без веба, или закрыть веб для определённых IP.

- [x] `config.py` — `web_enabled: bool = True` и `web_allowed_ips: str = ""`
- [x] `api/middleware.py` — `WebIPWhitelistMiddleware`: проверяет IP по `X-Forwarded-For` / `request.client.host`; `/api/*` и `/health` всегда доступны
- [x] `api/main.py` — web.router и admin.router регистрируются только если `web_enabled=True`; `WebIPWhitelistMiddleware` добавляется только если `web_allowed_ips` задан
- [x] CLAUDE.md — `WEB_ENABLED` и `WEB_ALLOWED_IPS` задокументированы в env-переменных
- [x] 133 теста проходят
- [ ] docker-compose `profiles` — отложено (достаточно `WEB_ENABLED=false` в .env)

---

### ✅ MM-25 — Сетевая безопасность RU-сервера

> Dante SOCKS5 прокси на RU сервере сейчас доступен без ограничений по IP.
> Нужно закрыть порт 1080 для всех кроме EU сервера (и опционально локальной машины разработчика).
> Реализовано через Ansible playbooks (не bash-скрипты).

- [x] `infrastructure/ansible/ru.yml` — ufw (deny all, allow 22 + 1080 только с EU IP / dev IP) + Dante с `socksmethod: username` + создание системного пользователя
- [x] `infrastructure/ansible/eu.yml` — Docker setup + git pull + `docker compose up --build -d` + healthcheck
- [x] `infrastructure/ansible/inventory.yml` — хосты EU и RU серверов
- [x] `infrastructure/ansible/group_vars/all.yml` — общие переменные (eu_server_ip, dante_user, deploy_dir)
- [x] `infrastructure/ansible/group_vars/vault.yml` — секреты (dante_password, не коммитится — gitignored)
- [x] `infrastructure/ansible/templates/danted.conf.j2` — Dante конфиг с username auth
- [x] **Применено на серверах** — ufw активен, Dante перезапущен с новым конфигом, прокси протестирован

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| SoundCloud rate limit | sleep(2) + 429 backoff с reset_time |
| Трек не найден (кириллица) | iuliia транслитерация + dual-path scoring |
| Обрыв задачи | arq retry + resumable пайплайн |
| Yandex Music недоступен с EU IP | SOCKS5 прокси через RU сервер ✅ |
| SoundCloud недоступен с RU IP | Воркер на EU сервере |
| 20-30 параллельных пользователей | arq max_jobs, asyncpg pool, per-user rate limit |
| Истёкший токен во время миграции | Проверка при старте + graceful fail |
| SC токен (cookie) — короткий срок | Уведомление + инструкция по обновлению |
