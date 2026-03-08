from core.services.base import Capability, MusicServiceAdapter


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

    async def fetch_liked_tracks(self, token: str) -> list[dict]:
        from core.spotify.client import SpotifyClient

        client = await SpotifyClient(token).init()
        try:
            tracks = await client.get_liked_tracks()
        finally:
            await client.close()
        return [{"artist": t.artists_str, "title": t.title} for t in tracks]
