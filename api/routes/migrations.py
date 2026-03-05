"""Migration routes: start + status."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.deps import arq_pool_dep, verify_internal_token
from core.db import create_migration, get_migration, get_track_stats, get_artist_stats

router = APIRouter(dependencies=[Depends(verify_internal_token)])


class StartMigrationRequest(BaseModel):
    user_id: str
    yandex_token: str
    soundcloud_token: str
    mode: Literal["tracks", "full"] = "tracks"


class StartMigrationResponse(BaseModel):
    migration_id: int


@router.post("", response_model=StartMigrationResponse, status_code=status.HTTP_201_CREATED)
async def start_migration(body: StartMigrationRequest, arq=Depends(arq_pool_dep)):
    """Создаёт запись миграции и ставит задачу в ARQ-очередь."""
    migration_id = await create_migration(body.user_id)
    job = await arq.enqueue_job(
        "run_migration_job",
        migration_id,
        body.yandex_token,
        body.soundcloud_token,
        body.mode,
        body.user_id,
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

    return {
        "migration": migration,
        "tracks": track_stats,
        "artists": artist_stats,
    }
