# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Music Migration — service for migrating music libraries between streaming platforms.
Current state: **MVP9 + MM-47**, deployed on EU server.
Supports: Yandex Music, Spotify, SoundCloud, File (CSV/JSON) — bidirectional migrations, Web UI, Telegram bot.

Transfer matrix:
```
FROM \ TO     | SoundCloud | File CSV  | Яндекс Музыка | Spotify
--------------|------------|-----------|---------------|--------
Яндекс Музыка |     ✓      |    ✓      |       –       |    ✓
Spotify       |     ✓      |    ✓      |       ✓       |    –
File CSV      |     ✓      |    –      |       ✓       |    ✓
SoundCloud    |     –      |    ✓      |       ✓       |    ✓
```

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

## Environment Variables (.env)

```env
# Telegram
TELEGRAM_BOT_TOKEN=        # Telegram bot token from @BotFather
ALLOWED_USERS=             # Comma-separated Telegram user IDs (empty = open to all)

# Yandex OAuth
YANDEX_CLIENT_ID=          # From oauth.yandex.ru app
YANDEX_CLIENT_SECRET=      # From oauth.yandex.ru app
YANDEX_TOKEN=              # Direct token for CLI mode only
YM_PROXY_URL=              # SOCKS5 proxy for Yandex API (e.g. socks5://user:pass@host:port)

# Spotify OAuth (MM-22)
SPOTIFY_CLIENT_ID=         # From developer.spotify.com app
SPOTIFY_CLIENT_SECRET=     # From developer.spotify.com app
SPOTIFY_REDIRECT_URI=      # e.g. https://yourdomain.com/auth/spotify/callback

# SoundCloud
SOUNDCLOUD_TOKEN=          # oauth_token cookie value (2-... or 3-...)
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

# Web access control (MM-31)
WEB_ENABLED=true           # false = disable web UI and admin (API/bot still work)
WEB_ALLOWED_IPS=           # comma-separated IPs allowed to access web UI; empty = allow all

# Misc
MATCH_THRESHOLD=75.0       # Minimum fuzzy match score (0–100)
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
    ├── main.py                         — FastAPI entry, router registration (web+admin gated by WEB_ENABLED)
    ├── middleware.py                   — AllowedUsersWebMiddleware, WebIPWhitelistMiddleware
    ├── routes/
    │   ├── web.py                      — Web UI: /, /auth, /auth/spotify, /auth/yandex,
    │   │                                  /migrate, /migrate/{id}/tracks, /history,
    │   │                                  /import, /export, /set-lang (Jinja2+HTMX)
    │   ├── migrations.py               — REST: POST /migrations, GET /migrations/{id}
    │   ├── reports.py                  — GET /migrations/{id}/not-found (queries DB)
    │   ├── services.py                 — GET /api/services, GET /api/services/matrix
    │   └── admin.py                    — Admin UI: /admin/login, /dashboard, /migrations, /users, /services
    ├── templates/                      — Jinja2 templates
    │   ├── base.html, index.html, auth.html, progress.html, result.html
    │   ├── history.html, tracks.html, import.html, export.html
    │   ├── fragments/status.html, fragments/import_preview.html
    │   └── admin/                      — Admin templates
    └── deps.py                         — FastAPI dependencies (verify_internal_token, check_migration_rate_limit)

worker/                                 — ARQ job definitions
    ├── main.py                         — WorkerSettings (functions, redis_settings)
    ├── tasks.py                        — run_migration_job (YM→SC, playlist_mode=True)
    │                                     run_file_migration_job (File→SC, playlist_mode=True)
    │                                     run_spotify_migration_job (Spotify→SC, playlist_mode=True)
    │                                     run_yandex_migration_job (any→YM)
    │                                     run_spotify_write_job (any→Spotify, auto-refresh token)
    └── notifications.py               — notify_telegram(), migration_done_text(), migration_failed_text()

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
    │                                     write (search_tracks, like_track, search_artists, follow_artist)
    ├── services/                       — Service registry + adapters
    │   ├── base.py                     — Capability flags + MusicServiceAdapter ABC
    │   ├── registry.py                 — ServiceRegistry singleton
    │   ├── yandex/adapter.py           — YandexMusicAdapter (READ + WRITE_LIKED_TRACKS + EXPORT)
    │   ├── soundcloud/adapter.py       — SoundCloudAdapter (READ + WRITE + EXPORT)
    │   ├── spotify/adapter.py          — SpotifyAdapter (READ + WRITE: LIKED_TRACKS | PLAYLISTS | LIKED_ARTISTS + EXPORT)
    │   └── file/adapter.py             — FileAdapter (CSV/JSON import/export)
    ├── export.py                       — export_library(service_id, token, fmt), exportable_services()
    ├── i18n.py                         — t(key, lang), detect_lang_web/tg, format_eta()
    ├── logger.py                       — setup_logger(service): single sink (pretty|json via LOG_FORMAT)
    ├── matcher.py                      — Fuzzy matching + Cyrillic transliteration + split_artists
    └── crypto.py                       — Token encryption/decryption (Fernet)

migration/
    ├── tracks.py                       — * → SC pipeline: search → match → collect sc_ids →
    │                                     create "YM Liked #N" playlists (playlist_mode=True)
    │                                     _run_pending_loop, _process_one_track, _create_liked_playlists
    ├── playlists.py                    — YM playlists → SC playlists
    ├── artists.py                      — YM liked artists → SC follows
    ├── spotify_tracks.py               — Spotify → SC (reuses _run_pending_loop, playlist_mode)
    ├── yandex_tracks.py                — any source → YM likes (multi-query, fuzzy match, sleep 1.0s)
    └── spotify_write.py                — any source → Spotify likes + artist follows (auto-refresh token)

bot/
    ├── main.py                         — aiogram 3.x entry
    ├── api_client.py                   — MigrationApiClient (talks to FastAPI)
    ├── handlers/                       — start, auth (FSM: selecting_from → token collection → confirming → selecting_limit),
    │                                     migration, status
    └── oauth/yandex.py                 — Yandex OAuth 2.0 (verification_code flow)

config.py                               — Pydantic settings (all env vars)
alembic/                                — DB migrations (alembic upgrade head)
nginx/nginx.conf                        — Reverse proxy to api:8000
docker-compose.yml                      — postgres + redis + api + bot + worker + nginx (log rotation)
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

## Key Patterns

- All I/O is async (SQLAlchemy 2.x async, aiohttp, aiogram)
- YM API calls batch by 150 tracks (`_BATCH_SIZE`)
- SoundCloud rate limiting: no proactive sleep (like Spotify pattern); 429 backoff in `like_track`/`follow_user`. Official OAuth has no documented aggregate rate limit (only 15k/24h for `/tracks/:id/stream` which we don't use)
- Migration is resumable: DB tracks `pending/liked/not_found/error` per track
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
- Bot FSM flow: `AuthFlow.selecting_from` → choose source (YM/Spotify) → token collection → `AuthFlow.confirming` (mode: tracks/full) → `AuthFlow.selecting_limit` (All/50/100/500) → start
- Bot Spotify path: requires `spotify_token` already in DB session (set via web UI OAuth); bot shows web link if missing
- `api/routes/migrations.py` routes based on `to_service`: `yandex_music` → `run_yandex_migration_job`, `spotify` → `run_spotify_write_job`, default SC → `run_migration_job` or `run_spotify_migration_job`
- `spotify_refresh_token` saved in DB (encrypted) during OAuth; `run_spotify_write_job` auto-refreshes before starting migration
- `soundcloud_refresh_token` saved in DB (encrypted) during SC OAuth (MM-52); `_refresh_sc_token_if_needed()` in `worker/tasks.py` auto-refreshes in all SC-destination jobs
- SC OAuth env vars: `SC_CLIENT_ID`, `SC_CLIENT_SECRET`, `SC_REDIRECT_URI`; when `sc_client_id` is set, bot redirects to web `/auth/soundcloud` instead of asking for cookie token
- Spotify track IDs are strings → dedup key uses `hash(id) & 0x7FFFFFFF`; ID stored in `sc_url` field for the actual like call
- `format_eta(track_count, to_service, lang)` in `core/i18n.py` — localised ETA string; `_SECS_PER_TRACK`: ym=1.5s, spotify=0.8s, sc=1.5s
- `playlist_mode=True` in all SC-destination worker jobs — collects sc_ids during search loop, creates "YM Liked #N" playlists at the end (batches of `SC_PLAYLIST_BATCH_SIZE`); `like_track` is implemented but bypassed in playlist_mode (was 404 due to Datadome cookie tokens; with OAuth should work but untested)
- SC write endpoints: `PUT /me/track_likes/{id}`, `POST /playlists`, `PUT /me/followings/{id}` — all correct; Authorization Code Flow grants write access without explicit scope declarations
- `WEB_ENABLED=false` disables BOTH web UI and admin panel (both routers registered inside the same `if settings.web_enabled` block in `api/main.py`); internal API + bot always available
