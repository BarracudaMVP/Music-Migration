"""
MVP2: Перенос плейлистов Яндекс Музыки → SoundCloud.

Использует кэш из БД (треки уже перенесённые в MVP1) чтобы не
искать одни и те же треки повторно.
"""
from dataclasses import dataclass
from loguru import logger

from core.db import (
    create_playlist_record,
    update_playlist,
    get_pending_playlists,
    get_liked_sc_tracks,
)
from core.yandex.client import YandexMusicClient
from core.soundcloud.client import SoundCloudClient
from core.matcher import find_best_match, TrackCandidate


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


async def migrate_playlists(
    ym_client: YandexMusicClient,
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
) -> PlaylistMigrationStats:
    """Пайплайн миграции плейлистов."""
    logger.info("Загружаю плейлисты из ЯМ...")
    ym_playlists = await ym_client.get_playlists()

    if not ym_playlists:
        logger.info("Нет плейлистов для переноса")
        return PlaylistMigrationStats()

    # Создаём записи в БД
    for pl in ym_playlists:
        await create_playlist_record(migration_id, pl.kind, pl.title)

    # Кэш уже перенесённых треков {ym_id: sc_id}
    track_cache = await get_liked_sc_tracks(migration_id)
    logger.info(f"Кэш треков: {len(track_cache)} записей")

    pending = await get_pending_playlists(migration_id)
    total = len(pending)
    stats = PlaylistMigrationStats(total=total)

    # Создаём маппинг kind → YMPlaylist для быстрого доступа
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
        # Сначала пробуем кэш
        sc_id = track_cache.get(track.id)
        if sc_id:
            sc_track_ids.append(sc_id)
            continue

        # Новый поиск
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
            track_cache[track.id] = match.track_id  # обновляем локальный кэш

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
