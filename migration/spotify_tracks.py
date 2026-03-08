"""
MM-22: Миграция из Spotify → SoundCloud.

Пайплайн:
1. Получаем треки/плейлисты/артистов из Spotify
2. Сохраняем в БД со статусом 'pending'
3. Запускаем общий _run_pending_loop (поиск → матчинг → лайк на SC)
"""
from __future__ import annotations

from loguru import logger

from core.db import (
    bulk_insert_tracks,
    update_migration,
    get_track_stats,
)
from core.spotify.client import SpotifyClient
from core.soundcloud.client import SoundCloudClient
from migration.tracks import _run_pending_loop, MigrationStats


async def migrate_spotify_tracks(
    spotify_client: SpotifyClient,
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
) -> MigrationStats:
    """Переносит лайкнутые треки Spotify → SoundCloud."""
    await update_migration(migration_id, status="running")

    logger.info("Шаг 1/3: загружаю треки из Spotify...")
    sp_tracks = await spotify_client.get_liked_tracks()

    if not sp_tracks:
        logger.warning("Нет лайкнутых треков в Spotify")
        await update_migration(migration_id, status="done")
        return MigrationStats()

    logger.info(f"Шаг 2/3: сохраняю {len(sp_tracks)} треков в БД...")
    await bulk_insert_tracks(
        migration_id,
        [
            {
                "ym_id": f"spotify:{t.id}",
                "ym_artist": t.artists_str,
                "ym_title": t.title,
                "ym_album": t.album,
            }
            for t in sp_tracks
        ],
    )

    logger.info("Шаг 3/3: обрабатываю треки...")
    stats = await _run_pending_loop(sc_client, migration_id, progress_callback)

    await update_migration(migration_id, status="done")
    logger.info(f"Spotify миграция треков завершена. {stats}")
    return stats


async def run_spotify_migration(
    spotify_token: str,
    soundcloud_token: str,
    migration_id: int,
    user_id: str = "cli",
    mode: str = "tracks",
    progress_callback=None,
) -> MigrationStats:
    """
    Точка входа для ARQ worker.
    mode: 'tracks' — только треки, 'full' — треки + плейлисты (TODO).
    """
    spotify_client = await SpotifyClient(spotify_token).init()
    sc_client = await SoundCloudClient(soundcloud_token).init()

    try:
        stats = await migrate_spotify_tracks(spotify_client, sc_client, migration_id, progress_callback)
    finally:
        await spotify_client.close()
        await sc_client.close()

    return stats
