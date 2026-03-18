"""
Миграция треков → Яндекс Музыка (из любого источника).

Source tracks are passed as [{"artist": str, "title": str}] —
fetched from any adapter (SoundCloud, Spotify, File, etc.).

Pipeline:
1. Insert source tracks into DB with status 'pending'
2. For each pending track: search on YM, fuzzy-match, like (via YandexMusicAdapter)
3. Return stats
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from core.db import (
    update_migration,
    bulk_insert_tracks,
)
from core.services.registry import ServiceRegistry
from migration.pipeline import run_pending_tracks_loop, TrackPipelineStats

# Pause between YM like operations to avoid rate limiting
_YM_WRITE_SLEEP = 1.0


@dataclass
class YandexMigrationStats:
    total: int = 0
    liked: int = 0
    not_found: int = 0
    errors: int = 0
    uncertain: int = 0

    def __str__(self) -> str:
        return (
            f"YM | Всего: {self.total} | Перенесено: {self.liked} | "
            f"Не найдено: {self.not_found} | Ошибок: {self.errors}"
        )


async def migrate_to_yandex(
    tracks_data: list[dict],
    ym_token: str,
    migration_id: int,
    progress_callback=None,
) -> YandexMigrationStats:
    """
    Main pipeline: list[{artist, title}] → Yandex Music likes.

    progress_callback(current, total, track_str) — optional, used by worker.
    """
    await update_migration(migration_id, status="running")

    logger.info(f"Вставляю {len(tracks_data)} треков в БД (миграция #{migration_id})...")
    await bulk_insert_tracks(
        migration_id,
        [
            {
                "ym_id": f"src:{i}",
                "ym_artist": t["artist"],
                "ym_title": t["title"],
                "ym_album": t.get("album", ""),
            }
            for i, t in enumerate(tracks_data)
        ],
    )

    adapter = ServiceRegistry.get("yandex_music")
    async with adapter.write_session(ym_token) as session:
        pipeline_stats = await run_pending_tracks_loop(
            session, migration_id, progress_callback, write_sleep=_YM_WRITE_SLEEP
        )

    await update_migration(migration_id, status="done")

    stats = YandexMigrationStats(
        total=pipeline_stats.total,
        liked=pipeline_stats.liked,
        not_found=pipeline_stats.not_found,
        errors=pipeline_stats.errors,
        uncertain=pipeline_stats.uncertain,
    )
    logger.info(f"Перенос в Яндекс Музыку завершён. {stats}")
    return stats
