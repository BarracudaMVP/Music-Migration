# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Music Migration — service for migrating music libraries between streaming platforms.
Current state: **MM-99** (последний завершённый — security & reliability fixes). **feature/spa смержена в main** (2026-03-26). Deployed on EU server.
Supports: Yandex Music, Spotify, SoundCloud, File (CSV/JSON) — bidirectional migrations, Web UI, Telegram bot.

Transfer matrix:
```
FROM \ TO     | SoundCloud | File (CSV/JSON) | Яндекс Музыка | Spotify
--------------|------------|-----------------|---------------|--------
Яндекс Музыка |     ✓      |        ✓        |       –       |    ✓
Spotify       |     ✓      |        ✓        |       ✓       |    –
File          |     ✓      |        ✗        |       ✓       |    ✓
SoundCloud    |     –      |        ✓        |       ✓       |    ✓
```
File→File запрещён (карточка "В файл" скрывается в UI когда FROM=File).

Note: SC destination uses **playlist_mode** — tracks are collected then placed into "YM Liked #N" playlists (SC `like_track` API returns 404 for external tokens).

## Install & Run

```bash
pip install -r requirements.txt
python run_api.py       # FastAPI server (port 8000)
python run_worker.py    # ARQ background worker (requires Redis)
python run.py           # Telegram bot (optional)
python cli.py           # CLI mode (uses YANDEX_TOKEN + SOUNDCLOUD_TOKEN from .env)
```

## Lint / Format

```bash
ruff check .
ruff format .
```

## Tests

```bash
.venv/Scripts/pytest tests/
```

## Deploy & Release (production, EU server)

Все команды выполняются **на EU сервере** из `/root/Music-Migration/`.

### Деплой

```bash
# Обновить до последнего main (самый частый случай)
bash scripts/deploy.sh

# Переключиться на тег (стабильный релиз)
bash scripts/deploy.sh v1.0-mm49

# Переключиться на конкретный коммит
bash scripts/deploy.sh 6e1b8ad

# Переключиться на ветку
bash scripts/deploy.sh main
```

Что делает `deploy.sh`:
1. `git fetch --all --tags` — получает свежие данные с remote
2. `git checkout <версия>` — переключается на нужный тег/коммит/ветку
3. Если ветка — `git pull` для подтягивания новых коммитов
4. `docker compose run --rm api alembic upgrade head` — применяет миграции БД
5. `docker compose up --build -d` — пересобирает образы и перезапускает стек

### Создание тега релиза (локально, перед деплоем)

```bash
# Создать тег на текущем коммите и запушить
bash scripts/tag-release.sh v1.0-mm49

# Создать с аннотацией
bash scripts/tag-release.sh v1.0-mm49 "Web UI redesign — stepwise flow"

# Просмотр всех тегов
bash scripts/tag-release.sh --list

# История тегов + коммиты
bash scripts/tag-release.sh --history

# Удалить тег (локально + remote)
bash scripts/tag-release.sh --delete v1.0-mm49
```

Что делает `tag-release.sh`:
- Создаёт аннотированный тег (`git tag -a`) — хранит автора и дату
- Пушит тег на remote (`git push origin <tag>`)
- При конфликте тега — спрашивает подтверждение перед перезаписью

### Типичный workflow релиза

```bash
# Локально (Windows):
git checkout main && git pull
bash scripts/tag-release.sh v1.0-mm49 "MM-49: web UI redesign"

# На EU сервере:
bash scripts/deploy.sh v1.0-mm49
```

### Прочие скрипты

```bash
# SSL первоначальная настройка (один раз)
bash scripts/setup-ssl.sh admin@musicmigration.site

# Обновление SSL-сертификата (cron: 0 3 1,15 * *)
bash scripts/renew-ssl.sh

# Docker стек
docker compose ps                      # статус контейнеров
docker compose logs -f --tail=50       # логи всех сервисов
docker compose logs -f api             # логи только API
```

### entrypoint.sh

Запускается внутри Docker-контейнера `api` при старте:
1. `alembic upgrade head` — применяет миграции
2. `uvicorn api.main:app --host 0.0.0.0 --port 8000` — запускает сервер

## Environment Variables (.env)

