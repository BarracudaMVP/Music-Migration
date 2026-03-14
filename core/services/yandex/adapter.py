from core.services.base import Capability, MusicServiceAdapter


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
