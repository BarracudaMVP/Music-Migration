from core.services.base import Capability, MusicServiceAdapter


class SoundCloudAdapter(MusicServiceAdapter):
    id = "soundcloud"
    name = "SoundCloud"
    capabilities = (
        Capability.WRITE_LIKED_TRACKS
        | Capability.WRITE_PLAYLISTS
        | Capability.WRITE_LIKED_ARTISTS
    )
