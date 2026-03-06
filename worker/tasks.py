"""ARQ job definitions for the migration worker."""
from loguru import logger


async def run_file_migration_job(
    ctx,
    migration_id: int,
    sc_token: str,
    tracks: list[dict],
    user_id: str,
) -> None:
    """ARQ job: переносит треки из файла на SoundCloud (без Яндекс Музыки)."""
    from migration.tracks import migrate_from_file_tracks
    from core.soundcloud.client import SoundCloudClient
    from core.db import update_migration

    logger.info(
        f"[job] File migration #{migration_id} for user {user_id!r}, "
        f"{len(tracks)} треков"
    )
    try:
        sc_client = await SoundCloudClient(sc_token).init()
        try:
            await migrate_from_file_tracks(sc_client, migration_id, tracks)
        finally:
            await sc_client.close()
        logger.info(f"[job] File migration #{migration_id} finished")
    except Exception as e:
        logger.error(f"[job] File migration #{migration_id} failed: {e}")
        await update_migration(migration_id, status="failed")
        raise


async def run_migration_job(
    ctx,
    migration_id: int,
    ym_token: str,
    sc_token: str,
    mode: str,
    user_id: str,
) -> None:
    """ARQ job: runs the migration pipeline for a pre-created migration record."""
    from migration.tracks import run_migration
    from core.db import update_migration

    logger.info(f"[job] Starting migration #{migration_id} for user {user_id!r}, mode={mode}")
    try:
        migrate_full = mode == "full"
        await run_migration(
            yandex_token=ym_token,
            soundcloud_token=sc_token,
            user_id=user_id,
            migration_id=migration_id,
            migrate_playlists=migrate_full,
            migrate_artists=migrate_full,
        )
        logger.info(f"[job] Migration #{migration_id} finished")
    except Exception as e:
        logger.error(f"[job] Migration #{migration_id} failed with unhandled error: {e}")
        await update_migration(migration_id, status="failed")
        raise
