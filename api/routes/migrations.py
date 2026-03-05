"""Migration routes: start + status."""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.deps import verify_internal_token
from core.db import get_migration, get_track_stats, get_artist_stats

router = APIRouter(dependencies=[Depends(verify_internal_token)])


class StartMigrationRequest(BaseModel):
    user_id: str
    yandex_token: str
    soundcloud_token: str
    mode: Literal["tracks", "full"] = "tracks"


class StartMigrationResponse(BaseModel):
    migration_id: int


@router.post("", response_model=StartMigrationResponse, status_code=status.HTTP_201_CREATED)
async def start_migration(body: StartMigrationRequest):
    """Создаёт запись миграции и запускает asyncio-задачу."""
    from migration.tracks import run_migration

    migrate_playlists = body.mode == "full"
    migrate_artists = body.mode == "full"

    migration_id_holder: list[int] = []

    async def _on_created(mid: int) -> None:
        migration_id_holder.append(mid)

    async def _task():
        try:
            await run_migration(
                yandex_token=body.yandex_token,
                soundcloud_token=body.soundcloud_token,
                user_id=body.user_id,
                migrate_playlists=migrate_playlists,
                migrate_artists=migrate_artists,
                on_migration_created=_on_created,
            )
        except Exception:
            pass  # errors logged inside run_migration

    task = asyncio.create_task(_task())

    # Ждём немного чтобы migration_id появился
    for _ in range(50):
        if migration_id_holder:
            break
        await asyncio.sleep(0.1)

    if not migration_id_holder:
        # Если миграция не стартовала — даём задаче отработать и смотрим
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
        except (asyncio.TimeoutError, Exception):
            pass

    if not migration_id_holder:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Migration did not start in time",
        )

    return StartMigrationResponse(migration_id=migration_id_holder[0])


@router.get("/{migration_id}")
async def get_migration_status(migration_id: int):
    """Возвращает статус + статистику треков/артистов."""
    migration = await get_migration(migration_id)
    if migration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration not found")

    track_stats = await get_track_stats(migration_id)
    artist_stats = await get_artist_stats(migration_id)

    return {
        "migration": migration,
        "tracks": track_stats,
        "artists": artist_stats,
    }
