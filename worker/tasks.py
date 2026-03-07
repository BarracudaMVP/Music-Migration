"""ARQ job definitions for the migration worker."""
from loguru import logger


async def _get_user_lang(user_id: str) -> str:
    """Look up user's preferred language from DB session."""
    try:
        from core.db import load_user_session
        session = await load_user_session(user_id)
        if session:
            return session.get("lang", "ru")
    except Exception:
        pass
    return "ru"


async def run_spotify_migration_job(
    ctx,
    migration_id: int,
    spotify_token: str,
    sc_token: str,
    mode: str,
    user_id: str,
) -> None:
    """ARQ job: migrate tracks from Spotify to SoundCloud."""
    from migration.spotify_tracks import run_spotify_migration
    from core.db import update_migration, get_track_stats
    from worker.notifications import notify_telegram, migration_done_text, migration_failed_text

    logger.info(f"[job] Spotify migration #{migration_id} for user {user_id!r}, mode={mode}")
    lang = await _get_user_lang(user_id)
    try:
        await run_spotify_migration(
            spotify_token=spotify_token,
            soundcloud_token=sc_token,
            migration_id=migration_id,
            user_id=user_id,
            mode=mode,
        )
        logger.info(f"[job] Spotify migration #{migration_id} finished")

        tracks = await get_track_stats(migration_id)
        await notify_telegram(user_id, migration_done_text(migration_id, tracks, lang=lang))

    except Exception as e:
        logger.error(f"[job] Spotify migration #{migration_id} failed: {e}")
        await update_migration(migration_id, status="failed")
        await notify_telegram(user_id, migration_failed_text(migration_id, lang=lang))
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
    from core.db import update_migration, get_track_stats, get_artist_stats
    from worker.notifications import notify_telegram, migration_done_text, migration_failed_text

    logger.info(f"[job] Starting migration #{migration_id} for user {user_id!r}, mode={mode}")
    lang = await _get_user_lang(user_id)
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

        tracks = await get_track_stats(migration_id)
        artists = await get_artist_stats(migration_id) if migrate_full else None
        await notify_telegram(user_id, migration_done_text(migration_id, tracks, artists, lang=lang))

    except Exception as e:
        logger.error(f"[job] Migration #{migration_id} failed with unhandled error: {e}")
        await update_migration(migration_id, status="failed")
        await notify_telegram(user_id, migration_failed_text(migration_id, lang=lang))
        raise


async def run_file_migration_job(
    ctx,
    migration_id: int,
    sc_token: str,
    tracks: list[dict],
    user_id: str,
) -> None:
    """ARQ job: migrate tracks from a file to SoundCloud (no Yandex Music)."""
    from migration.tracks import migrate_from_file_tracks
    from core.soundcloud.client import SoundCloudClient
    from core.db import update_migration, get_track_stats
    from worker.notifications import notify_telegram, migration_done_text, migration_failed_text

    logger.info(
        f"[job] File migration #{migration_id} for user {user_id!r}, "
        f"{len(tracks)} tracks"
    )
    lang = await _get_user_lang(user_id)
    try:
        sc_client = await SoundCloudClient(sc_token).init()
        try:
            await migrate_from_file_tracks(sc_client, migration_id, tracks)
        finally:
            await sc_client.close()
        logger.info(f"[job] File migration #{migration_id} finished")

        track_stats = await get_track_stats(migration_id)
        await notify_telegram(user_id, migration_done_text(migration_id, track_stats, lang=lang))

    except Exception as e:
        logger.error(f"[job] File migration #{migration_id} failed: {e}")
        await update_migration(migration_id, status="failed")
        await notify_telegram(user_id, migration_failed_text(migration_id, lang=lang))
        raise
