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

    def __str__(self) -> str:
        return (
            f"Spotify | Треков: {self.total} | Добавлено: {self.liked} | "
            f"Не найдено: {self.not_found} | Ошибок: {self.errors} | "
            f"Исполнителей: {self.artists_followed}"
        )


async def migrate_to_spotify(
    tracks_data: list[dict],
    artists_data: list[dict],
    spotify_token: str,
    migration_id: int,
    progress_callback=None,
) -> SpotifyWriteStats:
    """
    Main pipeline: list[{artist, title}] → Spotify likes.

    artists_data: list[{"name": str}] — optional, can be empty.
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

    adapter = ServiceRegistry.get("spotify")
    async with adapter.write_session(spotify_token) as session:
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

    await update_migration(migration_id, status="done")

    stats = SpotifyWriteStats(
        total=pipeline_stats.total,
        liked=pipeline_stats.liked,
        not_found=pipeline_stats.not_found,
        errors=pipeline_stats.errors,
        artists_followed=followed,
        artists_not_found=not_found,
    )
    logger.info(f"Перенос в Spotify завершён. {stats}")
    return stats


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
