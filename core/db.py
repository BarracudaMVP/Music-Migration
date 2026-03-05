"""
SQLite database layer.
Все операции асинхронные через aiosqlite.
"""
import aiosqlite
from loguru import logger
from config import settings
from core.crypto import encrypt_token, decrypt_token


DB_PATH = settings.db_path

# Allowlist полей для динамических UPDATE — защита от случайной инъекции
_MIGRATION_FIELDS = {"status", "soundcloud_user_id"}
_TRACK_FIELDS     = {"status", "sc_id", "sc_url", "match_score"}
_PLAYLIST_FIELDS  = {"status", "sc_playlist_id"}
_ARTIST_FIELDS    = {"status", "sc_user_id", "sc_username", "match_score"}


def _safe_update(fields: dict, allowed: set) -> dict:
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"Недопустимые поля для UPDATE: {bad}")
    return fields

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS user_sessions (
    user_id             TEXT    PRIMARY KEY,
    yandex_token        TEXT    NOT NULL,
    soundcloud_token    TEXT    NOT NULL,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS migrations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT    NOT NULL,
    soundcloud_user_id  INTEGER,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status              TEXT    NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS tracks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id    INTEGER NOT NULL,
    ym_id           TEXT    NOT NULL,
    ym_artist       TEXT    NOT NULL,
    ym_title        TEXT    NOT NULL,
    ym_album        TEXT    NOT NULL DEFAULT '',
    sc_id           INTEGER,
    sc_url          TEXT,
    match_score     REAL,
    status          TEXT    NOT NULL DEFAULT 'pending',
    UNIQUE (migration_id, ym_id),
    FOREIGN KEY (migration_id) REFERENCES migrations(id)
);

CREATE TABLE IF NOT EXISTS playlists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id    INTEGER NOT NULL,
    ym_kind         INTEGER NOT NULL,
    ym_title        TEXT    NOT NULL,
    sc_playlist_id  INTEGER,
    status          TEXT    NOT NULL DEFAULT 'pending',
    UNIQUE (migration_id, ym_kind),
    FOREIGN KEY (migration_id) REFERENCES migrations(id)
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id     INTEGER NOT NULL,
    ym_track_id     TEXT    NOT NULL,
    sc_track_id     INTEGER,
    PRIMARY KEY (playlist_id, ym_track_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id)
);

CREATE TABLE IF NOT EXISTS artists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    migration_id    INTEGER NOT NULL,
    ym_name         TEXT    NOT NULL,
    sc_user_id      INTEGER,
    sc_username     TEXT,
    match_score     REAL,
    status          TEXT    NOT NULL DEFAULT 'pending',
    UNIQUE (migration_id, ym_name),
    FOREIGN KEY (migration_id) REFERENCES migrations(id)
);
"""


async def init_db() -> None:
    """Создаёт все таблицы если не существуют."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()
    logger.info(f"Database initialised at {DB_PATH}")


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

async def create_migration(user_id: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO migrations (user_id) VALUES (?)",
            (user_id,),
        )
        await db.commit()
        return cursor.lastrowid


