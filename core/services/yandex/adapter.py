from core.services.base import Capability, MusicServiceAdapter


class YandexMusicAdapter(MusicServiceAdapter):
    id = "yandex_music"
    name = "Яндекс Музыка"
    capabilities = (
        Capability.READ_LIKED_TRACKS
        | Capability.READ_PLAYLISTS
        | Capability.READ_LIKED_ARTISTS
    )