```env
# Telegram
TELEGRAM_BOT_TOKEN=        # Telegram bot token from @BotFather
ALLOWED_USERS=             # Comma-separated Telegram user IDs (empty = open to all)

# Yandex OAuth
YANDEX_CLIENT_ID=          # From oauth.yandex.ru app
YANDEX_CLIENT_SECRET=      # From oauth.yandex.ru app
YANDEX_REDIRECT_URI=       # e.g. https://yourdomain.com/api/v1/auth/yandex/callback (MM-43/81)
YANDEX_TOKEN=              # Direct token for CLI mode only
YM_PROXY_URL=              # SOCKS5 proxy for Yandex API (e.g. socks5://user:pass@host:port)

# Spotify OAuth (MM-22)
SPOTIFY_CLIENT_ID=         # From developer.spotify.com app
SPOTIFY_CLIENT_SECRET=     # From developer.spotify.com app
SPOTIFY_REDIRECT_URI=      # e.g. https://yourdomain.com/api/v1/auth/spotify/callback
SPOTIFY_BOT_TOKEN=         # Optional: bot-account token for playlist creation (MM-88); falls back to user token if absent
SPOTIFY_BOT_REFRESH_TOKEN= # Optional: refresh token for bot account

# SoundCloud (MM-52)
SOUNDCLOUD_TOKEN=          # oauth_token cookie value (2-... or 3-...) — legacy, prefer OAuth below
SC_CLIENT_ID=              # From soundcloud.com/you/apps
SC_CLIENT_SECRET=          # From soundcloud.com/you/apps
SC_REDIRECT_URI=           # e.g. https://yourdomain.com/api/v1/auth/soundcloud/callback
SC_RATE_LIMIT_SLEEP=2.0    # Delay between SoundCloud write ops (seconds)
SC_PLAYLIST_BATCH_SIZE=500 # Max tracks per SoundCloud playlist in playlist_mode

# Database
DATABASE_URL=              # SQLAlchemy URL — PostgreSQL only: postgresql+asyncpg://user:pass@host/db
DB_ENCRYPTION_KEY=         # Fernet key for encrypting saved tokens

# Redis + Worker
REDIS_URL=redis://localhost:6379

# API
API_BASE_URL=http://localhost:8000  # internal bot→API (http://api:8000 in Docker)
WEB_BASE_URL=                       # public URL for user-facing links; falls back to API_BASE_URL if empty
API_INTERNAL_TOKEN=        # Shared secret for bot↔API calls
SECRET_KEY=                # SessionMiddleware secret (generate with: python -c "import secrets; print(secrets.token_hex(32))")
ADMIN_PASSWORD=            # Admin UI password

# SPA / JWT auth (MM-81)
CORS_ORIGINS=http://localhost:3000  # comma-separated allowed origins for /api/v1/ (add prod domain)
JWT_SECRET_KEY=            # generate: openssl rand -hex 32 (separate from SECRET_KEY)
JWT_ACCESS_TOKEN_TTL=900   # seconds (15 min)
JWT_REFRESH_TOKEN_TTL=2592000  # seconds (30 days)

# Dev mode (MM-80) — local development only
DEV_MODE=false             # true = _ensure_user_id() returns "dev_user"; auto-disabled on non-localhost domains

# Misc
MATCH_THRESHOLD=95.0       # Minimum fuzzy match score for "matched" (0–100)
MATCH_UNCERTAIN_FLOOR=60.0 # Lower bound for "uncertain" zone (below = not_found)
LOG_LEVEL=INFO
LOG_FORMAT=pretty           # "pretty" = colored stderr (dev), "json" = JSON stdout (Docker/Promtail)
```

Generate encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Architecture

