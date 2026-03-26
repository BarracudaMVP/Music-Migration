"""
Миграция → SoundCloud (треки, плейлисты, артисты из любого источника).

Пайплайн для YM / Spotify / File → SC:
1. Загружаем треки из источника
2. Сохраняем в БД со статусом 'pending' (idempotent)
3. Для каждого pending-трека: ищем на SC, матчим, добавляем в плейлист
4. Возвращаем итоговую статистику

При повторном запуске пропускает уже обработанные треки.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from loguru import logger

from core.db import (
    create_migration,
    update_migration,
    get_migration,
    bulk_insert_tracks,
    get_pending_tracks,
    get_previously_migrated_ym_ids,
    update_track,
    get_track_stats,
    create_playlist_record,
    update_playlist,
    get_pending_playlists,
    get_liked_sc_tracks,
    bulk_insert_artists,
    get_pending_artists,
    update_artist,
    get_artist_stats,
)
from config import settings
from core.yandex.client import YandexMusicClient
from core.spotify.client import SpotifyClient
from core.soundcloud.client import SoundCloudClient, LikeNotSupportedError
from core.matcher import find_best_match, split_artists, TrackCandidate


# ── Stats ─────────────────────────────────────────────────────────────────────


@dataclass
class MigrationStats:
    total: int = 0
    liked: int = 0          # напрямую лайкнуто через like_track API
    in_playlist: int = 0    # добавлено в плейлист (playlist_mode или fallback)
    not_found: int = 0
    errors: int = 0
    uncertain: int = 0  # найдены, но score ниже порога — сохранены в not_found
    skipped: int = 0   # уже перенесены в предыдущих запусках — пропущены

    @property
    def success(self) -> int:
        """Суммарно успешно перенесено (лайки + плейлист)."""
        return self.liked + self.in_playlist

    def __str__(self) -> str:
        parts = (
            f"Всего: {self.total} | "
            f"Перенесено: {self.success} (лайков: {self.liked}, в плейлист: {self.in_playlist}) | "
            f"Не найдено: {self.not_found} | "
            f"Сомнительных: {self.uncertain} | "
            f"Ошибок: {self.errors}"
        )
        if self.skipped:
            parts += f" | Пропущено (уже перенесено): {self.skipped}"
        return parts


@dataclass
class PlaylistMigrationStats:
    total: int = 0
    created: int = 0
    errors: int = 0

    def __str__(self) -> str:
        return (
            f"Плейлистов всего: {self.total} | "
            f"Создано: {self.created} | "
            f"Ошибок: {self.errors}"
        )


@dataclass
class ArtistMigrationStats:
    total: int = 0
    followed: int = 0
    not_found: int = 0
    errors: int = 0

    def __str__(self) -> str:
        return (
            f"Артистов всего: {self.total} | "
            f"Подписок: {self.followed} | "
            f"Не найдено: {self.not_found} | "
            f"Ошибок: {self.errors}"
        )


@dataclass
class FullMigrationStats:
    tracks: MigrationStats
    playlists: PlaylistMigrationStats | None = None
    artists: ArtistMigrationStats | None = None

    def __str__(self) -> str:
        parts = [str(self.tracks)]
        if self.playlists:
            parts.append(str(self.playlists))
        if self.artists:
            parts.append(str(self.artists))
        return "\n".join(parts)


# ── Tracks ────────────────────────────────────────────────────────────────────


async def migrate_tracks(
    ym_client: YandexMusicClient,
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
    playlist_mode: bool = False,
    track_limit: int | None = None,
    skip_already_migrated: bool = True,
    like_tracks: bool = False,
) -> MigrationStats:
    """Переносит лайкнутые треки Яндекс Музыки → SoundCloud."""
    await update_migration(migration_id, status="running")

    logger.info("Шаг 1/3: загружаю треки из Яндекс Музыки...")
    ym_tracks = await ym_client.get_liked_tracks(limit=track_limit)
    logger.info(f"Загружено {len(ym_tracks)} треков" + (f" (лимит {track_limit})" if track_limit else ""))

    if not ym_tracks:
        logger.warning("Нет лайкнутых треков в Яндекс Музыке")
        await update_migration(migration_id, status="done")
        return MigrationStats()

    logger.info(f"Шаг 2/3: сохраняю {len(ym_tracks)} треков в БД...")
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
                "ym_id": t.id,
                "ym_artist": t.artists_str,
                "ym_title": t.title,
                "ym_album": t.album,
            }
            for t in ym_tracks
        ],
        already_migrated=already_migrated,
    )

    logger.info("Шаг 3/3: обрабатываю треки...")
    stats = await _run_pending_loop(sc_client, migration_id, progress_callback, playlist_mode=playlist_mode, like_tracks=like_tracks)
    stats.skipped = skipped

    await update_migration(migration_id, status="done")
    logger.info(f"Миграция завершена. {stats}")
    return stats


async def migrate_spotify_tracks(
    spotify_client: SpotifyClient,
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
    playlist_mode: bool = False,
    track_limit: int | None = None,
    skip_already_migrated: bool = True,
    like_tracks: bool = False,
) -> MigrationStats:
    """Переносит лайкнутые треки Spotify → SoundCloud."""
    await update_migration(migration_id, status="running")

    logger.info("Шаг 1/3: загружаю треки из Spotify...")
    sp_tracks = await spotify_client.get_liked_tracks(limit=track_limit)

    if not sp_tracks:
        logger.warning("Нет лайкнутых треков в Spotify")
        await update_migration(migration_id, status="done")
        return MigrationStats()

    logger.info(f"Загружено {len(sp_tracks)} треков" + (f" (лимит {track_limit})" if track_limit else ""))
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
    stats = await _run_pending_loop(sc_client, migration_id, progress_callback, playlist_mode=playlist_mode, like_tracks=like_tracks)
    stats.skipped = skipped

    await update_migration(migration_id, status="done")
    logger.info(f"Spotify миграция треков завершена. {stats}")
    return stats


async def migrate_from_file_tracks(
    sc_client: SoundCloudClient,
    migration_id: int,
    tracks_data: list[dict],
    progress_callback=None,
    playlist_mode: bool = False,
    track_limit: int | None = None,
) -> MigrationStats:
    """
    Пайплайн переноса треков из файла → SC.
    tracks_data: list[{"artist": str, "title": str}]
    """
    await update_migration(migration_id, status="running")

    if track_limit:
        tracks_data = tracks_data[:track_limit]
        logger.info(f"Лимит треков: {track_limit}, будет обработано {len(tracks_data)}")
    logger.info(f"Вставляю {len(tracks_data)} треков из файла в БД...")
    await bulk_insert_tracks(
        migration_id,
        [
            {
                "ym_id": f"file:{i}",
                "ym_artist": t["artist"],
                "ym_title": t["title"],
                "ym_album": "",
            }
            for i, t in enumerate(tracks_data)
        ],
    )

    stats = await _run_pending_loop(sc_client, migration_id, progress_callback, playlist_mode=playlist_mode)
    await update_migration(migration_id, status="done")
    logger.info(f"Перенос из файла завершён. {stats}")
    return stats


async def _run_pending_loop(
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
    playlist_mode: bool = False,
    like_tracks: bool = False,
) -> MigrationStats:
    """Обрабатывает все pending-треки миграции: поиск → матчинг → лайк/плейлист."""
    pending = await get_pending_tracks(migration_id)
    total = len(pending)
    stats = MigrationStats(total=total)
    collected_ids: list[int] = []

    for i, row in enumerate(pending, start=1):
        track_str = f"{row['ym_artist']} — {row['ym_title']}"

        logger.info(f"[{i}/{total}] ▶ {track_str}")
        if progress_callback:
            await progress_callback(i, total, track_str)

        try:
            result, sc_id = await _process_one_track(sc_client, row, playlist_mode=playlist_mode, like_tracks=like_tracks)
        except Exception as e:
            logger.error(f"[{i}/{total}] Ошибка при обработке {track_str!r}: {e}")
            await update_track(row["id"], status="error")
            stats.errors += 1
            continue

        if result == "liked":
            stats.liked += 1
            if sc_id:  # liked tracks also go into the playlist
                collected_ids.append(sc_id)
            logger.debug(f"[{i}/{total}] OK (liked): {track_str}")
        elif result == "in_playlist":
            stats.in_playlist += 1
            if sc_id:  # collect for playlist creation
                collected_ids.append(sc_id)
            logger.debug(f"[{i}/{total}] OK (playlist): {track_str}")
        elif result == "uncertain":
            stats.uncertain += 1
            logger.debug(f"[{i}/{total}] uncertain: {track_str}")
        elif result == "error":
            stats.errors += 1
        else:
            stats.not_found += 1
            logger.debug(f"[{i}/{total}] not found: {track_str}")

    if collected_ids:
        logger.info(f"Создаю плейлисты для {len(collected_ids)} найденных треков...")
        await _create_liked_playlists(sc_client, collected_ids)

    return stats


async def _create_liked_playlists(sc_client: SoundCloudClient, track_ids: list[int]) -> None:
    """Создаёт плейлисты батчами по sc_playlist_batch_size треков."""
    batch_size = settings.sc_playlist_batch_size
    batches = [track_ids[i:i + batch_size] for i in range(0, len(track_ids), batch_size)]
    total = len(batches)
    for n, batch in enumerate(batches, start=1):
        title = f"YM Liked #{n}" if total > 1 else "YM Liked"
        logger.info(f"Создаю плейлист {title!r} ({len(batch)} треков)...")
        playlist = await sc_client.create_playlist(title, batch)
        if playlist:
            logger.info(f"Плейлист {title!r} создан: {playlist.url}")
        else:
            logger.warning(f"Не удалось создать плейлист {title!r}")


async def _process_one_track(
    sc_client: SoundCloudClient, row: dict, playlist_mode: bool = False, like_tracks: bool = False
) -> tuple[str, int | None]:
    """
    Обрабатывает один трек: поиск → матчинг → лайк или сбор ID для плейлиста.
    Возвращает: (status, sc_id | None)
      status: 'liked' | 'not_found' | 'uncertain' | 'error'
    """
    ym_artist = row["ym_artist"]
    ym_title = row["ym_title"]
    track_id = row["id"]

    artists = split_artists(ym_artist)
    queries = [f"{a} {ym_title}" for a in artists]

    if len(queries) > 1:
        results_list = await asyncio.gather(
            *[sc_client.search_tracks(q) for q in queries]
        )
    else:
        results_list = [await sc_client.search_tracks(queries[0])]

    all_candidates: dict[int, TrackCandidate] = {}
    for sc_results in results_list:
        for t in sc_results:
            if t.id not in all_candidates:
                all_candidates[t.id] = TrackCandidate(
                    track_id=t.id,
                    track_url=t.url,
                    artist=t.artist,
                    title=t.title,
                )

    candidates = list(all_candidates.values())

    if not candidates:
        fallback_results = await sc_client.search_tracks(ym_title)
        candidates = [
            TrackCandidate(track_id=t.id, track_url=t.url, artist=t.artist, title=t.title)
            for t in fallback_results
        ]

    match = find_best_match(ym_artist, ym_title, candidates)

    if match is None:
        logger.info(f"[match] {ym_artist} — {ym_title} → not_found (candidates={len(candidates)})")
        await update_track(track_id, status="not_found")
        return "not_found", None

    if match.matched:
        logger.info(f"[match] {ym_artist} — {ym_title} → {match.cand_artist} — {match.cand_title} (score={match.score:.0f})")
    elif match.uncertain:
        logger.info(f"[match] {ym_artist} — {ym_title} → uncertain: {match.cand_artist} — {match.cand_title} (score={match.score:.0f})")
    else:
        logger.info(f"[match] {ym_artist} — {ym_title} → not_found (score={match.score:.0f})")

    if match.uncertain:
        await update_track(
            track_id,
            status="not_found",
            sc_id=match.track_id,
            sc_url=match.track_url,
            match_score=match.score,
        )
        return "uncertain", None

    if not match.matched:
        await update_track(track_id, status="not_found", match_score=match.score)
        return "not_found", None

    if like_tracks:
        # like_tracks=True → пробуем прямой лайк; при 404 — fallback в плейлист
        try:
            success = await sc_client.like_track(match.track_id)
            if success:
                await update_track(
                    track_id,
                    status="liked",
                    sc_id=match.track_id,
                    sc_url=match.track_url,
                    match_score=match.score,
                )
                return "liked", match.track_id  # лайкнут + добавить в плейлист
            else:
                await update_track(track_id, status="error")
                return "error", None
        except LikeNotSupportedError:
            logger.info(f"[match] like_track 404 → fallback to playlist для {ym_artist} — {ym_title}")
            await update_track(
                track_id,
                status="in_playlist",
                sc_id=match.track_id,
                sc_url=match.track_url,
                match_score=match.score,
            )
            return "in_playlist", match.track_id

    if playlist_mode:
        # playlist_mode=True → только плейлист, лайк не вызывается
        await update_track(
            track_id,
            status="in_playlist",
            sc_id=match.track_id,
            sc_url=match.track_url,
            match_score=match.score,
        )
        return "in_playlist", match.track_id

    # Ни like_tracks ни playlist_mode — пробуем прямой лайк без плейлиста
    success = await sc_client.like_track(match.track_id)
    if success:
        await update_track(
            track_id,
            status="liked",
            sc_id=match.track_id,
            sc_url=match.track_url,
            match_score=match.score,
        )
        return "liked", None
    else:
        await update_track(track_id, status="error")
        return "error", None


# ── Playlists ─────────────────────────────────────────────────────────────────


async def migrate_playlists(
    ym_client: YandexMusicClient,
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
) -> PlaylistMigrationStats:
    """Пайплайн миграции плейлистов YM → SC."""
    logger.info("Загружаю плейлисты из ЯМ...")
    ym_playlists = await ym_client.get_playlists()

    if not ym_playlists:
        logger.info("Нет плейлистов для переноса")
        return PlaylistMigrationStats()

    for pl in ym_playlists:
        await create_playlist_record(migration_id, pl.kind, pl.title)

    track_cache = await get_liked_sc_tracks(migration_id)
    logger.info(f"Кэш треков: {len(track_cache)} записей")

    pending = await get_pending_playlists(migration_id)
    total = len(pending)
    stats = PlaylistMigrationStats(total=total)

    pl_by_kind = {pl.kind: pl for pl in ym_playlists}

    for i, row in enumerate(pending, start=1):
        if progress_callback:
            await progress_callback(i, total, row["ym_title"])

        ym_pl = pl_by_kind.get(row["ym_kind"])
        if not ym_pl:
            await update_playlist(row["id"], status="error")
            stats.errors += 1
            continue

        try:
            result = await _process_one_playlist(
                sc_client, row, ym_pl, migration_id, track_cache
            )
        except Exception as e:
            logger.error(f"Ошибка при обработке плейлиста {row['ym_title']!r}: {e}")
            await update_playlist(row["id"], status="error")
            stats.errors += 1
            continue

        if result:
            stats.created += 1
        else:
            stats.errors += 1

    logger.info(f"Плейлисты готовы. {stats}")
    return stats


async def _process_one_playlist(
    sc_client: SoundCloudClient,
    row: dict,
    ym_pl,
    migration_id: int,
    track_cache: dict[str, int],
) -> bool:
    """
    Создаёт один плейлист на SoundCloud.
    Треки берёт из кэша БД; для не найденных делает новый поиск.
    """
    sc_track_ids: list[int] = []

    for track in ym_pl.tracks:
        sc_id = track_cache.get(track.id)
        if sc_id:
            sc_track_ids.append(sc_id)
            continue

        query = f"{track.artists_str} {track.title}"
        results = await sc_client.search_tracks(query)
        if not results:
            continue

        candidates = [
            TrackCandidate(track_id=t.id, track_url=t.url, artist=t.artist, title=t.title)
            for t in results
        ]
        match = find_best_match(track.artists_str, track.title, candidates)
        if match and match.matched:
            sc_track_ids.append(match.track_id)
            track_cache[track.id] = match.track_id

    if not sc_track_ids:
        logger.warning(f"Плейлист {row['ym_title']!r}: ни один трек не найден на SC")
        await update_playlist(row["id"], status="error")
        return False

    sc_pl = await sc_client.create_playlist(row["ym_title"], sc_track_ids)
    if sc_pl:
        await update_playlist(row["id"], status="created", sc_playlist_id=sc_pl.id)
        logger.info(
            f"Создан плейлист {row['ym_title']!r}: "
            f"{len(sc_track_ids)}/{len(ym_pl.tracks)} треков"
        )
        return True

    await update_playlist(row["id"], status="error")
    return False


# ── Artists ───────────────────────────────────────────────────────────────────


async def migrate_artists(
    ym_client: YandexMusicClient,
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
) -> ArtistMigrationStats:
    """Пайплайн миграции артистов YM → SC."""
    logger.info("Загружаю лайкнутых артистов из ЯМ...")
    ym_artists = await ym_client.get_liked_artists()

    if not ym_artists:
        logger.info("Нет лайкнутых артистов")
        return ArtistMigrationStats()

    await bulk_insert_artists(
        migration_id,
        [{"ym_name": a.name} for a in ym_artists],
    )

    pending = await get_pending_artists(migration_id)
    total = len(pending)
    stats = ArtistMigrationStats(total=total)
    logger.info(f"Обрабатываю {total} артистов...")

    for i, row in enumerate(pending, start=1):
        if progress_callback and i % 5 == 0:
            await progress_callback(i, total, row["ym_name"])

        try:
            result = await _process_one_artist(sc_client, row)
        except Exception as e:
            logger.error(f"Ошибка при обработке артиста {row['ym_name']!r}: {e}")
            await update_artist(row["id"], status="error")
            stats.errors += 1
            continue

        if result == "followed":
            stats.followed += 1
        elif result == "not_found":
            stats.not_found += 1
        else:
            stats.errors += 1

    logger.info(f"Артисты готовы. {stats}")
    return stats


async def _process_one_artist(sc_client: SoundCloudClient, row: dict) -> str:
    ym_name = row["ym_name"]
    artist_id = row["id"]

    sc_users = await sc_client.search_users(ym_name)
    if not sc_users:
        await update_artist(artist_id, status="not_found")
        return "not_found"

    candidates = [
        TrackCandidate(
            track_id=u.id,
            track_url=u.url,
            artist=u.username,
            title="",
        )
        for u in sc_users
    ]

    match = find_best_match(ym_name, ym_name, candidates)
    if not match or not match.matched:
        await update_artist(artist_id, status="not_found")
        return "not_found"

    success = await sc_client.follow_user(match.track_id)
    if success:
        await update_artist(
            artist_id,
            status="followed",
            sc_user_id=match.track_id,
            sc_username=match.cand_artist,
            match_score=match.score,
        )
        return "followed"

    await update_artist(artist_id, status="error")
    return "error"


# ── Entry points ──────────────────────────────────────────────────────────────


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
    like_tracks: bool = False,
) -> MigrationStats:
    """
    Точка входа для ARQ worker (Spotify → SC).
    mode: 'tracks' — только треки, 'full' — треки + плейлисты (TODO).
    """
    spotify_client = await SpotifyClient(spotify_token).init()
    sc_client = await SoundCloudClient(soundcloud_token).init()

    try:
        stats = await migrate_spotify_tracks(
            spotify_client, sc_client, migration_id, progress_callback,
            playlist_mode=playlist_mode, track_limit=track_limit,
            skip_already_migrated=skip_already_migrated,
            like_tracks=like_tracks,
        )
    finally:
        await spotify_client.close()
        await sc_client.close()

    return stats


async def run_migration(
    yandex_token: str,
    soundcloud_token: str,
    user_id: str = "cli",
    do_playlists: bool = False,
    do_artists: bool = False,
    progress_callback=None,
    on_migration_created=None,
    migration_id: int | None = None,
    playlist_mode: bool = False,
    track_limit: int | None = None,
    skip_already_migrated: bool = True,
    like_tracks: bool = False,
) -> tuple[int, FullMigrationStats]:
    """
    Точка входа для CLI и бота (YM → SC).
    Инициализирует клиентов, создаёт запись в БД, запускает пайплайн.
    Возвращает (migration_id, FullMigrationStats).
    """
    ym_client = await YandexMusicClient(yandex_token, proxy_url=settings.ym_proxy_url or None).init()
    sc_client = await SoundCloudClient(soundcloud_token).init()

    if migration_id is None:
        migration_id = await create_migration(user_id)
        logger.info(f"Создана миграция #{migration_id} для пользователя {user_id!r}")

        if on_migration_created:
            await on_migration_created(migration_id)
    else:
        logger.info(f"Используется существующая миграция #{migration_id} для пользователя {user_id!r}")

    try:
        track_stats = await migrate_tracks(
            ym_client, sc_client, migration_id, progress_callback,
            playlist_mode=playlist_mode, track_limit=track_limit,
            skip_already_migrated=skip_already_migrated,
            like_tracks=like_tracks,
        )

        pl_stats = None
        if do_playlists:
            logger.info("Запускаю перенос плейлистов...")
            pl_stats = await migrate_playlists(ym_client, sc_client, migration_id)

        artist_stats = None
        if do_artists:
            logger.info("Запускаю перенос артистов...")
            artist_stats = await migrate_artists(ym_client, sc_client, migration_id)

    finally:
        await sc_client.close()

    return migration_id, FullMigrationStats(
        tracks=track_stats,
        playlists=pl_stats,
        artists=artist_stats,
    )
