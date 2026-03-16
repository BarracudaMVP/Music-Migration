"""CRUD-функции через SQLAlchemy 2.x async."""
from __future__ import annotations

from loguru import logger
from sqlalchemy import delete, func, null, or_, select, update
from core.crypto import decrypt_token, encrypt_token
from core.db.models import Artist, Migration, Playlist, PlaylistTrack, Track, UserSession
from core.db.session import AsyncSessionLocal, engine


def _dialect_insert(model):
    """Return dialect-appropriate Insert with on_conflict support.

    PostgreSQL in production; SQLite fallback is used only by in-memory test fixtures.
    """
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

async def create_migration(
    user_id: str,
    from_service: str | None = None,
    to_service: str | None = None,
) -> int:
    async with AsyncSessionLocal() as session:
        count_result = await session.execute(
            select(func.count()).select_from(Migration).where(Migration.user_id == user_id)
        )
        user_num = count_result.scalar_one() + 1
        migration = Migration(
            user_id=user_id,
            from_service=from_service,
            to_service=to_service,
            user_migration_number=user_num,
        )
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
            "from_service": row.from_service,
            "to_service": row.to_service,
            "soundcloud_user_id": row.soundcloud_user_id,
            "created_at": row.created_at,
            "status": row.status,
            "user_migration_number": row.user_migration_number,
        }


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------

async def get_previously_migrated_ym_ids(user_id: str, to_service: str) -> set[str]:
    """Возвращает ym_id треков, уже успешно перенесённых этим пользователем в to_service.
    Для soundcloud также включает старые миграции, где to_service IS NULL (до MM-55).
    Учитывает статусы 'liked' (прямой лайк) и 'in_playlist' (добавлен в плейлист)."""
    async with AsyncSessionLocal() as session:
        to_service_filter = Migration.to_service == to_service
        # Обратная совместимость: старые SC-миграции хранили NULL в to_service
        if to_service == "soundcloud":
            to_service_filter = or_(Migration.to_service == to_service, Migration.to_service == null())
        result = await session.execute(
            select(Track.ym_id)
            .join(Migration, Track.migration_id == Migration.id)
            .where(
                Migration.user_id == user_id,
                to_service_filter,
                Track.status.in_(["liked", "in_playlist"]),
            )
        )
        return {row for row in result.scalars()}


async def bulk_insert_tracks(
    migration_id: int,
    tracks: list[dict],
    already_migrated: set[str] | None = None,
) -> int:
    """Вставляет треки пачкой. Пропускает уже существующие (idempotent).
    Треки из already_migrated сразу помечаются status='liked' (пропуск поиска).
    Возвращает количество пропущенных (уже перенесённых) треков."""
    if not tracks:
        return 0
    skip = already_migrated or set()
    skipped = 0
    async with AsyncSessionLocal() as session:
        for t in tracks:
            ym_id = t["ym_id"]
            status = "liked" if ym_id in skip else "pending"
            if status == "liked":
                skipped += 1
            stmt = _dialect_insert(Track).values(
                migration_id=migration_id,
                ym_id=ym_id,
                ym_artist=t["ym_artist"],
                ym_title=t["ym_title"],
                ym_album=t.get("ym_album", ""),
                status=status,
            ).on_conflict_do_nothing()
            await session.execute(stmt)
        await session.commit()
    logger.debug(f"Inserted {len(tracks)} tracks for migration {migration_id} ({skipped} skipped as already migrated)")
    return skipped


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
    """Возвращает {ym_id: sc_id} для уже перенесённых треков (статусы liked и in_playlist)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Track.ym_id, Track.sc_id).where(
                Track.migration_id == migration_id,
                Track.status.in_(["liked", "in_playlist"]),
            )
        )
        return {row.ym_id: row.sc_id for row in result}


async def get_track_stats_batch(migration_ids: list[int]) -> dict[int, dict[str, int]]:
    """Возвращает {migration_id: {status: count}} для списка миграций (один SQL-запрос)."""
    if not migration_ids:
        return {}
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Track.migration_id, Track.status, func.count().label("cnt"))
            .where(Track.migration_id.in_(migration_ids))
            .group_by(Track.migration_id, Track.status)
        )
        stats: dict[int, dict[str, int]] = {}
        for row in result:
            if row.migration_id not in stats:
                stats[row.migration_id] = {}
            stats[row.migration_id][row.status] = row.cnt
        return stats


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


async def save_yandex_token(user_id: str, token: str) -> None:
    """Сохраняет или обновляет yandex_token для пользователя, не трогая остальные поля."""
    async with AsyncSessionLocal() as session:
        stmt = _dialect_insert(UserSession).values(
            user_id=user_id,
            yandex_token=encrypt_token(token),
            soundcloud_token="",
        ).on_conflict_do_update(
            index_elements=["user_id"],
            set_={"yandex_token": encrypt_token(token)},
        )
        await session.execute(stmt)
        await session.commit()


async def save_soundcloud_token(
    user_id: str,
    token: str,
    refresh_token: str | None = None,
) -> None:
    """Сохраняет или обновляет soundcloud_token (и refresh_token) для пользователя."""
    async with AsyncSessionLocal() as session:
        values: dict = {
            "user_id": user_id,
            "yandex_token": "",
            "soundcloud_token": encrypt_token(token),
        }
        update_values: dict = {"soundcloud_token": encrypt_token(token)}
        if refresh_token is not None:
            enc_refresh = encrypt_token(refresh_token)
            values["soundcloud_refresh_token"] = enc_refresh
            update_values["soundcloud_refresh_token"] = enc_refresh

        stmt = _dialect_insert(UserSession).values(**values).on_conflict_do_update(
            index_elements=["user_id"],
            set_=update_values,
        )
        await session.execute(stmt)
        await session.commit()


async def save_spotify_token(
    user_id: str,
    token: str,
    refresh_token: str | None = None,
) -> None:
    """Сохраняет или обновляет spotify_token (и refresh_token) для пользователя.
    Если сессии нет — создаёт с пустыми yandex/soundcloud токенами."""
    async with AsyncSessionLocal() as session:
        values: dict = {
            "user_id": user_id,
            "yandex_token": "",
            "soundcloud_token": "",
            "spotify_token": encrypt_token(token),
        }
        update_values: dict = {"spotify_token": encrypt_token(token)}
        if refresh_token is not None:
            enc_refresh = encrypt_token(refresh_token)
            values["spotify_refresh_token"] = enc_refresh
            update_values["spotify_refresh_token"] = enc_refresh

        stmt = _dialect_insert(UserSession).values(**values).on_conflict_do_update(
            index_elements=["user_id"],
            set_=update_values,
        )
        await session.execute(stmt)
        await session.commit()


async def clear_service_token(user_id: str, service: str) -> None:
    """Clears the stored token(s) for a service (marks as disconnected)."""
    _field_map: dict[str, dict] = {
        "yandex_music": {"yandex_token": ""},
        "soundcloud": {"soundcloud_token": "", "soundcloud_refresh_token": None},
        "spotify": {"spotify_token": None, "spotify_refresh_token": None},
    }
    fields = _field_map.get(service)
    if not fields:
        return
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(UserSession).where(UserSession.user_id == user_id).values(**fields)
        )
        await session.commit()


async def save_user_lang(user_id: str, lang: str) -> None:
    """Обновляет язык интерфейса пользователя."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(UserSession).where(UserSession.user_id == user_id).values(lang=lang)
        )
        await session.commit()


