"""
Миграция треков → Spotify (из любого источника): лайки треков + подписки на артистов.

Source tracks are passed as [{"artist": str, "title": str}] —
fetched from any adapter (SoundCloud, Yandex Music, File, etc.).

Pipeline:
1. Insert source tracks into DB with status 'pending'
2. For each pending track: search on Spotify, fuzzy-match, like (via SpotifyAdapter)
3. If artists provided: search Spotify, fuzzy-match, follow
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from loguru import logger

from core.db import (
    update_migration,
    bulk_insert_tracks,
    get_pending_artists,
    update_artist,
    bulk_insert_artists,
    get_track_urls_by_status,
)
from config import settings as _settings
from core.matcher import normalize, _score_pair
from core.services.base import AdapterWriteSession
from core.services.registry import ServiceRegistry
from migration.pipeline import run_pending_tracks_loop

# Pause between Spotify write operations to avoid rate limiting
_SPOTIFY_WRITE_SLEEP = 0.5


@dataclass
class SpotifyWriteStats:
    total: int = 0
    liked: int = 0
    not_found: int = 0
    errors: int = 0
    artists_followed: int = 0
    artists_not_found: int = 0
    playlist_url: str | None = None

    def __str__(self) -> str:
        base = (
            f"Spotify | Треков: {self.total} | Добавлено: {self.liked} | "
            f"Не найдено: {self.not_found} | Ошибок: {self.errors} | "
            f"Исполнителей: {self.artists_followed}"
        )
        if self.playlist_url:
            base += f" | Плейлист: {self.playlist_url}"
        return base


async def migrate_to_spotify(
    tracks_data: list[dict],
    artists_data: list[dict],
    spotify_token: str,
    migration_id: int,
    progress_callback=None,
    playlist_mode: bool = False,
    playlist_name: str = "Music Migration",
) -> SpotifyWriteStats:
    """
    Main pipeline: list[{artist, title}] → Spotify likes (or bot playlist).

    artists_data: list[{"name": str}] — optional, can be empty.
    progress_callback(current, total, track_str) — optional, used by worker.
    playlist_mode: if True, collect matched tracks and create a public playlist
                   via the bot account (SPOTIFY_BOT_TOKEN).
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

    adapter = ServiceRegistry.get("spotify")
    async with adapter.write_session(spotify_token, playlist_mode=playlist_mode) as session:
        pipeline_stats = await run_pending_tracks_loop(
            session, migration_id, progress_callback, write_sleep=_SPOTIFY_WRITE_SLEEP
        )

        if artists_data:
            logger.info(f"Вставляю {len(artists_data)} артистов в БД (миграция #{migration_id})...")
            await bulk_insert_artists(
                migration_id,
                [{"ym_name": a["name"]} for a in artists_data],
            )
            followed, not_found = await _run_pending_artists_loop(session, migration_id)
        else:
            followed, not_found = 0, 0

    # Create bot playlist when playlist_mode is active
    playlist_url: str | None = None
    if playlist_mode and pipeline_stats.in_playlist > 0:
        playlist_url = await _create_bot_playlist(migration_id, playlist_name)

    if playlist_url:
        await update_migration(migration_id, status="done", result_path=playlist_url)
    else:
        await update_migration(migration_id, status="done")

    stats = SpotifyWriteStats(
        total=pipeline_stats.total,
        liked=pipeline_stats.liked,
        not_found=pipeline_stats.not_found,
        errors=pipeline_stats.errors,
        artists_followed=followed,
        artists_not_found=not_found,
        playlist_url=playlist_url,
    )
    logger.info(f"Перенос в Spotify завершён. {stats}")
    return stats


async def _create_bot_playlist(migration_id: int, name: str) -> str | None:
    """Create a public Spotify playlist via the bot account. Returns the playlist URL or None."""
    from config import settings
    from core.spotify.client import SpotifyClient

    bot_token = settings.spotify_bot_token
    if not bot_token:
        logger.warning("[to_spotify] SPOTIFY_BOT_TOKEN not configured — skipping playlist creation")
        return None

    track_ids = await get_track_urls_by_status(migration_id, "in_playlist")
    if not track_ids:
        logger.warning(f"[to_spotify] No in_playlist tracks found for migration #{migration_id}")
        return None

    track_uris = [f"spotify:track:{tid}" for tid in track_ids]
    bot_client = await SpotifyClient(bot_token).init()
    try:
        playlist_id, playlist_url = await bot_client.create_playlist(name)
        await bot_client.add_tracks_to_playlist(playlist_id, track_uris)
    finally:
        await bot_client.close()

    logger.info(f"[to_spotify] Bot playlist {name!r} created with {len(track_uris)} tracks → {playlist_url}")
    return playlist_url


async def _run_pending_artists_loop(
    session: AdapterWriteSession,
    migration_id: int,
) -> tuple[int, int]:
    """Follow all pending artists on Spotify. Returns (followed, not_found)."""
    pending = await get_pending_artists(migration_id)
    total = len(pending)
    followed = 0
    not_found = 0

    for i, row in enumerate(pending, start=1):
        name = row["ym_name"]
        logger.info(f"[artist {i}/{total}] ▶ {name}")

        try:
            artists = await session.search_artist(name, limit=5)
            if not artists:
                await update_artist(row["id"], status="not_found")
                not_found += 1
                continue

            best = None
            best_score = 0.0
            for a in artists:
                score = _score_pair(normalize(name), normalize(a["name"]))
                if score > best_score:
                    best_score = score
                    best = a

            if best and best_score >= _settings.match_threshold:
                success = await session.follow_artist(best["id"])
                if success:
                    await update_artist(
                        row["id"],
                        status="liked",
                        sc_user_id=None,
                        sc_username=best["name"],
                        match_score=best_score,
                    )
                    followed += 1
                    logger.debug(f"[artist {i}/{total}] followed: {best['name']!r} ({best_score:.0f})")
                else:
                    await update_artist(row["id"], status="error")
            else:
                await update_artist(
                    row["id"],
                    status="not_found",
                    match_score=best_score if best else None,
                )
                not_found += 1
                logger.debug(f"[artist {i}/{total}] not found: {name!r}")

        except Exception as e:
            logger.error(f"[artist {i}/{total}] Ошибка: {name!r}: {e}")
            await update_artist(row["id"], status="error")

        await asyncio.sleep(_SPOTIFY_WRITE_SLEEP)

    return followed, not_found
