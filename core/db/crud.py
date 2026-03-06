"""
CRUD-функции через SQLAlchemy 2.x async.
API идентично core/db.py (aiosqlite) для обратной совместимости.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import delete, func, select, update
from core.crypto import decrypt_token, encrypt_token
from core.db.models import Artist, Migration, Playlist, PlaylistTrack, Track, UserSession
from core.db.session import AsyncSessionLocal, engine


def _dialect_insert(model):
    """Return dialect-appropriate Insert that supports on_conflict_do_nothing/update.

    Uses SQLite insert for SQLite/aiosqlite and PostgreSQL insert for asyncpg.
    Both dialects expose identical on_conflict_* APIs.
    """
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


# ---------------------------------------------------------------------------
# Инициализация
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """Создаёт все таблицы если не существуют (для SQLite / dev)."""
    from core.db.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialised")


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

async def create_migration(user_id: str) -> int:
    async with AsyncSessionLocal() as session:
        migration = Migration(user_id=user_id)
        session.add(migration)
        await session.commit()
        await session.refresh(migration)
        return migration.id


async def update_migration(migration_id: int, **fields) -> None:
    if not fields:
        return
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Migration).where(Migration.id == migration_id).values(**fields)
        )
        await session.commit()


async def get_migration(migration_id: int) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = await session.get(Migration, migration_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "user_id": row.user_id,
            "soundcloud_user_id": row.soundcloud_user_id,
            "created_at": row.created_at,
            "status": row.status,
        }


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------

async def bulk_insert_tracks(migration_id: int, tracks: list[dict]) -> None:
    """Вставляет треки пачкой. Пропускает уже существующие (idempotent)."""
    if not tracks:
        return
    async with AsyncSessionLocal() as session:
        for t in tracks:
            stmt = _dialect_insert(Track).values(
                migration_id=migration_id,
                ym_id=t["ym_id"],
                ym_artist=t["ym_artist"],
                ym_title=t["ym_title"],
                ym_album=t.get("ym_album", ""),
            ).on_conflict_do_nothing()
            await session.execute(stmt)
        await session.commit()
    logger.debug(f"Inserted {len(tracks)} tracks for migration {migration_id}")


async def get_pending_tracks(migration_id: int) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Track).where(
                Track.migration_id == migration_id, Track.status == "pending"
            )
        )
        return [_track_to_dict(r) for r in result.scalars()]


async def update_track(track_id: int, **fields) -> None:
    if not fields:
        return
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Track).where(Track.id == track_id).values(**fields)
        )
        await session.commit()


async def get_track_stats(migration_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Track.status, func.count().label("cnt"))
            .where(Track.migration_id == migration_id)
            .group_by(Track.status)
        )
        return {row.status: row.cnt for row in result}


async def get_all_tracks(migration_id: int) -> list[dict]:
    """Returns all tracks for a migration regardless of status."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Track).where(Track.migration_id == migration_id)
        )
        return [_track_to_dict(r) for r in result.scalars()]


async def get_tracks_page(
    migration_id: int,
    status: str | None = None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[dict], int]:
    """Returns (tracks, total_count) with optional status filter and pagination."""
    async with AsyncSessionLocal() as session:
        base_filter = Track.migration_id == migration_id
        count_q = select(func.count()).select_from(Track).where(base_filter)
        q = select(Track).where(base_filter)
        if status:
            count_q = count_q.where(Track.status == status)
            q = q.where(Track.status == status)
        total: int = (await session.execute(count_q)).scalar_one()
        q = q.order_by(Track.id).offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(q)
        return [_track_to_dict(r) for r in result.scalars()], total


