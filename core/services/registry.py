from __future__ import annotations

from core.services.base import Capability, MusicServiceAdapter


class ServiceRegistry:
    _adapters: dict[str, MusicServiceAdapter] = {}

    @classmethod
    def register(cls, adapter: MusicServiceAdapter) -> None:
        cls._adapters[adapter.id] = adapter

    @classmethod
    def all(cls) -> list[MusicServiceAdapter]:
        return list(cls._adapters.values())

    @classmethod
    def get(cls, service_id: str) -> MusicServiceAdapter:
        if service_id not in cls._adapters:
            raise KeyError(f"Unknown service: {service_id}")
        return cls._adapters[service_id]

    @classmethod
    def get_matrix(cls) -> list[dict]:
        """Returns [{from, to, capabilities}] pairs where READ+WRITE overlap exists."""
        read_caps = {
            Capability.READ_LIKED_TRACKS: Capability.WRITE_LIKED_TRACKS,
            Capability.READ_PLAYLISTS: Capability.WRITE_PLAYLISTS,
            Capability.READ_LIKED_ARTISTS: Capability.WRITE_LIKED_ARTISTS,
        }
        matrix = []
        adapters = cls.all()
        for src in adapters:
            for dst in adapters:
                if src.id == dst.id:
                    continue
                shared = []
                for read_cap, write_cap in read_caps.items():
                    if src.can(read_cap) and dst.can(write_cap):
                        shared.append(read_cap.name)
                if shared:
                    matrix.append({"from": src.id, "to": dst.id, "capabilities": shared})
        return matrix
