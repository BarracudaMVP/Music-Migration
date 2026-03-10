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
    get_migration,
    get_previously_migrated_ym_ids,
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
    playlist_mode: bool = False,
    track_limit: int | None = None,
    skip_already_migrated: bool = True,
) -> MigrationStats:
    """Переносит лайкнутые треки Spotify → SoundCloud."""
    await update_migration(migration_id, status="running")

    logger.info("Шаг 1/3: загружаю треки из Spotify...")
    sp_tracks = await spotify_client.get_liked_tracks()

    if not sp_tracks:
        logger.warning("Нет лайкнутых треков в Spotify")
        await update_migration(migration_id, status="done")
        return MigrationStats()

    if track_limit:
        sp_tracks = sp_tracks[:track_limit]
        logger.info(f"Лимит треков: {track_limit}, будет обработано {len(sp_tracks)}")
    logger.info(f"Шаг 2/3: сохраняю {len(sp_tracks)} треков в БД...")
    migration_record = await get_migration(migration_id) or {}
    user_id = migration_record.get("user_id", "")
    to_service = migration_record.get("to_service") or "soundcloud"

    already_migrated: set[str] = set()
    if skip_already_migrated:
        already_migrated = await get_previously_migrated_ym_ids(user_id, to_service)
        if already_migrated:
            logger.info(f"Найдено {len(already_migrated)} треков из предыдущих переносов — будут пропущены")

    skipped = await bulk_insert_tracks(
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
        already_migrated=already_migrated,
    )

    logger.info("Шаг 3/3: обрабатываю треки...")
    stats = await _run_pending_loop(sc_client, migration_id, progress_callback, playlist_mode=playlist_mode)
    stats.skipped = skipped

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
    playlist_mode: bool = False,
    track_limit: int | None = None,
    skip_already_migrated: bool = True,
) -> MigrationStats:
    """
    Точка входа для ARQ worker.
    mode: 'tracks' — только треки, 'full' — треки + плейлисты (TODO).
    """
    spotify_client = await SpotifyClient(spotify_token).init()
    sc_client = await SoundCloudClient(soundcloud_token).init()

    try:
        stats = await migrate_spotify_tracks(
            spotify_client, sc_client, migration_id, progress_callback,
            playlist_mode=playlist_mode, track_limit=track_limit,
            skip_already_migrated=skip_already_migrated,
        )
    finally:
        await spotify_client.close()
        await sc_client.close()

    return stats
