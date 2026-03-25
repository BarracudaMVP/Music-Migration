# MM — Music Migration

Универсальный сервис переноса музыкальных библиотек между стриминговыми платформами.
Доступен через Telegram-бот и веб-интерфейс. Единый бэкенд обрабатывает задачи от обоих клиентов.

---

## Стек

- **API**: FastAPI + Jinja2 + HTMX (legacy) / React SPA (MM-83 ✅, ветка `feature/spa`)
- **БД**: PostgreSQL + SQLAlchemy 2.x async + Alembic
- **Очередь**: arq (Redis)
- **Бот**: aiogram 3.x
- **Инфра**: Docker + docker-compose + Nginx
- **Прокси**: Dante SOCKS5 на RU сервере (для Яндекс Музыки)

---

## Архитектура

```
┌─────────────────────┐  ┌──────────────────────────┐  ┌────────────────────────┐
│   Telegram Bot      │  │  Web UI (Jinja2 + HTMX)  │  │   SPA Frontend         │
│   (aiogram 3.x)     │  │  / /migrate /history     │  │   (React/Vue/etc.)     │
│   FSM: пошаговый    │  │  /auth/* /api/flow/*     │  │   localhost:3000 / CDN │
└──────────┬──────────┘  └─────────────┬────────────┘  └──────────┬─────────────┘
           │ HTTP (internal API)        │ HTTP                      │ HTTP (JWT Bearer)
           └────────────────┬──────────┘                           │
                            ▼                                       │
              ┌─────────────────────────────────────────────────────┤
              │              FastAPI Server                          │
              │  /api/v1/*   — SPA JSON API (JWT, always on)        │
              │  /auth/*     — OAuth redirect/callback (oauth.py)   │
              │  /api/*      — Internal (bot, worker)               │
              │  /admin/*    — Admin UI (gated by WEB_ENABLED)      │
              │  Middleware: CORS, IP whitelist, AllowedUsers, Rate  │
              └────────┬────────────────────────────────────────────┘
                       │
            ┌──────────┼────────────┐
            ▼          ▼            ▼
      [PostgreSQL]   [Redis]   [Sessions]
       (tokens,     (ARQ jobs,  (cookies — Jinja2 only)
        migrations,  OAuth state, spa_refresh_token in DB)
        tracks)      progress,
                     rate limit)
                       │
                       ▼
          ┌────────────────────────┐
          │      ARQ Worker        │
          │  run_migration_job       │  ← YM → SC (playlist_mode=True)
          │  run_file_migration_job  │  ← File → SC (playlist_mode=True)
          │  run_spotify_migration_job│ ← Spotify → SC (playlist_mode=True)
          │  run_yandex_migration_job │  ← any → YM
          │  run_spotify_write_job   │  ← any → Spotify (auto-refresh token,
          │                          │    playlist_mode, playlist_name)
          └────────────┬─────────────┘
                       │
                       ▼
          ┌────────────────────────────┐
          │  migration/pipeline.py     │  ← platform-agnostic
          │  run_pending_tracks_loop() │     (MM-87 AdapterWriteSession ABC)
          └────────────┬───────────────┘
                       │  write_session(token)
         ┌─────────────┼──────────────┐
         ▼             ▼              ▼
  ┌─────────────┐ ┌──────────┐ ┌──────────────┐
  │ YM Adapter  │ │SC Adapter│ │Spotify Adapt.│  + FileAdapter
  │ (RU proxy   │ │(OAuth,   │ │(OAuth +       │    (CSV/JSON)
  │  socks5://) │ │playlist) │ │ auto-refresh, │
  │             │ │          │ │ playlist_mode)│
  └──────┬──────┘ └────┬─────┘ └──────┬───────┘
         │             │              │
         ▼             ▼              ▼
  api.music.yandex  api.soundcloud.com  api.spotify.com

DEV_MODE=true: _ensure_user_id() → "dev_user" (seed via scripts/seed_dev.py)
               auto-disabled if WEB_BASE_URL points to non-localhost domain
```

---

## Реестр сервисов

```
Capability:
  READ_LIKED_TRACKS      WRITE_LIKED_TRACKS
  READ_PLAYLISTS         WRITE_PLAYLISTS
  READ_LIKED_ARTISTS     WRITE_LIKED_ARTISTS
  EXPORT_TRACKS

Сервисы (текущее состояние, MM-76 + MM-81 + MM-85):
  yandex_music:   READ_LIKED_TRACKS, READ_PLAYLISTS, READ_LIKED_ARTISTS, EXPORT_TRACKS, WRITE_LIKED_TRACKS
  soundcloud:     READ_LIKED_TRACKS, WRITE_LIKED_TRACKS, WRITE_PLAYLISTS, WRITE_LIKED_ARTISTS, EXPORT_TRACKS
                  (OAuth Authorization Code Flow, api.soundcloud.com, Authorization: OAuth {token})
  file:           EXPORT_TRACKS, WRITE_LIKED_TRACKS  (MM-69: переименован с "file_csv"; CSV/JSON import+export)
  spotify:        READ_LIKED_TRACKS, READ_PLAYLISTS, READ_LIKED_ARTISTS, EXPORT_TRACKS,
                  WRITE_LIKED_TRACKS, WRITE_LIKED_ARTISTS, WRITE_PLAYLISTS (MM-88/89: create_playlist + add_tracks_to_playlist)
                  dev mode: max 25 пользователей в allowlist; SPOTIFY_BOT_TOKEN — опциональный бот-аккаунт для плейлистов
```

```
Матрица переносов (текущая):
FROM \ TO     | SoundCloud | Файл (CSV/JSON) | Яндекс Музыка | Spotify
--------------|------------|-----------------|---------------|--------
Яндекс Музыка |     ✓      |        ✓        |       –       |    ✓
Spotify       |     ✓      |        ✓        |       ✓       |    –
Файл          |     ✓      |        ✗        |       ✓       |    ✓
SoundCloud    |     –      |        ✓        |       ✓       |    ✓
```
Примечание: File→File запрещён (нет смысла). В UI карточка "В файл" скрывается когда FROM=Файл.

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

### ✅ MM-9 — SSL / HTTPS
- [x] Домен musicmigration.site куплен
- [x] Домен → A-запись на EU сервер (сделать вручную)
- [x] certbot certonly --standalone через docker (scripts/setup-ssl.sh)
- [x] nginx/nginx.conf — HTTP→HTTPS редирект + HTTPS server block (TLSv1.2/1.3, HSTS)
- [x] Авторенью: scripts/renew-ssl.sh (webroot, cron)
- [ ] WEB_BASE_URL=https://musicmigration.site в .env на сервере (после деплоя)
- [ ] Spotify redirect URI обновить в developer.spotify.com

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

### ✅ MM-27 — entrypoint.sh → scripts/

> Перенос скрипта запуска Docker-контейнера из корня проекта в `scripts/`.

- [x] `scripts/entrypoint.sh` — создан (копия корневого `entrypoint.sh`)
- [x] `entrypoint.sh` — удалён из корня
- [x] `Dockerfile.api` — обновлён: `chmod +x scripts/entrypoint.sh`, `CMD ["./scripts/entrypoint.sh"]`

**Файлы:** `scripts/entrypoint.sh` (создан), `entrypoint.sh` (удалён), `Dockerfile.api`

---

### ✅ MM-28 — Экспорт SoundCloud → File

> Экспортировать лайкнутые треки из SoundCloud в CSV/JSON файл.
> Логика аналогична MM-24 (YM → File) — достаточно добавить capability в адаптер.

- [x] `SoundCloudAdapter`: добавить `Capability.EXPORT_TRACKS` + `session_token_key = "soundcloud_token"`
- [x] `SoundCloudAdapter`: реализовать `fetch_liked_tracks(token)` → `[{artist, title}]` (через `SoundCloudClient.get_liked_tracks()`)
- [x] `/export` показывает SoundCloud как источник (шаблон динамический — подхватывает автоматически)
- [x] `SoundCloudClient.get_liked_tracks()` — новый метод: GET `/me/track_likes` с пагинацией через `next_href`

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

### ✅ MM-30 — README

- [x] Описание сервиса (что делает, кому нужен)
- [x] Инструкция по запуску через docker-compose (prod)
- [x] Переменные окружения (.env)
- [x] Telegram-бот — как найти, команды
- [x] Веб-интерфейс — разделы и функции
- [x] FAQ: как получить токены, что делать если трек не найден

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

### ✅ MM-32 — Читаемые логи в Docker

- [x] Убрать дублирование: `LOG_FORMAT` env var переключает режим (`pretty` | `json`)
- [x] `pretty` (default) — один sink: stderr, colored (локальная разработка)
- [x] `json` — один sink: stdout, newline-delimited JSON (Docker/Promtail)
- [x] `docker-compose.yml` — `LOG_FORMAT=json` прописан для api/bot/worker
- [x] `config.py` — `log_format` поле; `CLAUDE.md` — задокументировано

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

### ✅ MM-37 — Настройка Spotify приложения

> Без `SPOTIFY_CLIENT_ID / SECRET / REDIRECT_URI` Spotify в веб-интерфейсе скрыт и не работает.

**Scopes (все нужные, задаются в developer.spotify.com при создании app):**
- READ: `user-library-read`, `playlist-read-private`, `user-follow-read`
- WRITE (MM-39): `user-library-modify`, `user-follow-modify`

**Шаги (однократно на EU сервере):**
- [x] Создать Spotify app на developer.spotify.com → My Apps → Create app
- [x] Прописать Redirect URI: `{API_BASE_URL}/auth/spotify/callback`
- [x] Добавить в `.env` на EU сервере: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`
- [x] `docker compose restart api bot worker`
- [x] Проверить что кнопка Spotify появляется на `/auth` в веб-интерфейсе

**Код (уже готов):**
- `spotify_enabled = bool(cfg.spotify_client_id)` — кнопка скрыта если `SPOTIFY_CLIENT_ID` не задан
- `/auth/spotify` → 303 redirect с ошибкой если `spotify_client_id` пустой
- Все scopes прописаны в `core/spotify/oauth.py` (`_SCOPES`)

---

### ✅ MM-38 — Яндекс Музыка WRITE (лайки)

> Открывает направления: SC → YM ✓, Spotify → YM ✓

**YandexMusicClient (новые методы):**
- [x] `search_tracks(query, limit=10)` → `client.search(type_="track")`
- [x] `like_track(track_id)` → `client.users_likes_tracks_add([track_id])`

**Адаптеры:**
- [x] `YandexMusicAdapter` — добавлен `WRITE_LIKED_TRACKS`
- [x] `SoundCloudAdapter` — добавлен `READ_LIKED_TRACKS` (метод уже был, флаг отсутствовал)
- ServiceRegistry matrix автоматически открывает SC→YM и Spotify→YM

**Пайплайн:**
- [x] `migration/yandex_tracks.py` — `migrate_to_yandex(tracks_data, ym_client, migration_id)` — те же паттерны что в `tracks.py`: multi-query, dedup, fuzzy match, sleep 1.0s/трек
- [x] `worker/tasks.py` — `run_yandex_migration_job(ctx, migration_id, source_token, from_service, ym_token, user_id)` — читает треки через ServiceRegistry adapter
- [x] `worker/main.py` — зарегистрирован новый job
- [x] `api/routes/migrations.py` — добавлен `to_service` (`soundcloud` | `yandex_music`), маршрутизация на нужный job

---

### ✅ MM-39 — Spotify WRITE (лайки треков + подписки на артистов)

> Официальный Spotify API поддерживает запись. Открывает направления: YM → Spotify ✓, SC → Spotify ✓

**SpotifyClient (новые методы):**
- [x] `search_tracks(query, limit=10)` → `GET /search?type=track`
- [x] `like_track(track_id)` → `PUT /me/tracks` body `{"ids": [id]}`
- [x] `search_artists(query, limit=10)` → `GET /search?type=artist`
- [x] `follow_artist(artist_id)` → `PUT /me/following?type=artist` body `{"ids": [id]}`

**OAuth scopes:**
- [x] Добавлены `user-library-modify` и `user-follow-modify`
- [x] `spotify_refresh_token` — новый столбец в БД + алембик-миграция, сохраняется при OAuth

**SpotifyAdapter:**
- [x] Добавлены `WRITE_LIKED_TRACKS | WRITE_LIKED_ARTISTS`

**Пайплайн:**
- [x] `migration/spotify_write.py` — `migrate_to_spotify()` (треки) + `migrate_artists_to_spotify()` (артисты)
- [x] `worker/tasks.py` — `run_spotify_write_job`: читает треки через ServiceRegistry adapter, авто-рефреш токена перед стартом
- [x] `api/routes/migrations.py` — `to_service=spotify` маршрутизирует на `run_spotify_write_job`

---

### ✅ MM-40 — Динамическая оценка времени переноса

> `format_eta(track_count, to_service, lang, sc_rate_limit_sleep)` → «⏱ ~6 мин» / «⏱ ~4 ч 52 мин»

**Оценки по сервису-получателю:**
- `soundcloud`: `SC_RATE_LIMIT_SLEEP + 1.5` сек/трек (100 треков ≈ 6 мин при sleep=2.0)
- `spotify`: 0.8 сек/трек
- `yandex_music`: 1.5 сек/трек

**Реализация:**
- [x] `core/i18n.py` — `format_eta()`, ключи `eta_approx`, `eta_approx_hours`, `eta_label`
- [x] `bot_confirm`, `bot_confirm_spotify` — убран хардкод, добавлен `{eta}` placeholder
- [x] Бот, оба экрана подтверждения (`_show_confirmation`, `_show_confirmation_spotify`) — вычисляют и передают ETA
- [x] Веб, `status.html` fragment — показывает ETA по количеству pending-треков (строка ниже current_track)
- [x] `web.py` `migration_status_fragment` — вычисляет `eta` и передаёт в шаблон

---

### ✅ MM-41 — Spotify i18n в веб-интерфейсе

> В `auth.html` использовались ключи без перевода в `core/i18n.py`.

- [x] `auth_spotify_hint` — «Нажми кнопку ниже, чтобы войти через Spotify» (ru/en)
- [x] `auth_spotify_btn` — «Подключить Spotify» (ru/en)
- [x] `auth_source_label` — «Откуда переносить» (ru/en) — тоже отсутствовал
- [x] `auth_dest_label` — «Куда переносить» (ru/en) — тоже отсутствовал
- [x] Проверены все `t('...')` вызовы в templates/ — других пропущенных ключей нет

---

### 🔲 MM-42 — Яндекс Музыка WRITE артисты

> Дополнение к MM-38: лайки артистов в Яндекс Музыке.

- [ ] `YandexMusicClient.search_artists(query, limit=10)` → `client.search(type_="artist")`
- [ ] `YandexMusicClient.like_artist(artist_id)` → `users_likes_artists_add([artist_id])`
- [ ] `YandexMusicAdapter`: добавить `WRITE_LIKED_ARTISTS`
- [ ] `migration/yandex_tracks.py`: добавить `migrate_artists_to_yandex(artists_data, ym_client, migration_id)`
- [ ] `worker/tasks.py`: расширить `run_yandex_migration_job` поддержкой `migrate_artists`

---

### ✅ MM-43 — Яндекс OAuth автоматический callback (веб)

- [x] `config.py` — `yandex_redirect_uri: str`
- [x] `bot/oauth/yandex.py` — `get_callback_auth_url(state)`, `exchange_code_callback(code)`
- [x] `api/routes/web.py` — `GET /auth/yandex` (web start), `GET /auth/yandex/callback` (unified)
- [x] `api/templates/auth.html` — кнопка если `yandex_redirect_uri` задан, форма-fallback если нет
- [x] Зарегистрировать `https://musicmigration.site/auth/yandex/callback` в oauth.yandex.ru
- [x] `YANDEX_REDIRECT_URI=https://musicmigration.site/auth/yandex/callback` в .env на сервере

---

### ✅ MM-44 — Яндекс OAuth через веб-посредник для Telegram-бота

- [x] `bot/handlers/auth.py` — UUID state в FSM, кнопки [Войти] + [✓ Я авторизовался]
- [x] `api/routes/web.py` — `GET /auth/yandex/bot?state=bot_{uuid}` (bot start), сохраняет токен в Redis TTL 300s
- [x] `api/routes/web.py` — `GET /api/auth/yandex/poll/{state_id}` (internal, бот поллит)
- [x] `bot/api_client.py` — `poll_yandex_token(state_id)`
- [x] Fallback: если `yandex_redirect_uri` не задан — старый flow с вводом кода

---

### ✅ MM-45 — SoundCloud мобильная авторизация

> Закрыта как часть MM-52 — официальный OAuth полностью заменяет cookie-подход и решает мобильную авторизацию заодно.

---

### 🔲 MM-46 — Перенос приложения из /root/ в /opt/ на EU сервере

> Технический долг: приложение лежит в `/root/Music-Migration/` — домашней директории root.
> Стандартное место для сервисов: `/opt/music-migration/`.