async def get_liked_sc_tracks(migration_id: int) -> dict[str, int]:
    """Возвращает {ym_id: sc_id} для уже перенесённых треков."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Track.ym_id, Track.sc_id).where(
                Track.migration_id == migration_id, Track.status == "liked"
            )
        )
        return {row.ym_id: row.sc_id for row in result}


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

async def create_playlist_record(migration_id: int, ym_kind: int, ym_title: str) -> int:
    async with AsyncSessionLocal() as session:
        stmt = _dialect_insert(Playlist).values(
            migration_id=migration_id, ym_kind=ym_kind, ym_title=ym_title
        ).on_conflict_do_nothing()
        result = await session.execute(stmt)
        await session.commit()
        # rowcount > 0 means a new row was inserted; on conflict nothing is inserted
        # (inserted_primary_key may return (0,) which is truthy — do not use it)
        if result.rowcount > 0:
            return result.inserted_primary_key[0]
        # conflict: row already exists — fetch its id
        existing = await session.execute(
            select(Playlist.id).where(
                Playlist.migration_id == migration_id, Playlist.ym_kind == ym_kind
            )
        )
        return existing.scalar_one()


async def update_playlist(playlist_id: int, **fields) -> None:
    if not fields:
        return
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Playlist).where(Playlist.id == playlist_id).values(**fields)
        )
        await session.commit()


async def get_pending_playlists(migration_id: int) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Playlist).where(
                Playlist.migration_id == migration_id, Playlist.status == "pending"
            )
        )
        return [_playlist_to_dict(r) for r in result.scalars()]


# ---------------------------------------------------------------------------
# Artists
# ---------------------------------------------------------------------------

async def bulk_insert_artists(migration_id: int, artists: list[dict]) -> None:
    """artists: [{"ym_name": ...}]"""
    if not artists:
        return
    async with AsyncSessionLocal() as session:
        for a in artists:
            stmt = _dialect_insert(Artist).values(
                migration_id=migration_id, ym_name=a["ym_name"]
            ).on_conflict_do_nothing()
            await session.execute(stmt)
        await session.commit()


async def get_pending_artists(migration_id: int) -> list[dict]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Artist).where(
                Artist.migration_id == migration_id, Artist.status == "pending"
            )
        )
        return [_artist_to_dict(r) for r in result.scalars()]


async def update_artist(artist_id: int, **fields) -> None:
    if not fields:
        return
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Artist).where(Artist.id == artist_id).values(**fields)
        )
        await session.commit()


async def get_artist_stats(migration_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Artist.status, func.count().label("cnt"))
            .where(Artist.migration_id == migration_id)
            .group_by(Artist.status)
        )
        return {row.status: row.cnt for row in result}


# ---------------------------------------------------------------------------
# User sessions
# ---------------------------------------------------------------------------

async def save_user_session(user_id: str, yandex_token: str, soundcloud_token: str) -> None:
    async with AsyncSessionLocal() as session:
        stmt = _dialect_insert(UserSession).values(
            user_id=user_id,
            yandex_token=encrypt_token(yandex_token),
            soundcloud_token=encrypt_token(soundcloud_token),
        ).on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "yandex_token": encrypt_token(yandex_token),
                "soundcloud_token": encrypt_token(soundcloud_token),
            },
        )
        await session.execute(stmt)
        await session.commit()


async def load_user_session(user_id: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = await session.get(UserSession, user_id)
        if row is None:
            return None
        return {
            "yandex_token": decrypt_token(row.yandex_token),
            "soundcloud_token": decrypt_token(row.soundcloud_token),
            "updated_at": row.updated_at,
        }


async def delete_user_session(user_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(UserSession).where(UserSession.user_id == user_id)
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _track_to_dict(t: Track) -> dict:
    return {
        "id": t.id,
        "migration_id": t.migration_id,
        "ym_id": t.ym_id,
        "ym_artist": t.ym_artist,
        "ym_title": t.ym_title,
        "ym_album": t.ym_album,
        "sc_id": t.sc_id,
        "sc_url": t.sc_url,
        "match_score": t.match_score,
        "status": t.status,
    }


def _playlist_to_dict(p: Playlist) -> dict:
    return {
        "id": p.id,
        "migration_id": p.migration_id,
        "ym_kind": p.ym_kind,
        "ym_title": p.ym_title,
        "sc_playlist_id": p.sc_playlist_id,
        "status": p.status,
    }


def _artist_to_dict(a: Artist) -> dict:
    return {
        "id": a.id,
        "migration_id": a.migration_id,
        "ym_name": a.ym_name,
        "sc_user_id": a.sc_user_id,
        "sc_username": a.sc_username,
        "match_score": a.match_score,
        "status": a.status,
    }
