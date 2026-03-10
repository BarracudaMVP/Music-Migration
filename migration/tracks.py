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
    get_migration,
    bulk_insert_tracks,
    get_pending_tracks,
    get_previously_migrated_ym_ids,
    update_track,
    get_track_stats,
)
from config import settings
from core.yandex.client import YandexMusicClient
from core.soundcloud.client import SoundCloudClient
from core.matcher import find_best_match, split_artists, SCCandidate


@dataclass
class MigrationStats:
    total: int = 0
    liked: int = 0
    not_found: int = 0
    errors: int = 0
    uncertain: int = 0  # найдены, но score ниже порога — сохранены в not_found
    skipped: int = 0   # уже перенесены в предыдущих запусках — пропущены

    def __str__(self) -> str:
        parts = (
            f"Всего: {self.total} | "
            f"Перенесено: {self.liked} | "
            f"Не найдено: {self.not_found} | "
            f"Сомнительных: {self.uncertain} | "
            f"Ошибок: {self.errors}"
        )
        if self.skipped:
            parts += f" | Пропущено (уже перенесено): {self.skipped}"
        return parts


async def migrate_tracks(
    ym_client: YandexMusicClient,
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
    playlist_mode: bool = False,
    track_limit: int | None = None,
    skip_already_migrated: bool = True,
) -> MigrationStats:
    """
    Основной пайплайн миграции треков.

    progress_callback(current, total, track_str) — опциональный колбэк
    для обновления прогресса (используется ботом).
    track_limit — ограничить количество треков (None = все).
    """
    await update_migration(migration_id, status="running")

    # --- Шаг 1: загружаем треки из ЯМ ---
    logger.info("Шаг 1/3: загружаю треки из Яндекс Музыки...")
    ym_tracks = await ym_client.get_liked_tracks()
    if track_limit:
        ym_tracks = ym_tracks[:track_limit]
        logger.info(f"Лимит треков: {track_limit}, будет обработано {len(ym_tracks)}")

    if not ym_tracks:
        logger.warning("Нет лайкнутых треков в Яндекс Музыке")
        await update_migration(migration_id, status="done")
        return MigrationStats()

    # --- Шаг 2: сохраняем в БД (с дедупликацией предыдущих переносов) ---
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

    # --- Шаг 3: обрабатываем pending-треки ---
    logger.info("Шаг 3/3: обрабатываю треки...")
    stats = await _run_pending_loop(sc_client, migration_id, progress_callback, playlist_mode=playlist_mode)
    stats.skipped = skipped

    await update_migration(migration_id, status="done")
    logger.info(f"Миграция завершена. {stats}")
    return stats


