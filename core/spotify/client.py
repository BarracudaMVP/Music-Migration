"""
Клиент Spotify Web API.
Требует access_token (Bearer).
"""
from __future__ import annotations

import asyncio

import aiohttp
from loguru import logger

from core.spotify.models import SpotifyArtist, SpotifyPlaylist, SpotifyTrack

_BASE = "https://api.spotify.com/v1"
_PAGE_SIZE = 50


class SpotifyClient:
    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._session: aiohttp.ClientSession | None = None
        self.display_name: str = "unknown"

    async def init(self) -> "SpotifyClient":
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self._token}"}
        )
        async with self._session.get(f"{_BASE}/me") as resp:
            if resp.status == 401:
                await self._session.close()
                raise ValueError("Невалидный Spotify токен")
            data = await resp.json()
            self.display_name = data.get("display_name") or data.get("id", "unknown")
        logger.info(f"Spotify: авторизован как {self.display_name!r}")
        return self

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Лайкнутые треки
    # ------------------------------------------------------------------

    async def get_liked_tracks(self, limit: int | None = None) -> list[SpotifyTrack]:
        self._ensure_init()
        tracks: list[SpotifyTrack] = []
        url = f"{_BASE}/me/tracks"
        params: dict = {"limit": _PAGE_SIZE, "offset": 0}

        while url:
            async with self._session.get(url, params=params) as resp:  # type: ignore[union-attr]
                data = await resp.json()
            for item in data.get("items", []):
                raw = item.get("track")
                if raw and not raw.get("is_local"):
                    tracks.append(self._convert_track(raw))
                    if limit and len(tracks) >= limit:
                        logger.info(f"Spotify: загружено {len(tracks)} лайкнутых треков (лимит)")
                        return tracks
            url = data.get("next") or ""
            params = {}
            await asyncio.sleep(0.1)

        logger.info(f"Spotify: загружено {len(tracks)} лайкнутых треков")
        return tracks

    # ------------------------------------------------------------------
    # Плейлисты
    # ------------------------------------------------------------------

    async def get_playlists(self) -> list[SpotifyPlaylist]:
        self._ensure_init()
        playlists: list[SpotifyPlaylist] = []
        url = f"{_BASE}/me/playlists"
        params: dict = {"limit": _PAGE_SIZE, "offset": 0}

        while url:
            async with self._session.get(url, params=params) as resp:  # type: ignore[union-attr]
                data = await resp.json()
            for item in data.get("items", []):
                if not item:
                    continue
                tracks = await self._fetch_playlist_tracks(item["id"])
                playlists.append(SpotifyPlaylist(
                    id=item["id"],
                    title=item.get("name") or f"Playlist {item['id']}",
                    tracks=tracks,
                ))
                logger.debug(f"Spotify плейлист {item.get('name')!r}: {len(tracks)} треков")
                await asyncio.sleep(0.2)
            url = data.get("next") or ""
            params = {}

        logger.info(f"Spotify: загружено {len(playlists)} плейлистов")
        return playlists

    async def _fetch_playlist_tracks(self, playlist_id: str) -> list[SpotifyTrack]:
        tracks: list[SpotifyTrack] = []
        url = f"{_BASE}/playlists/{playlist_id}/tracks"
        params: dict = {"limit": _PAGE_SIZE, "offset": 0, "fields": "next,items(track(id,name,artists,album,duration_ms,is_local))"}

        while url:
            async with self._session.get(url, params=params) as resp:  # type: ignore[union-attr]
                data = await resp.json()
            for item in data.get("items", []):
                raw = item.get("track")
                if raw and not raw.get("is_local") and raw.get("id"):
                    tracks.append(self._convert_track(raw))
            url = data.get("next") or ""
            params = {}
            await asyncio.sleep(0.05)

        return tracks

    # ------------------------------------------------------------------
    # Исполнители
    # ------------------------------------------------------------------

    async def get_followed_artists(self) -> list[SpotifyArtist]:
        self._ensure_init()
        artists: list[SpotifyArtist] = []
        url = f"{_BASE}/me/following"
        params: dict = {"type": "artist", "limit": _PAGE_SIZE}

        while url:
            async with self._session.get(url, params=params) as resp:  # type: ignore[union-attr]
                data = await resp.json()
            page = data.get("artists", {})
            for item in page.get("items", []):
                artists.append(SpotifyArtist(id=item["id"], name=item["name"]))
            cursor = page.get("cursors", {})
            after = cursor.get("after") if cursor else None
            url = f"{_BASE}/me/following" if after else ""
            params = {"type": "artist", "limit": _PAGE_SIZE, "after": after} if after else {}
            await asyncio.sleep(0.1)

        logger.info(f"Spotify: загружено {len(artists)} исполнителей")
        return artists

    # ------------------------------------------------------------------
    # Поиск и запись
    # ------------------------------------------------------------------

    async def search_tracks(self, query: str, limit: int = 10) -> list[SpotifyTrack]:
        """Search tracks by query string."""
        self._ensure_init()
        logger.debug(f"[spotify] search query={query!r} type=track limit={limit}")
        async with self._session.get(  # type: ignore[union-attr]
            f"{_BASE}/search",
            params={"q": query, "type": "track", "limit": limit},
        ) as resp:
            data = await resp.json()
        result = [
            self._convert_track(item)
            for item in data.get("tracks", {}).get("items", [])
            if item and item.get("id")
        ]
        logger.debug(f"[spotify] search query={query!r} type=track → {len(result)} results")
        return result

    async def like_track(self, track_id: str) -> bool:
        """Save track to user's Liked Songs (PUT /me/tracks)."""
        self._ensure_init()
        logger.debug(f"[spotify] like track_id={track_id} → PUT /me/tracks")
        async with self._session.put(  # type: ignore[union-attr]
            f"{_BASE}/me/tracks",
            json={"ids": [track_id]},
        ) as resp:
            ok = resp.status in (200, 201)
            if not ok:
                body = await resp.text()
                logger.warning(f"[spotify] like track_id={track_id} → {resp.status}: {body}")
            else:
                logger.debug(f"[spotify] like track_id={track_id} → {resp.status} ok")
            return ok

    async def search_artists(self, query: str, limit: int = 10) -> list[SpotifyArtist]:
        """Search artists by query string."""
        self._ensure_init()
        logger.debug(f"[spotify] search query={query!r} type=artist limit={limit}")
        async with self._session.get(  # type: ignore[union-attr]
            f"{_BASE}/search",
            params={"q": query, "type": "artist", "limit": limit},
        ) as resp:
            data = await resp.json()
        result = [
            SpotifyArtist(id=item["id"], name=item["name"])
            for item in data.get("artists", {}).get("items", [])
            if item and item.get("id")
        ]
        logger.debug(f"[spotify] search query={query!r} type=artist → {len(result)} results")
        return result

    async def follow_artist(self, artist_id: str) -> bool:
        """Follow an artist (PUT /me/following?type=artist)."""
        self._ensure_init()
        logger.debug(f"[spotify] follow artist_id={artist_id} → PUT /me/following")
        async with self._session.put(  # type: ignore[union-attr]
            f"{_BASE}/me/following",
            params={"type": "artist"},
            json={"ids": [artist_id]},
        ) as resp:
            ok = resp.status in (200, 204)
            logger.debug(f"[spotify] follow artist_id={artist_id} → {resp.status} ({'ok' if ok else 'fail'})")
            return ok

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _convert_track(self, raw: dict) -> SpotifyTrack:
        artists = [a["name"] for a in raw.get("artists", []) if a.get("name")]
        album = raw.get("album", {}).get("name", "") if isinstance(raw.get("album"), dict) else ""
        return SpotifyTrack(
            id=raw["id"],
            title=raw.get("name", "Unknown"),
            artists=artists or ["Unknown"],
            album=album,
            duration_ms=raw.get("duration_ms", 0),
        )

    def _ensure_init(self) -> None:
        if self._session is None:
            raise RuntimeError("SpotifyClient не инициализирован. Вызови await client.init()")