- [ ] Создать системного пользователя `musicmigration` (без shell, без пароля)
- [ ] Перенести проект: `cp -r /root/Music-Migration /opt/music-migration`
- [ ] Обновить `deploy_dir` в Ansible `group_vars/all.yml`
- [ ] Обновить `docker-compose.yml` если есть абсолютные пути (volume mounts)
- [ ] Проверить nginx конфиг — путей к проекту там нет, но проверить
- [ ] `docker compose down` → перенос → `docker compose up -d` в новом месте
- [ ] Убедиться что `.env` скопирован и данные БД (postgres volume) сохранены
- [ ] Удалить `/root/Music-Migration/` после проверки

> Выполнять вместе с каким-либо плановым деплоем (например MM-9), чтобы не делать лишний даунтайм.

---

### ✅ MM-47 — SoundCloud playlist_mode (замена like_track плейлистами)

> SC API возвращает HTTP 404 на `PUT /me/track_likes/{id}` для внешних токенов.
> Решение: собирать sc_id в памяти в ходе поиска, в конце создавать плейлисты батчами.

- [x] `config.py` — `sc_playlist_batch_size: int = 500` (env: `SC_PLAYLIST_BATCH_SIZE`)
- [x] `migration/tracks.py` — `playlist_mode: bool = False` во всех функциях пайплайна
- [x] `migration/tracks.py` — `_process_one_track` возвращает `tuple[str, int | None]`; в playlist_mode не вызывает `like_track`, сразу маркирует `status=liked` и возвращает `sc_id`
- [x] `migration/tracks.py` — `_run_pending_loop` собирает `collected_ids`, после цикла вызывает `_create_liked_playlists`
- [x] `migration/tracks.py` — `_create_liked_playlists(sc_client, track_ids)`: батчи по `sc_playlist_batch_size`, плейлисты "YM Liked #1", "YM Liked #2"…
- [x] `migration/spotify_tracks.py` — `playlist_mode` пробрасывается через `migrate_spotify_tracks` и `run_spotify_migration`
- [x] `worker/tasks.py` — все три SC-джоба (`run_migration_job`, `run_file_migration_job`, `run_spotify_migration_job`) с `playlist_mode=True`
- [x] `CLAUDE.md` — `SC_PLAYLIST_BATCH_SIZE` в env vars, паттерн в Key Patterns, Architecture обновлена

**Ключевые решения:**
- Поиск и `like_track` разделены: весь цикл — только search+match (без write API), плейлист создаётся один раз в конце
- `playlist_mode=False` по умолчанию — не ломает тесты и CLI
- При одном батче плейлист называется "YM Liked", при нескольких — "YM Liked #N"

---

### ✅ MM-48 — Выбор режима лайков при переносе

> Сейчас `playlist_mode` жёстко захардкожен в воркере. Пользователь не влияет на то, лайкать ли треки.
> Нужно спрашивать при каждом переносе (кроме File): "Проставить лайки?" и действовать по ответу.
> Если лайки недоступны (SC 404) — автоматически fallback на плейлист.

**Флоу:**
```
Подтверждение переноса
  ├── [✓] Проставить лайки  →  пробуем like_track, при 404 fallback → playlist
  └── [ ] Только плейлист   →  playlist_mode=True, like_track не вызывается
```

**Статусы и модель лайков:**
- `liked` = "успешно обработано": трек либо добавлен в плейлист, либо лайкнут напрямую (статус один, не разделяем)
- Лайк — дополнительное действие: при `like_tracks=True` пробуем прямой лайк; при 404 → fallback в плейлист (тоже `liked`)
- Лайкнутый напрямую трек НЕ добавляется в плейлист дополнительно — одно или другое
- Отображение `liked` → **"Добавлено"** везде (БД-статус `liked` не меняется)

**Веб:**
- [x] `api/templates/index.html` — чекбокс "Проставить лайки на треки" (по умолчанию выключен)
- [x] `api/routes/web.py` — `like_tracks: bool = Form(False)`, передаётся в SC ARQ jobs
- [x] `core/i18n.py` — `status_transferred`, `status_progress`, `tstatus_liked`, `result_liked`, `result_progress`, `tracks_liked` → "Добавлено"/"Added"; `_TRACK_STATUS_LABEL_RU["liked"]` → "Добавлен"

**Бот:**
- [x] `bot/handlers/auth.py` — `_confirmation_kb` принимает `to_service`, `like_tracks`; новая кнопка-тогл "❤️ Лайкать треки: Вкл/Выкл" (только для SC destination); `on_toggle_like_tracks` handler
- [x] `bot/handlers/migration.py` — читает `like_tracks` из state, передаёт в `api_client.start_migration`
- [x] `bot/api_client.py` — поле `like_tracks` в теле запроса
- [x] `core/i18n.py` — `bot_like_tracks_on`, `bot_like_tracks_off`; `bot_progress_bar`, `bot_done_tracks`, `notif_done` → "Добавлено"

**Пайплайн:**
- [x] `api/routes/migrations.py` — `StartMigrationRequest.like_tracks: bool = False`; SC jobs получают `like_tracks=like`
- [x] `worker/tasks.py` — `run_migration_job`, `run_spotify_migration_job`, `run_file_migration_job`: `playlist_mode = not like_tracks`; `like_tracks` пробрасывается в migration functions
- [x] `migration/tracks.py` — `_process_one_track(like_tracks=False)`: при `like_tracks=True` — пробуем `like_track()`, при `LikeNotSupportedError` → возвращаем sc_id для плейлиста; `_run_pending_loop` собирает sc_id без привязки к `playlist_mode` (создаёт плейлисты если есть collected_ids)
- [x] `migration/spotify_tracks.py` — аналогично; `like_tracks` пробрасывается в `_run_pending_loop`
- [x] `core/soundcloud/client.py` — `LikeNotSupportedError` при HTTP 404 в `like_track`

---

### ✅ MM-49 — Редизайн веб-интерфейса (эталонный флоу)

> Полный редизайн UX веб-приложения: пошаговый выбор сервисов, авторизация встроена в флоу, импорт/экспорт как сервисы, чистая навигация.
> **Этот флоу является эталоном для MM-56** (редизайн бота): Telegram-бот должен воспроизвести ту же последовательность шагов в своём UI.

**Флоу главного экрана (пошаговый выбор):**
```
Шаг 1: Выбор FROM — карточки сервисов (YM | Spotify | SC | 📁 Из файла)
         → после клика карточка "FROM" фиксируется, появляются карточки TO
Шаг 2: Выбор TO — только те сервисы, куда возможен перенос из выбранного FROM (из матрицы)
         → если TO = "В файл" → выбор формата (CSV / JSON)
Шаг 3: Выбор типа контента — чекбоксы (Треки / Плейлисты / Артисты)
         → показываются только те, где есть пересечение READ у FROM и WRITE у TO
         → если доступен только один тип — чекбоксы всё равно показываются (но один из них неактивен)
Шаг 4: Авторизация — встроена прямо в флоу (не отдельная страница /auth)
         → показываются только нужные блоки авторизации (FROM + TO)
         → если токен уже сохранён и валиден — шаг пропускается автоматически
Шаг 5: Настройки переноса (лимит, пропуск ранее перенесённых)
Шаг 6: /migrate/{id} — прогресс
Шаг 7: /migrate/{id}/tracks — итог с "Мои переносы"
```

**Матрица доступности чекбоксов (из Capability флагов адаптеров):**
```
FROM → TO        | Треки | Плейлисты | Артисты
-----------------|-------|-----------|--------
YM → SC          |   ✓   |     ✓     |    ✓
YM → Spotify     |   ✓   |     ✗     |    ✓
YM → File        |   ✓   |     ✗     |    ✗
Spotify → SC     |   ✓   |     ✓     |    ✓
Spotify → YM     |   ✓   |     ✗     |    ✗  (YM нет WRITE_LIKED_ARTISTS)
Spotify → File   |   ✓   |     ✗     |    ✗
SC → YM          |   ✓   |     ✗     |    ✗  (SC нет READ_PLAYLISTS/READ_LIKED_ARTISTS)
SC → Spotify     |   ✓   |     ✗     |    ✗
SC → File        |   ✓   |     ✗     |    ✗
File → any       |   ✓   |     ✗     |    ✗
```
Логика: чекбокс активен (enabled) если `FROM.can(READ_X) and TO.can(WRITE_X)`, иначе disabled + не отмечен.
Блок чекбоксов всегда показывается. Недоступные типы отображаются серым (disabled).
Чекбокс "Треки" всегда enabled (треки поддерживаются для всех пар).

**Импорт/Экспорт как сервисы:**
- "Из файла" (FROM) — пользователь загружает файл; формат определяется автоматически (CSV/JSON); убрать подпись "Или загрузи файл со списком треков. Импорт" с главного экрана (она дублирует этот шаг)
- "В файл" (TO) — пользователь выбирает формат (CSV / JSON) после выбора TO
- Вкладки `/import` и `/export` скрыть из навигации (функциональность доступна через флоу)

**Навигация:**
- [ ] Скрыть кнопку "Аккаунт" — авторизация встроена в флоу выбора сервиса
- [ ] Скрыть кнопку "Выход" — выход только через сброс cookies в браузере, кнопки нет
- [ ] Скрыть вкладки "Импорт" и "Экспорт" из шапки
- [ ] "История" → "Мои переносы": видна только если у пользователя есть хотя бы один перенос; при входе если есть хотя бы один — автоматически редирект туда (или показ баннера)
- [ ] Смена языка — иконка флага (🇷🇺 / 🇬🇧) вместо текстовой кнопки, интуитивно понятна

**Безопасность миграций:**
- [x] Пользователь видит только свои миграции (`/migrate/{id}/tracks`, `/history` — фильтр по `user_id` из сессии)
- [x] Попытка открыть чужую миграцию → 403 или редирект на главную
- [ ] Админ через `/admin/migrations` видит все (без изменений) — не трогали, уже работает
- [x] `api/routes/web.py` — в `migration_progress`, `migration_status_fragment`, `get_migration_tracks` добавить проверку `migration["user_id"] == session_user_id`

**Что сделано:**

*Главная / выбор сервисов:*
- [x] `api/templates/index.html` — пошаговый флоу: FROM карточки → TO карточки (HTMX) → content types + auth + settings (HTMX)
- [x] `api/routes/web.py` — `GET /api/flow/to-step?from={service}` и `GET /api/flow/rest?from={service}&to={service}` (HTMX fragments)
- [ ] При выборе TO="file" — inline-выбор формата (отложено, file_csv не в матрице)
- [x] Убрана подпись "Или загрузи файл..." — заменена карточкой "📁 Из файла" → /import

*Выбор типа контента:*
- [x] `api/templates/fragments/flow_rest.html` — чекбоксы Треки/Плейлисты/Артисты
- [x] Логика доступности через `FROM.can(READ_X) and TO.can(WRITE_X)` — недоступные disabled
- [x] `POST /migrate` — читает `content_types[]` из формы, вычисляет `mode=full|tracks`
- [x] `core/i18n.py` — новые ключи добавлены

*Авторизация встроена:*
- [x] Статус авторизации FROM/TO показывается в `flow_rest.html` прямо в форме
- [x] OAuth callbacks после авторизации редиректят на `/?pf=...&pt=...` (восстановление флоу)

*Навигация:*
- [x] `api/templates/base.html` — убраны "Аккаунт", "Выход"; флаги 🇷🇺/🇬🇧 для языка; "Мои переносы" только при `has_migrations`
- [x] `api/routes/web.py` — `GET /` передаёт `has_migrations` в шаблон

*Мои переносы:*
- [x] "Мои переносы" в шапке при наличии переносов
- [ ] Авто-редирект на `/transfers` при наличии активного — отложено

*Защита миграций:*
- [x] Проверка `user_id` в `/migrate/{id}`, `/migrate/{id}/status-fragment`, `/migrate/{id}/tracks`

*i18n:*
- [x] Добавлены: `nav_my_transfers`, `step_from`, `step_to`, `step_content_type`, `step_auth`, `step_settings`, `content_tracks`, `content_playlists`, `content_artists`, `auth_status_connected`, `auth_status_not_connected`, `from_file_btn`, `step_loading`, `step_select_from`, `step_select_to`

---

### ✅ MM-50 — Лимит треков при переносе

> Для тестирования и поэтапного переноса: пользователь выбирает сколько треков перенести — все или первые N.
> Лимит применяется после загрузки из источника, перед вставкой в БД.

**Веб:**
- [x] `api/templates/index.html` — поле "Лимит треков": дропдаун (Все / 50 / 100 / 500)
- [x] `api/routes/web.py` — `track_limit: int = Form(0)` в `start_migrate`, `0` → `None`
- [x] `core/i18n.py` — ключи `index_track_limit`, `index_limit_all`, `index_limit_first`

**Бот:**
- [x] `bot/states.py` — добавлен `AuthFlow.selecting_limit`
- [x] `bot/handlers/auth.py` — кнопки режима `select_mode:tracks/full`; отдельный шаг лимита (Все/50/100/500)
- [x] `bot/handlers/migration.py` — `on_select_mode` → `selecting_limit`; `on_start_migration` парсит лимит
- [x] `bot/api_client.py` — `start_migration()` принимает и передаёт `track_limit`
- [x] `core/i18n.py` — `bot_select_limit`, `bot_btn_limit_all`, `bot_btn_limit_n`

**Пайплайн:**
- [x] `migration/tracks.py` — `migrate_tracks(..., track_limit=None)` + `migrate_from_file_tracks`
- [x] `migration/spotify_tracks.py` — `migrate_spotify_tracks(..., track_limit=None)`
- [x] `worker/tasks.py` — все 5 джобов принимают и пробрасывают `track_limit: int | None = None`
- [x] `api/routes/migrations.py` — `StartMigrationRequest` добавлен `track_limit: int | None = None`

---

### ✅ MM-51 — Выбор целевого сервиса (to_service) в боте

> Сейчас бот намертво переносит только в SoundCloud. Нужно добавить выбор куда переносим —
> SoundCloud, Яндекс Музыку или Spotify — симметрично тому как уже работает веб (дропдауны из матрицы).

**Новый флоу бота:**
```
/migrate
  → selecting_from   (YM | Spotify)
  → selecting_to     (SC | YM | Spotify — динамически из матрицы)
  → waiting_*_token  (сбор токенов для FROM + TO)
  → confirming
```

- [x] `bot/states.py` — добавлен `selecting_to = State()`
- [x] `bot/handlers/auth.py`:
  - `on_select_from_ym` / `on_select_from_spotify` — теперь вызывают `_show_to_selection` вместо прямого перехода к токенам
  - `_show_to_selection` — динамически строит клавиатуру из `ServiceRegistry.get_matrix()` для выбранного FROM
  - `on_select_to` — единый обработчик; маршрутизирует к нужным шагам авторизации по FROM+TO
  - `_route_to_sc` — валидация/запрос SC-токена
  - `_route_to_spotify` — проверка наличия spotify_token, ссылка на веб если нет
  - `_continue_after_ym_token` — после получения YM-токена роутит к SC или Spotify или сразу к подтверждению
  - `_show_confirmation` — универсальный, использует `_SERVICE_LABEL` для любого FROM
  - `_show_confirmation_spotify` — делегирует в `_show_confirmation` (обратная совместимость)
  - SC как FROM — `bot_sc_coming_soon`, state.clear()
- [x] `core/i18n.py` — ключи `bot_service_soundcloud`, `bot_select_to`, `bot_sc_coming_soon`
- [x] `bot/handlers/migration.py` — `to_service` читается из state, передаётся в `api_client.start_migration`
- [x] `api/routes/web.py` — ETA использует реальный `to_service` из migration record (сделано в MM-55)

---

### ✅ MM-52 — SoundCloud официальный OAuth (замена cookie-авторизации)

> Текущий метод (cookie `oauth_token` из DevTools) использует внутренний браузерный токен.
> SC API блокирует write-операции (like_track → 404, create_playlist → 403 Datadome) для таких токенов с server IP.
> Решение: официальный OAuth Authorization Code Flow — как уже сделано для Spotify (MM-22/39).
> Приложение зарегистрировано на soundcloud.com/you/apps, ожидается одобрение write scope.

**Что решает:**
- ✅ `PUT /me/track_likes/{id}` — нормальный лайк трека
- ✅ `POST /playlists` — создание плейлиста без Datadome
- ✅ Авторизация без DevTools (мобилка, любой браузер)
- ✅ refresh_token — токен не протухает

**Env vars (добавить в `.env` и `config.py`):**
```
SC_CLIENT_ID=
SC_CLIENT_SECRET=
SC_REDIRECT_URI=https://yourdomain.com/auth/soundcloud/callback
```

**Реализация (аналогично Spotify):**
- [x] `core/soundcloud/oauth.py` — `get_auth_url()`, `exchange_code()`, `refresh_access_token()`
- [x] `api/routes/web.py` — `GET /auth/soundcloud` (редирект на SC), `GET /auth/soundcloud/callback` (обмен кода, сохранение токена)
- [x] `api/templates/auth.html` — кнопка "Подключить SoundCloud" вместо поля ввода cookie
- [x] `core/db/models.py` — `UserSession.soundcloud_refresh_token` (новое поле)
- [x] `core/db/crud.py` — `save_soundcloud_token()`, `load_user_session()` обновлён
- [x] `alembic/versions/f6a7b8c9d0e1_add_soundcloud_refresh_token.py` — новая миграция
- [x] `worker/tasks.py` — `_refresh_sc_token_if_needed()` + auto-refresh в 3 джобах
- [x] Бот — `_ask_soundcloud_token()` → ссылка на веб если `sc_client_id` задан
- [x] `core/i18n.py` — `auth_sc_oauth_hint`, `auth_sc_oauth_btn`, `bot_sc_no_token`