async def _run_pending_loop(
    sc_client: SoundCloudClient,
    migration_id: int,
    progress_callback=None,
    playlist_mode: bool = False,
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
            result, sc_id = await _process_one_track(sc_client, row, playlist_mode=playlist_mode)
        except Exception as e:
            logger.error(f"[{i}/{total}] Ошибка при обработке {track_str!r}: {e}")
            await update_track(row["id"], status="error")
            stats.errors += 1
            continue

        if result == "liked":
            stats.liked += 1
            if playlist_mode and sc_id:
                collected_ids.append(sc_id)
            logger.debug(f"[{i}/{total}] OK: {track_str}")
        elif result == "uncertain":
            stats.uncertain += 1
            logger.debug(f"[{i}/{total}] uncertain: {track_str}")
        elif result == "error":
            stats.errors += 1
        else:
            stats.not_found += 1
            logger.debug(f"[{i}/{total}] not found: {track_str}")

    if playlist_mode and collected_ids:
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


async def migrate_from_file_tracks(
    sc_client: SoundCloudClient,
    migration_id: int,
    tracks_data: list[dict],
    progress_callback=None,
    playlist_mode: bool = False,
    track_limit: int | None = None,
) -> MigrationStats:
    """
    Пайплайн переноса треков из файла (без Яндекс Музыки).
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


async def _process_one_track(
    sc_client: SoundCloudClient, row: dict, playlist_mode: bool = False
) -> tuple[str, int | None]:
    """
    Обрабатывает один трек: поиск → матчинг → лайк или сбор ID для плейлиста.
    Возвращает: (status, sc_id | None)
      status: 'liked' | 'not_found' | 'uncertain' | 'error'
    """
    ym_artist = row["ym_artist"]
    ym_title = row["ym_title"]
    track_id = row["id"]

    # Поиск на SoundCloud: один запрос на каждого артиста (параллельно)
    artists = split_artists(ym_artist)
    queries = [f"{a} {ym_title}" for a in artists]

    if len(queries) > 1:
        results_list = await asyncio.gather(
            *[sc_client.search_tracks(q) for q in queries]
        )
    else:
        results_list = [await sc_client.search_tracks(queries[0])]

    # Дедупликация кандидатов по sc_id
    all_candidates: dict[int, SCCandidate] = {}
    for sc_results in results_list:
        for t in sc_results:
            if t.id not in all_candidates:
                all_candidates[t.id] = SCCandidate(
                    sc_id=t.id,
                    sc_url=t.url,
                    artist=t.artist,
                    title=t.title,
                )

    candidates = list(all_candidates.values())

    # Fallback: поиск только по названию если пул пустой
    if not candidates:
        fallback_results = await sc_client.search_tracks(ym_title)
        candidates = [
            SCCandidate(sc_id=t.id, sc_url=t.url, artist=t.artist, title=t.title)
            for t in fallback_results
        ]

    match = find_best_match(ym_artist, ym_title, candidates)

    if match is None:
        logger.info(f"[match] {ym_artist} — {ym_title} → not_found (candidates={len(candidates)})")
        await update_track(track_id, status="not_found")
        return "not_found", None

    if match.matched:
        logger.info(f"[match] {ym_artist} — {ym_title} → {match.sc_artist} — {match.sc_title} (score={match.score:.0f})")
    elif match.uncertain:
        logger.info(f"[match] {ym_artist} — {ym_title} → uncertain: {match.sc_artist} — {match.sc_title} (score={match.score:.0f})")
    else:
        logger.info(f"[match] {ym_artist} — {ym_title} → not_found (score={match.score:.0f})")

    # Сомнительное совпадение — не лайкаем, сохраняем для ручной проверки
    if match.uncertain:
        await update_track(
            track_id,
            status="not_found",
            sc_id=match.sc_id,
            sc_url=match.sc_url,
            match_score=match.score,
        )
        return "uncertain", None

    if not match.matched:
        await update_track(track_id, status="not_found", match_score=match.score)
        return "not_found", None

    if playlist_mode:
        # Плейлист-режим: сохраняем статус и возвращаем sc_id для создания плейлиста в конце
        await update_track(
            track_id,
            status="liked",
            sc_id=match.sc_id,
            sc_url=match.sc_url,
            match_score=match.score,
        )
        return "liked", match.sc_id

    # Обычный режим: лайкаем
    success = await sc_client.like_track(match.sc_id)
    if success:
        await update_track(
            track_id,
            status="liked",
            sc_id=match.sc_id,
            sc_url=match.sc_url,
            match_score=match.score,
        )
        return "liked", match.sc_id
    else:
        await update_track(track_id, status="error")
        return "error", None



async def run_migration(
    yandex_token: str,
    soundcloud_token: str,
    user_id: str = "cli",
    migrate_playlists: bool = False,
    migrate_artists: bool = False,
    progress_callback=None,
    on_migration_created=None,
    migration_id: int | None = None,
    playlist_mode: bool = False,
    track_limit: int | None = None,
    skip_already_migrated: bool = True,
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
    from migration.playlists import migrate_playlists as _migrate_playlists
    from migration.artists import migrate_artists as _migrate_artists

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
