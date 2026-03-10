"""
SoundCloud клиент.

Поиск  — прямые HTTP-запросы к api-v2.soundcloud.com с OAuth-токеном + SC_CLIENT_ID.
Write  — прямые HTTP-запросы к api-v2.soundcloud.com с OAuth-токеном.

Токен получается через официальный OAuth Authorization Code Flow (MM-52).
Формат заголовка: "Authorization: OAuth {access_token}"
"""
import asyncio
import re
import time
from urllib.parse import urlencode
from loguru import logger

import aiohttp

from core.soundcloud.models import SCTrack, SCUser, SCPlaylist

_BASE_URL = "https://api-v2.soundcloud.com"
# Кол-во результатов поиска для выбора кандидатов
_SEARCH_LIMIT = 10

# Кэш client_id, полученного со страниц soundcloud.com
_web_client_id_cache: str | None = None


async def _fetch_client_id_from_web() -> str | None:
    """Извлекает рабочий client_id из JS-бандлов soundcloud.com."""
    global _web_client_id_cache
    if _web_client_id_cache:
        return _web_client_id_cache
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://soundcloud.com/", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                html = await resp.text()
            script_urls = re.findall(
                r'<script[^>]+src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', html
            )
            for url in reversed(script_urls):  # последние бандлы содержат app-код
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        js = await resp.text()
                    m = re.search(r'client_id[=:]["\'`]([a-zA-Z0-9]{20,40})["\' `]', js)
                    if m:
                        _web_client_id_cache = m.group(1)
                        logger.info(f"[sc] fetched client_id from web: {_web_client_id_cache[:8]}...")
                        return _web_client_id_cache
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"[sc] failed to fetch client_id from soundcloud.com: {e}")
    return None


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
        # Получаем user_id через /me (опционально — 403 от неодобренных приложений игнорируем)
        try:
            me = await self._get("/me")
            self._user_id = me.get("id")
            self._username = me.get("username", "unknown")
        except Exception as e:
            # 403 = SC app not yet verified; write endpoints (/me/track_likes, /me/followings,
            # /playlists) work via /me/ URL prefix and don't require user_id locally.
            logger.warning(f"SoundCloud /me failed ({e}) — proceeding without user metadata")
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

    async def _get_client_id(self) -> str | None:
        """Возвращает рабочий client_id: из настроек или с soundcloud.com."""
        from config import settings
        return settings.sc_client_id or await _fetch_client_id_from_web()

    async def search_tracks(self, query: str) -> list[SCTrack]:
        """Ищет треки по запросу через API v2 с OAuth токеном."""
        self._ensure_init()
        client_id = await self._get_client_id()
        params: dict = {"q": query, "limit": _SEARCH_LIMIT}
        if client_id:
            params["client_id"] = client_id
        logger.debug(f"[sc] search query={query!r} → GET /search/tracks?{urlencode(params)}")
        try:
            data = await self._get("/search/tracks", params=params)
        except Exception as e:
            if "403" in str(e) and client_id:
                # client_id не работает — пробуем получить свежий с сайта
                global _web_client_id_cache
                _web_client_id_cache = None
                fresh_id = await _fetch_client_id_from_web()
                if fresh_id and fresh_id != client_id:
                    params["client_id"] = fresh_id
                    logger.debug(f"[sc] retrying search with fresh client_id")
                    try:
                        data = await self._get("/search/tracks", params=params)
                    except Exception as e2:
                        logger.warning(f"[sc] search query={query!r} → {e2} (url={_BASE_URL}/search/tracks?{urlencode(params)})")
                        return []
                else:
                    logger.warning(f"[sc] search query={query!r} → {e} (url={_BASE_URL}/search/tracks?{urlencode(params)})")
                    return []
            else:
                logger.warning(f"[sc] search query={query!r} → {e} (url={_BASE_URL}/search/tracks?{urlencode(params)})")
                return []
        tracks = []
        for item in data.get("collection", []):
            if not item or not isinstance(item, dict):
                continue
            user = item.get("user") or {}
            tracks.append(SCTrack(
                id=item.get("id", 0),
                title=item.get("title", "") or "",
                artist=user.get("username", "") or "",
                url=item.get("permalink_url", "") or "",
                duration_ms=item.get("duration", 0) or 0,
            ))
        logger.debug(f"[sc] search query={query!r} → {len(tracks)} results")
        return tracks

    async def search_users(self, query: str) -> list[SCUser]:
        """Ищет пользователей/артистов по имени через API v2 с OAuth токеном."""
        self._ensure_init()
        client_id = await self._get_client_id()
        params: dict = {"q": query, "limit": 3}
        if client_id:
            params["client_id"] = client_id
        logger.debug(f"[sc] search_users query={query!r} → GET /search/users?{urlencode(params)}")
        try:
            data = await self._get("/search/users", params=params)
        except Exception as e:
            logger.warning(f"[sc] search_users query={query!r} → {e}")
            return []
        users = []
        for item in data.get("collection", []):
            if not item or not isinstance(item, dict):
                continue
            users.append(SCUser(
                id=item.get("id", 0),
                username=item.get("username", "") or "",
                url=item.get("permalink_url", "") or "",
            ))
        logger.debug(f"[sc] search_users query={query!r} → {len(users)} results")
        return users

    # ------------------------------------------------------------------
    # Write-операции (прямой HTTP)
    # ------------------------------------------------------------------

    async def like_track(self, track_id: int) -> bool:
        """Лайкает трек. Возвращает True при успехе. Ждёт при 429."""
        self._ensure_init()
        url = f"/me/track_likes/{track_id}"
        logger.debug(f"[sc] like track_id={track_id} → PUT {url}")
        try:
            await self._put(url)
            logger.debug(f"[sc] like track_id={track_id} → ok")
            return True
        except RateLimitError as e:
            await self._wait_rate_limit(e.reset_time)
            try:
                await self._put(url)
                logger.debug(f"[sc] like track_id={track_id} → ok (retry)")
                return True
            except Exception as retry_err:
                logger.error(f"[sc] like track_id={track_id} → retry failed: {retry_err}")
                return False
        except Exception as e:
            logger.error(f"[sc] like track_id={track_id} → {e}")
            return False

    async def follow_user(self, user_id: int) -> bool:
        """Подписывается на артиста. Ждёт при 429."""
        self._ensure_init()
        url = f"/me/followings/{user_id}"
        logger.debug(f"[sc] follow user_id={user_id} → PUT {url}")
        try:
            await self._put(url)
            logger.debug(f"[sc] follow user_id={user_id} → ok")
            return True
        except RateLimitError as e:
            await self._wait_rate_limit(e.reset_time)
            try:
                await self._put(url)
                logger.debug(f"[sc] follow user_id={user_id} → ok (retry)")
                return True
            except Exception as retry_err:
                logger.error(f"[sc] follow user_id={user_id} → retry failed: {retry_err}")
                return False
        except Exception as e:
            logger.error(f"[sc] follow user_id={user_id} → {e}")
            return False

    async def create_playlist(self, title: str, track_ids: list[int]) -> SCPlaylist | None:
        """Создаёт публичный плейлист с заданными треками."""
        self._ensure_init()
        logger.debug(f"[sc] create_playlist title={title!r}, {len(track_ids)} tracks → POST /playlists")
        payload = {
            "playlist": {
                "title": title,
                "sharing": "public",
                "tracks": [{"id": tid} for tid in track_ids],
            }
        }
        try:
            data = await self._post("/playlists", json=payload)
            pl_id = data.get("id")
            logger.debug(f"[sc] create_playlist title={title!r} → ok id={pl_id}")
            return SCPlaylist(
                id=pl_id,
                title=data.get("title", title),
                url=data.get("permalink_url", ""),
                track_count=len(track_ids),
            )
        except RateLimitError as e:
            await self._wait_rate_limit(e.reset_time)
            return None
        except Exception as e:
            logger.error(f"[sc] create_playlist title={title!r} → {e}")
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
        if self._session is None:
            raise RuntimeError("Клиент не инициализирован. Вызови await client.init()")
