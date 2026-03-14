"""
Миграция треков → Spotify (из любого источника): лайки треков + подписки на артистов.

Source tracks are passed as [{"artist": str, "title": str}] —
fetched from any adapter (SoundCloud, Yandex Music, File, etc.).

Pipeline:
1. Insert source tracks into DB with status 'pending'
2. For each pending track: search on Spotify, fuzzy-match, like
3. If artists provided: search Spotify, fuzzy-match, follow
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
    bulk_insert_artists,
    get_pending_artists,
    update_artist,
)
from core.spotify.client import SpotifyClient
from core.matcher import find_best_match, split_artists, transliterate_variants, TrackCandidate

# Pause between Spotify write operations to avoid rate limiting
_SPOTIFY_WRITE_SLEEP = 0.5
# Number of search results to consider per query
_SEARCH_LIMIT = 10


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
    spotify_client: SpotifyClient,
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

    stats = await _run_pending_tracks_loop(spotify_client, migration_id, progress_callback)

    if artists_data:
        logger.info(f"Вставляю {len(artists_data)} артистов в БД (миграция #{migration_id})...")
        await bulk_insert_artists(
            migration_id,
            [{"ym_name": a["name"]} for a in artists_data],
        )
        followed, not_found = await _run_pending_artists_loop(spotify_client, migration_id)
        stats.artists_followed = followed
        stats.artists_not_found = not_found

    await update_migration(migration_id, status="done")
    logger.info(f"Перенос в Spotify завершён. {stats}")
    return stats


async def _run_pending_tracks_loop(
    client: SpotifyClient,
    migration_id: int,
    progress_callback=None,
) -> SpotifyWriteStats:
    """Process all pending tracks: search on Spotify → match → like."""
    pending = await get_pending_tracks(migration_id)
    total = len(pending)
    stats = SpotifyWriteStats(total=total)

    for i, row in enumerate(pending, start=1):
        track_str = f"{row['ym_artist']} — {row['ym_title']}"
        logger.info(f"[{i}/{total}] ▶ {track_str}")
        if progress_callback:
            await progress_callback(i, total, track_str)

        try:
            result = await _process_one_track(client, row)
        except Exception as e:
            logger.error(f"[{i}/{total}] Ошибка: {track_str!r}: {e}")
            await update_track(row["id"], status="error")
            stats.errors += 1
            continue

        if result == "liked":
            stats.liked += 1
            logger.debug(f"[{i}/{total}] OK: {track_str}")
        elif result == "error":
            stats.errors += 1
        else:
            stats.not_found += 1
            logger.debug(f"[{i}/{total}] not found: {track_str}")

        await asyncio.sleep(_SPOTIFY_WRITE_SLEEP)

    return stats


async def _run_pending_artists_loop(
    client: SpotifyClient,
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
            artists = await client.search_artists(name, limit=5)
            if not artists:
                await update_artist(row["id"], status="not_found")
                not_found += 1
                continue

            # Pick closest name match (simple: first result usually best)
            best = None
            best_score = 0.0
            for a in artists:
                from core.matcher import normalize, _score_pair
                score = _score_pair(normalize(name), normalize(a.name))
                if score > best_score:
                    best_score = score
                    best = a

            from config import settings as _cfg
            if best and best_score >= _cfg.match_threshold:
                success = await client.follow_artist(best.id)
                if success:
                    await update_artist(
                        row["id"],
                        status="liked",
                        sc_user_id=None,
                        sc_username=best.name,
                        match_score=best_score,
                    )
                    followed += 1
                    logger.debug(f"[artist {i}/{total}] followed: {best.name!r} ({best_score:.0f})")
                else:
                    await update_artist(row["id"], status="error")
            else:
                await update_artist(row["id"], status="not_found", match_score=best_score if best else None)
                not_found += 1
                logger.debug(f"[artist {i}/{total}] not found: {name!r}")

        except Exception as e:
            logger.error(f"[artist {i}/{total}] Ошибка: {name!r}: {e}")
            await update_artist(row["id"], status="error")

        await asyncio.sleep(_SPOTIFY_WRITE_SLEEP)

    return followed, not_found


async def _process_one_track(client: SpotifyClient, row: dict) -> str:
    """Search Spotify, fuzzy-match, like. Returns 'liked' | 'not_found'."""
    src_artist = row["ym_artist"]
    src_title = row["ym_title"]
    track_id = row["id"]

    # Multi-query strategy: one search per individual artist
    artists = split_artists(src_artist)
    queries = [f"{a} {src_title}" for a in artists]

    # Transliterated variants: Cyrillic artist names may be indexed under Latin spelling on Spotify
    # (e.g. "Баста" → "Basta", "Моргенштерн" → "Morgenshtern")
    seen_queries = set(queries)
    for a in artists:
        for variant in transliterate_variants(a):
            if variant != a:
                q = f"{variant} {src_title}"
                if q not in seen_queries:
                    queries.append(q)
                    seen_queries.add(q)

    if len(queries) > 1:
        results_list = await asyncio.gather(
            *[client.search_tracks(q, limit=_SEARCH_LIMIT) for q in queries]
        )
    else:
        results_list = [await client.search_tracks(queries[0], limit=_SEARCH_LIMIT)]

    # Deduplicate by Spotify track ID
    all_candidates: dict[str, TrackCandidate] = {}
    for sp_results in results_list:
        for t in sp_results:
            if t.id not in all_candidates:
                all_candidates[t.id] = TrackCandidate(
                    track_id=hash(t.id) & 0x7FFFFFFF,  # dedup key (int)
                    track_url=t.id,                      # Spotify track ID for liking
                    artist=t.artists_str,
                    title=t.title,
                )

    candidates = list(all_candidates.values())

    # Fallback: title-only search
    if not candidates:
        fallback = await client.search_tracks(src_title, limit=_SEARCH_LIMIT)
        candidates = [
            TrackCandidate(
                track_id=hash(t.id) & 0x7FFFFFFF,
                track_url=t.id,
                artist=t.artists_str,
                title=t.title,
            )
            for t in fallback
        ]

    match = find_best_match(src_artist, src_title, candidates)

    if match is None or not match.matched:
        await update_track(track_id, status="not_found", match_score=match.score if match else None)
        return "not_found"

    # Like on Spotify — track_url stores the Spotify track ID string
    success = await client.like_track(match.track_url)
    if success:
        await update_track(track_id, status="liked", match_score=match.score)
        return "liked"
    else:
        await update_track(track_id, status="error")
        return "error"
