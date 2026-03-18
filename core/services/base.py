from __future__ import annotations
from abc import ABC
from enum import Flag, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.matcher import MatchResult, TrackCandidate


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


class AdapterWriteSession(ABC):
    """
    Stateful write session wrapping an initialized platform client.

    Created via MusicServiceAdapter.write_session(token) context manager.
    Provides platform-agnostic search + write interface used by migration/pipeline.py.
    """

    #: If True, migration/pipeline.py adds Cyrillic→Latin transliteration variants
    #: to search queries (needed for Spotify where artists are indexed under Latin names).
    apply_transliteration: bool = False

    async def search_track(self, query: str, limit: int = 10) -> list["TrackCandidate"]:
        """Search for tracks by query string. Returns list of TrackCandidate."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support track search")

    async def write_track(self, match: "MatchResult") -> str:
        """
        Perform write operation (like / add to playlist).
        Returns status: 'liked' | 'in_playlist' | 'error'.
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support track write")

    async def search_artist(self, name: str, limit: int = 5) -> list[dict]:
        """Search for artists by name. Returns list[{"id": str, "name": str}]."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support artist search")

    async def follow_artist(self, artist_id: str) -> bool:
        """Follow/subscribe to an artist. Returns True on success."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support follow artist")

    async def close(self) -> None:
        """Release resources (called by write_session context manager)."""


class MusicServiceAdapter(ABC):
    id: str
    name: str
    capabilities: Capability
    session_token_key: str = ""  # key in user DB session dict for this service's token

    def can(self, cap: Capability) -> bool:
        return bool(self.capabilities & cap)

    async def fetch_liked_tracks(self, token: str, limit: int | None = None) -> list[dict]:
        """Fetch liked tracks and return [{artist, title}] for direct export.
        Override in adapters that have EXPORT_TRACKS capability."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support EXPORT_TRACKS")

    def write_session(self, token: str, **kwargs):
        """
        Returns an async context manager that yields an AdapterWriteSession.

        Usage:
            async with adapter.write_session(token) as session:
                await session.search_track(query)
                await session.write_track(match)

        Subclasses implement with @asynccontextmanager.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support write operations"
        )
