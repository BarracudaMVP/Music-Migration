from __future__ import annotations
from abc import ABC
from enum import Flag, auto


class Capability(Flag):
    READ_LIKED_TRACKS = auto()
    WRITE_LIKED_TRACKS = auto()
    READ_PLAYLISTS = auto()
    WRITE_PLAYLISTS = auto()
    READ_LIKED_ARTISTS = auto()
    WRITE_LIKED_ARTISTS = auto()
    EXPORT_FILE = auto()
    IMPORT_FILE = auto()
    EXPORT_TRACKS = auto()   # direct library export to file (without migration)


class MusicServiceAdapter(ABC):
    id: str
    name: str
    capabilities: Capability
    session_token_key: str = ""  # key in user DB session dict for this service's token

    def can(self, cap: Capability) -> bool:
        return bool(self.capabilities & cap)

    async def fetch_liked_tracks(self, token: str) -> list[dict]:
        """Fetch liked tracks and return [{artist, title}] for direct export.
        Override in adapters that have EXPORT_TRACKS capability."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support EXPORT_TRACKS")