async def update_migration(migration_id: int, **fields) -> None:
    if not fields:
        return
    fields = _safe_update(fields, _MIGRATION_FIELDS)
    sets = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [migration_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE migrations SET {sets} WHERE id = ?", values)
        await db.commit()


async def get_migration(migration_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM migrations WHERE id = ?", (migration_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------

async def bulk_insert_tracks(migration_id: int, tracks: list[dict]) -> None:
    """
    Вставляет треки пачкой. Пропускает уже существующие (idempotent).
    tracks: [{"ym_id": ..., "ym_artist": ..., "ym_title": ..., "ym_album": ...}]
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """
            INSERT OR IGNORE INTO tracks (migration_id, ym_id, ym_artist, ym_title, ym_album)
            VALUES (:migration_id, :ym_id, :ym_artist, :ym_title, :ym_album)
            """,
            [{"migration_id": migration_id, **t} for t in tracks],
        )
        await db.commit()
    logger.debug(f"Inserted {len(tracks)} tracks for migration {migration_id}")


async def get_pending_tracks(migration_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM tracks WHERE migration_id = ? AND status = 'pending'",
            (migration_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def update_track(track_id: int, **fields) -> None:
    if not fields:
        return
    fields = _safe_update(fields, _TRACK_FIELDS)
    sets = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [track_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE tracks SET {sets} WHERE id = ?", values)
        await db.commit()


async def get_track_stats(migration_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT status, COUNT(*) as cnt
            FROM tracks WHERE migration_id = ?
            GROUP BY status
            """,
            (migration_id,),
        ) as cur:
            rows = await cur.fetchall()
            return {r["status"]: r["cnt"] for r in rows}


async def get_liked_sc_tracks(migration_id: int) -> dict[str, int]:
    """Возвращает {ym_id: sc_id} для уже перенесённых треков — нужно для MVP2."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT ym_id, sc_id FROM tracks WHERE migration_id = ? AND status = 'liked'",
            (migration_id,),
        ) as cur:
            rows = await cur.fetchall()
            return {r["ym_id"]: r["sc_id"] for r in rows}


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

async def create_playlist_record(migration_id: int, ym_kind: int, ym_title: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO playlists (migration_id, ym_kind, ym_title) VALUES (?, ?, ?)",
            (migration_id, ym_kind, ym_title),
        )
        await db.commit()
        return cursor.lastrowid


async def update_playlist(playlist_id: int, **fields) -> None:
    if not fields:
        return
    fields = _safe_update(fields, _PLAYLIST_FIELDS)
    sets = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [playlist_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE playlists SET {sets} WHERE id = ?", values)
        await db.commit()


async def get_pending_playlists(migration_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM playlists WHERE migration_id = ? AND status = 'pending'",
            (migration_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Artists
# ---------------------------------------------------------------------------

async def bulk_insert_artists(migration_id: int, artists: list[dict]) -> None:
    """artists: [{"ym_name": ...}]"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT OR IGNORE INTO artists (migration_id, ym_name) VALUES (:migration_id, :ym_name)",
            [{"migration_id": migration_id, **a} for a in artists],
        )
        await db.commit()


async def get_pending_artists(migration_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM artists WHERE migration_id = ? AND status = 'pending'",
            (migration_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def update_artist(artist_id: int, **fields) -> None:
    if not fields:
        return
    fields = _safe_update(fields, _ARTIST_FIELDS)
    sets = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [artist_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE artists SET {sets} WHERE id = ?", values)
        await db.commit()


async def get_artist_stats(migration_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status, COUNT(*) as cnt FROM artists WHERE migration_id = ? GROUP BY status",
            (migration_id,),
        ) as cur:
            rows = await cur.fetchall()
            return {r["status"]: r["cnt"] for r in rows}


# ---------------------------------------------------------------------------
# User sessions (сохранение токенов между сессиями)
# ---------------------------------------------------------------------------

async def save_user_session(user_id: str, yandex_token: str, soundcloud_token: str) -> None:
    """Сохраняет или обновляет токены пользователя (зашифровано)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_sessions (user_id, yandex_token, soundcloud_token, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                yandex_token     = excluded.yandex_token,
                soundcloud_token = excluded.soundcloud_token,
                updated_at       = CURRENT_TIMESTAMP
            """,
            (user_id, encrypt_token(yandex_token), encrypt_token(soundcloud_token)),
        )
        await db.commit()


async def load_user_session(user_id: str) -> dict | None:
    """Загружает сохранённые токены пользователя. None если сессии нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_sessions WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "yandex_token":    decrypt_token(row["yandex_token"]),
                "soundcloud_token": decrypt_token(row["soundcloud_token"]),
                "updated_at":      row["updated_at"],
            }


async def delete_user_session(user_id: str) -> None:
    """Удаляет сохранённую сессию (например при инвалидном токене)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
        await db.commit()