**Порядок:**
1. Дождаться одобрения SC приложения (или протестировать с текущими credentials)
2. Проверить что `GET /me` работает с OAuth token
3. Проверить что `PUT /me/track_likes/{id}` работает
4. Реализовать полный flow

---

### ✅ MM-53 — Улучшение логирования (единый стандарт для всех клиентов)

> Сейчас логи при ошибках нечитаемы: видно только query-строку, но не URL, не params, не migration_id.
> Нужен единый формат логов поиска/записи для YM, SC и Spotify.

**Проблема (пример сейчас):**
```
WARNING | SC search_tracks('Дора Loverboy'): HTTP 403: {}
```
Не видно: какой URL, какие params (client_id?), в рамках какой миграции.

**Целевой формат (одинаковый для всех трёх клиентов):**
```
DEBUG | [sc] search query='Дора Loverboy' → GET /search/tracks?q=Дора+Loverboy&limit=10&client_id=xxx
DEBUG | [sc] search query='Дора Loverboy' → 200, 8 results
WARNING | [sc] search query='Дора Loverboy' → 403 {} (url=https://api-v2.soundcloud.com/search/tracks?...)

DEBUG | [ym] search query='Дора Loverboy' → 5 results
DEBUG | [spotify] search query='Дора Loverboy' → GET /search?q=...&type=track&limit=10 → 200, 6 results
```

**Что сделать — единый паттерн для search во всех клиентах:**

- [x] `core/soundcloud/client.py` — `search_tracks`, `search_users`:
  - `DEBUG` перед запросом: `[sc] search query={query!r} → GET {url}?{params}`
  - `DEBUG` после успеха: `[sc] search query={query!r} → {status}, {n} results`
  - `WARNING` при ошибке: `[sc] search query={query!r} → {status} {body} (url={full_url})`
  - `like_track`: `DEBUG [sc] like track_id={id}`, при ошибке `WARNING [sc] like {id} → {status}`
  - `create_playlist`: `DEBUG [sc] create_playlist title={title!r}, {n} tracks`
  - `follow_user`: `DEBUG [sc] follow user_id={id}`

- [x] `core/yandex/client.py` — `search_tracks`, `like_track`:
  - `DEBUG` перед запросом: `[ym] search query={query!r}`
  - `DEBUG` после: `[ym] search query={query!r} → {n} results`
  - `DEBUG`: `[ym] like track_id={id} → ok/fail`

- [x] `core/spotify/client.py` — `search_tracks`, `search_artists`, `like_track`, `follow_artist`:
  - `DEBUG` перед: `[spotify] search query={query!r} type={type}`
  - `DEBUG` после: `[spotify] search query={query!r} → {n} results`
  - `DEBUG`: `[spotify] like track_id={id}`, `[spotify] follow artist_id={id}`
  - `WARNING` при ошибке с полным URL и статусом

- [x] `worker/tasks.py`:
  - `logger.contextualize(migration_id=..., user_id=...)` во всех 5 джобах

- [x] `migration/tracks.py` — `_process_one_track`:
  - После матчинга: `DEBUG [match] '{ym_artist} — {ym_title}' → '{sc_artist} — {sc_title}' score={score} sc_id={id}`
  - Нет матча: `DEBUG [match] '{ym_artist} — {ym_title}' → not found (best score={score})`

---

### ✅ MM-54 — SC API фиксы (официальный endpoint + правильный auth)

> Переход с неофициального `api-v2.soundcloud.com` на официальный `api.soundcloud.com` по документации SC.

**Что сделано (в main, не в отдельной ветке):**
- [x] Base URL: `api-v2.soundcloud.com` → `api.soundcloud.com`
- [x] Search: `/search/tracks` → `/tracks`, `/search/users` → `/users`
- [x] Auth header: `Bearer` → `OAuth` (по SC docs: "OAuth ACCESS_TOKEN")
- [x] Убран `client_id` из search-params (не нужен при OAuth)
- [x] Убрана `_fetch_client_id_from_web()` и кэш `_web_client_id_cache`
- [x] Response parsing: обработка и `list`, и `{"collection": [...]}` форматов
- [x] `create_playlist` tracks: `{"id": N}` → `{"urn": "soundcloud:tracks:N"}`
- [x] Лог матча поднят с DEBUG до INFO, добавлен `sc_artist` + `sc_title`

---

### ✅ MM-55 — Инкрементальная миграция (дедупликация повторных переносов)

> Если пользователь уже переносил треки в SC (или другой сервис), повторный запуск
> не должен заново искать и добавлять уже перенесённые треки.

**Проблема:** сейчас каждый запуск миграции обрабатывает все треки с нуля.
Если перенесли 50 треков, потом запустили снова (ещё 150) — первые 50 будут продублированы в новом плейлисте.

**Решение (Вариант A — по БД):**
При старте новой миграции для того же `user_id` + `to_service`:
1. Найти все `ym_id` треков со статусом `liked` из предыдущих миграций того же пользователя и того же `to_service`
2. При `bulk_insert_tracks` помечать эти треки сразу `liked` (пропускать поиск)
3. В статистике считать их как "уже перенесено" (не в `liked`, а отдельно — `skipped`)

**Что менять:**
- [x] `core/db/crud.py` — `get_previously_migrated_ym_ids(user_id, to_service) -> set[str]`; для SC включает старые миграции с `to_service IS NULL` (обратная совместимость)
- [x] `core/db/crud.py` — `bulk_insert_tracks` принимает `already_migrated: set[str]`, треки из него вставляются с `status='liked'`; возвращает `int` (кол-во пропущенных)
- [x] `migration/tracks.py` — `MigrationStats.skipped` — новое поле; `migrate_tracks` читает `to_service` из записи миграции, вызывает `get_previously_migrated_ym_ids`, передаёт в `bulk_insert_tracks`
- [x] `core/db/models.py` — добавлены `from_service`, `to_service` в `Migration`
- [x] `core/db/crud.py` — `get_migration` возвращает `from_service`, `to_service`
- [x] `alembic/versions/g7h8i9j0k1l2_add_from_to_service_to_migrations.py` — миграция БД
- [x] `api/routes/web.py` — `create_migration` передаёт `from_service`/`to_service`; маршрутизация исправлена (была захардкожена SC); ETA использует реальный `to_service`
- [x] `api/routes/migrations.py` — `create_migration` передаёт `from_service`/`to_service`

- [x] `api/routes/migrations.py` — `StartMigrationRequest.skip_already_migrated: bool = True`; передаётся в каждый enqueue_job
- [x] `api/routes/web.py` — `skip_already_migrated: bool = Form(False)` (HTML checkbox); передаётся в enqueue_job
- [x] `api/templates/index.html` — чекбокс "Пропустить уже перенесённые треки" (checked по умолчанию)
- [x] `core/i18n.py` — ключи `index_skip_migrated`, `index_skip_migrated_hint`, `bot_skip_migrated_on/off`
- [x] `worker/tasks.py` — все 4 джоба принимают `skip_already_migrated: bool = True`
- [x] `migration/spotify_tracks.py` — аналогичная дедупликация для Spotify→SC
- [x] `bot/handlers/auth.py` — тогл "♻️ Пропускать уже перенесённые" в экране подтверждения
- [x] `bot/handlers/migration.py` — передаёт `skip_already_migrated` из state в api_client
- [x] `bot/api_client.py` — поле `skip_already_migrated` в теле запроса

**Итоговая модель статусов (принято в MM-48):** `status='liked'` означает "успешно обработано" — трек либо добавлен в плейлист, либо лайкнут напрямую. Разделения статусов нет. Лайк — дополнительное действие, не меняет статус. Если `like_tracks=True` и SC вернул 404 → трек попадает в плейлист (тоже `liked`). Таким образом: `liked` = "в плейлисте" ИЛИ "напрямую лайкнуто". Лайкнутый напрямую трек в плейлист не добавляется. Модель принята как окончательная — разделять `in_playlist`/`liked` не планируется.

---

### 🔲 MM-56 — Редизайн интерфейса бота (точное воспроизведение веб-флоу MM-49)

> **Суть:** бот должен воспроизвести веб-интерфейс (MM-49) **как можно точнее** средствами Telegram UI.
> Веб — **эталон**: те же шаги в том же порядке, та же матрица сервисов, те же настройки, те же флаги.
> Отличия — только технические ограничения Telegram: inline-кнопки вместо HTMX-карточек,
> нет инлайн файлпикера (File→X/X→File доступны только через веб).
> Любое отклонение от веб-флоу требует явного обоснования.

**Флоу бота (целевой):**
```
/migrate
  → Шаг 1: Выбор FROM — кнопки сервисов (YM 🎵 | Spotify 🟢 | SC*)
  → Шаг 2: Выбор TO  — кнопки из матрицы для выбранного FROM
  → Шаг 3: Выбор типа контента — кнопки-тогглы: 🎵 Треки | 📋 Плейлисты | 👤 Артисты
            → показываются только те, где есть пересечение READ у FROM и WRITE у TO
            → если доступен только один тип — шаг пропускается, передаётся автоматически
  → Шаг 4: Авторизация — только нужные шаги (FROM + TO); если токен валиден — пропускается
  → Шаг 5: Настройки — лимит треков, пропуск перенесённых (тогли на одном экране)
  → Старт → прогресс-бар → итог
```

**Матрица доступности (та же, что в MM-49):**
- YM→SC: Треки ✓, Плейлисты ✓, Артисты ✓
- YM→Spotify: Треки ✓, Артисты ✓
- YM→File: только Треки
- Spotify→SC: Треки ✓, Плейлисты ✓, Артисты ✓
- Spotify→YM: только Треки
- SC→any: только Треки
- File→any: только Треки
Логика: `FROM.can(READ_X) and TO.can(WRITE_X)` через ServiceRegistry/адаптеры.

**Изменения:**
- [ ] Единый экран настроек перед стартом (сейчас лимит выбирается отдельным шагом, остальные — тоглы на confirmation)
- [ ] Убрать разделение "tracks" / "full" как отдельных кнопок → заменить на шаг выбора типа контента (Треки/Плейлисты/Артисты)
- [ ] Добавить FSM-состояние `selecting_content_type` между шагом выбора TO и авторизацией
- [ ] Инлайн-кнопки с тогглом (✅/☐) — пользователь жмёт чтобы выбрать/снять, затем "Далее →"
- [ ] Если для пары FROM→TO доступен только один тип контента — шаг пропускается автоматически
- [ ] Экран подтверждения с краткой сводкой: FROM → TO, выбранные типы, кол-во треков (ETA), все тогли на одном экране
- [ ] SC как FROM (пока недоступен) — заглушка, не падение
- [ ] `bot/states.py` — добавить `AuthFlow.selecting_content_type`
- [ ] `bot/handlers/auth.py` — добавить хендлер шага выбора типа контента; передавать `content_types` в API
- [ ] `core/i18n.py` — новые ключи: `bot_select_content_type`, `bot_content_tracks`, `bot_content_playlists`, `bot_content_artists`, `bot_content_next`

**Принципы синхронизации с MM-49:**
- Та же матрица сервисов (из `ServiceRegistry`)
- Те же флаги: `skip_already_migrated`, `like_tracks`, `track_limit`
- SC как FROM — кнопка присутствует, но показывает "скоро" или ведёт на веб

---

### 🔲 MM-57 — Тесты для каждой задачи (правило + покрытие)

> Правило: после реализации каждой MM-задачи обязательно писать/запускать тесты.
> Текущее покрытие: 133 теста (в основном API + matcher). Нужно покрыть воркер, пайплайн миграции, bot handlers.

**Правило (действует с MM-57):**
- После каждой задачи: написать тесты на новую функциональность → убедиться что `pytest tests/` проходит
- Тесты размещать в `tests/` рядом с остальными
- Если задача не добавляет новую бизнес-логику — минимум: smoke-тест что новый параметр передаётся

**Что покрыть (ретроактивно):**
- [ ] `migration/tracks.py` — `_process_one_track` с `like_tracks=True` (success + LikeNotSupportedError fallback)
- [ ] `migration/tracks.py` — `_process_one_track` с `playlist_mode=True`
- [ ] `core/soundcloud/client.py` — `like_track` поднимает `LikeNotSupportedError` при 404
- [ ] `core/db/crud.py` — `get_previously_migrated_ym_ids`, `bulk_insert_tracks` с `already_migrated`
- [ ] `api/routes/migrations.py` — `StartMigrationRequest` принимает `like_tracks`, `skip_already_migrated`
- [ ] `worker/tasks.py` — `run_migration_job` вычисляет `playlist_mode = not like_tracks`
- [ ] `bot/handlers/auth.py` — `_confirmation_kb` строит клавиатуру с тоглом лайков для SC destination

---

### 🔲 MM-58 — Ревью архитектуры

> Проверка текущей архитектуры на масштабируемость, устранение технического долга,
> выработка рекомендаций перед переходом на Go (MM-59).

**Что ревьюить:**
- [ ] **Модели данных** — `Migration`, `Track`: достаточно ли полей? нужен ли `liked_flag` как отдельное поле?
- [ ] **Worker** — ARQ vs Celery vs собственный планировщик; масштабирование воркеров
- [ ] **API vs Bot** — дублирование логики; стоит ли Bot общаться напрямую с DB минуя API?
- [ ] **ServiceRegistry** — текущий паттерн адаптеров; что изменить при переходе на gRPC/REST-сервисы?
- [ ] **Миграции БД** — alembic-версии без коллизий; стратегия для production downtime-free
- [ ] **Мониторинг** — Loki/Promtail/Grafana; что добавить для алертинга?
- [ ] **Rate limiting** — per-user в Redis; достаточно ли для 20-30 пользователей?
- [ ] **Безопасность** — зашифрованные токены в БД; rotation strategy; SSRF-риски в SC/YM клиентах
- [ ] **Тесты** — 133 теста, но нет интеграционных; стоит ли добавить docker-based integration tests?

**Выход:** документ `docs/architecture-review.md` с рекомендациями и приоритизированным backlog'ом.

---

### 🔲 MM-59 — Перенос сервиса на Go

> Стратегический: реализация ядра (миграционный пайплайн + API) на Go для
> повышения производительности, типобезопасности и упрощения деплоя.

**Обоснование:**
- Python async работает, но GIL ограничивает CPU-bound matching при больших библиотеках
- Go: статическая линковка → один бинарник без зависимостей; goroutines → дешёвый параллелизм
- Telegram bot на Go: telebot/telego — зрелые библиотеки

**Стратегия (поэтапная, не big-bang rewrite):**
```
Этап 1: Go-воркер параллельно с Python
  - Новый go-worker читает те же ARQ jobs из Redis (JSON-сериализация совместима)
  - Пишет в ту же PostgreSQL через pgx/sqlc
  - Python API остаётся, Python bot остаётся
  - A/B: часть джобов → Go, часть → Python

Этап 2: Go API (FastAPI → Gin/Chi/Fiber)
  - Перенос /api/migrations, /api/sessions на Go
  - Python остаётся только для веб-UI (Jinja2) пока нет Go-шаблонизатора

Этап 3: Go Bot (aiogram → telego)
  - Перенос FSM-логики бота на Go
  - Удаление Python полностью

Этап 4: Веб-UI
  - Возможна замена Jinja2+HTMX на Go html/template + htmx (тот же HTMX)
  - Или: React SPA + Go REST API
```

**Что делать в первую очередь:**
- [ ] Изучить: `pgx` (PostgreSQL), `asynq` (очередь, совместима с Redis), `go-redis`, `rapidfuzz-go`
- [ ] Прото-воркер: `run_migration_job` на Go — поиск SC треков + создание плейлиста
- [ ] Benchmark: Python vs Go на 1000 треков (throughput, memory)
- [ ] Решить: `sqlc` vs `gorm` vs `ent` для работы с БД
- [ ] Структура репозитория: monorepo (Python + Go в одном repo) или split

**Риски:**
- Fuzzy matching: `rapidfuzz` на Python → нужен аналог на Go (нет прямого порта; можно через CGO или переписать алгоритм)
- iuliia транслитерация: Python-библиотека → нужен Go-порт
- SC/YM клиенты: переписать HTTP-клиенты (несложно, Go net/http)

---

### ✅ MM-60 — Упрощение навигации веб-UI

> Убрать лишние пункты из навигационной панели до редизайна MM-49.

**Что сделано:**
- [x] Убраны из nav (десктоп + мобайл): **Импорт**, **Экспорт**, **Выйти**
- [x] Оставлены: **Главная**, **История**, **Аккаунт**, **переключатель языка**
- [x] Страницы `/import`, `/export` по-прежнему работают (просто без ссылок в меню)

**Файлы:** `api/templates/base.html`

---

### ✅ MM-61 — Фикс ложных матчей в fuzzy-поиске (token_set_ratio)

> `token_set_ratio` давал score=100 когда название трека является подстрокой кандидата
> (например "заря" vs "Алая Заря"), что приводило к ложным матчам с неправильным артистом.