```
run_api.py       → api/main.py          — FastAPI app (routers, SessionMiddleware)
run_worker.py    → worker/              — ARQ worker (background migration jobs)
run.py           → bot/main.py          — aiogram 3.x Telegram bot
cli.py                                  — CLI migration runner

api/
    ├── main.py                         — FastAPI entry, router registration; SessionMiddleware always-on (OAuth flow)
    ├── security.py                     — JWT utils (MM-81): create_access_token (HS256), create_refresh_token, decode_access_token, get_current_user FastAPI dep
    ├── routes/
    │   ├── api_v1.py                   — Public JSON API for SPA (MM-81): /api/v1/auth/*, /api/v1/services, /api/v1/migrations/* (Bearer JWT)
    │   ├── oauth.py                    — Pure utility module (MM-82, no router): _ensure_user_id, _session_user_id,
    │   │                                  _state_save, _state_get, _issue_oauth_code — imported by api_v1.py
    │   │                                  Redis: oauth_state:{provider}:{state} TTL 600s, oauth_code:{code} TTL 30s
    │   ├── bot_auth.py                 — Bot/worker auth: router (X-Internal-Token) POST /api/auth/yandex/token,
    │   │                                  POST /api/auth/soundcloud/validate, GET /api/auth/yandex/poll/{state_id};
    │   │                                  router_public (no auth) GET /auth/yandex/bot
    │   ├── migrations.py               — REST: POST /migrations, GET /migrations/{id}
    │   ├── reports.py                  — GET /migrations/{id}/not-found (queries DB)
    │   └── services.py                 — GET /api/services, GET /api/services/matrix
    └── deps.py                         — FastAPI dependencies (verify_internal_token, check_migration_rate_limit)

worker/                                 — ARQ job definitions
    ├── main.py                         — WorkerSettings (functions, redis_settings)
    ├── tasks.py                        — run_migration_job (YM→SC, playlist_mode=True)
    │                                     run_file_migration_job (File→SC, playlist_mode=True)
    │                                     run_spotify_migration_job (Spotify→SC, playlist_mode=True)
    │                                     run_yandex_migration_job (any→YM)
    │                                     run_spotify_write_job (any→Spotify, auto-refresh, playlist_mode, playlist_name)
    └── notifications.py               — notify_telegram(), migration_done_text(playlist_url=), migration_failed_text()

core/
    ├── db/                             — SQLAlchemy 2.x async package
    │   ├── models.py                   — UserSession (yandex_token, soundcloud_token, soundcloud_refresh_token,
    │   │                                  spotify_token, spotify_refresh_token, lang, role)
    │   ├── session.py                  — async engine + sessionmaker
    │   ├── crud.py                     — DB operations (save_spotify_token, save_soundcloud_token, get_all_tracks, set_user_role…)
    │   └── __init__.py                 — public re-exports
    ├── yandex/
    │   ├── client.py                   — YandexMusicClient: liked tracks, playlists, artists, search, like_track
    │   └── proxy_request.py            — SocksProxyRequest (aiohttp-socks, socks5://)
    ├── soundcloud/
    │   ├── client.py                   — SoundCloudClient: search, write ops, get_liked_tracks, create_playlist
    │   ├── oauth.py                    — SC Authorization Code Flow: get_auth_url, exchange_code, refresh_access_token (MM-52)
    │   └── models.py                   — SCTrack, SCUser, SCPlaylist
    ├── spotify/
    │   ├── models.py                   — SpotifyTrack, SpotifyPlaylist, SpotifyArtist
    │   ├── oauth.py                    — Authorization Code Flow + refresh_access_token
    │   └── client.py                   — SpotifyClient: read (liked tracks/playlists/artists) +
    │                                     write (search_tracks, like_track, search_artists, follow_artist,
    │                                     create_playlist(name)→(id,url), add_tracks_to_playlist(id,uris) batches 100)
    ├── services/                       — Service registry + adapters (MM-87: AdapterWriteSession ABC)
    │   ├── base.py                     — Capability flags + MusicServiceAdapter ABC + AdapterWriteSession ABC
    │   │                                  (AdapterWriteSession: search_track, write_track, search_artist, follow_artist)
    │   ├── registry.py                 — ServiceRegistry singleton
    │   ├── yandex/adapter.py           — YandexMusicAdapter (READ + WRITE_LIKED_TRACKS + EXPORT); write_session()
    │   ├── soundcloud/adapter.py       — SoundCloudAdapter (READ + WRITE + EXPORT); write_session()
    │   ├── spotify/adapter.py          — SpotifyAdapter (READ + WRITE: LIKED_TRACKS | PLAYLISTS | LIKED_ARTISTS + EXPORT)
    │   │                                  write_session(token, playlist_mode=False) → _SpotifyWriteSession
    │   │                                  playlist_mode=True: write_track returns "in_playlist" (no like_track call)
    │   └── file/adapter.py             — FileAdapter (CSV/JSON import/export)
    ├── export.py                       — export_library(service_id, token, fmt), exportable_services()
    ├── i18n.py                         — t(key, lang), detect_lang_web/tg, format_eta()
    ├── logger.py                       — setup_logger(service): single sink (pretty|json via LOG_FORMAT)
    ├── matcher.py                      — Fuzzy matching + Cyrillic transliteration + split_artists
    └── crypto.py                       — Token encryption/decryption (Fernet)

migration/                              — пайплайны по destination (unified to_* naming, MM-76)
    ├── pipeline.py                     — platform-agnostic loop (MM-87): run_pending_tracks_loop(session, migration_id,
    │                                     progress_callback, write_sleep) → TrackPipelineStats; process_one_track(session, row)
    ├── to_soundcloud.py                — any → SC (треки + плейлисты + артисты): YM, Spotify, File источники;
    │                                     MigrationStats, PlaylistMigrationStats, ArtistMigrationStats, FullMigrationStats;
    │                                     _run_pending_loop, _process_one_track, _create_liked_playlists (playlist_mode);
    │                                     run_migration() (YM→SC CLI/bot entry), run_spotify_migration() (Spotify→SC worker)
    ├── to_yandex.py                    — any → YM лайки (multi-query, fuzzy match, sleep 1.0s)
    └── to_spotify.py                   — any → Spotify (MM-87 pipeline + MM-88/89 playlist mode);
                                          migrate_to_spotify(playlist_mode, playlist_name);
                                          _create_playlist(migration_id, name, user_token): uses SPOTIFY_BOT_TOKEN or user_token;
                                          SpotifyWriteStats.playlist_url → stored in Migration.result_path

bot/
    ├── main.py                         — aiogram 3.x entry
    ├── api_client.py                   — MigrationApiClient (talks to FastAPI)
    ├── handlers/                       — start, auth (FSM: selecting_from → token collection → confirming → selecting_limit),
    │                                     migration, status
    └── oauth/yandex.py                 — Yandex OAuth 2.0 (verification_code flow)

config.py                               — Pydantic settings (all env vars)
alembic/                                — DB migrations (alembic upgrade head)
nginx/nginx.conf                        — Reverse proxy: /api/→api:8000, = /auth/yandex/bot→api:8000, /→frontend:80
nginx/spa.conf                          — SPA static: try_files → /index.html
Dockerfile.frontend.prod                — Multi-stage: node build → nginx:alpine static serve
docker-compose.yml                      — postgres + redis + api + bot + worker + nginx + frontend (log rotation)
docker-compose.monitoring.yml           — opt-in: Loki + Promtail + Grafana
monitoring/
    ├── loki/config.yml                 — Loki local filesystem storage
    ├── promtail/config.yml             — docker_sd_configs → Loki, parses loguru JSON
    └── grafana/provisioning/           — auto-provision Loki datasource
```

