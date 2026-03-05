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


class MusicServiceAdapter(ABC):
    id: str
    name: str
    capabilities: Capability

    def can(self, cap: Capability) -> bool:
        return bool(self.capabilities & cap)
