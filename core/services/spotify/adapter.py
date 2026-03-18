from contextlib import asynccontextmanager

from core.matcher import TrackCandidate, MatchResult
from core.services.base import Capability, MusicServiceAdapter, AdapterWriteSession


class _SpotifyWriteSession(AdapterWriteSession):
    """Write session wrapping an initialized SpotifyClient."""

    apply_transliteration = True  # Cyrillic artists may be indexed under Latin names on Spotify

    def __init__(self, client, *, playlist_mode: bool = False) -> None:
        self._client = client
        self._playlist_mode = playlist_mode

    async def search_track(self, query: str, limit: int = 10) -> list[TrackCandidate]:
        results = await self._client.search_tracks(query, limit=limit)
        return [
            TrackCandidate(
                track_id=hash(t.id) & 0x7FFFFFFF,  # int dedup key from string Spotify ID
                track_url=t.id,                      # Spotify track ID for like_track()
                artist=t.artists_str,
                title=t.title,
            )
            for t in results
        ]

    async def write_track(self, match: MatchResult) -> str:
        if self._playlist_mode:
            return "in_playlist"
        success = await self._client.like_track(match.track_url)
        return "liked" if success else "error"

    async def search_artist(self, name: str, limit: int = 5) -> list[dict]:
        artists = await self._client.search_artists(name, limit=limit)
        return [{"id": a.id, "name": a.name} for a in artists]

    async def follow_artist(self, artist_id: str) -> bool:
        return await self._client.follow_artist(artist_id)

    async def close(self) -> None:
        await self._client.close()


class SpotifyAdapter(MusicServiceAdapter):
    id = "spotify"
    name = "Spotify"
    session_token_key = "spotify_token"
    capabilities = (
        Capability.READ_LIKED_TRACKS
        | Capability.READ_PLAYLISTS
        | Capability.READ_LIKED_ARTISTS
        | Capability.EXPORT_TRACKS
        | Capability.WRITE_LIKED_TRACKS
        | Capability.WRITE_LIKED_ARTISTS
    )

    async def fetch_liked_tracks(self, token: str, limit: int | None = None) -> list[dict]:
        from core.spotify.client import SpotifyClient

        client = await SpotifyClient(token).init()
        try:
            tracks = await client.get_liked_tracks(limit=limit)
        finally:
            await client.close()
        return [{"artist": t.artists_str, "title": t.title} for t in tracks]

    @asynccontextmanager
    async def write_session(self, token: str, **kwargs):
        from core.spotify.client import SpotifyClient

        playlist_mode = kwargs.get("playlist_mode", False)
        client = await SpotifyClient(token).init()
        session = _SpotifyWriteSession(client, playlist_mode=playlist_mode)
        try:
            yield session
        finally:
            await session.close()
