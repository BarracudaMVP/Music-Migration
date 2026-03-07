from core.services.base import Capability, MusicServiceAdapter


class SpotifyAdapter(MusicServiceAdapter):
    id = "spotify"
    name = "Spotify"
    capabilities = (
        Capability.READ_LIKED_TRACKS
        | Capability.READ_PLAYLISTS
        | Capability.READ_LIKED_ARTISTS
    )
