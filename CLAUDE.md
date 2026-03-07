# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Music Migration — service for migrating music libraries between streaming platforms.
Current state: **MVP9**, deployed on EU server.
Supports: Yandex Music → SoundCloud (liked tracks, playlists, artists), Web UI, Telegram bot.

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

# Database
DATABASE_URL=              # SQLAlchemy URL (sqlite+aiosqlite:///migration.db or postgresql+asyncpg://...)
DB_ENCRYPTION_KEY=         # Fernet key for encrypting saved tokens

# Redis + Worker
REDIS_URL=redis://localhost:6379

# API
API_BASE_URL=http://localhost:8000
API_INTERNAL_TOKEN=        # Shared secret for bot↔API calls
SECRET_KEY=                # SessionMiddleware secret (generate with: python -c "import secrets; print(secrets.token_hex(32))")
ADMIN_PASSWORD=            # Admin UI password

# Misc
MATCH_THRESHOLD=75.0       # Minimum fuzzy match score (0–100)
LOG_LEVEL=INFO
```

Generate encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Architecture

```
run_api.py       → api/main.py          — FastAPI app (6 routers, SessionMiddleware)
run_worker.py    → worker/              — ARQ worker (background migration jobs)
run.py           → bot/main.py          — aiogram 3.x Telegram bot
cli.py                                  — CLI migration runner

api/
    ├── main.py                         — FastAPI entry, router registration
    ├── routes/
    │   ├── web.py                      — Web UI: /, /auth, /migrate, /history (Jinja2+HTMX)
    │   ├── migrations.py               — REST: POST /migrations, GET /migrations/{id}
    │   ├── reports.py                  — GET /migrations/{id}/not-found (queries DB)
    │   ├── services.py                 — GET /api/services, GET /api/services/matrix
    │   └── admin.py                    — Admin UI: /admin/login, /dashboard, /migrations, /users
    ├── templates/                      — Jinja2 templates (base, index, auth, progress, result, history)
    │   └── admin/                      — Admin templates
    └── deps.py                         — FastAPI dependencies (verify_internal_token)

worker/                                 — ARQ job definitions
    ├── main.py                         — WorkerSettings (functions, cron_jobs, redis_settings)
    ├── tasks.py                        — run_migration_job, run_file_migration_job, run_spotify_migration_job
    └── notifications.py               — notify_telegram(), migration_done_text(), migration_failed_text()

core/
    ├── db/                             — SQLAlchemy 2.x async package
    │   ├── models.py                   — ORM models (UserSession.spotify_token nullable)
    │   ├── session.py                  — async engine + sessionmaker
    │   ├── crud.py                     — DB operations (save_spotify_token, get_all_tracks)
    │   └── __init__.py                 — public re-exports
    ├── yandex/client.py                — YandexMusicClient: liked tracks, playlists, artists
    ├── yandex/proxy_request.py         — SocksProxyRequest (aiohttp-socks)
    ├── soundcloud/client.py            — SoundCloudClient: search + write ops
    ├── soundcloud/models.py            — SCTrack, SCUser, SCPlaylist
    ├── spotify/                        — Spotify integration (MM-22)
    │   ├── models.py                   — SpotifyTrack, SpotifyPlaylist, SpotifyArtist
    │   ├── oauth.py                    — Authorization Code Flow: get_auth_url, exchange_code, refresh_access_token
    │   └── client.py                   — SpotifyClient: get_liked_tracks, get_playlists, get_followed_artists
    ├── services/                       — Service registry + adapters
    │   ├── base.py                     — Capability flags + MusicServiceAdapter ABC
    │   ├── registry.py                 — ServiceRegistry singleton
    │   ├── yandex/adapter.py           — YandexMusicAdapter
    │   ├── soundcloud/adapter.py       — SoundCloudAdapter
    │   ├── spotify/adapter.py          — SpotifyAdapter (READ_LIKED_TRACKS | READ_PLAYLISTS | READ_LIKED_ARTISTS)
    │   └── file/adapter.py             — FileAdapter (CSV/JSON)
    ├── matcher.py                      — Fuzzy matching + Cyrillic transliteration + split_artists
    └── crypto.py                       — Token encryption/decryption (Fernet)

migration/
    ├── tracks.py                       — MVP1 pipeline: YM likes → SC likes (multi-query search)
    ├── playlists.py                    — MVP2: YM playlists → SC playlists
    ├── artists.py                      — MVP2: YM liked artists → SC follows
    └── spotify_tracks.py               — MM-22: Spotify likes → SC likes (reuses _run_pending_loop)

bot/
    ├── main.py                         — aiogram 3.x entry
    ├── api_client.py                   — MigrationApiClient (talks to FastAPI)
    ├── handlers/                       — start, auth, migration, status
    └── oauth/yandex.py                 — Yandex OAuth 2.0

config.py                               — Pydantic settings (all env vars)
alembic/                                — DB migrations (alembic upgrade head)
nginx/nginx.conf                        — Reverse proxy to api:8000
docker-compose.yml                      — postgres + redis + api + bot + worker + nginx (all with log rotation)
docker-compose.monitoring.yml           — opt-in: Loki + Promtail + Grafana
monitoring/
    ├── loki/config.yml                 — Loki local filesystem storage
    ├── promtail/config.yml             — docker_sd_configs → Loki, parses loguru JSON
    └── grafana/provisioning/           — auto-provision Loki datasource
```

## Auth Flow

1. User opens Web UI or sends `/migrate` in bot
2. If saved session exists → silently validate both tokens → go to confirmation screen
3. If no session → Yandex OAuth (button link → user logs in → pastes code back) → SoundCloud token (cookie from DevTools)
4. Tokens saved encrypted in SQLite/PostgreSQL

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
- SoundCloud rate limiting: `sc_rate_limit_sleep` delay + 429 handling with backoff
- Migration is resumable: DB tracks `pending/liked/not_found/error` per track
- `YandexMusicClient._uid` may be None for some OAuth tokens → API calls omit `user_id` param
- SQLAlchemy `_dialect_insert()` helper selects sqlite/postgresql dialect at runtime
- `render_as_batch=True` in alembic for SQLite ALTER TABLE support
- ARQ job_id stored in Redis key `migration_job:{id}` (TTL 86400s); admin cancel uses `Job.abort(timeout=2)`
- `from_service`/`to_service` validated against ServiceRegistry matrix before job enqueue
- Track search uses multi-query strategy: `split_artists()` splits compound artists (feat./&/x), runs parallel SC searches, deduplicates by sc_id, then falls back to title-only if pool is empty
- `_SEARCH_LIMIT = 10` in SoundCloudClient for better candidate coverage
- `setup_logger(service)` in `core/logger.py` — call once per entry point; stdout JSON sink for Promtail, stderr colored for dev
- Monitoring stack is opt-in: `docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d`
