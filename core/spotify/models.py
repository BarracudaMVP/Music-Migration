from dataclasses import dataclass, field


@dataclass
class SpotifyTrack:
    id: str
    title: str
    artists: list[str]
    album: str = ""
    duration_ms: int = 0

    @property
    def artists_str(self) -> str:
        return ", ".join(self.artists) if self.artists else "Unknown"

    def __str__(self) -> str:
        return f"{self.artists_str} — {self.title}"


@dataclass
class SpotifyPlaylist:
    id: str
    title: str
    tracks: list[SpotifyTrack] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.title} ({len(self.tracks)} треков)"


@dataclass
class SpotifyArtist:
    id: str
    name: str

    def __str__(self) -> str:
        return self.name