**Проблема:**
- `token_set_ratio("заря", "алая заря")` = 100 — subset-матч
- `WRatio("lizer", "liderzhnec")` ≈ 80 — partial matching
- Итог: `0.4*80 + 0.6*100 = 92` → "Lizer — Заря" матчился с "LiderZHNEC — Алая Заря"

**Что сделано:**
- [x] Убран `fuzz.token_set_ratio` из `_score_pair` в `core/matcher.py`
- [x] Оставлены: `fuzz.WRatio` + `fuzz.token_sort_ratio`
- [x] `MATCH_UNCERTAIN_FLOOR` добавлен в `.env.example`
- [x] Исправлен дефолт `match_threshold`: 95.0 → 75.0 в `config.py`

**Файлы:** `core/matcher.py`, `config.py`, `.env.example`

---

### ✅ MM-62 — Web UI bug fixes (Query alias + lang switcher)

> Два критических бага в веб-UI: FROM-сервис не реагировал на выбор; языковой переключатель показывал флаг другого языка.

**Проблемы:**
- `GET /api/flow/to-step?from=X` → FastAPI ожидал `?from_service=X` → 422 → HTMX ничего не показывал
- `GET /api/flow/rest?from=X&to=Y` → та же проблема с именами параметров
- `base.html` при `lang='en'` показывал 🇷🇺 (а не 🇬🇧) — отображался флаг ДРУГОГО языка

**Что сделано:**
- [x] `api/routes/web.py` — добавлен `Query(..., alias="from")` / `Query(..., alias="to")` для `flow_to_step` и `flow_rest`
- [x] `api/templates/base.html` — языковой переключатель теперь показывает текущий язык (🇬🇧 EN / 🇷🇺 RU)
- [x] `tests/test_web_flow.py` — 4 новых теста (145 total, все проходят)

**Файлы:** `api/routes/web.py`, `api/templates/base.html`, `tests/test_web_flow.py`

---

### ✅ MM-63 — Web UI redesign (icons + visual polish)

> Замена emoji-иконок на SVG brand icons для каждого сервиса.

