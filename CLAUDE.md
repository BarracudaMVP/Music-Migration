# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Music Migration — Telegram bot for migrating music libraries from Yandex Music to SoundCloud.
Supports: liked tracks (MVP1), playlists + artists (MVP2), Telegram bot interface (MVP3 — done).

## Install & Run

```bash
pip install -r requirements.txt
python run.py          # start Telegram bot
python cli.py          # CLI mode (uses YANDEX_TOKEN + SOUNDCLOUD_TOKEN from .env)
```

## Lint / Format

```bash
ruff check .
ruff format .
```

## Environment Variables (.env)

```env
TELEGRAM_BOT_TOKEN=        # Telegram bot token from @BotFather
YANDEX_CLIENT_ID=          # From oauth.yandex.ru app (for OAuth flow)
YANDEX_CLIENT_SECRET=      # From oauth.yandex.ru app
YANDEX_TOKEN=              # Direct token for CLI mode only
SOUNDCLOUD_TOKEN=          # SoundCloud oauth_token cookie value (2-... or 3-...)
ALLOWED_USERS=             # Comma-separated Telegram user IDs (empty = open to all)
DB_ENCRYPTION_KEY=         # Fernet key for encrypting saved tokens in DB
SC_RATE_LIMIT_SLEEP=2.0    # Delay between SoundCloud write ops (seconds)
MATCH_THRESHOLD=75.0       # Minimum fuzzy match score (0–100)
DB_PATH=migration.db
LOG_LEVEL=INFO
```

Generate encryption key:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Architecture

```
run.py / cli.py
    └── bot/main.py              — aiogram 3.x bot entry point
    └── bot/handlers/
        ├── start.py             — /start, /migrate, /cancel, /help
        ├── auth.py              — FSM: Yandex OAuth → SoundCloud token
        ├── migration.py         — FSM: run migration, progress updates
        └── status.py            — /status command
    └── bot/oauth/yandex.py      — Yandex OAuth 2.0 (Authorization Code flow)

core/
    ├── yandex/client.py         — YandexMusicClient: liked tracks, playlists, artists
    ├── soundcloud/client.py     — SoundCloudClient: search (soundcloud-v2) + write (aiohttp)
    ├── matcher.py               — Fuzzy matching with Cyrillic transliteration (rapidfuzz + iuliia)
    ├── db.py                    — SQLite via aiosqlite: migrations, tracks, playlists, artists, sessions
    └── crypto.py                — Token encryption/decryption (Fernet)

migration/
    ├── tracks.py                — MVP1 pipeline: YM likes → SC likes
    ├── playlists.py             — MVP2: YM playlists → SC playlists
    └── artists.py               — MVP2: YM liked artists → SC follows
```

## Auth Flow

1. User sends `/migrate`
2. If saved session exists → silently validate both tokens → go to confirmation screen
3. If no session → Yandex OAuth (button link → user logs in → pastes code back) → SoundCloud token (cookie from DevTools)
4. Tokens saved encrypted in SQLite

## Key Patterns

- All I/O is async
- YM API calls batch by 150 tracks (`_BATCH_SIZE`)
- SoundCloud rate limiting: `sc_rate_limit_sleep` delay + 429 handling with backoff
- Migration is resumable: SQLite tracks `pending/liked/not_found/error` per track
- `YandexMusicClient._uid` may be None for some OAuth tokens → API calls omit `user_id` param in that case (library falls back to `self.me`)
