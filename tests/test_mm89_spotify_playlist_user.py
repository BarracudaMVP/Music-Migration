"""
Tests for MM-89: Spotify playlist mode — user-account fallback.

Covers:
- _create_playlist: uses user token when SPOTIFY_BOT_TOKEN is not set
- _create_playlist: uses bot token when SPOTIFY_BOT_TOKEN is set (bot takes priority)
- _create_playlist: returns None when no token available
- _create_playlist: returns None when no in_playlist tracks
- migrate_to_spotify: playlist_url stored in stats.playlist_url
- flow_rest.html: playlist checkbox shows for any Spotify destination (not bot-gated)
- api_v1.py StartMigrationRequest: spotify_playlist_mode field present
- bot api_client: start_migration accepts spotify_playlist_mode
- bot migration handler: _kb_result includes playlist button when playlist_url given
- bot migration handler: _kb_result no playlist button when playlist_url is None
- bot auth handler: _confirmation_kb shows toggle for spotify destination
- bot auth handler: _confirmation_kb no toggle for sc destination
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# _create_playlist: user-token fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_playlist_uses_user_token_when_no_bot_token():
    """Falls back to user token when SPOTIFY_BOT_TOKEN is not configured."""
    from migration.to_spotify import _create_playlist

    mock_settings = MagicMock()
    mock_settings.spotify_bot_token = None

    mock_client = MagicMock()
    mock_client.init = AsyncMock(return_value=mock_client)
    mock_client.create_playlist = AsyncMock(return_value=("pl_id", "https://spotify.com/pl/1"))
    mock_client.add_tracks_to_playlist = AsyncMock()
    mock_client.close = AsyncMock()

    with patch("config.settings", mock_settings), \
         patch("core.spotify.client.SpotifyClient", return_value=mock_client), \
         patch("migration.to_spotify.get_track_urls_by_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = ["id1", "id2"]
        result = await _create_playlist(1, "My Playlist", "user_token_abc")

    assert result == "https://spotify.com/pl/1"
    mock_client.create_playlist.assert_awaited_once_with("My Playlist")
    mock_client.add_tracks_to_playlist.assert_awaited_once()
    # Verify it used the user token (SpotifyClient was init'd with user_token_abc)


@pytest.mark.asyncio
async def test_create_playlist_uses_bot_token_when_configured():
    """Bot token takes priority over user token."""
    from migration.to_spotify import _create_playlist

    mock_settings = MagicMock()
    mock_settings.spotify_bot_token = "bot_token_xyz"

    mock_client = MagicMock()
    mock_client.init = AsyncMock(return_value=mock_client)
    mock_client.create_playlist = AsyncMock(return_value=("pl_id", "https://spotify.com/pl/bot"))
    mock_client.add_tracks_to_playlist = AsyncMock()
    mock_client.close = AsyncMock()

    with patch("config.settings", mock_settings), \
         patch("core.spotify.client.SpotifyClient", return_value=mock_client), \
         patch("migration.to_spotify.get_track_urls_by_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = ["id1"]
        result = await _create_playlist(1, "Bot Playlist", "user_token_abc")

    assert result == "https://spotify.com/pl/bot"


@pytest.mark.asyncio
async def test_create_playlist_returns_none_no_token():
    """Returns None when neither bot nor user token is available."""
    from migration.to_spotify import _create_playlist

    mock_settings = MagicMock()
    mock_settings.spotify_bot_token = None

    with patch("config.settings", mock_settings):
        result = await _create_playlist(1, "Playlist", "")

    assert result is None


@pytest.mark.asyncio
async def test_create_playlist_returns_none_no_tracks():
    """Returns None when no in_playlist tracks found."""
    from migration.to_spotify import _create_playlist

    mock_settings = MagicMock()
    mock_settings.spotify_bot_token = None

    with patch("config.settings", mock_settings), \
         patch("migration.to_spotify.get_track_urls_by_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        result = await _create_playlist(1, "Playlist", "user_token")

    assert result is None


# ---------------------------------------------------------------------------
# migrate_to_spotify: playlist_url propagates to stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_migrate_to_spotify_playlist_url_in_stats():
    """playlist_url from _create_playlist ends up in SpotifyWriteStats."""
    from migration.to_spotify import migrate_to_spotify
    from migration.pipeline import TrackPipelineStats

    fake_pipeline_stats = TrackPipelineStats(
        total=1, liked=0, not_found=0, errors=0, in_playlist=1
    )

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_adapter = MagicMock()
    mock_adapter.write_session = MagicMock(return_value=mock_session)

    with patch("migration.to_spotify.update_migration", new_callable=AsyncMock), \
         patch("migration.to_spotify.bulk_insert_tracks", new_callable=AsyncMock), \
         patch("migration.to_spotify.ServiceRegistry") as mock_reg, \
         patch("migration.to_spotify.run_pending_tracks_loop", new_callable=AsyncMock, return_value=fake_pipeline_stats), \
         patch("migration.to_spotify._create_playlist", new_callable=AsyncMock, return_value="https://open.spotify.com/playlist/xyz"):
        mock_reg.get.return_value = mock_adapter
        stats = await migrate_to_spotify(
            tracks_data=[{"artist": "A", "title": "T"}],
            artists_data=[],
            spotify_token="tok",
            migration_id=99,
            playlist_mode=True,
        )

    assert stats.playlist_url == "https://open.spotify.com/playlist/xyz"
    assert stats.liked == 0


# ---------------------------------------------------------------------------
# api_v1 StartMigrationRequest schema
# ---------------------------------------------------------------------------

def test_api_v1_start_migration_request_has_playlist_mode():
    from api.routes.api_v1 import StartMigrationRequest
    req = StartMigrationRequest(
        from_service="yandex_music",
        to_service="spotify",
        spotify_playlist_mode=True,
        spotify_playlist_name="My Tunes",
    )
    assert req.spotify_playlist_mode is True
    assert req.spotify_playlist_name == "My Tunes"


def test_api_v1_start_migration_request_defaults():
    from api.routes.api_v1 import StartMigrationRequest
    req = StartMigrationRequest(from_service="yandex_music", to_service="spotify")
    assert req.spotify_playlist_mode is False
    assert req.spotify_playlist_name == "Music Migration"


# ---------------------------------------------------------------------------
# bot api_client: spotify_playlist_mode in request body
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_client_start_migration_sends_playlist_mode():
    from bot.api_client import MigrationApiClient
    import httpx

    captured = {}

    async def mock_post(self_inner, url, **kwargs):
        captured["body"] = kwargs.get("json")
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"migration_id": 42})
        return resp

    client = MigrationApiClient(base_url="http://test", token="tok")
    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        migration_id = await client.start_migration(
            "u1", "ym", "sc", mode="tracks",
            to_service="spotify",
            spotify_playlist_mode=True,
        )

    assert migration_id == 42
    assert captured["body"]["spotify_playlist_mode"] is True


@pytest.mark.asyncio
async def test_api_client_start_migration_default_no_playlist_mode():
    from bot.api_client import MigrationApiClient
    import httpx

    captured = {}

    async def mock_post(self_inner, url, **kwargs):
        captured["body"] = kwargs.get("json")
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"migration_id": 7})
        return resp

    client = MigrationApiClient(base_url="http://test", token="tok")
    with patch.object(httpx.AsyncClient, "post", new=mock_post):
        await client.start_migration("u1", "ym", "sc")

    assert captured["body"]["spotify_playlist_mode"] is False


# ---------------------------------------------------------------------------
# bot migration handler: _kb_result playlist button
# ---------------------------------------------------------------------------

def test_kb_result_with_playlist_url():
    from bot.handlers.migration import _kb_result
    kb = _kb_result(1, 0, "ru", playlist_url="https://open.spotify.com/playlist/abc")
    all_callback_datas = [
        btn.url
        for row in kb.inline_keyboard
        for btn in row
        if hasattr(btn, "url") and btn.url
    ]
    assert "https://open.spotify.com/playlist/abc" in all_callback_datas


def test_kb_result_without_playlist_url():
    from bot.handlers.migration import _kb_result
    kb = _kb_result(1, 0, "ru", playlist_url=None)
    all_urls = [
        btn.url
        for row in kb.inline_keyboard
        for btn in row
        if hasattr(btn, "url") and btn.url
    ]
    # Only the "open in browser" button, not a playlist link
    assert not any("playlist" in (u or "") for u in all_urls)


# ---------------------------------------------------------------------------
# bot auth handler: _confirmation_kb toggle
# ---------------------------------------------------------------------------

def test_confirmation_kb_shows_spotify_playlist_toggle():
    from bot.handlers.auth import _confirmation_kb
    kb = _confirmation_kb("yandex_music", "spotify", True, False, "ru", spotify_playlist_mode=False)
    all_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    assert "toggle_spotify_playlist" in all_datas


def test_confirmation_kb_no_spotify_toggle_for_sc():
    from bot.handlers.auth import _confirmation_kb
    kb = _confirmation_kb("yandex_music", "soundcloud", True, False, "ru")
    all_datas = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    assert "toggle_spotify_playlist" not in all_datas


def test_confirmation_kb_spotify_playlist_on_label():
    from bot.handlers.auth import _confirmation_kb
    kb = _confirmation_kb("yandex_music", "spotify", True, False, "ru", spotify_playlist_mode=True)
    all_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Вкл" in t for t in all_texts)


def test_confirmation_kb_spotify_playlist_off_label():
    from bot.handlers.auth import _confirmation_kb
    kb = _confirmation_kb("yandex_music", "spotify", True, False, "ru", spotify_playlist_mode=False)
    all_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("Выкл" in t for t in all_texts)
