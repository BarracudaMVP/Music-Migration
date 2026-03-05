from dataclasses import dataclass, field


@dataclass
class YMTrack:
    id: str
    title: str
    artists: list[str]      # ["Artist1", "Artist2"]
    album: str = ""
    duration_ms: int = 0

    @property
    def artist(self) -> str:
        """Основной артист (первый в списке)."""
        return self.artists[0] if self.artists else "Unknown"

    @property
    def artists_str(self) -> str:
        """Все артисты через запятую."""
        return ", ".join(self.artists) if self.artists else "Unknown"

    def __str__(self) -> str:
        return f"{self.artists_str} — {self.title}"


@dataclass
class YMPlaylist:
    kind: int
    title: str
    tracks: list[YMTrack] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.title} ({len(self.tracks)} треков)"


@dataclass
class YMArtist:
    id: int
    name: str

    def __str__(self) -> str:
        return self.name
