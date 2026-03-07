from core.services.base import Capability, MusicServiceAdapter


class SoundCloudAdapter(MusicServiceAdapter):
    id = "soundcloud"
    name = "SoundCloud"
    session_token_key = "soundcloud_token"
    capabilities = (
        Capability.WRITE_LIKED_TRACKS
        | Capability.WRITE_PLAYLISTS
        | Capability.WRITE_LIKED_ARTISTS
        | Capability.EXPORT_TRACKS
    )

    async def fetch_liked_tracks(self, token: str) -> list[dict]:
        from core.soundcloud.client import SoundCloudClient

        client = SoundCloudClient(token)
        await client.init()
        try:
            tracks = await client.get_liked_tracks()
        finally:
            await client.close()
        return [{"artist": t.artist, "title": t.title} for t in tracks]