async def load_user_session(user_id: str) -> dict | None:
    async with AsyncSessionLocal() as session:
        row = await session.get(UserSession, user_id)
        if row is None:
            return None
        return {
            "yandex_token": decrypt_token(row.yandex_token),
            "soundcloud_token": decrypt_token(row.soundcloud_token),
            "soundcloud_refresh_token": decrypt_token(row.soundcloud_refresh_token) if row.soundcloud_refresh_token else None,
            "spotify_token": decrypt_token(row.spotify_token) if row.spotify_token else None,
            "spotify_refresh_token": decrypt_token(row.spotify_refresh_token) if row.spotify_refresh_token else None,
            "role": row.role,
            "lang": row.lang,
            "updated_at": row.updated_at,
        }


async def set_user_role(user_id: str, role: str) -> None:
    """Устанавливает роль пользователя ('user' | 'admin')."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(UserSession).where(UserSession.user_id == user_id).values(role=role)
        )
        await session.commit()


async def delete_user_session(user_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(UserSession).where(UserSession.user_id == user_id)
        )
        await session.commit()


async def save_spa_refresh_token(user_id: str, refresh_token: str) -> None:
    """Сохраняет SPA refresh token (зашифрованный) в UserSession (MM-81)."""
    async with AsyncSessionLocal() as session:
        stmt = _dialect_insert(UserSession).values(
            user_id=user_id,
            yandex_token="",
            soundcloud_token="",
            spa_refresh_token=encrypt_token(refresh_token),
        ).on_conflict_do_update(
            index_elements=["user_id"],
            set_={"spa_refresh_token": encrypt_token(refresh_token)},
        )
        await session.execute(stmt)
        await session.commit()


async def get_user_id_by_spa_refresh_token(refresh_token: str) -> str | None:
    """Находит user_id по SPA refresh token. Возвращает None если не найден (MM-81)."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(UserSession.user_id, UserSession.spa_refresh_token)
            .where(UserSession.spa_refresh_token.isnot(None))
        )
        for user_id, enc_token in rows:
            if decrypt_token(enc_token) == refresh_token:
                return user_id
        return None


async def revoke_spa_refresh_token(user_id: str) -> None:
    """Удаляет SPA refresh token (logout) (MM-81)."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(spa_refresh_token=None)
        )
        await session.commit()


async def get_user_migrations(user_id: str) -> list[dict]:
    """Возвращает все миграции пользователя, новые сначала (MM-81)."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Migration)
            .where(Migration.user_id == user_id)
            .order_by(Migration.created_at.desc())
        )
        return [
            {
                "id": m.id,
                "user_id": m.user_id,
                "from_service": m.from_service,
                "to_service": m.to_service,
                "status": m.status,
                "user_migration_number": m.user_migration_number,
                "created_at": m.created_at,
            }
            for m in rows.scalars()
        ]


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
