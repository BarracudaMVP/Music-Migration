# Local Development Setup

Guide for running Music Migration locally — e.g. for frontend work on templates.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Git

## Quick start

```bash
git clone <repo-url>
cd Music-Migration

docker compose -f docker-compose.dev.yml up --build
```

Open http://localhost:8000

## Seed the dev user (once)

The first time (or after `down -v`), seed a fake session so all services
appear "connected" in the UI:

```bash
# Inside the running api container:
docker compose -f docker-compose.dev.yml exec api python -c "
import asyncio
from core.db.crud import save_yandex_token, save_soundcloud_token, save_spotify_token
asyncio.run(save_yandex_token('dev_user', 'fake'))
asyncio.run(save_soundcloud_token('dev_user', 'fake'))
asyncio.run(save_spotify_token('dev_user', 'fake'))
print('done')
"
```

After that just open http://localhost:8000 — all services show as connected,
the auth gate is open, you can navigate the full flow.

## How it works

`DEV_MODE=true` makes every browser visit use `user_id=dev_user` instead of
a random ID. The app finds the seeded `UserSession` in the DB and considers
all services authenticated. No special routes, no cookie tricks.

## What works vs what doesn't

| Feature | Works locally |
|---------|--------------|
| Web UI navigation (all pages) | ✅ |
| HTMX fragments (service cards, auth status) | ✅ |
| Auth gate (button enabled/disabled) | ✅ (after seed) |
| History page | ✅ (empty until migrations run) |
| Admin UI at /admin | ✅ (password: `admin`) |
| Real OAuth (Yandex / Spotify / SC) | ❌ (callback URL mismatch) |
| Actual migration jobs | ❌ (worker not running, fake tokens) |

## Logging

`LOG_LEVEL=DEBUG` and `LOG_FORMAT=pretty` are set in `.env.dev` — all logs
are shown in colored output.

## Dev stack

`docker-compose.dev.yml` runs only: `postgres` + `redis` + `api` (port 8000).
Not started: `nginx`, `bot`, `worker`.

## Stopping

```bash
docker compose -f docker-compose.dev.yml down

# Also remove the dev DB volume:
docker compose -f docker-compose.dev.yml down -v
```

## Security notes

- `DEV_MODE=false` is the production default
- If `DEV_MODE=true` accidentally ends up on prod: all users share `user_id=dev_user`
  (obvious UX bug, not a security breach — fake tokens fail on real API calls)
- `docker-compose.dev.yml` has no SSL volumes — can't be used as a prod stack
- `.env.dev` contains no real credentials