## Auth Flow

**Web UI:**
1. User opens `/` → selects source/destination → goes to `/auth`
2. If saved session exists → silently validate tokens → go to confirmation
3. If no session:
   - Yandex: OAuth button → `https://oauth.yandex.ru/verification_code` → user pastes code back
   - SoundCloud: user pastes `oauth_token` cookie from DevTools
   - Spotify: OAuth redirect → `/auth/spotify/callback` → token saved automatically
4. Tokens saved encrypted in PostgreSQL

**Telegram bot:**
1. `/migrate` → inline buttons: choose source (Yandex Music / Spotify)
2. Yandex path: saved token validation → if expired, re-auth via OAuth code
3. Spotify path: requires `spotify_token` already in DB (set via web UI); shows web link if missing
4. Confirmation screen with track count + ETA → start migration

## Documentation Rules

After completing **every task** (MM-XX or any meaningful change), always update:

1. **`PLAN.md`** — mark the task ✅, update subtasks checkboxes, add/correct implementation details
2. **`memory/progress.md`** — write a dedicated section for the task: what was done, which files were changed, key decisions, what was removed/changed vs original plan
3. **`CLAUDE.md`** (this file) — update Architecture diagram and Key Patterns if new patterns were introduced
4. **`memory/MEMORY.md`** — update key paths or patterns if something structurally changed

Rule: **no task is considered done until docs are updated.**

## Testing Rules

After completing **every task** (MM-XX), write and run tests:

1. Write tests covering new business logic in `tests/`
2. Run `.venv/Scripts/pytest tests/` — must pass (133+ tests)
3. If the task adds no new business logic — at minimum a smoke test that the new parameter flows through correctly

Rule: **no task is considered done until `pytest tests/` passes (295+ tests).**

## Key Patterns

