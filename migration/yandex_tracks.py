"""
Migration pipeline: any source → Yandex Music liked tracks.

Source tracks are passed as [{"artist": str, "title": str}] —
fetched from any adapter (SoundCloud, Spotify, File, etc.).

Pipeline:
1. Insert source tracks into DB with status 'pending'
2. For each pending track: search on YM, fuzzy-match, like
3. Return stats
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from loguru import logger

from core.db import (
    update_migration,
    bulk_insert_tracks,
    get_pending_tracks,
    update_track,
)
from core.yandex.client import YandexMusicClient
from core.matcher import find_best_match, split_artists, SCCandidate

# Pause between YM like operations to avoid rate limiting
_YM_WRITE_SLEEP = 1.0
# Number of search results to consider per query
_SEARCH_LIMIT = 10


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
    ym_client: YandexMusicClient,
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

    stats = await _run_pending_loop(ym_client, migration_id, progress_callback)
    await update_migration(migration_id, status="done")
    logger.info(f"Перенос в Яндекс Музыку завершён. {stats}")
    return stats


async def _run_pending_loop(
    ym_client: YandexMusicClient,
    migration_id: int,
    progress_callback=None,
) -> YandexMigrationStats:
    """Process all pending tracks: search on YM → match → like."""
    pending = await get_pending_tracks(migration_id)
    total = len(pending)
    stats = YandexMigrationStats(total=total)

    for i, row in enumerate(pending, start=1):
        track_str = f"{row['ym_artist']} — {row['ym_title']}"
        logger.info(f"[{i}/{total}] ▶ {track_str}")
        if progress_callback:
            await progress_callback(i, total, track_str)

        try:
            result = await _process_one_track(ym_client, row)
        except Exception as e:
            logger.error(f"[{i}/{total}] Ошибка: {track_str!r}: {e}")
            await update_track(row["id"], status="error")
            stats.errors += 1
            continue

        if result == "liked":
            stats.liked += 1
            logger.debug(f"[{i}/{total}] OK: {track_str}")
        elif result == "uncertain":
            stats.uncertain += 1
            logger.debug(f"[{i}/{total}] uncertain: {track_str}")
        else:
            stats.not_found += 1
            logger.debug(f"[{i}/{total}] not found: {track_str}")

        await asyncio.sleep(_YM_WRITE_SLEEP)

    return stats


async def _process_one_track(ym_client: YandexMusicClient, row: dict) -> str:
    """Search YM, fuzzy-match, like. Returns 'liked' | 'not_found' | 'uncertain'."""
    src_artist = row["ym_artist"]
    src_title = row["ym_title"]
    track_id = row["id"]

    # Multi-query strategy: one search per individual artist
    artists = split_artists(src_artist)
    queries = [f"{a} {src_title}" for a in artists]

    if len(queries) > 1:
        results_list = await asyncio.gather(
            *[ym_client.search_tracks(q, limit=_SEARCH_LIMIT) for q in queries]
        )
    else:
        results_list = [await ym_client.search_tracks(queries[0], limit=_SEARCH_LIMIT)]

    # Deduplicate by YM track ID
    all_candidates: dict[int, SCCandidate] = {}
    for ym_results in results_list:
        for t in ym_results:
            ym_int_id = int(t.id)
            if ym_int_id not in all_candidates:
                all_candidates[ym_int_id] = SCCandidate(
                    sc_id=ym_int_id,   # used as dedup key
                    sc_url=t.id,       # string YM track ID for liking
                    artist=t.artists_str,
                    title=t.title,
                )

    candidates = list(all_candidates.values())

    # Fallback: title-only search
    if not candidates:
        fallback = await ym_client.search_tracks(src_title, limit=_SEARCH_LIMIT)
        candidates = [
            SCCandidate(sc_id=int(t.id), sc_url=t.id, artist=t.artists_str, title=t.title)
            for t in fallback
        ]

    match = find_best_match(src_artist, src_title, candidates)

    if match is None:
        await update_track(track_id, status="not_found")
        return "not_found"

    if match.uncertain:
        await update_track(track_id, status="not_found", match_score=match.score)
        return "uncertain"

    if not match.matched:
        await update_track(track_id, status="not_found", match_score=match.score)
        return "not_found"

    # Like on YM — sc_url stores the YM track ID string
    success = await ym_client.like_track(match.sc_url)
    if success:
        await update_track(track_id, status="liked", match_score=match.score)
        return "liked"
    else:
        await update_track(track_id, status="error")
        return "error"