**Задачи:**
- [x] Добавить SVG-иконки для Spotify (#1ED760, simpleicons), SoundCloud (#FF3300, simpleicons)
- [x] Yandex Music — кастомный SVG: красный прямоугольник rx=6 + буква «Я» (simpleicons не имеет yandexmusic)
- [x] File — SVG документ-иконка (Feather/Heroicons стиль, серый)
- [x] `_SERVICE_ICONS` в `api/routes/web.py` — строки SVG вместо emoji; `width="1em" height="1em"` → масштабируется через `text-2xl`/`text-lg` родителя
- [x] Шаблоны: добавлен `| safe` фильтр + `leading-none` в 5 местах (`index.html`, `flow_to.html` ×2, `flow_rest.html` ×2)
- [x] Жёстко закодированный `📁` в `flow_to.html` заменён на `service_icons.get('file')`

**Файлы:** `api/routes/web.py`, `api/templates/index.html`, `api/templates/fragments/flow_to.html`, `api/templates/fragments/flow_rest.html`

---

### ✅ MM-64 — Live progress UX (per-user numbering + faster updates)

> Улучшение UX прогресса миграции: понятная нумерация, более частые обновления, позиция трека в очереди.

- [x] DB: `user_migration_number` поле в `Migration` + alembic миграция `h8i9j0k1l2m3`
- [x] `core/db/crud.py` — `create_migration()` считает предыдущие миграции пользователя и сохраняет порядковый номер
- [x] `core/db/crud.py` — `get_migration()` возвращает `user_migration_number`
- [x] `api/routes/web.py` — history route передаёт `user_migration_number` в шаблон
- [x] Шаблоны: `user_migration_number or id` вместо глобального `id`:
  - `api/templates/history.html`
  - `api/templates/progress.html`
  - `api/templates/fragments/status.html`
- [x] Веб: HTMX polling 3s → 1s (`progress.html` + `fragments/status.html`)
- [x] Worker: `[i/total]` prefix в `migration_current_track` Redis key (`worker/tasks.py`)
- [x] Бот: `_POLL_INTERVAL` 15s → 5s (`bot/handlers/migration.py`)

---

### 🔲 MM-65 — Вынос настроек в БД + Admin UI

> Настройки сейчас разбросаны по `.env` и требуют рестарта при изменении. Задача: вынести
> операционные и OAuth-настройки в БД с редактированием через Admin UI, оставив в `.env`
> только bootstrap/security параметры.

**Принцип разделения:**

*Остаётся в `.env` (нельзя в БД):*
- `DATABASE_URL`, `REDIS_URL` — нужны до подключения к БД
- `DB_ENCRYPTION_KEY` — ключ шифрования самой БД, хранить в БД бессмысленно
- `SECRET_KEY` — SessionMiddleware, нужен при старте до загрузки чего-либо
- `API_INTERNAL_TOKEN` — shared secret bot↔API
- `TELEGRAM_BOT_TOKEN` — нужен до старта бота
- `WEB_ENABLED`, `WEB_ALLOWED_IPS` — инфраструктурные (контролируют доступ к самому UI)
- `LOG_LEVEL`, `LOG_FORMAT` — нужны при инициализации логгера

*`ADMIN_PASSWORD` — гибридный:*
- Если задан в `.env` → override (bootstrap и аварийный сброс)
- Если не задан в `.env` → берётся из БД (хранится как bcrypt-хеш)
- Смена через Admin UI → пишет в БД
- Сброс: задать `ADMIN_PASSWORD` в `.env` + рестарт → перезапишет значение в БД → убрать из `.env`

*Переходит в БД (редактируется через Admin UI):*

| Настройка | Зачем в БД |
|-----------|-----------|
| `MATCH_THRESHOLD` | Тюнинг матчинга без рестарта |
| `MATCH_UNCERTAIN_FLOOR` | То же |
| `SC_RATE_LIMIT_SLEEP` | Оперативная реакция на rate limit SC |
| `SC_PLAYLIST_BATCH_SIZE` | Эксперименты с батчингом |
| `YM_PROXY_URL` | Смена прокси без рестарта |
| `YANDEX_CLIENT_ID/SECRET/REDIRECT_URI` | Смена OAuth app без рестарта |
| `SPOTIFY_CLIENT_ID/SECRET/REDIRECT_URI` | То же |
| `SC_CLIENT_ID/SECRET/REDIRECT_URI` | То же |
| `ALLOWED_USERS` | Управление через UI (сейчас строка в .env) |

**Архитектура:**

```
core/db/models.py     — новая таблица AppSettings (key, value, updated_at)
core/db/crud.py       — get_setting(key, default), set_setting(key, value), get_all_settings()
config.py             — Settings.get_effective(key): .env → DB → default (priority)
                        При старте: если ADMIN_PASSWORD в .env → сохранить в DB → убрать из памяти
api/routes/admin.py   — новая вкладка /admin/settings: GET (форма), POST (сохранить)
api/templates/admin/settings.html — форма редактирования настроек с группами
alembic/              — новая миграция для таблицы AppSettings
```

**Загрузка настроек в runtime:**
- Настройки из БД кешируются в памяти (TTL 60с или при изменении через UI)
- `config.settings` остаётся точкой входа; для DB-настроек добавить `settings.get_db("key")`
- При изменении через UI → инвалидировать кеш → следующее обращение перечитает из БД

**Admin UI — вкладка "Настройки":**
```
[Матчинг]
  Порог совпадения:          [75.0]
  Нижняя граница неточных:  [60.0]

[SoundCloud]
  Задержка записи (сек):    [2.0]
  Размер батча плейлистов:  [500]

[Яндекс Музыка]
  Proxy URL:                [socks5://...]

[OAuth — Яндекс]
  Client ID / Secret / Redirect URI

[OAuth — Spotify]
  Client ID / Secret / Redirect URI

[OAuth — SoundCloud]
  Client ID / Secret / Redirect URI

[Доступ]
  Allowed Users (через запятую): [123456, 789012]
  Сменить пароль администратора: [новый пароль]
```

**Задачи:**
- [ ] `alembic` — миграция: таблица `app_settings (key VARCHAR PK, value TEXT, updated_at)`
- [ ] `core/db/models.py` — модель `AppSetting`
- [ ] `core/db/crud.py` — `get_setting()`, `set_setting()`, `get_all_settings()`, кеш с TTL
- [ ] `config.py` — при старте: если `ADMIN_PASSWORD` задан в env → bcrypt → сохранить в БД → обнулить в памяти
- [ ] `api/routes/admin.py` — маршруты `/admin/settings` GET/POST; смена пароля через отдельный POST
- [ ] `api/templates/admin/settings.html` — форма с группами настроек
- [ ] Обновить потребителей настроек: `matcher.py`, `worker/tasks.py`, `core/soundcloud/client.py` — читать из кеша БД вместо `settings.*`
- [ ] `.env.example` — пометить перенесённые параметры как `# опционально — теперь в Admin UI`
- [ ] Тесты: юнит-тесты для `get_setting/set_setting`, интеграционный для admin settings endpoint

**Ограничения:**
- OAuth-секреты хранить зашифровано через `crypto.py` (тот же Fernet что для токенов)
- `YM_PROXY_URL` — если задан в `.env`, он берётся первым (override для отладки)
- При деплое с нуля: настройки инициализируются из `.env` в БД при первом старте (если в БД нет)

---

### 🔲 MM-66 — Media Catalog (кэш поиска + cross-platform resolver)

> Сохранять поисковые запросы треков и найденные платформенные ссылки в общую медиа-базу.
> Повторные миграции тех же треков используют кэш вместо API-поиска.

**Идея:** при поиске трека (например "Lizer Заря") сохранять нормализованный запрос в `media_tracks`,
а при нахождении на платформе — ссылку/id в `media_track_links`. Каталог обезличен (без user_id),
обогащается со временем всеми миграциями.

**Схема БД:**

```sql
media_tracks
  id SERIAL PK
  search_query VARCHAR  -- нормализованный (через matcher.py)
  title VARCHAR
  artist VARCHAR
  created_at TIMESTAMP

media_track_links
  id SERIAL PK
  track_id FK → media_tracks
  platform VARCHAR  -- 'ym' | 'sc' | 'spotify'
  platform_id VARCHAR
  url VARCHAR
  match_score FLOAT
  found_at TIMESTAMP
```

**Логика поиска с кэшем:**
1. Нормализовать запрос → проверить `media_track_links` для нужной платформы
2. HIT (и `found_at` < 30 дней) → использовать `platform_id` напрямую, пропустить API-поиск
3. MISS → обычный API-поиск → сохранить результат в каталог

**Затронутые файлы:**
- [ ] `alembic/` — миграция: таблицы `media_tracks`, `media_track_links`
- [ ] `core/db/models.py` — модели `MediaTrack`, `MediaTrackLink`
- [ ] `core/db/crud.py` — `get_cached_track()`, `save_track_to_catalog()`
- [ ] `migration/tracks.py` — интеграция кэша в `_process_one_track`
- [ ] `migration/yandex_tracks.py` — аналогично
- [ ] `migration/spotify_write.py` — аналогично
- [ ] Тесты: cache hit/miss, TTL-инвалидация, нормализация запроса

**Нюансы:**
- TTL 30 дней на `found_at` — треки могут удаляться с платформ; при 404 — удалять ссылку
- Не кэшировать результаты с `match_score < 90` во избежание ложных хитов
- Нормализация через существующий `matcher.py`
- Приватность: каталог общий, user_id не хранится

---

### ✅ MM-67 — Unified file import/export in main flow

**Задача:** интегрировать "Из файла" и "В файл" в стандартный HTMX-флоу на главной странице.

**Что сделано:**
- `core/i18n.py` — добавлены ключи `from_file_label`, `export_fmt_label`
- `worker/tasks.py` — `run_yandex_migration_job` + `run_spotify_write_job` получили `tracks_override: list[dict] | None` — пропускает `fetch_liked_tracks` если передан
- `api/routes/web.py`:
  - `index` — `file_csv` добавлен в `from_services` вручную
  - `flow_to_step` — для `from_service=="file_csv"` возвращает все сервисы с `WRITE_LIKED_TRACKS`
  - `flow_rest` — передаёт `is_from_file`/`is_to_file`; для file_csv пропускает adapter lookup
  - `GET /import`, `GET /export` → редиректы на `/`
  - `POST /migrate` — новые параметры `export_fmt`, `file`; три case: export→файл (без job), import←файл (с tracks_override), обычный
- `api/templates/index.html` — `enctype="multipart/form-data"`, убрана отдельная карточка file (теперь в from_services loop)
- `api/templates/fragments/flow_to.html` — export-карточка стала HTMX-кнопкой
- `api/templates/fragments/flow_rest.html` — условный рендеринг: file picker, format select, disabled checkboxes, кнопка "Скачать файл" для export

**Тесты:** +7 в `test_web_flow.py` (flow_to file_csv, flow_rest from/to file, redirects, index содержит file_csv)

---

### ✅ MM-68 — matcher.py адаптация для всех сервисов

**Задача:** убедиться что fuzzy-матчинг работает одинаково для YM, Spotify, SC, File как источников.

**Анализ (проведён):**
- Логика `score_track_match` и `find_best_match` универсальна — не привязана к конкретным платформам
- `transliterate_variants` — только для кириллицы, для EN просто `[text]` — корректно
- `normalize` — убирает feat./remaster, пунктуацию — работает для всех сервисов
- Все миграции (→SC, →YM, →Spotify) используют один и тот же `find_best_match`

**Что сделано:**
- [x] Добавлены тесты в `test_matcher.py` (класс `TestCrossServiceMatching`) — Spotify→SC, SC→YM, File→any, проверка transliteration skip для EN
- [x] Переименованы параметры `score_track_match`: `ym_artist/ym_title/sc_artist/sc_title` → `source_artist/source_title/cand_artist/cand_title`
- [x] Переименованы параметры `find_best_match`: `ym_artist/ym_title` → `source_artist/source_title`
- [x] Обновлён docstring `SCCandidate`: явно указано что это generic кандидат для любой целевой платформы
- [x] Обновлён docstring модуля `core/matcher.py`: "между стриминговыми платформами" вместо "между Яндекс Музыкой и SoundCloud"

---

### ✅ MM-69 — Rename file_csv → file

**Задача:** `FileAdapter.id = "file_csv"` — имя отражает только CSV, хотя поддерживается и JSON. Переименовать в `"file"`.

**Что сделано:**
- [x] `core/services/file/adapter.py` — `id = "file"`, `name = "Файл (CSV/JSON)"`
- [x] `core/i18n.py` — ключ `svc_file_csv` → `svc_file`
- [x] `api/routes/web.py` — все `"file_csv"` → `"file"` (11 мест); `_SERVICE_ICONS`: `"file"` вместо `"file_csv"`
- [x] `api/templates/fragments/flow_to.html` — `data-to="file"`, `hx-get="...&to=file"`, `onclick="selectTo('file')"`; проверка `!= 'file'`
- [x] `api/templates/fragments/flow_rest.html` — все `'file_csv'` → `'file'`
- [x] `tests/test_web_flow.py` — обновлены все `file_csv` → `file`, функции и docstring'и
- [x] `alembic/versions/i9j0k1l2m3n4_rename_file_csv_to_file.py` — `UPDATE migrations SET from_service/to_service = 'file' WHERE = 'file_csv'`

**Тесты:** 162 passed

---

### ✅ MM-70 — Main screen UX: auth-gate + content_type validation

**Задача:** кнопка "Начать перенос" теперь disabled когда нужные сервисы не авторизованы; последний чекбокс типа контента нельзя снять.

**Что сделано:**
- `api/templates/fragments/flow_rest.html` — вычисление `auth_ok` через Jinja2 (`needs_from_auth`, `needs_to_auth`); кнопка submit `disabled + opacity-50 + cursor-not-allowed` когда `not auth_ok`; подсказка под кнопкой
- `api/templates/fragments/flow_rest.html` — JS-защита: последний активный чекбокс `content_types` нельзя снять
- `core/i18n.py` — ключ `auth_required_hint` (ru/en)
- `api/routes/web.py` — в `POST /migrate` redirectы при missing token: `/auth?error=` → `/?error=` (3 места: case 1 export, case 2 import, case 3 normal)

**Файлы:** `api/templates/fragments/flow_rest.html`, `core/i18n.py`, `api/routes/web.py`

---

### ✅ MM-71 — Удаление мёртвого кода

**Задача:** после MM-67 эндпоинты `/import/preview`, `/import/start`, `/export/start` и их шаблоны недостижимы из UI — удалить.

**Что удалено:**
- `api/routes/web.py` — `POST /import/preview` (~55 строк), `POST /import/start` (~60 строк), `POST /export/start` (~45 строк)
- `api/routes/web.py` — `from core.db.crud import get_all_tracks` (не используется после удаления)
- `api/templates/import.html` — удалён
- `api/templates/export.html` — удалён
- `api/templates/fragments/import_preview.html` — удалён
- `core/i18n.py` — удалены: `nav_import`, `nav_export`; весь блок Import (`import_*`, preview `preview_*`); большинство export ключей (`export_title`, `export_subtitle`, `export_back`, `export_content`, `export_liked_tracks`, `export_playlists`, `export_note`, `export_no_ym_token`, `export_format`, `export_csv_hint`, `export_json_hint`, `export_loading`); оставлены `export_fmt_label` + `export_btn` (используются в flow_rest.html)

**Что сохранено:**
- `GET /import` и `GET /export` — остались как редиректы на `/`
- `_MAX_UPLOAD_BYTES` — используется в `POST /migrate`

**Файлы:** `api/routes/web.py`, `api/templates/import.html` (удалён), `api/templates/export.html` (удалён), `api/templates/fragments/import_preview.html` (удалён), `core/i18n.py`

---

### ✅ MM-72 — Стандартизация migration/

**Задача:** нет единой конвенции именования файлов в `migration/`.

**Было → Стало:**
| Старый файл | Новый файл | Что делает |
|---|---|---|
| `tracks.py` + `spotify_tracks.py` | `sc_tracks.py` | любой → SC (треки; merge, т.к. spotify_tracks импортировал `_run_pending_loop` из tracks) |
| `artists.py` | `sc_artists.py` | YM → SC (артисты) |
| `playlists.py` | `sc_playlists.py` | YM → SC (плейлисты) |
| `yandex_tracks.py` | `to_yandex.py` | любой → YM |
| `spotify_write.py` | `to_spotify.py` | любой → Spotify |

**Конвенция:** по destination — `sc_*` для → SC, `to_*` для → YM/Spotify.

**Изменённые файлы:**
- [x] `migration/sc_tracks.py` — создан (merge tracks.py + spotify_tracks.py); секции YM→SC, Spotify→SC, File→SC, shared pipeline internals
- [x] `migration/sc_artists.py` — создан из artists.py
- [x] `migration/sc_playlists.py` — создан из playlists.py
- [x] `migration/to_yandex.py` — создан из yandex_tracks.py
- [x] `migration/to_spotify.py` — создан из spotify_write.py
- [x] Старые файлы удалены (tracks, artists, playlists, spotify_tracks, yandex_tracks, spotify_write)
- [x] `worker/tasks.py` — обновлены все 5 импортов
- [x] `cli.py` — обновлён импорт
- [x] `tests/test_pipeline.py` — обновлены все `migration.tracks` → `migration.sc_tracks`

**Тесты:** 162 passed

---

### 🔲 MM-73 — Обновление monitoring stack

**Задача:** версии мониторингового стека устарели (2023 → 2026).

**Текущие версии vs актуальные:**
- Loki: `2.9.0` → `3.2.x` (breaking changes в конфиге возможны)
- Promtail: `2.9.0` → **deprecated** в 3.x, заменён на **Grafana Alloy**
- Grafana: `10.2.0` → `11.4.x`

**Шаги:**
- [ ] Обновить `grafana/grafana:10.2.0` → `grafana/grafana:11.4.0`
- [ ] Решить: оставить Promtail 2.9.0 (last stable) или мигрировать на Grafana Alloy
- [ ] Обновить Loki `2.9.0` → `3.2.0`, проверить совместимость `monitoring/loki/config.yml`
- [ ] Обновить `monitoring/promtail/config.yml` если нужно под новую схему

---

### 🔲 MM-74 — Улучшение алгоритма матчинга: анализ промахов + play count

**Задача:** Некоторые треки не матчатся даже когда правильный кандидат присутствует в пуле
поиска. Нужно разобраться в причинах и расширить алгоритм.

**Контекст:** Алгоритм задокументирован в `core/matcher.py` (5 шагов: нормализация →
транслитерация → попарный score → итоговый score → зоны). Переменные переименованы в
платформонезависимые (`TrackCandidate`, `track_id`, `track_url`, `cand_artist`, `cand_title`).

**Известные причины промахов (из docstring):**
1. Трека нет на целевой платформе
2. Артист известен под другим именем/псевдонимом
3. Кириллическое имя не совпало ни с одним вариантом транслитерации
4. Короткое название (1–2 слова) → score недостаточен
5. Коллаборация с разным порядком имён
6. Доступна только другая версия (Remix, Live, Cover)
7. Трек за пределами SEARCH_LIMIT первых результатов

**Что сделать:**

**Часть 1 — Диагностика промахов:**
- [ ] Добавить режим отладки: при `LOG_LEVEL=DEBUG` логировать всех кандидатов и их score
      (сейчас логируется только лучший)
- [ ] Добавить в `/migrations/{id}/not-found` поле `best_score` в UI
      (уже есть `match_score` в БД — вывести в таблице)
- [ ] Исследовать реальные промахи пользователя: передать примеры → разобрать причину →
      задокументировать

**Часть 2 — Play count как сигнал матчинга:**
- [ ] Оценить: у каких платформ есть play count в API ответах
  - SoundCloud: `playback_count` в `/tracks` — **есть**
  - Yandex Music: `plays_count` — **есть** (в некоторых ответах)
  - Spotify: `popularity` (0–100) — **есть**
- [ ] Если play count доступен: добавить нормализованный сигнал в score
  - Идея: при прочих равных предпочесть более популярный трек
  - Вес: небольшой (~10%), не перебивающий текстовый score
- [ ] Обновить `TrackCandidate`: добавить опциональное поле `play_count: int | None = None`
- [ ] Обновить `find_best_match` для учёта play count при равных score

**Часть 3 — Словарь псевдонимов:**
- [ ] Добавить статический словарь `ARTIST_ALIASES: dict[str, list[str]]` в matcher.py
      для известных случаев: `{"Земфира": ["Zemfira", "Zemphira"], ...}`
- [ ] Применять в `transliterate_variants` как дополнительный вариант

**Files:** `core/matcher.py`, `migration/tracks.py` (логирование кандидатов),
`api/routes/reports.py` (вывод score в UI)

---

### ✅ MM-75 — Ревью и очистка legacy-эндпоинтов: /auth, /import, /export

**Задача:** После перехода на единый флоу (`/`) и HTMX-фрагменты (`/api/flow/*`) часть
эндпоинтов могла стать ненужной. Проверить каждый с учётом **всех клиентов**: веб UI,
Telegram-бот, внешние ссылки.

**Эндпоинты для проверки:**

| Эндпоинт | Текущее поведение | Вопрос |
|---|---|---|
| `GET /auth` + `auth.html` | Форма ввода YM-токена (fallback когда `YANDEX_REDIRECT_URI` не настроен) | Используется ботом? Остался ли fallback актуальным? |
| `GET /import` | 303 → `/` | Можно удалить редирект? Есть ли внешние ссылки? |
| `GET /export` | 303 → `/` | Можно удалить редирект? Есть ли внешние ссылки? |

**Решения и реализация:**

| Эндпоинт | Решение | Действие |
|---|---|---|
| `GET /auth` | **KEEP + FIX** | Нужен как fallback YM-кода и для показа ошибок OAuth. Баг: игнорировал `flow_from`/`flow_to` → пользователь застревал после ввода кода |
| `POST /auth/yandex` | **FIX** | После успеха всегда шёл на `/auth`. Теперь: сохраняет токен в БД + восстанавливает флоу (`/?pf=...&pt=...`) |
| `POST /auth/soundcloud` | **DELETE** | Dead code с MM-52 — нет форм в шаблонах |
| `GET /import` | **DELETE** | Чистый `303 → /`, нет входящих ссылок |
| `GET /export` | **DELETE** | То же самое |

- [x] `GET /auth`: добавлен приём `flow_from`/`flow_to`, сохраняются в `request.session`
- [x] `POST /auth/yandex`: добавлен `save_yandex_token()` + восстановление флоу после успеха
- [x] `POST /auth/soundcloud` удалён (dead code c MM-52)
- [x] `GET /import`, `GET /export` удалены
- [x] Тесты `test_import_page_redirects_to_home`, `test_export_page_redirects_to_home` удалены
- [x] `save_yandex_token` добавлен в импорты `api/routes/web.py`

**Файлы:** `api/routes/web.py`, `tests/test_web_flow.py`

---

### ✅ MM-76 — migration/ рефакторинг: sc_* → to_soundcloud.py

> Привести конвенцию именования модулей `migration/` к единому стилю `to_*` по аналогии с `to_yandex.py` и `to_spotify.py`.

**Проблема:** После MM-72 конвенция стала смешанной:
- SC-направление: `sc_tracks.py`, `sc_playlists.py`, `sc_artists.py` (по типу контента)
- YM-направление: `to_yandex.py` (единый файл)
- Spotify-направление: `to_spotify.py` (единый файл)

**Решение:** Слить `sc_tracks.py` + `sc_playlists.py` + `sc_artists.py` → `to_soundcloud.py`.

**Задачи:**
- [x] Создать `migration/to_soundcloud.py` — объединить все три файла
  - Секции: `# ── Tracks ──`, `# ── Playlists ──`, `# ── Artists ──`, `# ── Entry points ──`
  - Публичный API: `migrate_tracks()`, `migrate_playlists()`, `migrate_artists()`, `run_migration()`, `run_spotify_migration()`, `migrate_from_file_tracks()`
- [x] Обновить импорты в `worker/tasks.py` (все `from migration.sc_*`)
- [x] Обновить импорт в `cli.py`
- [x] Удалить `sc_tracks.py`, `sc_playlists.py`, `sc_artists.py`
- [x] Обновить тесты (`migration.sc_tracks` → `migration.to_soundcloud`)
- [x] Обновить CLAUDE.md (architecture diagram)

**Итоговая структура `migration/`:**
```
migration/
    ├── to_soundcloud.py   — any → SC (треки, плейлисты, артисты)
    ├── to_yandex.py       — any → YM лайки
    └── to_spotify.py      — any → Spotify (лайки + подписки)
```

**Файлы:** `migration/sc_tracks.py`, `migration/sc_playlists.py`, `migration/sc_artists.py` → `migration/to_soundcloud.py`, `worker/tasks.py`, `cli.py`, `tests/test_pipeline.py`

---

### ✅ MM-77 — SoundCloud как источник (чтение библиотеки)

> Полноценная поддержка SoundCloud как FROM-сервиса: чтение лайкнутых треков и подписок на артистов.

**Что сделано:**
- [x] `SoundCloudClient.get_liked_tracks(limit=None)` — добавлен `limit` param, ранняя остановка пагинации
- [x] `SoundCloudClient.get_followings(limit=None)` — новый метод: `GET /me/followings` с пагинацией через `next_href`
- [x] `SoundCloudAdapter.capabilities` — добавлен `READ_LIKED_ARTISTS`
- [x] `SoundCloudAdapter.fetch_liked_tracks(token, limit)` — передаёт `limit` в клиент
- [x] `SoundCloudAdapter.fetch_liked_artists(token)` — новый метод, возвращает `[{"name": username}]`
- [x] `web.py` — SC как FROM уже маршрутизируется корректно (SC→YM, SC→Spotify, SC→File)
- [x] `tests/test_sc_source.py` — 14 тестов: клиент (pagination, limit), адаптер (capabilities, fetch), матрица
- Пагинация `get_liked_tracks`: уже была реализована через `next_href`; добавлена только ранняя остановка по `limit`

**Матрица после MM-77:**
- SC→YM: треки ✓
- SC→Spotify: треки + артисты ✓ (READ_LIKED_ARTISTS добавлен)
- SC→File: треки через экспорт ✓

**Файлы:** `core/soundcloud/client.py`, `core/services/soundcloud/adapter.py`, `tests/test_sc_source.py`

---

### ✅ MM-78 — Асинхронный экспорт в файл (через ARQ worker)

> Экспорт в CSV/JSON идёт через ARQ worker, результат хранится в Redis (TTL 24h).

**Что сделано:**
- [x] `worker/tasks.py` — `run_export_job(ctx, migration_id, service_id, token, fmt, user_id)`: вызывает `export_library()`, сохраняет bytes в Redis `export_data:{id}` (TTL 86400s), обновляет `status=done + result_path=fmt`, уведомляет Telegram со ссылкой
- [x] `worker/main.py` — `run_export_job` добавлен в `functions`
- [x] `core/db/models.py` — поле `result_path: Mapped[str | None]` в `Migration`
- [x] `core/db/crud.py` — `get_migration()` возвращает `result_path`
- [x] `alembic/versions/k1l2m3n4o5p6_add_result_path_to_migrations.py` — новая миграция
- [x] `api/routes/web.py` — `POST /migrate` с `to_service=file`: вместо sync → `create_migration` + `enqueue run_export_job` + redirect на `/migrate/{id}`
- [x] `api/routes/web.py` — `GET /migrate/{id}/export-file`: читает из Redis, отдаёт файл (410 если TTL истёк, 404 если не готово)
- [x] `fragments/status.html` — кнопка Download для экспортных миграций (`to_service=file` + `result_path` заполнен)
- [x] `tests/test_export_job.py` — 7 тестов: job success/failure/status-sequence, endpoint 200/404/410/missing

**Ключевые решения:**
- Redis вместо shared filesystem (worker и api — разные Docker-контейнеры)
- `result_path` хранит формат (`"csv"`/`"json"`) — и флаг готовности, и content-type для download
- `progress_callback` в `export_library` — не реализован (export атомарен, прогресс не нужен)

**Файлы:** `worker/tasks.py`, `worker/main.py`, `core/db/models.py`, `core/db/crud.py`, `alembic/versions/k1l2m3n4o5p6_*`, `api/routes/web.py`, `api/templates/fragments/status.html`, `tests/test_export_job.py`

---

### ✅ MM-79 — Auth refactor: вынос в api/routes/oauth.py + унификация под SPA

> Подготовка auth-слоя к JWT (MM-81). Все OAuth-роуты выносятся из перегруженного `web.py` в `oauth.py` и унифицируются. OAuth это только redirect-машина, UI авторизации — в SPA.
>
> **Именование:** `api/routes/auth.py` → `api/routes/bot_auth.py` (internal bot auth). Новый `api/routes/oauth.py` — все OAuth redirect/callback роуты.

**Что исправлено:**

До MM-79 state и session хранились несогласованно:

| Аспект | Было (несогласованно) | Стало |
|---|---|---|
| State storage | cookie `_ym_state` / session `spotify_oauth_state` / cookie `_sc_state` | Redis `oauth_state:{provider}:{state}` TTL 600s |
| После успеха | `session["ym_token"]` = raw token | `session["ym_connected"] = True` (токен только в БД) |
| Куда идут ошибки | `/auth?error=` | `/?error=...` |

**Что сделано:**
- [x] `api/routes/oauth.py` создан — все OAuth роуты из `web.py` вынесены
- [x] `api/routes/auth.py` → `api/routes/bot_auth.py`; зарегистрирован в `api/main.py`
- [x] State storage унифицирован: Redis TTL 600s для всех трёх провайдеров
- [x] `session["ym_token"]` удалён → `session["ym_connected"] = True`
- [x] `POST /auth/yandex` (форма ручного ввода кода) удалён
- [x] Short-lived `oauth_code:{code}` (Redis TTL 30s) после успешного OAuth для MM-81
- [x] `_ensure_user_id` / `_session_user_id` перенесены в `oauth.py`, `web.py` импортирует оттуда
- [x] Тесты: 16 новых тестов `tests/test_oauth.py`, 182 passed

**Файлы:** `api/routes/oauth.py` (создан), `api/routes/bot_auth.py` (из auth.py), `api/routes/web.py`, `api/main.py`, `api/templates/auth.html`, `tests/test_oauth.py`

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
| Истёкший токен во время миграции | auto-refresh в воркере (MM-52 SC + MM-39 Spotify) ✅ |
| ~~SC токен (cookie) — короткий срок~~ | ~~Уведомление + инструкция по обновлению~~ — **неактуально**: заменён официальным OAuth (MM-52) |
| JWT refresh token утечка | Fernet-шифрование в БД; отзыв через `revoke_spa_refresh_token`; TTL 30 дней |
| DEV_MODE случайно включён на проде | `guard_dev_mode` validator в config.py — автосброс если URL не localhost ✅ |

---

### ✅ MM-80 — Local dev mode (локальный запуск для фронтендеров)

> Локальная среда для разработки UI без реальных OAuth credentials и без конфликта с продакшном.

**Проблема:** OAuth callbacks ведут на реальный домен → нельзя авторизоваться локально.
Nginx требует SSL-сертификаты → сложно поднять локально. Нужен способ обойти auth gate для UI-разработки.

**Решение:**
- `DEV_MODE=true` в `.env` включает маршрут `/dev/login` — устанавливает фейковую сессию
- `docker-compose.dev.yml` — standalone стек (postgres + redis + api, без nginx/bot/worker)
- `.env.dev` — готовый шаблон с фейковыми кредами, без реальных секретов
- `LOCAL_SETUP.md` — полная инструкция для нового разработчика

**Реализация (итоговая — после ревью, `/dev/login` убран):**
- [x] `config.py` — `dev_mode: bool = False`; `model_validator` форсирует `LOG_LEVEL=DEBUG` + `LOG_FORMAT=pretty` при `dev_mode=True`
- [x] `api/routes/web.py` — `_ensure_user_id()` в `DEV_MODE` всегда возвращает `"dev_user"` и прописывает в сессию
- [x] `api/main.py` — startup warning при `dev_mode=True`
- [x] `scripts/seed_dev.py` — создаёт `UserSession(user_id='dev_user')` с фейковыми токенами для YM/SC/Spotify; запускается из `entrypoint.sh` при `DEV_MODE=true`
- [x] `scripts/entrypoint.sh` — добавлен запуск `seed_dev.py` если `DEV_MODE=true`
- [x] `docker-compose.dev.yml` — postgres + redis + api (порт 8000 напрямую), без nginx/bot/worker
- [x] `.env.dev` — фейковые credentials, `DEV_MODE=true`; добавлен в `!.env.dev` исключение `.gitignore`
- [x] `.gitignore` — `!.env.dev`
- [x] `LOCAL_SETUP.md` — полная инструкция
- [x] `tests/test_dev_mode.py` — 6 тестов: default False, parse True, авто-DEBUG logging, logging не трогается при False, dev_user в URL, /dev/login → 404

**Как работает автоавторизация (без роута):**
1. Браузер открывает `/` → `_ensure_user_id()` → возвращает `"dev_user"` (фиксировано в dev mode)
2. `flow_rest` вызывает `load_user_session("dev_user")` → находит фейковые токены в БД (из seed)
3. `_connected()` видит токены → возвращает `True` для всех сервисов → auth gate открыт
4. Никаких специальных роутов — просто открыть браузер

**Безопасность:**
- Нет специального роута → нечего угадывать/эксплуатировать
- `dev_mode=False` по умолчанию; случайный `DEV_MODE=true` на проде → все пользователи делят один `user_id` (UX-баг, не уязвимость)
- `docker-compose.dev.yml` без SSL-volumes — нельзя использовать вместо прода
- Фейковые токены не проходят реальные API-вызовы — миграции падают сразу

**Дополнительная защита от прода:**
- `model_validator` в `config.py`: если `WEB_BASE_URL` или `API_BASE_URL` указывает на не-localhost домен — `dev_mode` принудительно сбрасывается в `False`, даже если в `.env` стоит `true`. Таким образом случайная копия `.env.dev` на прод не активирует dev mode.

**Файлы:** `config.py`, `api/routes/web.py`, `api/main.py`, `docker-compose.dev.yml`, `.env.dev`, `.gitignore`, `LOCAL_SETUP.md`, `tests/test_dev_mode.py`

---

### ✅ MM-81 — SPA: JWT auth + /api/v1/ layer (Фаза 1 + 2)

> Добавить JWT-аутентификацию и публичный JSON API для отдельного SPA-фронтенда. Переход **безболезненный и поэтапный**: старый веб-UI (Jinja2+HTMX) и Telegram-бот продолжают работать параллельно на всём протяжении задачи. `SessionMiddleware` убирается только в Фазе 2 — после того как SPA полностью готов.

**Требует завершения MM-79** (auth callbacks уже генерируют short-lived code).

**Принципы:**
- Никаких HTML-страниц для /auth — OAuth это redirect-машина, UI авторизации в SPA
- Старый веб-UI не ломается ни на одном шаге
- JWT в `Authorization: Bearer`, не в cookies → CORS без `allow_credentials`
- Refresh token хранится в БД (зашифрованный Fernet), access token — только в памяти SPA

**Решение по Admin panel (зафиксировано):**
- Сейчас (MM-79/81): Jinja2 `/admin/*` **не трогаем** — работает параллельно с SPA
- Переход к SPA admin делается в рамках MM-65 (настройки в БД)
- Схема: `POST /api/v1/admin/login { password }` → JWT с `role: "admin"` → SPA показывает admin-раздел (Вариант A: единый SPA, роль из JWT)
- `ADMIN_PASSWORD` из env остаётся, меняется только транспорт (form → JSON)
- После MM-65: Jinja2 admin (`api/routes/admin.py` + `api/templates/admin/`) удаляется

---

**Фаза 1 — Параллельный запуск (бэкенд)** ✅ _2026-03-13_

- [x] Добавить CORS middleware в `api/main.py` (`cors_origins`, `allow_credentials=False`)
- [x] Добавить настройки в `config.py`: `cors_origins`, `jwt_secret_key`, `jwt_access_token_ttl`, `jwt_refresh_token_ttl`
- [x] Создать `api/security.py`: `create_access_token()` (JWT HS256), `create_refresh_token()` (opaque hex), `decode_access_token()`, `get_current_user` FastAPI dep
- [x] Добавить поле `spa_refresh_token` в `UserSession` + alembic-миграция `j0k1l2m3n4o5`
- [x] `core/db/crud.py`: `save_spa_refresh_token`, `get_user_id_by_spa_refresh_token`, `revoke_spa_refresh_token`, `get_user_migrations`
- [x] Создать `api/routes/api_v1.py` с роутером `/api/v1/`:

  **Auth:**
  ```
  POST /api/v1/auth/exchange      { code } → { access_token, refresh_token, expires_in }
  POST /api/v1/auth/refresh       { refresh_token } → { access_token, expires_in }
  POST /api/v1/auth/logout        Bearer → 204 (инвалидирует refresh token в БД)
  GET  /api/v1/auth/me            Bearer → { user_id, ym_connected, sc_connected, spotify_connected, lang }
  ```

  **OAuth start (редиректы, без Bearer):**
  ```
  GET  /api/v1/auth/yandex/start?redirect_uri=...    → 302 oauth.yandex.ru
  GET  /api/v1/auth/spotify/start?redirect_uri=...   → 302 accounts.spotify.com
  GET  /api/v1/auth/soundcloud/start?redirect_uri=... → 302 api.soundcloud.com/oauth/authorize
  ```
  `redirect_uri` — куда вернуть SPA после OAuth (валидируется по whitelist из `CORS_ORIGINS`)

  **Services:**
  ```
  GET  /api/v1/services           → [{ id, name, capabilities }]
  GET  /api/v1/services/matrix    → [{ from, to }]
  ```

  **Migrations:**
  ```
  POST /api/v1/migrations              Bearer, JSON body → { migration_id }
  GET  /api/v1/migrations              Bearer → [{ id, from_service, to_service, status, created_at, stats }]
  GET  /api/v1/migrations/{id}         Bearer → { migration, stats, current_track, eta }
  GET  /api/v1/migrations/{id}/tracks  Bearer, ?status=&page= → { tracks, total, pages }
  GET  /api/v1/migrations/{id}/export  Bearer, ?fmt=csv|json → FileResponse
  ```

  **SSE прогресс (вместо polling):**
  ```
  GET  /api/v1/migrations/{id}/stream  Bearer → text/event-stream (каждые 1s: stats + current_track)
  ```

- [x] Зарегистрировать `api_v1_router` в `api/main.py` (всегда, вне `WEB_ENABLED`)
- [x] `POST /api/v1/migrations` принимает JSON body (`StartMigrationRequest`)
- [x] Обновить тесты: 23 новых теста в `tests/test_api_v1.py`, итого 205 passed

**Фаза 1 ✅** — JWT auth, `/api/v1/` роутер, `spa_refresh_token` в БД, 23 теста
**Фаза 2 ✅** — OAuth start/callback перенесены под `/api/v1/auth/*`, redirect URI обновлены у провайдеров и в `.env`, задеплоено

#### Инструкция: перенос Redirect URI под `/api/v1/` (Фаза 2)

**Что менять у провайдеров:**

**Yandex:** [oauth.yandex.ru](https://oauth.yandex.ru) → приложение → Redirect URIs
- старый: `https://musicmigration.site/auth/yandex/callback`
- новый: `https://musicmigration.site/api/v1/auth/yandex/callback`

**Spotify:** [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → Edit Settings → Redirect URIs
- старый: `https://musicmigration.site/auth/spotify/callback`
- новый: `https://musicmigration.site/api/v1/auth/spotify/callback`

**SoundCloud:** [soundcloud.com/you/apps](https://soundcloud.com/you/apps) → приложение
- старый: `https://musicmigration.site/auth/soundcloud/callback`
- новый: `https://musicmigration.site/api/v1/auth/soundcloud/callback`

**Что менять в `.env` на EU сервере:**
```env
YANDEX_REDIRECT_URI=https://musicmigration.site/api/v1/auth/yandex/callback
SPOTIFY_REDIRECT_URI=https://musicmigration.site/api/v1/auth/spotify/callback
SC_REDIRECT_URI=https://musicmigration.site/api/v1/auth/soundcloud/callback
CORS_ORIGINS=http://localhost:3000,https://musicmigration.site
JWT_SECRET_KEY=          # generate: openssl rand -hex 32 (отдельный от SECRET_KEY)
JWT_ACCESS_TOKEN_TTL=900
JWT_REFRESH_TOKEN_TTL=2592000
```

**Порядок действий (zero-downtime):**
1. Добавить новые URI у провайдеров (не удаляя старые — большинство провайдеров разрешают несколько)
2. Задеплоить код с новыми роутами
3. Обновить `.env`, перезапустить `docker compose up -d`
4. Убедиться что OAuth работает по новым путям
5. Удалить старые URI у провайдеров

---

### ✅ MM-83 — React SPA: страницы и полный флоу

> Ветка: `feature/spa`. Все страницы реализованы.

**Стек:** Vite + React 19 + TypeScript + React Router v6 + plain CSS (тёмная тема)

**Реализовано:**
- [x] `frontend/` — Vite + React + TypeScript проект
- [x] `api/` слой: `client.ts` (fetch wrapper, JWT Bearer), `auth.ts`, `services.ts`, `migrations.ts`
- [x] Базовый CSS (тёмная тема, CSS-переменные) + стили для всех компонентов
- [x] `App.tsx` — роутинг (BrowserRouter, 5 роутов)
- [x] `AuthCallbackPage.tsx` — обмен code → JWT + redirect к flow_from/flow_to
- [x] `docker-compose.dev.yml` — frontend сервис порт 3000
- [x] `HomePage.tsx` — выбор from/to сервисов, auth-статусы на карточках, OAuth кнопки, `canProceed` gate
- [x] `MigratePage.tsx` — настройки (limit, skip_already, like_tracks, spotify_playlist_mode) + старт
- [x] `ProgressPage.tsx` — polling каждые 2с, прогресс-бар, статистика, terminal actions
- [x] `HistoryPage.tsx` — список миграций, статус-бейджи, success/not_found, ссылка на плейлист
- [x] `api/migrations.ts` — типы под реальные ответы API (TrackStats, MigrationDetail, TracksPage)
- [x] `api/services.ts` — MatrixEntry, UserStatus, isConnected, fetchUserStatus

**Не входит в MM-83 (отдельные задачи):**
- File→XX upload (нет multipart endpoint в `/api/v1/`)
- Cancel миграции пользователем (нет user-facing cancel API)
- Disconnect сервиса, смена языка

---

### 🔲 MM-82 — Удаление Jinja2 UI (после готовности SPA)

> Финальный cleanup после того как SPA-фронтенд задеплоен и стабилен.

- [ ] `WEB_ENABLED=false` в `.env` на EU сервере → отключить Jinja2 UI (бот и API продолжают работать)
- [ ] Убрать `SessionMiddleware` из `api/main.py`
- [ ] Удалить `api/templates/`, `api/routes/web.py`, `api/routes/oauth.py` (бот-роуты перенести в `bot_auth.py`)
- [ ] Удалить HTMX-фрагменты: `GET /api/flow/*` (заменены SPA)
- [ ] Удалить `WEB_ENABLED`, `web_allowed_ips` из `config.py` и `api/middleware.py`
- [ ] Обновить `docker-compose.yml`: добавить `frontend` сервис (nginx static)
- [ ] Обновить CLAUDE.md, тесты

---

### 🔲 MM-84 — VK Музыка: интеграция (чтение + запись лайков)

> Двунаправленная интеграция с ВКонтакте Музыкой.
> Ветка: `mm-84-vk-music`

#### Контекст (результаты ресерча)

**VK Audio API требует партнёрского статуса** — `audio.*` методы возвращают error 201 (Access denied) для обычных приложений. Доступ выдаётся VK отдельно после рассмотрения заявки.

**Авторизация — два сценария (зависит от одобрения VK):**

**Сценарий A (целевой): собственное приложение с официальным audio-доступом**
- Регистрируем приложение на vk.com/apps → получаем `VK_CLIENT_ID` + `VK_CLIENT_SECRET`
- Подаём заявку на доступ к Audio API (support.vk.com или раздел прав в настройках приложения)
- При одобрении: стандартный **Authorization Code Flow** со scope `audio+offline`
- OAuth endpoint: `https://oauth.vk.com/authorize`, token: `https://oauth.vk.com/token`
- Пользователь авторизуется через привычный VK OAuth popup — никаких костылей
- **Новые env:** `VK_CLIENT_ID`, `VK_CLIENT_SECRET`, `VK_REDIRECT_URI`

**Сценарий Б (fallback): Kate Mobile credentials**
- Используем публичные credentials Kate Mobile (`client_id=2685278`) — стандарт в экосистеме
- Password grant: пользователь вводит телефон+пароль → получаем token
- Или: пользователь сам получает token и вставляет вручную (как SC cookie до MM-52)
- Риск: VK может отозвать Kate Mobile access в любой момент
- **Реализовать как fallback**, если Сценарий A не одобрят

**Реализуем Сценарий A сразу** (код чище, OAuth как у Spotify/SC). Сценарий Б — только если VK откажет.

**Ограничения (оба сценария):**
- `audio.createPlaylist` (создание плейлиста) — только если VK явно одобрит; **пока не реализуем**
- Нет ISRC → матчинг по artist + title + duration
- Rate limit: ≤1 req/s (официально 3 req/s, на практике безопаснее 1 req/s)

#### Capability flags

```
VKMusicAdapter:
  READ_LIKED_TRACKS       ✓   audio.get (owner_id, count up to 6000)
  READ_PLAYLISTS          ✓   audio.getPlaylists + audio.get(album_id=...)
  WRITE_LIKED_TRACKS      ✓   audio.search + audio.add
  WRITE_PLAYLISTS         ✗   partner-only, не реализуем
  WRITE_LIKED_ARTISTS     ✗   нет концепции "подписки на артиста" в VK Audio API
  EXPORT                  ✓   через FileAdapter
```

#### Матрица переносов (добавить в Transfer Matrix)

```
FROM \ TO  | VK Музыка
-----------|----------
ЯМ         |     ✓  (треки)
Spotify    |     ✓  (треки)
File       |     ✓  (треки)
SoundCloud |     ✓  (треки)

VK Музыка → ЯМ, Spotify, SoundCloud, File — все направления ✓
```

#### Структура файлов

```
core/vk/
  client.py        — VKMusicClient: get_liked_tracks(), get_playlists(), search_track(), add_track()
  models.py        — VKTrack(id, owner_id, artist, title, duration, access_key), VKPlaylist
core/services/vk/
  adapter.py       — VKMusicAdapter: READ_LIKED_TRACKS | READ_PLAYLISTS | WRITE_LIKED_TRACKS | EXPORT
migration/
  to_vk.py         — any → VK лайки (search + add, sleep 1.0s, fuzzy match)
worker/tasks.py    — run_vk_migration_job (any → VK)
api/routes/
  web.py           — добавить VK в auth flow (вставка токена, как SC cookie)
  api_v1.py        — поддержка vk_token в /api/v1/auth/me и /api/v1/migrations
config.py          — VK_ACCESS_TOKEN (для CLI), VK_KATE_USER_AGENT
```

#### Авторизация (два варианта)

**Вариант A — Authorization Code Flow (бэкенд-редирект, как Spotify/SC):**
1. Кнопка «Войти через VK» → redirect на `https://oauth.vk.com/authorize?client_id=...&scope=audio,offline&response_type=code&redirect_uri=...`
2. VK → callback `/api/v1/auth/vk/callback?code=...` → обмен code → access_token → JWT

**Вариант B — VK ID Widget (встроенный виджет, лучше для SPA):**
- VK одобрил приложение + предоставил возможность встроить виджет авторизации
- JS SDK: `<script src="https://vk.com/js/api/openapi.js">`
- `VK.init({ apiId: VK_CLIENT_ID })` → `VK.Auth.login(callback, scope)` → получаем `access_token` прямо в браузере без редиректа
- Токен отправляется на бэкенд `POST /api/v1/auth/vk/token {access_token}` → валидация → JWT
- **Преимущество:** пользователь не покидает SPA, нативный VK попап
- **Новый бэкенд endpoint:** `POST /api/v1/auth/vk/token` — принимает access_token от виджета, валидирует через `users.get`, сохраняет, возвращает JWT

**Реализуем оба:** виджет — основной путь в SPA, redirect — fallback и для Jinja2 UI.

#### Ключевые технические детали

- `audio.get`: `owner_id` = user_id (отрицательный для групп), `count` (max ~6000), `offset`
- `audio.search`: `q="{artist} {title}"`, `count=10`, сортировка по релевантности
- `audio.add`: `audio_id` + `owner_id` + опционально `access_key` (для треков из чужих библиотек)
- track dedup key: `f"{owner_id}_{id}"` (аналог sc_id)
- Duration matching: ±5 секунд от оригинала — дополнительный критерий после fuzzy match
- `vk_api_url = "https://api.vk.com/method/"`, `v = "5.131"`
- User-Agent: `KateMobileAndroid/56 lite-460 (Android 4.4.2; SDK 19; x86; unknown Android SDK built for x86; en)`
- Sleep между write ops: 1.0s (аналог YM)

#### Зависимости

```
vkpymusic>=3.5.1   # либо прямые запросы через aiohttp (без лишних зависимостей)
```
Если `vkpymusic` не поддерживает async нативно → использовать `asyncio.to_thread` или писать клиент напрямую через `aiohttp`.

#### Новые env-переменные

```env
VK_CLIENT_ID=        # из vk.com/apps (настройки приложения)
VK_CLIENT_SECRET=    # из vk.com/apps
VK_REDIRECT_URI=     # https://yourdomain.com/api/v1/auth/vk/callback
VK_ACCESS_TOKEN=     # для CLI-режима (опц.)
```

#### Задачи

- [ ] `core/vk/models.py` — `VKTrack`, `VKPlaylist`
- [ ] `core/vk/client.py` — `VKMusicClient`: `init()`, `get_liked_tracks()`, `get_playlists()`, `search_track()`, `add_track()` (async через aiohttp, Kate Mobile UA)
- [ ] `core/services/vk/adapter.py` — `VKMusicAdapter` (READ_LIKED_TRACKS | READ_PLAYLISTS | WRITE_LIKED_TRACKS | EXPORT)
- [ ] `migration/to_vk.py` — `run_migration()`: любой источник → VK лайки (fuzzy match + duration check + audio.add)
- [ ] `worker/tasks.py` — `run_vk_migration_job`
- [ ] `api/routes/oauth.py` — VK OAuth redirect/callback (`GET /auth/vk`, `GET /api/v1/auth/vk/callback`) — Authorization Code Flow
- [ ] `api/routes/api_v1.py` — `POST /api/v1/auth/vk/token` (виджет: принять access_token от JS SDK, валидировать через `users.get`, сохранить, вернуть JWT); `vk_token` в `/auth/me`; поддержка `from_service=vk_music` / `to_service=vk_music` в `POST /api/v1/migrations`
- [ ] SPA: VK ID Widget в `HomePage.tsx` — подключить VK OpenAPI JS SDK, `VK.Auth.login()` → `POST /api/v1/auth/vk/token`
- [ ] `config.py` — `vk_access_token`, `vk_kate_user_agent`
- [ ] `core/db/models.py` + alembic — `UserSession.vk_token`
- [ ] `core/db/crud.py` — `save_vk_token`, `get_vk_token`
- [ ] Тесты: клиент (mock aiohttp), adapter capabilities, migration pipeline
- [ ] CLAUDE.md, PLAN.md, progress.md обновить

---

### ✅ MM-85 — Spotify продакшн-фиксы + оптимизации матчинга

#### Проблемы

1. `like_track` → 403 Forbidden на `PUT /me/tracks` (deprecated endpoint)
2. Ошибки 403 засчитывались как `not_found` в статистике
3. Поиск на Spotify не находил треки для артистов с кириллическим именем (Баста → Basta)
4. Fetch всех треков перед срезом по лимиту — лишние запросы
5. `_SEARCH_LIMIT` захардкожен, нельзя настроить без кода
6. Матчинг проверял всех кандидатов даже после идеального совпадения (score=100)

#### Решения

- [x] `like_track` → новый `PUT /me/library?uris=spotify:track:{id}` (не deprecated)
- [x] `_run_pending_tracks_loop`: `elif result == "error": stats.errors += 1` (отдельно от not_found)
- [x] `_process_one_track`: добавлены транслитерированные варианты имён артистов в поисковые запросы (`transliterate_variants`)
- [x] `get_liked_tracks(limit)` в YM и Spotify клиентах — останавливает пагинацию/батч при достижении лимита
- [x] `SEARCH_LIMIT` → `settings.search_limit` (env: `SEARCH_LIMIT`, default 5)
- [x] `find_best_match`: `break` при `score == 100.0` — не проверяет остальных кандидатов
- [x] UI: добавлена опция 5 треков (для тестирования), убрана 100
- [x] Логирование scope в refresh_access_token для диагностики
- [x] `like_track`: логирует тело ответа при не-200 (WARNING уровень)

#### Файлы

- `core/spotify/client.py` — новый эндпоинт, лимит пагинации, логирование ошибок
- `core/yandex/client.py` — `get_liked_tracks(limit)`
- `core/services/yandex/adapter.py`, `core/services/spotify/adapter.py` — пробрасывают limit
- `core/services/base.py` — сигнатура `fetch_liked_tracks(token, limit=None)`
- `core/soundcloud/client.py` — `search_limit` из settings
- `core/matcher.py` — early exit на score=100
- `migration/to_spotify.py` — stats fix, transliterate_variants, settings.search_limit
- `config.py` — `search_limit: int = Field(default=5)`
- `worker/tasks.py` — передаёт limit в fetch, логирует scope
- `api/templates/fragments/flow_rest.html` — опция 5 треков

---

## Spotify Dev Mode — обходной путь (запасной план)

Extended Quota Mode недоступен (требует регистрации компании).
Текущий воркараунд: добавлять пользователей вручную в Dashboard → Settings → User Management (лимит 25).

Если ручное управление станет неудобным — реализовать **Playwright-автоматизацию** добавления/удаления пользователей из allowlist:

- [ ] `scripts/spotify_allowlist.py` — Playwright-скрипт: логин в Spotify Developer Dashboard, добавление/удаление email из allowlist
- [ ] Команды: `add <email>`, `remove <email>`, `list`
- [ ] Опционально: интеграция с БД — автодобавление при первом OAuth пользователя

> ⚠️ Технически нарушает Spotify ToS — использовать осознанно.

---

### MM-86 — Ресёрч аналогов: фичи и подходы

**Цель**: изучить конкурентов, найти идеи для улучшения сервиса.

#### Что исследовать

- [ ] Составить список сервисов-аналогов (Soundiiz, TuneMyMusic, Stamp, SongShift, FreeYourMusic и др.)
- [ ] Для каждого: поддерживаемые платформы, ограничения бесплатного тарифа, UX-отличия
- [ ] Что переносят помимо лайков: плейлисты, подписки на артистов, история прослушиваний, рейтинги
- [ ] Как решают проблему дев-режима Spotify (если решают)
- [ ] Уникальные фичи: мёрж библиотек, дедупликация, автосинхронизация, статистика матчинга
- [ ] Сформировать список идей для бэклога

#### Файлы

- `memory/research_competitors.md` — результаты ресёрча (не коммитить в публичный репо)

---

### ✅ MM-87 — Рефакторинг адаптеров: адаптеры как единственная точка взаимодействия с сервисами

**Цель**: пайплайны `migration/to_*.py` не должны знать о деталях конкретных платформ. Вся логика взаимодействия — поиск, запись — живёт в адаптере. Пайплайн работает только через интерфейс `AdapterWriteSession`.

#### Реализовано

- [x] `AdapterWriteSession` ABC в `core/services/base.py` — `search_track`, `write_track`, `search_artist`, `follow_artist`, `apply_transliteration`
- [x] `MusicServiceAdapter.write_session(token)` — async context manager → `AdapterWriteSession`
- [x] `_YMWriteSession` в `core/services/yandex/adapter.py`
- [x] `_SpotifyWriteSession` (с `apply_transliteration=True`) в `core/services/spotify/adapter.py`
- [x] `_SCWriteSession` (playlist_mode / like_tracks / LikeNotSupportedError fallback) в `core/services/soundcloud/adapter.py`
- [x] `migration/pipeline.py` — `process_one_track(session, row)` + `run_pending_tracks_loop()` — единый пайплайн
- [x] `migration/to_yandex.py` — принимает `ym_token: str`, не импортирует `YandexMusicClient`
- [x] `migration/to_spotify.py` — принимает `spotify_token: str`, `_run_pending_artists_loop` через сессию
- [x] `worker/tasks.py` — убраны `SpotifyClient` и `YandexMusicClient` из job-функций
- [x] 23 теста в `tests/test_adapter_write.py`, 237 всего проходят

#### Не в рамках MM-87 (отложено)
- `migration/to_soundcloud.py` — оставлена как есть (760 строк, playlist-batching SC-специфично)
- `api/routes/services.py` — matrix уже строится из Capability флагов (реализовано ранее)

#### Ключевые паттерны
- `adapter.write_session(token)` — async context manager, клиент создаётся и закрывается внутри
- `session.apply_transliteration` — Bool флаг; `pipeline.process_one_track` добавляет транслитерацию если True
- Transliteration при поиске: нужна для Spotify (Cyrillic → Latin), не нужна для YM

---

### ✅ MM-89 — Spotify: режим создания плейлиста вместо (или вместе с) лайками треков

**Цель**: при миграции в Spotify давать пользователю выбор — лайкать треки в коллекцию (текущее поведение) или создавать плейлист с найденными треками. Оба режима должны работать.

#### Что сделано

- [x] `_create_bot_playlist` переименована в `_create_playlist(migration_id, name, user_token)` — использует `settings.spotify_bot_token or user_token` (fallback на токен пользователя)
- [x] `flow_rest.html` — чекбокс режима плейлиста показывается для ВСЕХ Spotify-назначений (не только когда бот настроен)
- [x] `api/routes/api_v1.py` — `StartMigrationRequest`: `spotify_playlist_mode: bool = False` + `spotify_playlist_name: str = "Music Migration"`; пробрасывается в `run_spotify_write_job`
- [x] `bot/handlers/auth.py` — `_confirmation_kb` получает `spotify_playlist_mode: bool = False`; кнопка `toggle_spotify_playlist` для Spotify-назначения; `on_toggle_spotify_playlist` handler
- [x] `bot/handlers/migration.py` — `_kb_result` принимает `playlist_url: str | None`, добавляет кнопку плейлиста; `on_start_migration` читает `spotify_playlist_mode` из state; `_poll_migration` пробрасывает `result_path`
- [x] `bot/api_client.py` — `spotify_playlist_mode: bool = False` в `start_migration`
- [x] `core/i18n.py` — ключи `bot_spotify_playlist_on`, `bot_spotify_playlist_off`, `bot_btn_open_playlist`
- [x] 16 тестов в `tests/test_mm89_spotify_playlist_user.py`; MM-88 тесты обновлены (`_create_bot_playlist` → `_create_playlist`)

#### Ключевые решения

- `_create_playlist` работает без `SPOTIFY_BOT_TOKEN` — берёт токен пользователя как fallback; плейлист будет на аккаунте пользователя
- Чекбокс в UI теперь не гейтирован на `spotify_bot_configured`
- SPA endpoint `/api/v1/migrations` получил поддержку `spotify_playlist_mode` (была пропущена в MM-88)

#### Файлы

- `migration/to_spotify.py` — `_create_playlist` (renamed)
- `api/templates/fragments/flow_rest.html` — убрана проверка `spotify_bot_configured`
- `api/routes/api_v1.py` — новые параметры в `StartMigrationRequest`
- `bot/handlers/auth.py`, `bot/handlers/migration.py`, `bot/api_client.py` — playlist toggle + result button
- `core/i18n.py` — новые ключи
- `tests/test_mm89_spotify_playlist_user.py` (новый), `tests/test_mm88_spotify_playlist.py` (обновлён)

---

### ✅ MM-90 — SC like_track: исправлен эндпоинт (405 → POST /likes/tracks/{urn})

**Проблема:** `PUT /me/track_likes/{id}` возвращал HTTP 405 "unknown route" — эндпоинт не существует.

**Причина:** задокументированный в CLAUDE.md эндпоинт не соответствует официальной документации SC.
По [SC Open API docs](https://developers.soundcloud.com/docs/api/explorer/open-api#/likes/post_likes_tracks__track_urn_)
правильный эндпоинт: `POST /likes/tracks/{track_urn}`, где URN = `soundcloud:tracks:{track_id}`.

**Что исправлено:**
- [x] `core/soundcloud/client.py` — `like_track()`: `PUT /me/track_likes/{id}` → `POST /likes/tracks/soundcloud:tracks:{id}`; `_put()` → `_post()`
- [x] `CLAUDE.md` — обновлён задокументированный эндпоинт

**Файлы:** `core/soundcloud/client.py`, `CLAUDE.md`

---

### ✅ MM-93 — Валидация токенов перед запуском миграции

**Проблема:** при невалидном Spotify/YM/SC токене воркер падал с `ValueError` уже после постановки задачи в очередь — пользователь видел статус "ошибка" без понятного объяснения и кнопки переавторизации.

**Что сделано:**

- [x] `core/db/crud.py` — `clear_service_token(user_id, service)`: обнуляет токен + refresh_token в БД для сервиса
- [x] `api/routes/web.py` — `_validate_service_token(service, token)` + `_SESSION_FLAG` dict + `_check_token(service, pf, pt)` closure в handler:
  - Spotify: `SpotifyClient(token).init()` → 401 = невалидный
  - YM: `YandexMusicClient(token).init()` → auth failure
  - SC: прямой HTTP GET `/me` → 401 = невалидный (403 — ожидаемо для неодобренных приложений)
- [x] При ошибке: `clear_service_token`, удаление session флага, редирект `/?error=...&pf={from}&pt={to}` (восстанавливает флоу + показывает кнопку авторизации)
- [x] Вызов во всех 3 кейсах `start_migrate` (export/import/normal) перед enqueue
- [x] Тесты: `test_clear_service_token_spotify/yandex/unknown_service`

**Файлы:** `core/db/crud.py`, `core/db/__init__.py`, `api/routes/web.py`, `tests/test_db_integration.py`

---

### ✅ MM-94 — SC like_tracks: трек добавляется и в плейлист тоже

**Проблема:** при включённой галочке "Лайкнуть треки" (like_tracks=True) плейлист НЕ создавался — трек только лайкался напрямую. Плейлист должен создаваться всегда.

**Причина:** в `_process_one_track` при успешном лайке возвращалось `("liked", None)` — `None` вместо `match.track_id` означало что sc_id не попадал в `collected_ids` → плейлист для трека не создавался.

**Что исправлено:**
- [x] `migration/to_soundcloud.py` — `_process_one_track`: `return "liked", None` → `return "liked", match.track_id`
- [x] `migration/to_soundcloud.py` — `_run_pending_loop`: для `result == "liked"` добавлен `if sc_id: collected_ids.append(sc_id)`
- [x] `tests/test_pipeline.py` — `test_process_track_like_tracks_success`: обновлён assert `sc_id == 55` (было `is None`)

**Итоговое поведение:**
- `like_tracks=False` + `playlist_mode=True`: только плейлист → `status=in_playlist`
- `like_tracks=True`: прямой лайк → `status=liked` + sc_id идёт в `collected_ids` → плейлист тоже создаётся

**Файлы:** `migration/to_soundcloud.py`, `tests/test_pipeline.py`

---

### 🔲 MM-91 — Rate limiting: защита API от флуда

**Контекст:** Сейчас ограничена только частота запуска миграций (10/час per user_id, Redis).
Все остальные эндпоинты — `/api/v1/`, OAuth, HTMX-поллинг — без ограничений.

**Два уровня защиты:**

**Уровень 1 — Nginx** (первый рубеж, только прод):
- [ ] `nginx/nginx.conf` — `limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s`
- [ ] `/api/v1/` — `limit_req zone=api burst=20 nodelay`
- [ ] `/api/v1/auth/exchange` + `/api/v1/auth/refresh` — отдельная зона `2r/s` (брутфорс кодов)
- [ ] 429 response с `Retry-After` заголовком

**Уровень 2 — FastAPI middleware** (работает и без nginx, для dev):
- [ ] Добавить `slowapi` в `requirements.txt`
- [ ] `api/main.py` — `Limiter(key_func=get_remote_address)` + `SlowAPIMiddleware`
- [ ] Декораторы `@limiter.limit("30/minute")` на тяжёлые эндпоинты: `GET /api/v1/migrations/{id}`, `GET /api/v1/migrations/{id}/tracks`
- [ ] Декоратор `@limiter.limit("5/minute")` на `/api/v1/auth/exchange`, `/api/v1/auth/refresh`

**Файлы:** `nginx/nginx.conf`, `api/main.py`, `requirements.txt`

---

### ✅ MM-92 — Web UI: статусы треков, история, инлайн список, переименования

**Цель:** улучшить отображение информации о миграции и треках в веб-интерфейсе.

**Что сделано:**

- [x] Новый статус `in_playlist` — трек добавлен в плейлист (не лайкнут напрямую). Раньше `playlist_mode` ставил `status="liked"`, теперь — `status="in_playlist"`. Режимы взаимоисключающие.
- [x] `MigrationStats.in_playlist` + `.success` property = `liked + in_playlist`
- [x] `get_track_stats_batch()` в `core/db/crud.py` — один SQL-запрос для статистики N миграций (история, без N+1)
- [x] История (`/history`) — иконки + имена сервисов from/to, `success_count/total_count`, кнопка "Новый перенос"
- [x] Страница миграции (`/migrate/{id}`) — убрана кнопка "Подробный отчёт"; инлайн список треков при завершении через HTMX sub-fragment (`/migrate/{id}/tracks-fragment`)
- [x] Новый шаблон `fragments/tracks_table.html` — фильтр табов + таблица + пагинация (50/страница), HTMX-навигация
- [x] `/migrate/{id}/result` → 301 редирект на `/migrate/{id}`
- [x] "Score" → "Точность" / "SC" → "Ссылка" во всех шаблонах
- [x] Ссылки на треки — по типу сервиса назначения: Spotify → open.spotify.com/track/{id}, YM → music.yandex.ru/track/{id}, SC → полный URL
- [x] Прогресс (`progress.html`) — показывает from/to сервис
- [x] Тесты: обновлены + 5 новых (stats, in_playlist статусы, batch stats в DB)

**Файлы изменены:**
- `migration/to_soundcloud.py` — `MigrationStats.in_playlist`, `_process_one_track` возвращает `in_playlist`
- `core/db/crud.py` — `get_track_stats_batch`, `get_previously_migrated_ym_ids` учитывает `in_playlist`
- `core/db/__init__.py` — экспорт `get_track_stats_batch`
- `core/i18n.py` — `tstatus_in_playlist`, `history_new_btn`, `tracks_col_score`, `tracks_col_sc`, `history_success_count`
- `api/routes/web.py` — `/tracks-fragment` эндпоинт, история со статистикой
- `api/templates/history.html`, `progress.html`, `fragments/status.html`, `tracks.html`
- `api/templates/fragments/tracks_table.html` (новый)
- `api/templates/admin/migrations.html`, `admin/migration_detail.html`
- `tests/test_pipeline.py`, `tests/test_db_integration.py`

---

### ✅ MM-88 — Spotify: обход ограничений через бот-пользователя (плейлист-шаринг)

**Цель**: обойти лимит 25 пользователей в dev-режиме Spotify — вместо лайка треков на аккаунте пользователя, создавать плейлист от имени бот-аккаунта и отдавать пользователю ссылку.

#### Что сделано

- [x] `SPOTIFY_BOT_TOKEN` / `SPOTIFY_BOT_REFRESH_TOKEN` в config.py
- [x] `SpotifyClient.create_playlist(name)` → `(playlist_id, playlist_url)` + `add_tracks_to_playlist(id, uris)` (батч 100)
- [x] `get_track_urls_by_status(migration_id, status)` в `core/db/crud.py`
- [x] `_SpotifyWriteSession(playlist_mode=True)`: `write_track` возвращает `"in_playlist"` без вызова `like_track`
- [x] `migrate_to_spotify(playlist_mode=True, playlist_name=...)`: после пайплайна вызывает `_create_bot_playlist`
- [x] `playlist_url` сохраняется в `Migration.result_path`; возвращается в `SpotifyWriteStats.playlist_url`
- [x] `run_spotify_write_job`: `playlist_mode`, `playlist_name` параметры; `playlist_url` в Telegram-уведомлении
- [x] `api/routes/migrations.py`: `spotify_playlist_mode`, `spotify_playlist_name` поля в `StartMigrationRequest`
- [x] `api/routes/web.py`: форма + `spotify_bot_configured` в контексте шаблона
- [x] `status.html`: кнопка "Открыть плейлист" для Spotify-миграций с `result_path`
- [x] `flow_rest.html`: чекбокс режима плейлиста для `to=spotify` когда бот настроен
- [x] `notifications.py`: `playlist_url` ссылка в Telegram-сообщении
- [x] 13 тестов в `tests/test_mm88_spotify_playlist.py`, 272 всего проходят

#### Файлы

- `config.py` — новые env vars
- `core/spotify/client.py` — `create_playlist`, `add_tracks_to_playlist`
- `core/db/crud.py`, `core/db/__init__.py` — `get_track_urls_by_status`
- `core/services/spotify/adapter.py` — `playlist_mode` в `_SpotifyWriteSession` + `write_session`
- `migration/to_spotify.py` — `playlist_mode`, `_create_bot_playlist`, `SpotifyWriteStats.playlist_url`
- `worker/tasks.py`, `worker/notifications.py` — проброс параметров
- `api/routes/migrations.py`, `api/routes/web.py` — новые параметры
- `api/templates/fragments/status.html`, `flow_rest.html` — UI
- `core/i18n.py` — новые ключи: `index_spotify_playlist_mode`, `status_open_playlist_btn`, `notif_done_playlist`

---

### 🔲 MM-96 — Фикс like_track → not-authenticated для →YM миграций

**Баг:** При миграции в Яндекс Музыку `POST /users/{uid}/likes/tracks/add-multiple` возвращает 403 `{'name': 'not-authenticated', 'message': ''}`. `init()` проходит успешно (uid получен через Yandex ID API), но write-операция падает.

**Исследовано и исключено:**
- Прокси работает — `SocksProxyRequest._request_wrapper` создаёт `ProxyConnector` per-request для ВСЕХ запросов
- Заголовок `Authorization: OAuth {token}` передаётся корректно (через `self.headers` → `Request.post` → kwargs)
- Формат track_id правильный — `str(track.id)` (числовой ID); `user_id` передаётся явно

**Причина:** В `bot/oauth/yandex.py` строка 17 документировано: `"Права: login:info + Яндекс.Музыка (все на чтение)"`. OAuth-приложение на `oauth.yandex.ru` настроено только с **read**-правами. Write-endpoint требует write-скоупа — отсюда 403.

**Шаги фикса:**

- [ ] На `oauth.yandex.ru` добавить write-право для Яндекс.Музыки в настройках приложения
- [ ] Пользователь должен пройти re-auth (старый токен write-скоуп не получит ретроактивно)
- [ ] Обновить комментарий в `bot/oauth/yandex.py:17` — убрать `(все на чтение)`, указать что нужны и read, и write права
- [ ] `core/yandex/proxy_request.py:56` — логировать HTTP-статус отдельно: `UnauthorizedError(f"HTTP {resp.status}: {message}")`
- [ ] `core/yandex/client.py:240` — отдельно ловить `UnauthorizedError` в `like_track` → WARNING с подсказкой про re-auth вместо generic ERROR

**Файлы:** `core/yandex/client.py:240`, `core/yandex/proxy_request.py:56`, `bot/oauth/yandex.py:17`

---

### ✅ MM-96 — SPA: фиксы auth URL, page_size, dev-mode авторизация

**Проблема:** Три бага обнаруженных при первом запуске SPA в dev-режиме:
1. `GET /api/v1/auth/yandex_music` → 404 — сервис ID `yandex_music` не совпадал с именем endpoint `/auth/yandex`
2. `get_tracks_page(..., page_size=50)` → игнорировалось — параметр называется `per_page`
3. SPA не могла авторизоваться в DEV_MODE — JWT не выдавался, хотя `dev_user` был в БД

**Что исправлено:**

- [x] `frontend/src/api/auth.ts` — `getOAuthStartUrl`: маппинг `SERVICE_AUTH_SLUG = {yandex_music: 'yandex'}` перед построением URL → фиксит 404 на `/auth/yandex_music`
- [x] `api/routes/api_v1.py` — `get_migration_tracks`: `page_size=page_size` → `per_page=page_size` (имя параметра в crud)
- [x] `api/security.py` — `get_current_user`: при `DEV_MODE=true` сразу возвращает `"dev_user"` без проверки JWT
- [x] `frontend/src/api/auth.ts` — `refreshAccessToken`: при отсутствии refresh token в localStorage пробует `GET /auth/me` без заголовка; в DEV_MODE сервер отдаёт 200 → SPA ставит sentinel `"dev"` в память и продолжает работу; в проде → 401 → поведение прежнее

**Принцип dev-bypass:** без нового endpoint — backend просто не проверяет JWT в DEV_MODE, frontend использует существующий `/auth/me` как зонд.

**Файлы:** `frontend/src/api/auth.ts`, `api/routes/api_v1.py`, `api/security.py`

---

### 🔲 MM-95 — Яндекс Музыка: режим создания плейлиста

**Контекст:** Миграция → YM сейчас только лайкает треки. Нет режима плейлиста (аналогично SC `playlist_mode`). Галочка "Проставить лайки" для YM скрыта в UI (MM-94) именно потому что второго режима нет.

**Цель:** Дать выбор: лайкать треки ИЛИ создать плейлист с найденными треками.

**YM API:**
- `POST /users/{uid}/playlists` — создание плейлиста (title, visibility)
- `POST /users/{uid}/playlists/{kind}/change-relative` — добавление треков (revision + diff с insert)

**Что сделать:**

- [ ] `core/yandex/client.py` — `create_playlist(title)` → kind; `add_tracks_to_playlist(kind, track_ids)`
- [ ] `migration/to_yandex.py` — `playlist_mode: bool` в `migrate_to_yandex` + `_run_pending_loop`:
  - `playlist_mode=False` (default): лайки → `status=liked`
  - `playlist_mode=True`: собирает track_ids → создаёт плейлист в конце → `status=in_playlist`
- [ ] `worker/tasks.py` — `run_yandex_migration_job` принимает `like_tracks: bool = True`; передаёт `playlist_mode=not like_tracks`
- [ ] `api/routes/web.py` — передавать `like_tracks=like` в `run_yandex_migration_job`
- [ ] `api/templates/fragments/flow_rest.html` — показывать чекбокс для `to_service == 'yandex_music'`
- [ ] Тесты: `playlist_mode`, батчинг `add_tracks_to_playlist`

**Файлы:** `core/yandex/client.py`, `migration/to_yandex.py`, `worker/tasks.py`, `api/routes/web.py`, `api/templates/fragments/flow_rest.html`

---

### 🔲 MM-97 — SPA: Admin Panel

**Цель:** Перенести функционал Jinja2-админки в React SPA — без отдельного `/admin/*` роутера. Доступ через роль `role="admin"` в JWT, уже возвращаемой `/api/v1/auth/me`.

#### Новые `/api/v1/` endpoints (admin-only)

Зависимость `require_admin`:
```python
async def require_admin(user_id: str = Depends(get_current_user)):
    session = await load_user_session(user_id)
    if not session or session.get("role") != "admin":
        raise HTTPException(403)
    return user_id
```

- [ ] `GET /api/v1/stats` — дашборд: total_migrations, total_users, total_tracks; by_status (migrations + tracks); последние 10 миграций
- [ ] `GET /api/v1/admin/migrations` — все миграции (filter: `?status=`, `?user_id=`), до 200; `require_admin`
- [ ] `GET /api/v1/admin/migrations/{id}` — детали + треки (filter: `?status=`), до 500; `require_admin`
- [ ] `POST /api/v1/admin/migrations/{id}/cancel` — отмена ARQ job + статус cancelled; `require_admin`
- [ ] `POST /api/v1/admin/migrations/{id}/restart` — сброс error треков в pending, re-enqueue; `require_admin`
- [ ] `GET /api/v1/admin/users` — все юзеры + migration_count; `require_admin`
- [ ] `POST /api/v1/admin/users/{user_id}/role` — смена роли (user/admin); `require_admin`

> `/api/v1/services` и `/api/v1/services/matrix` уже открыты — сервис-реестр показывается без нового endpoint.

#### Существующие endpoints — расширение для admin

- [ ] `GET /api/v1/migrations` — если `role=admin`, принимает `?user_id=` и возвращает все миграции (иначе только свои)
- [ ] `GET /api/v1/migrations/{id}` — если `role=admin`, пропускает ownership check

#### SPA (frontend)

- [ ] `App.tsx` — маршрут `/admin` + sub-routes `/admin/dashboard`, `/admin/migrations`, `/admin/migrations/:id`, `/admin/users`; обёртка `<AdminRoute>` (redirect если `role !== "admin"`)
- [ ] `AdminDashboardPage` — stat-карточки + таблица миграций по статусу + последние 10
- [ ] `AdminMigrationsPage` — таблица всех миграций, фильтры status/user_id
- [ ] `AdminMigrationDetailPage` — треки с фильтром + кнопки cancel/restart
- [ ] `AdminUsersPage` — таблица юзеров + смена роли
- [ ] Навбар/меню — ссылка "Admin" появляется если `role === "admin"`

#### Auth

- Старый `/admin/login` (пароль) — оставить работающим до момента когда первый admin-юзер будет назначен через DB/CLI
- Или добавить одноразовый CLI-скрипт `scripts/make_admin.py user_id` как альтернативу

**Файлы:** `api/routes/api_v1.py`, `api/security.py` (require_admin), `frontend/src/pages/admin/*`, `frontend/src/App.tsx`

---

### ✅ MM-98 — SPA: UI фиксы и недостающие фичи

- [x] `HomePage.tsx` — убраны `service-badge` с карточек FROM/TO
- [x] `MigratePage.tsx` — content_types чекбоксы (tracks/playlists/artists, disabled для from=file)
- [x] `StartMigrationRequest` — `content_types` теперь передаётся из UI
- [x] File import: file-picker в `MigratePage`, `parseImportFile()` парсит CSV/JSON на клиенте, `tracks_override` в JSON body
- [x] `api/routes/api_v1.py` — `tracks_override` в `StartMigrationRequest`; file→SC → `run_file_migration_job`; file→YM/Spotify → `tracks_override` в воркеры
- [x] Export (to=file): кнопки CSV↓/JSON↓ в `ProgressPage` (status=done)
- [x] Lang switcher: `LangContext` + `LangSwitcher` компонент в `App.tsx`, `localStorage` persist (без бэкенда)
- [x] `MigratePage.tsx` — Spotify playlist name input (когда spotifyPlaylistMode=true)
- [x] 5 новых тестов в `tests/test_mm98_spa_ui.py`; 295 passed total

---

### 🔲 MM-99 — Code Review: безопасность и качество кода

**Цель:** исправить проблемы выявленные в ходе полного ревью кодовой базы (2026-03-25). Разбито по приоритету.

#### Критические (блокирующие продакшн)

- [ ] **Валидатор шифрования токенов** — `config.py`: добавить `model_validator` который выбрасывает `ValueError` если `db_encryption_key=""` и `dev_mode=False`; предотвращает случайный запуск прода без шифрования
- [ ] **Скрыть детали ошибок в OAuth redirects** — `api/routes/api_v1.py`, `api/routes/oauth.py`: вместо `str(e)[:120]` в URL — логировать ошибку, пользователю отдавать generic `"internal_error"`
- [ ] **Валидация файловых загрузок** — `api/routes/web.py`: добавить проверку magic bytes (`python-magic` или встроенный `imghdr`-аналог), ограничение размера (10 MB), whitelist расширений `.csv`/`.json`

#### Высокий приоритет

- [ ] **Rate limit на auth endpoints** — `api/routes/api_v1.py`: добавить slowapi лимиты на `POST /auth/exchange` (10/мин) и `POST /auth/refresh` (30/мин)
- [ ] **ARQ job timeout** — `worker/main.py`: добавить `job_timeout=3600` (1 час) в `WorkerSettings`; в каждую джоб-функцию добавить `max_tries=1`
- [ ] **Fix `decrypt_token` fallback** — `core/crypto.py`: при `InvalidToken` логировать error и `raise ValueError("Token decryption failed")` вместо `return value` (encrypted строка как plain text — ломает API вызовы)
- [ ] **Spotify token refresh mid-migration** — `worker/tasks.py` / `migration/to_spotify.py`: передавать `refresh_token` в `_SpotifyWriteSession`; при истечении access token (401 от API) — вызывать `refresh_access_token()` и продолжать
- [ ] **Fix race condition job ID** — `api/routes/migrations.py`: сохранять job_id в Redis ДО старта джоба; использовать `arq.enqueue_job(..., job_id=pre_generated_id)` или атомарный set-then-enqueue
- [ ] **CORS whitelist** — `api/main.py`: заменить `allow_methods=["*"]` → `["GET", "POST", "PUT", "DELETE", "OPTIONS"]`, `allow_headers=["*"]` → `["Authorization", "Content-Type", "Accept"]`
- [ ] **`secrets.token_hex` для session ID** — `api/routes/oauth.py:52`: `uid = f"web_{uuid.uuid4().hex[:12]}"` → `f"web_{secrets.token_hex(16)}"`

#### Средний приоритет

- [ ] **Idempotency key для POST /migrations** — `api/routes/migrations.py`: принимать необязательный `Idempotency-Key` header; проверять Redis `idempotency:{key}` TTL 60s перед созданием новой миграции
- [ ] **Exponential backoff для 429** — `core/soundcloud/client.py`, `core/spotify/client.py`: при `RateLimitError` — ждать 2^attempt секунд (макс 60с) перед retry
- [ ] **Schema-валидация `tracks_override`** — `worker/tasks.py`: при `tracks_override is not None` — валидировать каждый элемент через `pydantic.TypeAdapter(list[TrackInput]).validate_python(tracks_override)` (добавить `TrackInput` модель)
- [ ] **`/health` расширенный** — `api/main.py`: проверять ping к PostgreSQL (`select 1`) и Redis (`await redis.ping()`); возвращать `{"status": "ok", "db": "ok", "redis": "ok"}` или 503

#### Не делать сейчас (зафиксировано, ждёт SPA Фаза 2)

- Refresh token в `localStorage` — исправляется переходом на httpOnly cookie в MM-82 (после удаления Jinja2 и SessionMiddleware; требует `allow_credentials=True` в CORS)
- Linear scan refresh tokens — допустимо для текущего объёма пользователей; индекс добавить позже

**Файлы:** `config.py`, `api/main.py`, `api/routes/api_v1.py`, `api/routes/oauth.py`, `api/routes/migrations.py`, `api/routes/web.py`, `core/crypto.py`, `worker/main.py`, `worker/tasks.py`, `migration/to_spotify.py`, `core/soundcloud/client.py`, `core/spotify/client.py`

---