- All I/O is async (SQLAlchemy 2.x async, aiohttp, aiogram)
- YM API calls batch by 150 tracks (`_BATCH_SIZE`)
- SoundCloud rate limiting: no proactive sleep (like Spotify pattern); 429 backoff in `like_track`/`follow_user`. Official OAuth has no documented aggregate rate limit (only 15k/24h for `/tracks/:id/stream` which we don't use)
- Migration is resumable: DB tracks `pending/liked/in_playlist/not_found/error` per track. `liked` = directly liked; `in_playlist` = added to SC playlist (not directly liked). Modes are mutually exclusive. `MigrationStats.success = liked + in_playlist`
- `YandexMusicClient._uid` may be None for some OAuth tokens → API calls omit `user_id` param
- SQLAlchemy `_dialect_insert()` uses PostgreSQL insert in production; SQLite fallback only for in-memory test fixtures
- Schema managed by `alembic upgrade head` (runs in entrypoint.sh); `init_db()` removed
- Dev deps (aiosqlite, pytest) in `requirements-dev.txt`; production deps in `requirements.txt`
- ARQ job_id stored in Redis key `migration_job:{id}` (TTL 86400s); admin cancel uses `Job.abort(timeout=2)`
- `from_service`/`to_service` validated against ServiceRegistry matrix before job enqueue
- Track search uses multi-query strategy: `split_artists()` splits compound artists (feat./&/x), runs parallel SC searches, deduplicates by sc_id, then falls back to title-only if pool is empty
- `_SEARCH_LIMIT = 10` in SoundCloudClient for better candidate coverage
- `setup_logger(service)` in `core/logger.py` — call once per entry point; stdout JSON sink for Promtail, stderr colored for dev
- Monitoring stack is opt-in: `docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d`
- Bot FSM flow: `AuthFlow.selecting_from` → choose source (YM/Spotify) → `AuthFlow.selecting_to` → token collection → `AuthFlow.confirming` (mode: tracks/full) → `AuthFlow.selecting_limit` (All/50/100/500) → start
- Bot Spotify path: requires `spotify_token` already in DB session (set via web UI OAuth); bot shows web link if missing
- `api/routes/migrations.py` routes based on `to_service`: `yandex_music` → `run_yandex_migration_job`, `spotify` → `run_spotify_write_job`, default SC → `run_migration_job` or `run_spotify_migration_job`
- `spotify_refresh_token` saved in DB (encrypted) during OAuth; `run_spotify_write_job` auto-refreshes before starting migration
- `soundcloud_refresh_token` saved in DB (encrypted) during SC OAuth (MM-52); `_refresh_sc_token_if_needed()` in `worker/tasks.py` auto-refreshes in all SC-destination jobs
- SC OAuth env vars: `SC_CLIENT_ID`, `SC_CLIENT_SECRET`, `SC_REDIRECT_URI`; when `sc_client_id` is set, bot redirects to `/api/v1/auth/soundcloud/start` instead of asking for cookie token
- SC search uses official `api.soundcloud.com/tracks` (not api-v2), auth via `Authorization: OAuth {token}` (per SC docs — not Bearer); no `client_id` param; `soundcloud-v2` library removed (used invalid hardcoded client_id → 403)
- SC `/me` returns 403 for unverified apps — expected; `_ensure_init()` checks only `self._session is None`
- `save_yandex_token(user_id, token)` in `core/db/crud.py` — upsert only YM field (doesn't touch SC/Spotify); called from `auth_yandex_callback` in `api/routes/oauth.py` to persist token to DB
- YM `init()` raises `ValueError` if uid cannot be obtained (expired token); `_fetch_uid_from_yandex_id` logs HTTP status+body on failure
- Spotify track IDs are strings → dedup key uses `hash(id) & 0x7FFFFFFF`; ID stored in `sc_url` field for the actual like call
- Spotify `like_track` uses `PUT /me/library?uris=spotify:track:{id}` (new non-deprecated endpoint); old `PUT /me/tracks` returned 403 in dev mode
- `get_liked_tracks(limit)` in YM and Spotify clients stops pagination early when limit is reached (no full fetch before slice); `to_soundcloud.py` passes `limit=track_limit` directly (MM-102 fix — was fetch-all+slice)
- `settings.search_limit` (env: `SEARCH_LIMIT`, default 5) controls candidate count per search query for both Spotify and SC destinations
- `find_best_match` breaks immediately on `score == 100.0` — no need to check remaining candidates
- `transliterate_variants(artist)` applied in `migration/pipeline.process_one_track` when `session.apply_transliteration=True` (set by `_SpotifyWriteSession`); adds Latin search queries for Cyrillic artist names (e.g. Баста → Basta)
- MM-87 `AdapterWriteSession` ABC in `core/services/base.py` — `search_track`, `write_track`, `search_artist`, `follow_artist`; each adapter exposes `write_session(token)` `@asynccontextmanager`; `migration/pipeline.py` has unified `process_one_track(session, row)` + `run_pending_tracks_loop`; `to_yandex.py` and `to_spotify.py` no longer import platform clients directly
- MM-88/89 Spotify playlist mode: `run_spotify_write_job(playlist_mode=True, playlist_name=...)` → `_SpotifyWriteSession(playlist_mode=True)` collects `spotify:track:{id}` URIs, calls `_create_playlist(migration_id, name, user_token)` after pipeline; `playlist_url` saved to `Migration.result_path`; `SpotifyClient.create_playlist(name)` → `(id, url)` + `add_tracks_to_playlist(id, uris)` (batches of 100)
- `_create_playlist(migration_id, name, user_token)` in `migration/to_spotify.py` — uses `settings.spotify_bot_token or user_token`; playlist is created on bot account if `SPOTIFY_BOT_TOKEN` set, otherwise on user account
- Bot FSM confirmation: `toggle_spotify_playlist` callback for Spotify destination (`bot/handlers/auth.py`); result screen has playlist link button (`bot/handlers/migration.py`); `spotify_playlist_mode` stored in FSM state
- Spotify dev mode: max 25 allowlisted users in Dashboard → Settings → User Management; Playwright automation planned as fallback (see PLAN.md)
- `format_eta(track_count, to_service, lang)` in `core/i18n.py` — localised ETA string; `_SECS_PER_TRACK`: ym=1.5s, spotify=0.8s, sc=1.5s
- `playlist_mode=True` in all SC-destination worker jobs — collects sc_ids during search loop, creates "YM Liked #N" playlists at the end (batches of `SC_PLAYLIST_BATCH_SIZE`); sets `status="in_playlist"`. `like_tracks=True` sets `status="liked"` (direct like); on `LikeNotSupportedError` falls back to `status="in_playlist"`
- SC write endpoints: `POST /likes/tracks/soundcloud:tracks:{id}`, `POST /playlists`, `PUT /me/followings/{id}` — Authorization Code Flow grants write access without explicit scope declarations
- `get_track_stats_batch(migration_ids)` в `core/db/crud.py` — один GROUP BY запрос для статистики N миграций (история без N+1); возвращает `dict[int, dict[str, int]]`
- Deploy: `bash scripts/deploy.sh [тег|коммит|ветка]` — fetch + checkout + alembic + docker compose up --build; `bash scripts/tag-release.sh v1.0-mmXX` — аннотированный тег + push
- File import/export unified in main flow (MM-67): `"file"` (FileAdapter.id, MM-69) добавлен в `from_services` вручную (не из matrix); `flow_to_step` для `from_service=="file"` — все адаптеры с WRITE_LIKED_TRACKS, карточка "В файл" скрывается (File→File запрещён); `POST /migrate` принимает `file: UploadFile | None` + `export_fmt`; три case: export sync, import parse+job, обычный
- `FileAdapter.id = "file"` (MM-69, ранее `"file_csv"`); i18n ключ `svc_file`; alembic миграция `i9j0k1l2m3n4` обновляет старые записи в БД
- `TrackInput(artist: str, title: str)` в `api/routes/api_v1.py` и `worker/tasks.py` — Pydantic модель для file import треков; `StartMigrationRequest.tracks_override: list[TrackInput] | None`; конвертируется в `list[dict]` перед ARQ enqueue; `TypeAdapter(list[TrackInput]).validate_python(tracks_override)` в worker для безопасной десериализации из Redis
- `tracks_override: list[dict] | None` в `run_yandex_migration_job` и `run_spotify_write_job` — пропускает `fetch_liked_tracks` если задан (для file import)
- `score_track_match(source_artist, source_title, cand_artist, cand_title)` и `find_best_match(source_artist, source_title, ...)` — параметры переименованы из `ym_*`/`sc_*` в универсальные (MM-68); `TrackCandidate` — generic кандидат для любой целевой платформы (переименован из `SCCandidate`)
- `scripts/entrypoint.sh` — Docker entry для api: `alembic upgrade head` → uvicorn; при `DEV_MODE=true` также запускает `scripts/seed_dev.py`
- dev mode (MM-80): `DEV_MODE=true` активирует: `_ensure_user_id()` возвращает фиксированный `"dev_user"`; `scripts/seed_dev.py` сидирует `UserSession(user_id='dev_user')` с фейковыми токенами (запускается из `entrypoint.sh` при `DEV_MODE=true`); `guard_dev_mode` `model_validator` в `config.py` автоматически сбрасывает `dev_mode=False` если `WEB_BASE_URL`/`API_BASE_URL` указывает на не-localhost домен; `docker-compose.dev.yml` — standalone стек без nginx/bot/worker; `.env.dev` — шаблон без реальных секретов (коммитится в git); `LOCAL_SETUP.md` — инструкция
- DEV_MODE JWT bypass (MM-96): `get_current_user` в `api/security.py` при `settings.dev_mode=True` сразу возвращает `"dev_user"` без проверки Bearer JWT — все `/api/v1/` endpoints работают без токена; SPA при старте без refresh token пробует `GET /api/v1/auth/me` без заголовка: 200 → sentinel `"dev"` в память (авто-логин), 401 → обычный OAuth flow
- SPA auth URL mapping (MM-96): `getOAuthStartUrl` в `frontend/src/api/auth.ts` использует `SERVICE_AUTH_SLUG = {yandex_music: 'yandex'}` — service ID `yandex_music` маппится на endpoint slug `yandex` (`/api/v1/auth/yandex`)
- MM-98 file import via SPA: CSV/JSON парсится в браузере (`parseImportFile` в `migrations.ts`), треки передаются как `tracks_override: list[dict]` в JSON body `POST /api/v1/migrations`; file→SC → `run_file_migration_job(tracks=...)`, file→YM/Spotify → `tracks_override` в `run_yandex_migration_job`/`run_spotify_write_job`
- MM-98 lang switcher: `LangContext` + `LangSwitcher` в `frontend/src/App.tsx`; язык хранится в `localStorage('lang')` — без бэкенд-endpoint, без DB
- MM-98 export: кнопки CSV↓/JSON↓ в `ProgressPage` (to_service=file, status=done) → `GET /api/v1/migrations/{id}/export?fmt=csv|json` с `download` атрибутом
- OAuth routing (MM-79/82): `api/routes/oauth.py` — pure utility module (no router): `_ensure_user_id`, `_state_save`, `_state_get`, `_issue_oauth_code`; `api/routes/bot_auth.py` — router (X-Internal-Token) for internal calls + router_public (no auth) for `GET /auth/yandex/bot`; state в Redis `oauth_state:{provider}:{state}` TTL 600s; после OAuth → short-lived `oauth_code:{code}` (TTL 30s) → SPA обменивает на JWT через `POST /api/v1/auth/exchange`; callback routes зарегистрированы на `/api/v1/auth/*/callback`
- migration/ unified `to_*` naming (MM-76): `sc_tracks+sc_playlists+sc_artists` → `to_soundcloud.py`; `run_migration()` params renamed `migrate_playlists`/`migrate_artists` → `do_playlists`/`do_artists` to avoid name collision with the functions
- MM-81 JWT SPA auth: access token = JWT HS256 TTL 15min (in memory), refresh token = opaque hex 64 chars stored encrypted in `UserSession.spa_refresh_token`; exchange flow: OAuth callback → `oauth_code:{code}` Redis TTL 30s → `POST /api/v1/auth/exchange` → JWT pair
- MM-81 CORS: `CORSMiddleware(allow_credentials=False)` — JWT in `Authorization: Bearer` header, not cookies; origins from `cors_origins` setting (comma-separated)
- MM-81/82: `/api/v1/` router always registered; Jinja2 UI removed (MM-82) — SessionMiddleware kept always-on for OAuth flow (`_ensure_user_id`)
- `get_user_id_by_spa_refresh_token` does linear scan of user_sessions + Fernet decrypt compare (no index on refresh token — acceptable for current user count)
- Test patch targets for `/api/v1/` routes: use `api.routes.api_v1.func_name` (not `core.db.crud.func_name`) since functions are imported at module load time
- MM-83 SPA OAuth callback redirect (bugfix): `api_v1.py` callbacks capture `code = await _issue_oauth_code(user_id)` and redirect to `{WEB_BASE_URL}/auth/callback?code={code}&flow_from=...&flow_to=...`; `WEB_BASE_URL=http://localhost:3000` in dev; SPA route `/auth/callback` exchanges code for JWT via `POST /api/v1/auth/exchange`
- MM-83 SPA frontend: `frontend/` — Vite + React 19 + TypeScript + React Router v6; Vite proxy `/api` → `http://api:8000` (dev only, replaces nginx in prod); `docker-compose.dev.yml` runs `frontend` service on port 3000 with `node_modules` in Docker volume
- MM-97 Admin SPA: `role` claim in JWT (set in `exchange_code`/`refresh_token` from DB); `require_admin` dep in `api/security.py` → 401/403; `get_current_user_role` dep (safe, no raise); `GET /api/v1/stats` + `GET /api/v1/users` (admin-only); `GET /api/v1/migrations` supports `?user_id=` + pagination for admin; `GET /api/v1/migrations/{id}` bypasses ownership for admin; frontend: `AdminRoute` + `AdminLayout` + `/dashboard`, `/migrations`, `/users` pages; `getTokenRole()` in `auth.ts`; `INITIAL_ADMIN_USER_ID` env var for bootstrap
- MM-98 SPA UI fixes: auth badge removed from service cards; content_types selector (tracks/playlists/artists); file import (CSV/JSON picker) + export (sync download); language switcher via `LangContext` in `App.tsx` (localStorage, no backend); Spotify playlist name input
- ARQ job timeout: `worker/main.py` `job_timeout = 2 * 3600`; all job functions have `except BaseException` after `except Exception` — catches `asyncio.CancelledError` on ARQ timeout and sets migration `status="failed"` so frontend stops polling
- File import 5MB limit: `parseImportFile()` in `frontend/src/api/migrations.ts` checks `file.size > 5MB` and wraps `JSON.parse` in try-catch; `POST /auth/logout` endpoint removed — no logout flow in SPA
- SPA i18n (post-merge fix): `frontend/src/i18n.ts` — `t(key, lang)`, `tStatus(status, lang)`, `tService(svcId, lang)`, `formatDate(dt, lang)`; ~70 keys in `RU`/`EN` objects; pages use `useLang()` hook from `App.tsx` `LangContext`; no backend involvement
- nginx routing (post-merge fix): `location = /auth/yandex/bot` (exact match) — only real API endpoint under `/auth/*`; all other `/auth/*` paths (e.g. `/auth/callback`) fall through to SPA via `location /`; `.env.dev` redirect URIs use `/api/v1/auth/*/callback` (correct path after MM-82)
- MM-99 security: `decrypt_token` raises `ValueError` on corrupt token (empty string passthrough — no decrypt attempted); `guard_encryption_key` model_validator in `config.py` blocks prod startup without `DB_ENCRYPTION_KEY`; CORS explicit whitelist `["GET","POST","PUT","DELETE","OPTIONS"]`/`["Authorization","Content-Type","Accept"]`; rate limits on auth endpoints via Redis fixed-window `rl:{endpoint}:{ip}:{slot}` (INCR+EXPIRE); OAuth error details never leaked to redirect URL (logged only); `job_id = secrets.token_hex(16)` written to Redis BEFORE `enqueue_job` to fix race condition; `X-Idempotency-Key` header on `POST /api/v1/migrations` — `idempotency:{key}` TTL 60s; admin nav i18n `nav_migrations`/`nav_users` (RU/EN)
- MM-99 health: `GET /health` returns `{"status":"ok"|"degraded","redis":"ok"|"error"|"unavailable","db":"ok"|"error","version":"X.Y.Z"}`; 503 if any component down; tests: `test_api_health.py` — unit tests calling `health(Response())` directly with mocked arq/engine
- MM-100 SPA UX: `refreshAccessToken()` в `auth.ts` удаляет `refresh_token` из localStorage только при `ApiError.status === 401|403` (не при сетевых ошибках); `fromServices` явно добавляет `file` через `IMPORT_FILE`; `toServices` для `file→*` фильтрует `WRITE_LIKED_TRACKS`; MigratePage → redirect to `/`; limit options: 5/50/500/All; `getMigrationTracks()` в ProgressPage poll; history match%; terminal buttons `borderRadius: 9999px`
- MM-102 SPA UX: `index.html` title "Music Migration"; auth badges на service cards (FROM/TO) когда `userStatus` загружен; `file` добавлен в `toServices` через `EXPORT_FILE` (экспорт); `AuthCallbackPage` → `/?from=...&to=...` (сохраняет выбор сервисов); `HomePage` читает `from`/`to` из URL params; ProgressPage "Подготовка…" вместо 0/0; track list пагинация 50/стр.
