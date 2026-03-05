from dataclasses import dataclass


@dataclass
class SCTrack:
    id: int
    title: str
    artist: str   # username автора трека
    url: str
    duration_ms: int = 0

    def __str__(self) -> str:
        return f"{self.artist} — {self.title}"


@dataclass
class SCUser:
    id: int
    username: str
    url: str

    def __str__(self) -> str:
        return self.username


@dataclass
class SCPlaylist:
    id: int
    title: str
    url: str
    track_count: int = 0
