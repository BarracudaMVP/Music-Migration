"""
MVP2: Перенос лайкнутых артистов Яндекс Музыки → подписки на SoundCloud.
"""
from dataclasses import dataclass
from loguru import logger

from core.db import (
    bulk_insert_artists,
    get_pending_artists,
    update_artist,
    get_artist_stats,
)
from core.yandex.client import YandexMusicClient
from core.soundcloud.client import SoundCloudClient
from core.matcher import find_best_match, SCCandidate


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


async def migrate_artists(
    ym_client: YandexMusicClient,
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
) -> ArtistMigrationStats:
    """Пайплайн миграции артистов."""
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
        SCCandidate(
            sc_id=u.id,
            sc_url=u.url,
            artist=u.username,
            title="",
        )
        for u in sc_users
    ]

    # Для артистов матчим только по имени — передаём имя и как artist, и как title
    match = find_best_match(ym_name, ym_name, candidates)
    if not match or not match.matched:
        await update_artist(artist_id, status="not_found")
        return "not_found"

    success = await sc_client.follow_user(match.sc_id)
    if success:
        await update_artist(
            artist_id,
            status="followed",
            sc_user_id=match.sc_id,
            sc_username=match.sc_artist,
            match_score=match.score,
        )
        return "followed"

    await update_artist(artist_id, status="error")
    return "error"
