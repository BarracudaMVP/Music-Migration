"""Migration routes: start + status."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.deps import arq_pool_dep, verify_internal_token
from core.db import create_migration, get_migration, get_track_stats, get_artist_stats

router = APIRouter(dependencies=[Depends(verify_internal_token)])


class StartMigrationRequest(BaseModel):
    user_id: str
    yandex_token: str = ""
    soundcloud_token: str = ""
    mode: Literal["tracks", "full"] = "tracks"
    from_service: Literal["yandex_music", "spotify", "soundcloud"] = "yandex_music"
    to_service: Literal["soundcloud", "yandex_music", "spotify"] = "soundcloud"
    spotify_token: str | None = None
    spotify_refresh_token: str | None = None
    track_limit: int | None = None
    skip_already_migrated: bool = True


class StartMigrationResponse(BaseModel):
    migration_id: int


@router.post("", response_model=StartMigrationResponse, status_code=status.HTTP_201_CREATED)
async def start_migration(body: StartMigrationRequest, arq=Depends(arq_pool_dep)):
    """Создаёт запись миграции и ставит задачу в ARQ-очередь."""
    migration_id = await create_migration(body.user_id, from_service=body.from_service, to_service=body.to_service)

    skip = body.skip_already_migrated

    if body.to_service == "yandex_music":
        source_token = body.spotify_token if body.from_service == "spotify" else body.soundcloud_token
        job = await arq.enqueue_job(
            "run_yandex_migration_job",
            migration_id, source_token, body.from_service, body.yandex_token, body.user_id,
            track_limit=body.track_limit, skip_already_migrated=skip,
        )
    elif body.to_service == "spotify":
        source_token = (
            body.soundcloud_token if body.from_service == "soundcloud"
            else body.yandex_token
        )
        job = await arq.enqueue_job(
            "run_spotify_write_job",
            migration_id, source_token, body.from_service,
            body.spotify_token or "", body.spotify_refresh_token, body.user_id,
            track_limit=body.track_limit, skip_already_migrated=skip,
        )
    elif body.from_service == "spotify" and body.spotify_token:
        job = await arq.enqueue_job(
            "run_spotify_migration_job",
            migration_id, body.spotify_token, body.soundcloud_token, body.mode, body.user_id,
            track_limit=body.track_limit, skip_already_migrated=skip,
        )
    else:
        job = await arq.enqueue_job(
            "run_migration_job",
            migration_id, body.yandex_token, body.soundcloud_token, body.mode, body.user_id,
            track_limit=body.track_limit, skip_already_migrated=skip,
        )

    if job:
        await arq.set(f"migration_job:{migration_id}", job.job_id, ex=86400)
    return StartMigrationResponse(migration_id=migration_id)


@router.get("/{migration_id}")
async def get_migration_status(migration_id: int):
    """Возвращает статус + статистику треков/артистов."""
    migration = await get_migration(migration_id)
    if migration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Migration not found")

    track_stats = await get_track_stats(migration_id)
    artist_stats = await get_artist_stats(migration_id)

    current_track = None
    if migration["status"] == "running":
        from api.main import get_arq_pool
        arq = get_arq_pool()
        if arq:
            val = await arq.get(f"migration_current_track:{migration_id}")
            if val:
                current_track = val.decode() if isinstance(val, bytes) else val

    return {
        "migration": migration,
        "tracks": track_stats,
        "artists": artist_stats,
        "current_track": current_track,
    }
