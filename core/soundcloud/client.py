"""
SoundCloud клиент.

Поиск  — через библиотеку soundcloud-v2 (read-only).
Write  — прямые HTTP-запросы к api-v2.soundcloud.com с OAuth-токеном.

Токен получается через официальный OAuth Authorization Code Flow (MM-52).
Формат заголовка: "Authorization: OAuth {access_token}"
"""
import asyncio
import time
from loguru import logger

import aiohttp
import soundcloud as sc_lib

from core.soundcloud.models import SCTrack, SCUser, SCPlaylist
from config import settings

_BASE_URL = "https://api-v2.soundcloud.com"
# Кол-во результатов поиска для выбора кандидатов
_SEARCH_LIMIT = 10


class RateLimitError(Exception):
    """SoundCloud вернул 429. Содержит reset_time (unix timestamp)."""
    def __init__(self, reset_time: float | None = None):
        self.reset_time = reset_time
        super().__init__(f"Rate limited, reset at {reset_time}")


class SoundCloudClient:
    def __init__(self, token: str) -> None:
        # Принимаем токен как с префиксом "OAuth ...", так и без
        self._raw_token = token.strip()
        self._auth_header = (
            self._raw_token
            if self._raw_token.startswith("OAuth ")
            else f"OAuth {self._raw_token}"
        )
        self._user_id: int | None = None
        self._username: str = ""
        self._session: aiohttp.ClientSession | None = None
        # Read-only клиент для поиска
        self._sc: sc_lib.SoundCloud | None = None

    async def init(self) -> "SoundCloudClient":
        """Создаёт сессию, проверяет токен, получает user_id."""
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": self._auth_header,
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Origin": "https://soundcloud.com",
                "Referer": "https://soundcloud.com/",
            }
        )
        # Инициализируем read-only клиент (для поиска не нужна авторизация,
        # но передаём токен чтобы получать персонализированные результаты)
        self._sc = sc_lib.SoundCloud(auth_token=self._raw_token)

        # Проверяем токен через /me
        try:
            me = await self._get("/me")
            self._user_id = me["id"]
        except (KeyError, TypeError):
            raise ValueError(
                "Не удалось получить данные аккаунта SoundCloud. "
                "Токен истёк или неверен — авторизуйся через веб-интерфейс заново."
            )
        self._username = me.get("username", "unknown")
        logger.info(f"SoundCloud: авторизован как {self._username!r} (id={self._user_id})")
        return self

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Чтение библиотеки
    # ------------------------------------------------------------------

    async def get_liked_tracks(self) -> list[SCTrack]:
        """Возвращает все лайкнутые треки текущего пользователя."""
        self._ensure_init()
        tracks: list[SCTrack] = []
        params = {"limit": 200, "linked_partitioning": 1}
        path = "/me/track_likes"
        while path:
            data = await self._get(path, params=params)
            params = {}  # next_href уже содержит все параметры
            for item in data.get("collection", []):
                raw = item.get("track") or item  # SC может вернуть трек напрямую или в ключе track
                if not raw or not isinstance(raw, dict):
                    continue
                user = raw.get("user") or {}
                tracks.append(SCTrack(
                    id=raw.get("id", 0),
                    title=raw.get("title", "") or "",
                    artist=user.get("username", "") or "",
                    url=raw.get("permalink_url", "") or "",
                    duration_ms=raw.get("duration", 0) or 0,
                ))
            next_href = data.get("next_href")
            if next_href:
                from urllib.parse import urlparse
                parsed = urlparse(next_href)
                path = parsed.path + ("?" + parsed.query if parsed.query else "")
            else:
                path = None
        logger.info(f"SC get_liked_tracks: получено {len(tracks)} треков")
        return tracks

    # ------------------------------------------------------------------
    # Поиск (read-only, soundcloud-v2)
    # ------------------------------------------------------------------

    async def search_tracks(self, query: str) -> list[SCTrack]:
        """
        Ищет треки по запросу. Возвращает до _SEARCH_LIMIT результатов.
        Запрос выполняется в thread pool т.к. soundcloud-v2 синхронный.
        """
        self._ensure_init()
        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(self._sc.search_tracks(query, limit=_SEARCH_LIMIT)),
            )
            return [self._convert_track(t) for t in results if t]
        except Exception as e:
            logger.warning(f"SC search_tracks({query!r}): {e}")
            return []

    async def search_users(self, query: str) -> list[SCUser]:
        """Ищет пользователей/артистов по имени."""
        self._ensure_init()
        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None,
                lambda: list(self._sc.search_users(query, limit=3)),
            )
            return [self._convert_user(u) for u in results if u]
        except Exception as e:
            logger.warning(f"SC search_users({query!r}): {e}")
            return []

    # ------------------------------------------------------------------
    # Write-операции (прямой HTTP)
    # ------------------------------------------------------------------

    async def like_track(self, track_id: int) -> bool:
        """
        Лайкает трек. Возвращает True при успехе.
        Автоматически ждёт при rate limit (429).
        """
        self._ensure_init()
        url = f"/me/track_likes/{track_id}"
        try:
            await self._put(url)
            await asyncio.sleep(settings.sc_rate_limit_sleep)
            return True
        except RateLimitError as e:
            await self._wait_rate_limit(e.reset_time)
            try:
                await self._put(url)
                await asyncio.sleep(settings.sc_rate_limit_sleep)
                return True
            except Exception as retry_err:
                logger.error(f"like_track {track_id}: retry failed — {retry_err}")
                return False
        except Exception as e:
            logger.error(f"like_track {track_id}: {e}")
            return False

    async def follow_user(self, user_id: int) -> bool:
        """Подписывается на артиста."""
        self._ensure_init()
        url = f"/me/followings/{user_id}"
        try:
            await self._put(url)
            await asyncio.sleep(settings.sc_rate_limit_sleep)
            return True
        except RateLimitError as e:
            await self._wait_rate_limit(e.reset_time)
            try:
                await self._put(url)
                await asyncio.sleep(settings.sc_rate_limit_sleep)
                return True
            except Exception as retry_err:
                logger.error(f"follow_user {user_id}: retry failed — {retry_err}")
                return False
        except Exception as e:
            logger.error(f"follow_user {user_id}: {e}")
            return False

    async def create_playlist(self, title: str, track_ids: list[int]) -> SCPlaylist | None:
        """Создаёт публичный плейлист с заданными треками."""
        self._ensure_init()
        payload = {
            "playlist": {
                "title": title,
                "sharing": "public",
                "tracks": [{"id": tid} for tid in track_ids],
            }
        }
        try:
            data = await self._post("/playlists", json=payload)
            return SCPlaylist(
                id=data["id"],
                title=data.get("title", title),
                url=data.get("permalink_url", ""),
                track_count=len(track_ids),
            )
        except RateLimitError as e:
            await self._wait_rate_limit(e.reset_time)
            return None
        except Exception as e:
            logger.error(f"create_playlist {title!r}: {e}")
            return None

    # ------------------------------------------------------------------
    # Низкоуровневые HTTP-методы
    # ------------------------------------------------------------------

    async def _get(self, path: str, **kwargs) -> dict:
        resp = await self._session.get(f"{_BASE_URL}{path}", **kwargs)
        return await self._handle_response(resp)

    async def _post(self, path: str, **kwargs) -> dict:
        resp = await self._session.post(f"{_BASE_URL}{path}", **kwargs)
        return await self._handle_response(resp)

    async def _put(self, path: str, **kwargs) -> dict:
        resp = await self._session.put(f"{_BASE_URL}{path}", **kwargs)
        return await self._handle_response(resp)

    async def _handle_response(self, resp: aiohttp.ClientResponse) -> dict:
        if resp.status == 429:
            reset_time = None
            try:
                body = await resp.json(content_type=None)
                reset_time = body.get("reset_time")
            except Exception:
                pass
            raise RateLimitError(reset_time)

        if resp.status in (200, 201):
            try:
                body = await resp.json(content_type=None)
            except Exception:
                return {}
            # SoundCloud иногда возвращает ошибку в теле с 200 статусом
            if isinstance(body, dict) and "name" in body and "message" in body:
                raise Exception(f"SoundCloud error: {body['name']} — {body['message']}")
            return body

        # 200-range без тела (например 204 No Content при лайке)
        if 200 <= resp.status < 300:
            return {}

        text = await resp.text()
        raise Exception(f"HTTP {resp.status}: {text[:200]}")

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_rate_limit(reset_time: float | None) -> None:
        if reset_time:
            wait = max(0.0, reset_time - time.time()) + 1.0
        else:
            wait = 60.0  # fallback: ждём минуту
        logger.warning(f"Rate limit SoundCloud — жду {wait:.0f} сек...")
        await asyncio.sleep(wait)

    def _convert_track(self, track) -> SCTrack:
        artist = ""
        if hasattr(track, "user") and track.user:
            artist = getattr(track.user, "username", "") or ""
        return SCTrack(
            id=track.id,
            title=getattr(track, "title", "") or "",
            artist=artist,
            url=getattr(track, "permalink_url", "") or "",
            duration_ms=getattr(track, "duration", 0) or 0,
        )

    def _convert_user(self, user) -> SCUser:
        return SCUser(
            id=user.id,
            username=getattr(user, "username", "") or "",
            url=getattr(user, "permalink_url", "") or "",
        )

    def _ensure_init(self) -> None:
        if self._session is None or self._user_id is None:
            raise RuntimeError("Клиент не инициализирован. Вызови await client.init()")
