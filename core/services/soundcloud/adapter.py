from contextlib import asynccontextmanager

from core.matcher import TrackCandidate, MatchResult
from core.services.base import Capability, MusicServiceAdapter, AdapterWriteSession


class _SCWriteSession(AdapterWriteSession):
    """
    Write session wrapping an initialized SoundCloudClient.

    playlist_mode=True (default): write_track returns 'in_playlist' without
    calling like_track (SC like API returns 404 for external OAuth tokens).

    like_tracks=True: write_track calls like_track; on LikeNotSupportedError
    falls back to 'in_playlist'.
    """

    def __init__(self, client, *, playlist_mode: bool = True, like_tracks: bool = False) -> None:
        self._client = client
        self._playlist_mode = playlist_mode
        self._like_tracks = like_tracks

    async def search_track(self, query: str, limit: int = 10) -> list[TrackCandidate]:
        results = await self._client.search_tracks(query)
        return [
            TrackCandidate(
                track_id=t.id,
                track_url=t.url,
                artist=t.artist,
                title=t.title,
            )
            for t in results[:limit]
        ]

    async def write_track(self, match: MatchResult) -> str:
        from core.soundcloud.client import LikeNotSupportedError

        if self._like_tracks:
            try:
                success = await self._client.like_track(match.track_id)
                return "liked" if success else "error"
            except LikeNotSupportedError:
                return "in_playlist"
        elif self._playlist_mode:
            return "in_playlist"
        else:
            success = await self._client.like_track(match.track_id)
            return "liked" if success else "error"

    async def search_artist(self, name: str, limit: int = 5) -> list[dict]:
        users = await self._client.search_users(name)
        return [{"id": str(u.id), "name": u.username} for u in users[:limit]]

    async def follow_artist(self, artist_id: str) -> bool:
        return await self._client.follow_user(int(artist_id))

    async def close(self) -> None:
        await self._client.close()


class SoundCloudAdapter(MusicServiceAdapter):
    id = "soundcloud"
    name = "SoundCloud"
    session_token_key = "soundcloud_token"
    capabilities = (
        Capability.READ_LIKED_TRACKS
        | Capability.READ_LIKED_ARTISTS
        | Capability.WRITE_LIKED_TRACKS
        | Capability.WRITE_PLAYLISTS
        | Capability.WRITE_LIKED_ARTISTS
        | Capability.EXPORT_TRACKS
    )

    async def fetch_liked_tracks(self, token: str, limit: int | None = None) -> list[dict]:
        from core.soundcloud.client import SoundCloudClient

        client = SoundCloudClient(token)
        await client.init()
        try:
            tracks = await client.get_liked_tracks(limit=limit)
        finally:
            await client.close()
        return [{"artist": t.artist, "title": t.title} for t in tracks]

    async def fetch_liked_artists(self, token: str) -> list[dict]:
        from core.soundcloud.client import SoundCloudClient

        client = SoundCloudClient(token)
        await client.init()
        try:
            users = await client.get_followings()
        finally:
            await client.close()
        return [{"name": u.username} for u in users]

    @asynccontextmanager
    async def write_session(
        self,
        token: str,
        *,
        playlist_mode: bool = True,
        like_tracks: bool = False,
        **kwargs,
    ):
        from core.soundcloud.client import SoundCloudClient

        client = SoundCloudClient(token)
        await client.init()
        session = _SCWriteSession(client, playlist_mode=playlist_mode, like_tracks=like_tracks)
        try:
            yield session
        finally:
            await session.close()
