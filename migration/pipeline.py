"""
Platform-agnostic migration pipeline: search → fuzzy match → write.

Used by to_yandex.py and to_spotify.py (any destination that implements
AdapterWriteSession). SoundCloud destination retains its own pipeline
in to_soundcloud.py due to playlist-batching and artist-migration logic.

Pipeline flow (per track):
1. Build multi-query list via split_artists()
2. Optionally expand with transliteration variants (if session.apply_transliteration)
3. Search on destination in parallel → deduplicate by track_id
4. Fallback to title-only search if pool is empty
5. Fuzzy-match with find_best_match()
6. Call session.write_track(match) → status
7. Update DB record
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from loguru import logger

from config import settings
from core.db import get_pending_tracks, update_track
from core.matcher import find_best_match, split_artists, transliterate_variants, TrackCandidate
from core.services.base import AdapterWriteSession


@dataclass
class TrackPipelineStats:
    total: int = 0
    liked: int = 0
    in_playlist: int = 0
    not_found: int = 0
    errors: int = 0
    uncertain: int = 0

    @property
    def success(self) -> int:
        return self.liked + self.in_playlist

    def __str__(self) -> str:
        return (
            f"Всего: {self.total} | "
            f"Перенесено: {self.success} (лайков: {self.liked}, в плейлист: {self.in_playlist}) | "
            f"Не найдено: {self.not_found} | Ошибок: {self.errors}"
        )


async def process_one_track(
    session: AdapterWriteSession,
    row: dict,
) -> str:
    """
    Universal: multi-query search → fuzzy match → write.

    Returns status: 'liked' | 'in_playlist' | 'not_found' | 'uncertain' | 'error'.
    Updates DB track record.
    """
    src_artist = row["ym_artist"]
    src_title = row["ym_title"]
    track_id = row["id"]

    artists = split_artists(src_artist)
    queries: list[str] = []
    seen_queries: set[str] = set()

    for a in artists:
        q = f"{a} {src_title}"
        if q not in seen_queries:
            queries.append(q)
            seen_queries.add(q)

    # Transliteration variants (e.g. Spotify: Cyrillic artists indexed under Latin names)
    if session.apply_transliteration:
        for a in artists:
            for variant in transliterate_variants(a):
                if variant != a:
                    q = f"{variant} {src_title}"
                    if q not in seen_queries:
                        queries.append(q)
                        seen_queries.add(q)

    if len(queries) > 1:
        results_list = await asyncio.gather(
            *[session.search_track(q, limit=settings.search_limit) for q in queries]
        )
    else:
        results_list = [await session.search_track(queries[0], limit=settings.search_limit)]

    # Deduplicate by track_id
    all_candidates: dict[int, TrackCandidate] = {}
    for results in results_list:
        for c in results:
            if c.track_id not in all_candidates:
                all_candidates[c.track_id] = c

    candidates = list(all_candidates.values())

    # Fallback: title-only search
    if not candidates:
        fallback = await session.search_track(src_title, limit=settings.search_limit)
        candidates = list({c.track_id: c for c in fallback}.values())

    match = find_best_match(src_artist, src_title, candidates)

    if match is None:
        logger.info(f"[match] {src_artist} — {src_title} → not_found (candidates={len(candidates)})")
        await update_track(track_id, status="not_found")
        return "not_found"

    if match.matched:
        logger.info(
            f"[match] {src_artist} — {src_title} → "
            f"{match.cand_artist} — {match.cand_title} (score={match.score:.0f})"
        )
    elif match.uncertain:
        logger.info(
            f"[match] {src_artist} — {src_title} → uncertain: "
            f"{match.cand_artist} — {match.cand_title} (score={match.score:.0f})"
        )
    else:
        logger.info(f"[match] {src_artist} — {src_title} → not_found (score={match.score:.0f})")

    if match.uncertain:
        await update_track(track_id, status="not_found", sc_url=match.track_url, match_score=match.score)
        return "uncertain"

    if not match.matched:
        await update_track(track_id, status="not_found", match_score=match.score)
        return "not_found"

    status = await session.write_track(match)
    if status in ("liked", "in_playlist"):
        await update_track(track_id, status=status, sc_url=match.track_url, match_score=match.score)
    else:
        await update_track(track_id, status="error")
    return status


async def run_pending_tracks_loop(
    session: AdapterWriteSession,
    migration_id: int,
    progress_callback=None,
    write_sleep: float = 0.0,
) -> TrackPipelineStats:
    """Process all pending tracks for migration_id using the given write session."""
    pending = await get_pending_tracks(migration_id)
    total = len(pending)
    stats = TrackPipelineStats(total=total)

    for i, row in enumerate(pending, start=1):
        track_str = f"{row['ym_artist']} — {row['ym_title']}"
        logger.info(f"[{i}/{total}] ▶ {track_str}")
        if progress_callback:
            await progress_callback(i, total, track_str)

        try:
            status = await process_one_track(session, row)
        except Exception as e:
            logger.error(f"[{i}/{total}] Ошибка: {track_str!r}: {e}")
            await update_track(row["id"], status="error")
            stats.errors += 1
            continue

        if status == "liked":
            stats.liked += 1
        elif status == "in_playlist":
            stats.in_playlist += 1
        elif status == "uncertain":
            stats.uncertain += 1
            stats.not_found += 1
        elif status == "error":
            stats.errors += 1
        else:  # not_found
            stats.not_found += 1

        if write_sleep > 0:
            await asyncio.sleep(write_sleep)

    return stats
