"""ARQ job definitions for the migration worker."""
from loguru import logger

_CURRENT_TRACK_TTL = 86400  # seconds


def _make_progress_callback(redis, migration_id: int):
    """Returns an async callback that writes the current track to Redis."""
    async def callback(current: int, total: int, track_str: str) -> None:
        await redis.set(
            f"migration_current_track:{migration_id}",
            track_str,
            ex=_CURRENT_TRACK_TTL,
        )
    return callback


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


async def run_yandex_migration_job(
    ctx,
    migration_id: int,
    source_token: str,
    from_service: str,
    ym_token: str,
    user_id: str,
    track_limit: int | None = None,
) -> None:
    """ARQ job: migrate liked tracks from any source service → Yandex Music."""
    from migration.yandex_tracks import migrate_to_yandex
    from core.yandex.client import YandexMusicClient
    from core.db import update_migration, get_track_stats
    from worker.notifications import notify_telegram, migration_done_text, migration_failed_text
    from config import settings

    logger.info(
        f"[job] YM migration #{migration_id} from {from_service!r} for user {user_id!r}"
    )
    lang = await _get_user_lang(user_id)
    progress_cb = _make_progress_callback(ctx["redis"], migration_id)

    try:
        # Fetch source tracks via the appropriate adapter
        from core.services.registry import ServiceRegistry
        adapter = ServiceRegistry.get(from_service)
        tracks_data = await adapter.fetch_liked_tracks(source_token)
        if track_limit:
            tracks_data = tracks_data[:track_limit]
        logger.info(f"[job] Fetched {len(tracks_data)} tracks from {from_service}")

        ym_client = await YandexMusicClient(
            ym_token, proxy_url=settings.ym_proxy_url or None
        ).init()

        await migrate_to_yandex(
            tracks_data=tracks_data,
            ym_client=ym_client,
            migration_id=migration_id,
            progress_callback=progress_cb,
        )
        logger.info(f"[job] YM migration #{migration_id} finished")

        tracks = await get_track_stats(migration_id)
        await notify_telegram(user_id, migration_done_text(migration_id, tracks, lang=lang))

    except Exception as e:
        logger.error(f"[job] YM migration #{migration_id} failed: {e}")
        await update_migration(migration_id, status="failed")
        await notify_telegram(user_id, migration_failed_text(migration_id, lang=lang))
        raise


async def run_spotify_migration_job(
    ctx,
    migration_id: int,
    spotify_token: str,
    sc_token: str,
    mode: str,
    user_id: str,
    track_limit: int | None = None,
) -> None:
    """ARQ job: migrate tracks from Spotify to SoundCloud."""
    from migration.spotify_tracks import run_spotify_migration
    from core.db import update_migration, get_track_stats
    from worker.notifications import notify_telegram, migration_done_text, migration_failed_text

    logger.info(f"[job] Spotify migration #{migration_id} for user {user_id!r}, mode={mode}")
    lang = await _get_user_lang(user_id)
    progress_cb = _make_progress_callback(ctx["redis"], migration_id)
    sc_token = await _refresh_sc_token_if_needed(sc_token, user_id)
    try:
        await run_spotify_migration(
            spotify_token=spotify_token,
            soundcloud_token=sc_token,
            migration_id=migration_id,
            user_id=user_id,
            mode=mode,
            progress_callback=progress_cb,
            playlist_mode=True,
            track_limit=track_limit,
        )
        logger.info(f"[job] Spotify migration #{migration_id} finished")

        tracks = await get_track_stats(migration_id)
        await notify_telegram(user_id, migration_done_text(migration_id, tracks, lang=lang))

    except Exception as e:
        logger.error(f"[job] Spotify migration #{migration_id} failed: {e}")
        await update_migration(migration_id, status="failed")
        await notify_telegram(user_id, migration_failed_text(migration_id, lang=lang))
        raise


