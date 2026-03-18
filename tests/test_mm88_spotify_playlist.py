"""
Tests for MM-88: Spotify bot playlist mode.

Covers:
- _SpotifyWriteSession: playlist_mode=True returns 'in_playlist' without calling like_track
- _SpotifyWriteSession: playlist_mode=False (default) calls like_track
- SpotifyAdapter.write_session passes playlist_mode kwarg
- migrate_to_spotify: calls _create_bot_playlist when playlist_mode=True and in_playlist > 0
- migrate_to_spotify: stores playlist_url in SpotifyWriteStats
- _create_bot_playlist: no-op when SPOTIFY_BOT_TOKEN is not configured
- _create_bot_playlist: creates playlist via bot client and returns URL
- migration_done_text: includes playlist_url link when provided
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.matcher import MatchResult


def _match(track_url="sp_id_123", score=90.0):
    return MatchResult(
        track_id=1,
        track_url=track_url,
        cand_artist="Artist",
        cand_title="Title",
        score=score,
        matched=True,
        uncertain=False,
    )


# ---------------------------------------------------------------------------
# _SpotifyWriteSession — playlist_mode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spotify_session_playlist_mode_no_like():
    """playlist_mode=True: write_track returns 'in_playlist' without calling like_track."""
    from core.services.spotify.adapter import _SpotifyWriteSession

    client = MagicMock()
    client.like_track = AsyncMock(return_value=True)

    session = _SpotifyWriteSession(client, playlist_mode=True)
    status = await session.write_track(_match())

    assert status == "in_playlist"
    client.like_track.assert_not_called()


@pytest.mark.asyncio
async def test_spotify_session_default_mode_likes():
    """playlist_mode=False (default): write_track calls like_track."""
    from core.services.spotify.adapter import _SpotifyWriteSession

    client = MagicMock()
    client.like_track = AsyncMock(return_value=True)

    session = _SpotifyWriteSession(client)
    status = await session.write_track(_match(track_url="sp_id_abc"))

    client.like_track.assert_called_once_with("sp_id_abc")
    assert status == "liked"


# ---------------------------------------------------------------------------
# SpotifyAdapter.write_session — kwargs forwarding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spotify_adapter_write_session_playlist_mode():
    """write_session(token, playlist_mode=True) creates a session with playlist_mode=True."""
    from core.services.spotify.adapter import SpotifyAdapter, _SpotifyWriteSession

    mock_client = MagicMock()
    mock_client.like_track = AsyncMock(return_value=True)
    mock_client.close = AsyncMock()

    with patch("core.spotify.client.SpotifyClient") as MockClient:
        MockClient.return_value.init = AsyncMock(return_value=mock_client)

        adapter = SpotifyAdapter()
        async with adapter.write_session("fake_token", playlist_mode=True) as session:
            assert isinstance(session, _SpotifyWriteSession)
            assert session._playlist_mode is True


# ---------------------------------------------------------------------------
# migrate_to_spotify — playlist_mode integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_migrate_to_spotify_calls_create_bot_playlist():
    """playlist_mode=True and in_playlist > 0 → _create_bot_playlist is called."""
    from migration.to_spotify import migrate_to_spotify

    mock_stats = MagicMock()
    mock_stats.total = 2
    mock_stats.liked = 0
    mock_stats.in_playlist = 2
    mock_stats.not_found = 0
    mock_stats.errors = 0
    mock_stats.uncertain = 0

    mock_session = MagicMock()
    mock_session.apply_transliteration = False

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_write_session(token, **kwargs):
        yield mock_session

    mock_adapter = MagicMock()
    mock_adapter.write_session = fake_write_session

    with patch("migration.to_spotify.ServiceRegistry") as MockRegistry, \
         patch("migration.to_spotify.bulk_insert_tracks", AsyncMock()), \
         patch("migration.to_spotify.update_migration", AsyncMock()), \
         patch("migration.to_spotify.run_pending_tracks_loop", AsyncMock(return_value=mock_stats)), \
         patch("migration.to_spotify._create_bot_playlist", AsyncMock(return_value="https://open.spotify.com/playlist/abc")) as mock_create:
        MockRegistry.get.return_value = mock_adapter
        stats = await migrate_to_spotify(
            tracks_data=[{"artist": "A", "title": "T"}],
            artists_data=[],
            spotify_token="tok",
            migration_id=1,
            playlist_mode=True,
            playlist_name="My Playlist",
        )

    mock_create.assert_called_once_with(1, "My Playlist")
    assert stats.playlist_url == "https://open.spotify.com/playlist/abc"


@pytest.mark.asyncio
async def test_migrate_to_spotify_no_playlist_when_no_in_playlist_tracks():
    """playlist_mode=True but in_playlist == 0 → _create_bot_playlist is NOT called."""
    from migration.to_spotify import migrate_to_spotify

    mock_stats = MagicMock()
    mock_stats.total = 1
    mock_stats.liked = 0
    mock_stats.in_playlist = 0
    mock_stats.not_found = 1
    mock_stats.errors = 0
    mock_stats.uncertain = 0

    mock_session = MagicMock()
    mock_session.apply_transliteration = False

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_write_session(token, **kwargs):
        yield mock_session

    mock_adapter = MagicMock()
    mock_adapter.write_session = fake_write_session

    with patch("migration.to_spotify.ServiceRegistry") as MockRegistry, \
         patch("migration.to_spotify.bulk_insert_tracks", AsyncMock()), \
         patch("migration.to_spotify.update_migration", AsyncMock()), \
         patch("migration.to_spotify.run_pending_tracks_loop", AsyncMock(return_value=mock_stats)), \
         patch("migration.to_spotify._create_bot_playlist", AsyncMock()) as mock_create:
        MockRegistry.get.return_value = mock_adapter
        stats = await migrate_to_spotify(
            tracks_data=[{"artist": "A", "title": "T"}],
            artists_data=[],
            spotify_token="tok",
            migration_id=1,
            playlist_mode=True,
        )

    mock_create.assert_not_called()
    assert stats.playlist_url is None


@pytest.mark.asyncio
async def test_migrate_to_spotify_no_playlist_when_mode_false():
    """playlist_mode=False → _create_bot_playlist is never called."""
    from migration.to_spotify import migrate_to_spotify

    mock_stats = MagicMock()
    mock_stats.total = 1
    mock_stats.liked = 1
    mock_stats.in_playlist = 0
    mock_stats.not_found = 0
    mock_stats.errors = 0
    mock_stats.uncertain = 0

    mock_session = MagicMock()
    mock_session.apply_transliteration = False

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_write_session(token, **kwargs):
        yield mock_session

    mock_adapter = MagicMock()
    mock_adapter.write_session = fake_write_session

    with patch("migration.to_spotify.ServiceRegistry") as MockRegistry, \
         patch("migration.to_spotify.bulk_insert_tracks", AsyncMock()), \
         patch("migration.to_spotify.update_migration", AsyncMock()), \
         patch("migration.to_spotify.run_pending_tracks_loop", AsyncMock(return_value=mock_stats)), \
         patch("migration.to_spotify._create_bot_playlist", AsyncMock()) as mock_create:
        MockRegistry.get.return_value = mock_adapter
        await migrate_to_spotify(
            tracks_data=[{"artist": "A", "title": "T"}],
            artists_data=[],
            spotify_token="tok",
            migration_id=1,
            playlist_mode=False,
        )

    mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# _create_bot_playlist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_bot_playlist_no_token_returns_none():
    """Returns None when SPOTIFY_BOT_TOKEN is not configured."""
    from migration.to_spotify import _create_bot_playlist

    with patch("config.settings") as mock_settings, \
         patch("migration.to_spotify.get_track_urls_by_status", AsyncMock(return_value=["id1"])):
        mock_settings.spotify_bot_token = ""
        result = await _create_bot_playlist(1, "Test")

    assert result is None


@pytest.mark.asyncio
async def test_create_bot_playlist_creates_and_returns_url():
    """Creates playlist via bot client and returns the URL."""
    from migration.to_spotify import _create_bot_playlist

    mock_client = MagicMock()
    mock_client.create_playlist = AsyncMock(return_value=("playlist_id_123", "https://open.spotify.com/playlist/123"))
    mock_client.add_tracks_to_playlist = AsyncMock()
    mock_client.close = AsyncMock()

    with patch("config.settings") as mock_settings, \
         patch("migration.to_spotify.get_track_urls_by_status", AsyncMock(return_value=["sp1", "sp2"])), \
         patch("core.spotify.client.SpotifyClient") as MockClient:
        mock_settings.spotify_bot_token = "bot_token_xyz"
        MockClient.return_value.init = AsyncMock(return_value=mock_client)

        result = await _create_bot_playlist(42, "My Playlist")

    assert result == "https://open.spotify.com/playlist/123"
    mock_client.create_playlist.assert_called_once_with("My Playlist")
    mock_client.add_tracks_to_playlist.assert_called_once_with(
        "playlist_id_123",
        ["spotify:track:sp1", "spotify:track:sp2"],
    )
    mock_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_create_bot_playlist_no_tracks_returns_none():
    """Returns None when there are no in_playlist tracks."""
    from migration.to_spotify import _create_bot_playlist

    with patch("config.settings") as mock_settings, \
         patch("migration.to_spotify.get_track_urls_by_status", AsyncMock(return_value=[])):
        mock_settings.spotify_bot_token = "bot_token_xyz"
        result = await _create_bot_playlist(1, "Empty")

    assert result is None


# ---------------------------------------------------------------------------
# SpotifyClient.create_playlist / add_tracks_to_playlist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spotify_client_create_playlist():
    """create_playlist calls POST /users/{user_id}/playlists and returns (id, url)."""
    from core.spotify.client import SpotifyClient

    mock_session = MagicMock()

    me_resp = MagicMock()
    me_resp.json = AsyncMock(return_value={"id": "user123"})
    me_resp.__aenter__ = AsyncMock(return_value=me_resp)
    me_resp.__aexit__ = AsyncMock(return_value=False)

    playlist_resp = MagicMock()
    playlist_resp.json = AsyncMock(return_value={
        "id": "pl_id_abc",
        "external_urls": {"spotify": "https://open.spotify.com/playlist/pl_id_abc"},
    })
    playlist_resp.__aenter__ = AsyncMock(return_value=playlist_resp)
    playlist_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session.get = MagicMock(return_value=me_resp)
    mock_session.post = MagicMock(return_value=playlist_resp)

    client = SpotifyClient("fake_token")
    client._session = mock_session

    pl_id, pl_url = await client.create_playlist("Test Playlist")
    assert pl_id == "pl_id_abc"
    assert pl_url == "https://open.spotify.com/playlist/pl_id_abc"


@pytest.mark.asyncio
async def test_spotify_client_add_tracks_to_playlist_batches():
    """add_tracks_to_playlist sends requests in batches of 100."""
    from core.spotify.client import SpotifyClient

    batch_resp = MagicMock()
    batch_resp.status = 201
    batch_resp.__aenter__ = AsyncMock(return_value=batch_resp)
    batch_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=batch_resp)

    client = SpotifyClient("fake_token")
    client._session = mock_session

    # 150 tracks → 2 batches
    uris = [f"spotify:track:id{i}" for i in range(150)]
    await client.add_tracks_to_playlist("pl_id", uris)

    assert mock_session.post.call_count == 2


# ---------------------------------------------------------------------------
# notifications.migration_done_text — playlist_url
# ---------------------------------------------------------------------------

def test_migration_done_text_includes_playlist_url():
    """playlist_url is included as a link when provided."""
    from worker.notifications import migration_done_text

    tracks = {"liked": 0, "in_playlist": 5, "not_found": 1, "error": 0}
    text = migration_done_text(
        migration_id=7,
        tracks=tracks,
        lang="ru",
        playlist_url="https://open.spotify.com/playlist/abc123",
    )

    assert "https://open.spotify.com/playlist/abc123" in text


def test_migration_done_text_no_playlist_url():
    """No playlist link when playlist_url is None."""
    from worker.notifications import migration_done_text

    tracks = {"liked": 3, "not_found": 1, "error": 0}
    text = migration_done_text(migration_id=8, tracks=tracks, lang="ru")

    assert "open.spotify.com" not in text
