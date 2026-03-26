"""Tests for MM-98: tracks_override in POST /api/v1/migrations."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    from api.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def mock_arq_pool():
    pool = MagicMock()
    pool.close = AsyncMock()
    pool.get = AsyncMock(return_value=None)
    pool.delete = AsyncMock()
    pool.setex = AsyncMock()
    pool.enqueue_job = AsyncMock()
    return pool


@pytest.fixture(autouse=True)
def ensure_services_registered():
    from core.services.registry import ServiceRegistry
    from core.services.yandex.adapter import YandexMusicAdapter
    from core.services.soundcloud.adapter import SoundCloudAdapter
    from core.services.file.adapter import FileAdapter
    from core.services.spotify.adapter import SpotifyAdapter
    for adapter in [YandexMusicAdapter(), SoundCloudAdapter(), FileAdapter(), SpotifyAdapter()]:
        ServiceRegistry.register(adapter)


def _make_valid_token(user_id: str = "test_user") -> str:
    from api.security import create_access_token
    return create_access_token(user_id)


FAKE_SESSION = {
    "yandex_token": "ym_tok",
    "soundcloud_token": "sc_tok",
    "spotify_token": "sp_tok",
    "spotify_refresh_token": "sp_refresh",
    "soundcloud_refresh_token": "sc_refresh",
    "lang": "ru",
    "role": "user",
}

SAMPLE_TRACKS = [
    {"artist": "Artist A", "title": "Song 1"},
    {"artist": "Artist B", "title": "Song 2"},
]


# ---------------------------------------------------------------------------
# POST /api/v1/migrations — tracks_override file→YM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_migration_file_to_ym_with_tracks_override(app, mock_arq_pool):
    """file→YM with tracks_override must enqueue run_yandex_migration_job with tracks_override."""
    token = _make_valid_token("user_file_ym")

    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
            with patch("api.routes.api_v1.load_user_session", new_callable=AsyncMock, return_value=FAKE_SESSION):
                with patch("api.routes.api_v1.create_migration", new_callable=AsyncMock, return_value=42):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/migrations",
                            json={
                                "from_service": "file",
                                "to_service": "yandex_music",
                                "tracks_override": SAMPLE_TRACKS,
                            },
                            headers={"Authorization": f"Bearer {token}"},
                        )

    assert response.status_code == 201
    assert response.json()["migration_id"] == 42

    mock_arq_pool.enqueue_job.assert_called_once()
    job_name, *_ = mock_arq_pool.enqueue_job.call_args.args
    assert job_name == "run_yandex_migration_job"
    kwargs = mock_arq_pool.enqueue_job.call_args.kwargs
    assert kwargs["tracks_override"] == SAMPLE_TRACKS


@pytest.mark.asyncio
async def test_start_migration_file_to_spotify_with_tracks_override(app, mock_arq_pool):
    """file→Spotify with tracks_override must enqueue run_spotify_write_job with tracks_override."""
    token = _make_valid_token("user_file_sp")

    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
            with patch("api.routes.api_v1.load_user_session", new_callable=AsyncMock, return_value=FAKE_SESSION):
                with patch("api.routes.api_v1.create_migration", new_callable=AsyncMock, return_value=43):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/migrations",
                            json={
                                "from_service": "file",
                                "to_service": "spotify",
                                "tracks_override": SAMPLE_TRACKS,
                                "spotify_playlist_mode": True,
                                "spotify_playlist_name": "My Import",
                            },
                            headers={"Authorization": f"Bearer {token}"},
                        )

    assert response.status_code == 201
    assert response.json()["migration_id"] == 43

    mock_arq_pool.enqueue_job.assert_called_once()
    job_name, *_ = mock_arq_pool.enqueue_job.call_args.args
    assert job_name == "run_spotify_write_job"
    kwargs = mock_arq_pool.enqueue_job.call_args.kwargs
    assert kwargs["tracks_override"] == SAMPLE_TRACKS
    assert kwargs["playlist_mode"] is True
    assert kwargs["playlist_name"] == "My Import"


@pytest.mark.asyncio
async def test_start_migration_file_to_sc_with_tracks_override(app, mock_arq_pool):
    """file→SC with tracks_override must enqueue run_file_migration_job with tracks list."""
    token = _make_valid_token("user_file_sc")

    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
            with patch("api.routes.api_v1.load_user_session", new_callable=AsyncMock, return_value=FAKE_SESSION):
                with patch("api.routes.api_v1.create_migration", new_callable=AsyncMock, return_value=44):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/migrations",
                            json={
                                "from_service": "file",
                                "to_service": "soundcloud",
                                "tracks_override": SAMPLE_TRACKS,
                            },
                            headers={"Authorization": f"Bearer {token}"},
                        )

    assert response.status_code == 201
    assert response.json()["migration_id"] == 44

    mock_arq_pool.enqueue_job.assert_called_once()
    job_name, *_ = mock_arq_pool.enqueue_job.call_args.args
    assert job_name == "run_file_migration_job"
    kwargs = mock_arq_pool.enqueue_job.call_args.kwargs
    assert kwargs["tracks"] == SAMPLE_TRACKS


@pytest.mark.asyncio
async def test_start_migration_file_to_sc_without_tracks_override_returns_400(app, mock_arq_pool):
    """file→SC without tracks_override must return 400."""
    token = _make_valid_token("user_file_sc_notrack")

    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
            with patch("api.routes.api_v1.load_user_session", new_callable=AsyncMock, return_value=FAKE_SESSION):
                with patch("api.routes.api_v1.create_migration", new_callable=AsyncMock, return_value=45):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/migrations",
                            json={
                                "from_service": "file",
                                "to_service": "soundcloud",
                            },
                            headers={"Authorization": f"Bearer {token}"},
                        )

    assert response.status_code == 400
    assert "tracks_override" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_start_migration_normal_ym_to_sc_no_tracks_override(app, mock_arq_pool):
    """Normal YM→SC migration must NOT pass tracks_override to run_migration_job."""
    token = _make_valid_token("user_ym_sc")

    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
            with patch("api.routes.api_v1.load_user_session", new_callable=AsyncMock, return_value=FAKE_SESSION):
                with patch("api.routes.api_v1.create_migration", new_callable=AsyncMock, return_value=46):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.post(
                            "/api/v1/migrations",
                            json={
                                "from_service": "yandex_music",
                                "to_service": "soundcloud",
                            },
                            headers={"Authorization": f"Bearer {token}"},
                        )

    assert response.status_code == 201
    job_name, *_ = mock_arq_pool.enqueue_job.call_args.args
    assert job_name == "run_migration_job"
    # run_migration_job does NOT receive tracks_override
    kwargs = mock_arq_pool.enqueue_job.call_args.kwargs
    assert "tracks_override" not in kwargs