async def run_spotify_write_job(
    ctx,
    migration_id: int,
    source_token: str,
    from_service: str,
    spotify_token: str,
    spotify_refresh_token: str | None,
    user_id: str,
    track_limit: int | None = None,
) -> None:
    """ARQ job: migrate liked tracks + artists from any source → Spotify."""
    from migration.spotify_write import migrate_to_spotify
    from core.spotify.client import SpotifyClient
    from core.db import update_migration, get_track_stats
    from worker.notifications import notify_telegram, migration_done_text, migration_failed_text
    from config import settings

    logger.info(
        f"[job] Spotify WRITE migration #{migration_id} from {from_service!r} for user {user_id!r}"
    )
    lang = await _get_user_lang(user_id)
    progress_cb = _make_progress_callback(ctx["redis"], migration_id)

    try:
        # Auto-refresh Spotify token if we have a refresh token
        access_token = spotify_token
        if spotify_refresh_token:
            try:
                from core.spotify.oauth import refresh_access_token
                refreshed = await refresh_access_token(spotify_refresh_token)
                access_token = refreshed["access_token"]
                logger.info(f"[job] Refreshed Spotify access token for migration #{migration_id}")
            except Exception as e:
                logger.warning(f"[job] Could not refresh Spotify token: {e}, using existing token")

        # Fetch source tracks via adapter
        from core.services.registry import ServiceRegistry
        adapter = ServiceRegistry.get(from_service)
        tracks_data = await adapter.fetch_liked_tracks(source_token)
        if track_limit:
            tracks_data = tracks_data[:track_limit]
        logger.info(f"[job] Fetched {len(tracks_data)} tracks from {from_service}")

        # Fetch artists if adapter implements fetch_liked_artists
        artists_data: list[dict] = []
        fetch_artists_fn = getattr(adapter, "fetch_liked_artists", None)
        if callable(fetch_artists_fn):
            try:
                raw_artists = await fetch_artists_fn(source_token)
                artists_data = [{"name": a["name"]} for a in raw_artists]
                logger.info(f"[job] Fetched {len(artists_data)} artists from {from_service}")
            except Exception as e:
                logger.warning(f"[job] Could not fetch artists from {from_service}: {e}")

        sp_client = await SpotifyClient(access_token).init()
        try:
            await migrate_to_spotify(
                tracks_data=tracks_data,
                artists_data=artists_data,
                spotify_client=sp_client,
                migration_id=migration_id,
                progress_callback=progress_cb,
            )
        finally:
            await sp_client.close()

        logger.info(f"[job] Spotify WRITE migration #{migration_id} finished")

        tracks = await get_track_stats(migration_id)
        await notify_telegram(user_id, migration_done_text(migration_id, tracks, lang=lang))

    except Exception as e:
        logger.error(f"[job] Spotify WRITE migration #{migration_id} failed: {e}")
        await update_migration(migration_id, status="failed")
        await notify_telegram(user_id, migration_failed_text(migration_id, lang=lang))
        raise


async def _refresh_sc_token_if_needed(sc_token: str, user_id: str) -> str:
    """Auto-refresh SC access token using stored refresh token."""
    try:
        from core.db import load_user_session
        from core.soundcloud.oauth import refresh_access_token
        from core.db.crud import save_soundcloud_token
        session = await load_user_session(user_id)
        if session and session.get("soundcloud_refresh_token"):
            refreshed = await refresh_access_token(session["soundcloud_refresh_token"])
            new_token = refreshed["access_token"]
            await save_soundcloud_token(user_id, new_token, refresh_token=refreshed.get("refresh_token"))
            logger.info(f"[job] Refreshed SC access token for user {user_id!r}")
            return new_token
    except Exception as e:
        logger.warning(f"[job] Could not refresh SC token: {e}, using existing token")
    return sc_token


async def run_migration_job(
    ctx,
    migration_id: int,
    ym_token: str,
    sc_token: str,
    mode: str,
    user_id: str,
    track_limit: int | None = None,
) -> None:
    """ARQ job: runs the migration pipeline for a pre-created migration record."""
    from migration.tracks import run_migration
    from core.db import update_migration, get_track_stats, get_artist_stats
    from worker.notifications import notify_telegram, migration_done_text, migration_failed_text

    logger.info(f"[job] Starting migration #{migration_id} for user {user_id!r}, mode={mode}")
    lang = await _get_user_lang(user_id)
    progress_cb = _make_progress_callback(ctx["redis"], migration_id)
    sc_token = await _refresh_sc_token_if_needed(sc_token, user_id)
    try:
        migrate_full = mode == "full"
        await run_migration(
            yandex_token=ym_token,
            soundcloud_token=sc_token,
            user_id=user_id,
            migration_id=migration_id,
            migrate_playlists=migrate_full,
            migrate_artists=migrate_full,
            progress_callback=progress_cb,
            playlist_mode=True,
            track_limit=track_limit,
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
    track_limit: int | None = None,
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
    progress_cb = _make_progress_callback(ctx["redis"], migration_id)
    sc_token = await _refresh_sc_token_if_needed(sc_token, user_id)
    try:
        sc_client = await SoundCloudClient(sc_token).init()
        try:
            await migrate_from_file_tracks(sc_client, migration_id, tracks, progress_cb, playlist_mode=True, track_limit=track_limit)
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
