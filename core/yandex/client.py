"""
Обёртка над yandex-music для получения данных пользователя.
Все методы асинхронные.
"""
import asyncio
import aiohttp
from loguru import logger
from yandex_music import ClientAsync, exceptions as ym_exceptions

from core.yandex.models import YMTrack, YMPlaylist, YMArtist

# Максимальный размер батча для client.tracks()
_BATCH_SIZE = 150
# Задержка между батч-запросами (сек)
_BATCH_SLEEP = 0.3


class YandexMusicClient:
    def __init__(self, token: str) -> None:
        self._token = token
        self._client: ClientAsync | None = None
        self._uid: str | None = None

    async def init(self) -> "YandexMusicClient":
        """Инициализирует клиент и проверяет токен."""
        try:
            self._client = await ClientAsync(self._token).init()
            account = (
                self._client.me.account
                if self._client.me is not None
                else None
            )
            login = (
                getattr(account, "login", None)
                or getattr(account, "display_name", None)
                or getattr(account, "uid", None)
                or "unknown"
            )
            uid = getattr(account, "uid", None)
            if uid is not None:
                self._uid = str(uid)
            else:
                # OAuth-токены (y0_...) не возвращают uid в /account/status.
                # Получаем его через Yandex ID API.
                self._uid = await self._fetch_uid_from_yandex_id()
                if self._uid:
                    logger.info(f"uid получен через Yandex ID API: {self._uid}")
                else:
                    logger.warning("uid не удалось получить — запросы могут завершиться ошибкой")
            logger.info(f"Яндекс Музыка: авторизован как {login!r} (uid={self._uid})")
        except ym_exceptions.UnauthorizedError:
            raise ValueError("Невалидный токен Яндекс Музыки")
        except Exception as e:
            raise ValueError(f"Ошибка подключения к Яндекс Музыке: {e}")
        return self

    async def _fetch_uid_from_yandex_id(self) -> str | None:
        """Получает uid пользователя через Yandex ID API как фолбэк для OAuth-токенов."""
        try:
            async with aiohttp.ClientSession() as session:
                resp = await session.get(
                    "https://login.yandex.ru/info",
                    params={"format": "json"},
                    headers={"Authorization": f"OAuth {self._token}"},
                )
                if resp.status == 200:
                    data = await resp.json()
                    uid = data.get("id") or data.get("uid")
                    return str(uid) if uid else None
                logger.warning(f"Yandex ID API вернул {resp.status}")
        except Exception as e:
            logger.warning(f"Ошибка запроса к Yandex ID API: {e}")
        return None

    # ------------------------------------------------------------------
    # Лайкнутые треки
    # ------------------------------------------------------------------

    async def get_liked_tracks(self) -> list[YMTrack]:
        """
        Возвращает все лайкнутые треки пользователя.
        Загружает метаданные батчами по _BATCH_SIZE.
        """
        self._ensure_init()
        logger.info("Загружаю список лайкнутых треков...")

        tracks_list = await self._client.users_likes_tracks(
            **({} if self._uid is None else {"user_id": self._uid})
        )
        if not tracks_list:
            logger.warning("Список лайков пуст")
            return []

        # TracksList содержит TrackShort (только id + album_id).
        # Собираем пары (track_id, album_id) для батч-запроса.
        track_shorts = tracks_list.tracks or []
        total = len(track_shorts)
        logger.info(f"Найдено {total} лайкнутых треков, загружаю метаданные...")

        result: list[YMTrack] = []
        for i in range(0, total, _BATCH_SIZE):
            batch = track_shorts[i : i + _BATCH_SIZE]
            track_ids = [
                f"{ts.id}" + (f":{ts.album_id}" if ts.album_id else "")
                for ts in batch
            ]
            try:
                full_tracks = await self._client.tracks(track_ids)
            except Exception as e:
                logger.warning(f"Батч {i // _BATCH_SIZE + 1}: ошибка запроса — {e}, пропускаю")
                await asyncio.sleep(_BATCH_SLEEP)
                continue

            for track in full_tracks:
                if track is None:
                    continue
                result.append(self._convert_track(track))

            logger.debug(f"Загружено {min(i + _BATCH_SIZE, total)}/{total}")
            await asyncio.sleep(_BATCH_SLEEP)

        logger.info(f"Загружено треков: {len(result)}/{total}")
        return result

    # ------------------------------------------------------------------
    # Плейлисты
    # ------------------------------------------------------------------

    async def get_playlists(self) -> list[YMPlaylist]:
        """
        Возвращает все пользовательские плейлисты вместе с треками.
        Исключает системные плейлисты («Мне нравится», «Избранное»).
        """
        self._ensure_init()
        logger.info("Загружаю плейлисты...")

        raw_playlists = await self._client.users_playlists_list(
            **({} if self._uid is None else {"user_id": self._uid})
        )
        if not raw_playlists:
            return []

        result: list[YMPlaylist] = []
        for pl in raw_playlists:
            # kind=3 — системный плейлист «Мне нравится», пропускаем
            if pl.kind == 3:
                continue
            try:
                full_pl = await self._client.users_playlists(
                    kind=pl.kind,
                    **({} if self._uid is None else {"user_id": self._uid}),
                )
                if not full_pl:
                    continue
                # users_playlists может вернуть список или объект
                pl_obj = full_pl[0] if isinstance(full_pl, list) else full_pl
                tracks = await pl_obj.fetch_tracks_async()
                ym_tracks = [
                    self._convert_track(t.track)
                    for t in (tracks or [])
                    if t and t.track
                ]
                result.append(YMPlaylist(
                    kind=pl.kind,
                    title=pl.title or f"Playlist {pl.kind}",
                    tracks=ym_tracks,
                ))
                logger.debug(f"Плейлист {pl.title!r}: {len(ym_tracks)} треков")
                await asyncio.sleep(_BATCH_SLEEP)
            except Exception as e:
                logger.warning(f"Не удалось загрузить плейлист {pl.title!r}: {e}")

        logger.info(f"Загружено плейлистов: {len(result)}")
        return result

    # ------------------------------------------------------------------
    # Лайкнутые артисты
    # ------------------------------------------------------------------

    async def get_liked_artists(self) -> list[YMArtist]:
        """Возвращает всех артистов, которых лайкнул пользователь."""
        self._ensure_init()
        logger.info("Загружаю лайкнутых артистов...")

        likes = await self._client.users_likes_artists(
            **({} if self._uid is None else {"user_id": self._uid})
        )
        if not likes:
            return []

        result: list[YMArtist] = []
        for like in likes:
            artist = like.artist if hasattr(like, "artist") else like
            if artist and artist.id and artist.name:
                result.append(YMArtist(id=artist.id, name=artist.name))

        logger.info(f"Загружено артистов: {len(result)}")
        return result

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _convert_track(self, track) -> YMTrack:
        """Конвертирует yandex_music.Track → YMTrack."""
        artists = [a.name for a in (track.artists or []) if a.name]
        album = ""
        if track.albums:
            album = track.albums[0].title or ""
        return YMTrack(
            id=str(track.id),
            title=track.title or "Unknown",
            artists=artists if artists else ["Unknown"],
            album=album,
            duration_ms=track.duration_ms or 0,
        )

    def _ensure_init(self) -> None:
        if self._client is None:
            raise RuntimeError("Клиент не инициализирован. Вызови await client.init()")
