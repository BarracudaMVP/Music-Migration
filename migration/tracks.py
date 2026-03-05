"""
MVP1: Миграция лайкнутых треков Яндекс Музыки → SoundCloud.

Пайплайн:
1. Получаем треки из ЯМ
2. Сохраняем все в БД со статусом 'pending' (idempotent)
3. Для каждого pending-трека: ищем на SC, матчим, лайкаем
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
    bulk_insert_tracks,
    get_pending_tracks,
    update_track,
    get_track_stats,
)
from core.yandex.client import YandexMusicClient
from core.soundcloud.client import SoundCloudClient
from core.matcher import find_best_match, SCCandidate


@dataclass
class MigrationStats:
    total: int = 0
    liked: int = 0
    not_found: int = 0
    errors: int = 0
    uncertain: int = 0  # найдены, но score ниже порога — сохранены в not_found

    def __str__(self) -> str:
        return (
            f"Всего: {self.total} | "
            f"Перенесено: {self.liked} | "
            f"Не найдено: {self.not_found} | "
            f"Сомнительных: {self.uncertain} | "
            f"Ошибок: {self.errors}"
        )


async def migrate_tracks(
    ym_client: YandexMusicClient,
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
) -> MigrationStats:
    """
    Основной пайплайн миграции треков.

    progress_callback(current, total, track_str) — опциональный колбэк
    для обновления прогресса (используется ботом).
    """
    await update_migration(migration_id, status="running")

    # --- Шаг 1: загружаем треки из ЯМ ---
    logger.info("Шаг 1/3: загружаю треки из Яндекс Музыки...")
    ym_tracks = await ym_client.get_liked_tracks()

    if not ym_tracks:
        logger.warning("Нет лайкнутых треков в Яндекс Музыке")
        await update_migration(migration_id, status="done")
        return MigrationStats()

    # --- Шаг 2: сохраняем в БД ---
    logger.info(f"Шаг 2/3: сохраняю {len(ym_tracks)} треков в БД...")
    await bulk_insert_tracks(
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
    )

    # --- Шаг 3: обрабатываем pending-треки ---
    pending = await get_pending_tracks(migration_id)
    total = len(pending)
    logger.info(f"Шаг 3/3: обрабатываю {total} треков...")

    stats = MigrationStats(total=total)

    for i, row in enumerate(pending, start=1):
        track_str = f"{row['ym_artist']} — {row['ym_title']}"

        if progress_callback and i % 10 == 0:
            await progress_callback(i, total, track_str)

        try:
            result = await _process_one_track(sc_client, row)
        except Exception as e:
            logger.error(f"[{i}/{total}] Ошибка при обработке {track_str!r}: {e}")
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

    await update_migration(migration_id, status="done")
    logger.info(f"Миграция завершена. {stats}")
    return stats


async def _process_one_track(sc_client: SoundCloudClient, row: dict) -> str:
    """
    Обрабатывает один трек: поиск → матчинг → лайк.
    Возвращает: 'liked' | 'not_found' | 'uncertain'
    """
    ym_artist = row["ym_artist"]
    ym_title = row["ym_title"]
    track_id = row["id"]

    # Поиск на SoundCloud
    query = f"{ym_artist} {ym_title}"
    sc_results = await sc_client.search_tracks(query)

    if not sc_results:
        await update_track(track_id, status="not_found")
        return "not_found"

    # Матчинг
    candidates = [
        SCCandidate(
            sc_id=t.id,
            sc_url=t.url,
            artist=t.artist,
            title=t.title,
        )
        for t in sc_results
    ]
    match = find_best_match(ym_artist, ym_title, candidates)

    if match is None:
        await update_track(track_id, status="not_found")
        return "not_found"

    # Сомнительное совпадение — не лайкаем, сохраняем для ручной проверки
    if match.uncertain:
        await update_track(
            track_id,
            status="not_found",
            sc_id=match.sc_id,
            sc_url=match.sc_url,
            match_score=match.score,
        )
        return "uncertain"

    if not match.matched:
        await update_track(track_id, status="not_found", match_score=match.score)
        return "not_found"

    # Лайкаем
    success = await sc_client.like_track(match.sc_id)
    if success:
        await update_track(
            track_id,
            status="liked",
            sc_id=match.sc_id,
            sc_url=match.sc_url,
            match_score=match.score,
        )
        return "liked"
    else:
        await update_track(track_id, status="error")
        return "error"



async def run_migration(
    yandex_token: str,
    soundcloud_token: str,
    user_id: str = "cli",
    migrate_playlists: bool = False,
    migrate_artists: bool = False,
    progress_callback=None,
    on_migration_created=None,
    migration_id: int | None = None,
) -> tuple[int, "FullMigrationStats"]:
    """
    Точка входа для CLI и бота.
    Инициализирует клиентов, создаёт запись в БД, запускает пайплайн.
    Возвращает (migration_id, FullMigrationStats).

    migrate_playlists / migrate_artists — включают MVP2.
    on_migration_created(migration_id) — вызывается сразу после создания
    записи в БД (используется ботом для /status).
    migration_id — если передан (ARQ worker), пропускаем create_migration и on_migration_created.
    """
    from core.db import init_db
    from migration.playlists import migrate_playlists as _migrate_playlists
    from migration.artists import migrate_artists as _migrate_artists

    await init_db()

    from config import settings
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
            ym_client, sc_client, migration_id, progress_callback
        )

        pl_stats = None
        if migrate_playlists:
            logger.info("Запускаю перенос плейлистов...")
            pl_stats = await _migrate_playlists(ym_client, sc_client, migration_id)

        artist_stats = None
        if migrate_artists:
            logger.info("Запускаю перенос артистов...")
            artist_stats = await _migrate_artists(ym_client, sc_client, migration_id)

    finally:
        await sc_client.close()

    return migration_id, FullMigrationStats(
        tracks=track_stats,
        playlists=pl_stats,
        artists=artist_stats,
    )


@dataclass
class FullMigrationStats:
    tracks: MigrationStats
    playlists: "PlaylistMigrationStats | None" = None
    artists: "ArtistMigrationStats | None" = None

    def __str__(self) -> str:
        parts = [str(self.tracks)]
        if self.playlists:
            parts.append(str(self.playlists))
        if self.artists:
            parts.append(str(self.artists))
        return "\n".join(parts)
