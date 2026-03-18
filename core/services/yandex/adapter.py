from contextlib import asynccontextmanager

from core.matcher import TrackCandidate, MatchResult
from core.services.base import Capability, MusicServiceAdapter, AdapterWriteSession


class _YMWriteSession(AdapterWriteSession):
    """Write session wrapping an initialized YandexMusicClient."""

    def __init__(self, client) -> None:
        self._client = client

    async def search_track(self, query: str, limit: int = 10) -> list[TrackCandidate]:
        results = await self._client.search_tracks(query, limit=limit)
        return [
            TrackCandidate(
                track_id=int(t.id),
                track_url=t.id,       # string YM track ID used in like_track()
                artist=t.artists_str,
                title=t.title,
            )
            for t in results
        ]

    async def write_track(self, match: MatchResult) -> str:
        success = await self._client.like_track(match.track_url)
        return "liked" if success else "error"


class YandexMusicAdapter(MusicServiceAdapter):
    id = "yandex_music"
    name = "Яндекс Музыка"
    session_token_key = "yandex_token"
    capabilities = (
        Capability.READ_LIKED_TRACKS
        | Capability.READ_PLAYLISTS
        | Capability.READ_LIKED_ARTISTS
        | Capability.EXPORT_TRACKS
        | Capability.WRITE_LIKED_TRACKS
    )

    async def fetch_liked_tracks(self, token: str, limit: int | None = None) -> list[dict]:
        from config import settings
        from core.yandex.client import YandexMusicClient

        client = await YandexMusicClient(
            token, proxy_url=settings.ym_proxy_url or None
        ).init()
        tracks = await client.get_liked_tracks(limit=limit)
        return [
            {"artist": ", ".join(t.artists), "title": t.title}
            for t in tracks
        ]

    @asynccontextmanager
    async def write_session(self, token: str, **kwargs):
        from config import settings
        from core.yandex.client import YandexMusicClient

        client = await YandexMusicClient(
            token, proxy_url=settings.ym_proxy_url or None
        ).init()
        yield _YMWriteSession(client)
