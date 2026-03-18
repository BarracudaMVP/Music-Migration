"""Tests for MM-77: SoundCloud as source service (read library)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.soundcloud.models import SCTrack, SCUser
from core.services.base import Capability
from core.services.soundcloud.adapter import SoundCloudAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_track_item(track_id: int, title: str, artist: str) -> dict:
    return {
        "track": {
            "id": track_id,
            "title": title,
            "permalink_url": f"https://soundcloud.com/artist/track-{track_id}",
            "duration": 200000,
            "user": {"username": artist},
        }
    }


def _make_user_item(user_id: int, username: str) -> dict:
    return {
        "id": user_id,
        "username": username,
        "permalink_url": f"https://soundcloud.com/{username}",
    }


# ---------------------------------------------------------------------------
# SoundCloudClient.get_liked_tracks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_liked_tracks_returns_all():
    from core.soundcloud.client import SoundCloudClient

    page = {"collection": [_make_track_item(1, "Track A", "Artist A")], "next_href": None}

    client = SoundCloudClient("token")
    client._session = MagicMock()
    client._session.get = AsyncMock()

    with patch.object(client, "_get", AsyncMock(return_value=page)):
        tracks = await client.get_liked_tracks()

    assert len(tracks) == 1
    assert tracks[0].id == 1
    assert tracks[0].title == "Track A"
    assert tracks[0].artist == "Artist A"


@pytest.mark.asyncio
async def test_get_liked_tracks_pagination():
    from core.soundcloud.client import SoundCloudClient

    page1 = {
        "collection": [_make_track_item(1, "A", "X"), _make_track_item(2, "B", "Y")],
        "next_href": "https://api.soundcloud.com/me/track_likes?limit=200&offset=200",
    }
    page2 = {
        "collection": [_make_track_item(3, "C", "Z")],
        "next_href": None,
    }

    client = SoundCloudClient("token")
    client._session = MagicMock()

    call_count = 0

    async def mock_get(path, **kwargs):
        nonlocal call_count
        call_count += 1
        return page1 if call_count == 1 else page2

    with patch.object(client, "_get", side_effect=mock_get):
        tracks = await client.get_liked_tracks()

    assert len(tracks) == 3
    assert call_count == 2


@pytest.mark.asyncio
async def test_get_liked_tracks_limit_stops_early():
    from core.soundcloud.client import SoundCloudClient

    page = {
        "collection": [
            _make_track_item(1, "A", "X"),
            _make_track_item(2, "B", "Y"),
            _make_track_item(3, "C", "Z"),
        ],
        "next_href": "https://api.soundcloud.com/me/track_likes?offset=200",
    }

    client = SoundCloudClient("token")
    client._session = MagicMock()

    with patch.object(client, "_get", AsyncMock(return_value=page)):
        tracks = await client.get_liked_tracks(limit=2)

    assert len(tracks) == 2


# ---------------------------------------------------------------------------
# SoundCloudClient.get_followings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_followings_returns_users():
    from core.soundcloud.client import SoundCloudClient

    page = {
        "collection": [
            _make_user_item(10, "artist_one"),
            _make_user_item(20, "artist_two"),
        ],
        "next_href": None,
    }

    client = SoundCloudClient("token")
    client._session = MagicMock()

    with patch.object(client, "_get", AsyncMock(return_value=page)):
        users = await client.get_followings()

    assert len(users) == 2
    assert users[0].id == 10
    assert users[0].username == "artist_one"
    assert users[1].username == "artist_two"


@pytest.mark.asyncio
async def test_get_followings_limit():
    from core.soundcloud.client import SoundCloudClient

    page = {
        "collection": [
            _make_user_item(1, "a"),
            _make_user_item(2, "b"),
            _make_user_item(3, "c"),
        ],
        "next_href": None,
    }

    client = SoundCloudClient("token")
    client._session = MagicMock()

    with patch.object(client, "_get", AsyncMock(return_value=page)):
        users = await client.get_followings(limit=2)

    assert len(users) == 2


@pytest.mark.asyncio
async def test_get_followings_empty():
    from core.soundcloud.client import SoundCloudClient

    page = {"collection": [], "next_href": None}

    client = SoundCloudClient("token")
    client._session = MagicMock()

    with patch.object(client, "_get", AsyncMock(return_value=page)):
        users = await client.get_followings()

    assert users == []


# ---------------------------------------------------------------------------
# SoundCloudAdapter capabilities
# ---------------------------------------------------------------------------

def test_sc_adapter_has_read_liked_tracks():
    adapter = SoundCloudAdapter()
    assert adapter.can(Capability.READ_LIKED_TRACKS)


def test_sc_adapter_has_read_liked_artists():
    adapter = SoundCloudAdapter()
    assert adapter.can(Capability.READ_LIKED_ARTISTS)


def test_sc_adapter_has_write_capabilities():
    adapter = SoundCloudAdapter()
    assert adapter.can(Capability.WRITE_LIKED_TRACKS)
    assert adapter.can(Capability.WRITE_PLAYLISTS)
    assert adapter.can(Capability.WRITE_LIKED_ARTISTS)


# ---------------------------------------------------------------------------
# SoundCloudAdapter.fetch_liked_tracks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adapter_fetch_liked_tracks():
    adapter = SoundCloudAdapter()
    tracks = [
        SCTrack(id=1, title="Song A", artist="DJ X", url="https://sc/1", duration_ms=180000),
        SCTrack(id=2, title="Song B", artist="DJ Y", url="https://sc/2", duration_ms=200000),
    ]

    mock_client = AsyncMock()
    mock_client.get_liked_tracks = AsyncMock(return_value=tracks)
    mock_client.close = AsyncMock()

    with patch("core.soundcloud.client.SoundCloudClient", return_value=mock_client):
        result = await adapter.fetch_liked_tracks("token", limit=50)

    assert result == [
        {"artist": "DJ X", "title": "Song A"},
        {"artist": "DJ Y", "title": "Song B"},
    ]
    mock_client.get_liked_tracks.assert_called_once_with(limit=50)


# ---------------------------------------------------------------------------
# SoundCloudAdapter.fetch_liked_artists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adapter_fetch_liked_artists():
    adapter = SoundCloudAdapter()
    users = [
        SCUser(id=10, username="ArtistOne", url="https://sc/artistone"),
        SCUser(id=20, username="ArtistTwo", url="https://sc/artisttwo"),
    ]

    mock_client = AsyncMock()
    mock_client.get_followings = AsyncMock(return_value=users)
    mock_client.close = AsyncMock()

    with patch("core.soundcloud.client.SoundCloudClient", return_value=mock_client):
        result = await adapter.fetch_liked_artists("token")

    assert result == [{"name": "ArtistOne"}, {"name": "ArtistTwo"}]


@pytest.mark.asyncio
async def test_adapter_fetch_liked_artists_empty():
    adapter = SoundCloudAdapter()

    mock_client = AsyncMock()
    mock_client.get_followings = AsyncMock(return_value=[])
    mock_client.close = AsyncMock()

    with patch("core.soundcloud.client.SoundCloudClient", return_value=mock_client):
        result = await adapter.fetch_liked_artists("token")

    assert result == []


# ---------------------------------------------------------------------------
# Matrix: SC appears as FROM service
# ---------------------------------------------------------------------------

def test_sc_in_matrix_as_from(isolated_registry):
    from core.services.registry import ServiceRegistry
    from core.services.yandex.adapter import YandexMusicAdapter
    from core.services.spotify.adapter import SpotifyAdapter

    ServiceRegistry.register(SoundCloudAdapter())
    ServiceRegistry.register(YandexMusicAdapter())
    ServiceRegistry.register(SpotifyAdapter())

    matrix = ServiceRegistry.get_matrix()
    from_sc = [e for e in matrix if e["from"] == "soundcloud"]

    to_ids = {e["to"] for e in from_sc}
    assert "yandex_music" in to_ids   # SC → YM (треки)
    assert "spotify" in to_ids        # SC → Spotify (треки + артисты)


def test_sc_to_spotify_includes_artists(isolated_registry):
    from core.services.registry import ServiceRegistry
    from core.services.spotify.adapter import SpotifyAdapter

    ServiceRegistry.register(SoundCloudAdapter())
    ServiceRegistry.register(SpotifyAdapter())

    matrix = ServiceRegistry.get_matrix()
    sc_to_spotify = next(
        (e for e in matrix if e["from"] == "soundcloud" and e["to"] == "spotify"), None
    )
    assert sc_to_spotify is not None
    assert "READ_LIKED_ARTISTS" in sc_to_spotify["capabilities"]


@pytest.fixture
def isolated_registry():
    from core.services.registry import ServiceRegistry
    original = dict(ServiceRegistry._adapters)
    ServiceRegistry._adapters.clear()
    yield
    ServiceRegistry._adapters.clear()
    ServiceRegistry._adapters.update(original)
