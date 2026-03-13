"""Tests for MM-81: Public JSON API v1 for SPA frontend (api/routes/api_v1.py)."""
from __future__ import annotations

import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# security.py: create/decode/get_current_user
# ---------------------------------------------------------------------------


def test_create_and_decode_access_token():
    from api.security import create_access_token, decode_access_token
    token = create_access_token("user123")
    assert decode_access_token(token) == "user123"


def test_decode_invalid_token_returns_none():
    from api.security import decode_access_token
    assert decode_access_token("not.a.jwt") is None


def test_decode_wrong_secret_returns_none():
    import jwt
    from datetime import datetime, timezone, timedelta
    payload = {"sub": "user123", "exp": datetime.now(timezone.utc) + timedelta(seconds=900)}
    bad_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
    from api.security import decode_access_token
    assert decode_access_token(bad_token) is None


def test_create_refresh_token_is_hex():
    from api.security import create_refresh_token
    token = create_refresh_token()
    assert len(token) == 64
    int(token, 16)  # must be valid hex


# ---------------------------------------------------------------------------
# GET /api/v1/services
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_services_v1(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/services")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    ids = [s["id"] for s in data]
    assert "yandex_music" in ids
    assert "soundcloud" in ids


@pytest.mark.asyncio
async def test_get_matrix_v1(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/services/matrix")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Each entry has from/to
    assert all("from" in entry and "to" in entry for entry in data)


# ---------------------------------------------------------------------------
# POST /api/v1/auth/exchange
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_success(app, mock_arq_pool):
    mock_arq_pool.get = AsyncMock(return_value=b"user_abc")

    import api.main as main_module
    original_pool = main_module._arq_pool
    main_module._arq_pool = mock_arq_pool
    try:
        with patch("api.routes.api_v1.save_spa_refresh_token", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/auth/exchange", json={"code": "test-code-123"})
    finally:
        main_module._arq_pool = original_pool

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_exchange_code_invalid(app, mock_arq_pool):
    mock_arq_pool.get = AsyncMock(return_value=None)

    import api.main as main_module
    original_pool = main_module._arq_pool
    main_module._arq_pool = mock_arq_pool
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/exchange", json={"code": "bad-code"})
    finally:
        main_module._arq_pool = original_pool

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_exchange_code_no_redis(app):
    import api.main as main_module
    original_pool = main_module._arq_pool
    main_module._arq_pool = None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/exchange", json={"code": "x"})
    finally:
        main_module._arq_pool = original_pool

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_invalid(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.api_v1.get_user_id_by_spa_refresh_token", new_callable=AsyncMock, return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "no-such-token"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/auth/me — requires Bearer token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_missing_token(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token.here"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_valid_token_no_session(app, mock_arq_pool):
    token = _make_valid_token("user_xyz")
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.api_v1.load_user_session", new_callable=AsyncMock, return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "user_xyz"
    assert data["ym_connected"] is False


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_missing_token(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_valid_token(app, mock_arq_pool):
    token = _make_valid_token("user_logout")
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.api_v1.revoke_spa_refresh_token", new_callable=AsyncMock) as mock_revoke:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 204
    mock_revoke.assert_called_once_with("user_logout")


# ---------------------------------------------------------------------------
# OAuth start routes (now canonical — no /start suffix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yandex_oauth_no_redirect_uri(app, mock_arq_pool):
    """/api/v1/auth/yandex without YANDEX_REDIRECT_URI → /?error="""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("config.settings.yandex_redirect_uri", ""):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as client:
                response = await client.get("/api/v1/auth/yandex")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")


@pytest.mark.asyncio
async def test_yandex_oauth_redirects_to_provider(app, mock_arq_pool):
    """/api/v1/auth/yandex with config → redirect to Yandex OAuth."""
    mock_arq_pool.setex = AsyncMock()
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("config.settings.yandex_redirect_uri", "https://example.com/callback"):
            with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
                with patch("bot.oauth.yandex.get_callback_auth_url", return_value="https://oauth.yandex.ru/authorize?state=web_xxx"):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as client:
                        response = await client.get("/api/v1/auth/yandex")
    assert response.status_code == 303
    assert "oauth.yandex.ru" in response.headers["location"]


@pytest.mark.asyncio
async def test_spotify_oauth_no_client_id(app, mock_arq_pool):
    """/api/v1/auth/spotify without SPOTIFY_CLIENT_ID → /?error="""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("config.settings.spotify_client_id", ""):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as client:
                response = await client.get("/api/v1/auth/spotify")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")


@pytest.mark.asyncio
async def test_soundcloud_oauth_no_client_id(app, mock_arq_pool):
    """/api/v1/auth/soundcloud without SC_CLIENT_ID → /?error="""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("config.settings.sc_client_id", ""):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as client:
                response = await client.get("/api/v1/auth/soundcloud")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")


@pytest.mark.asyncio
async def test_old_start_routes_gone(app, mock_arq_pool):
    """/api/v1/auth/yandex/start etc. removed — 404."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as client:
            r1 = await client.get("/api/v1/auth/yandex/start")
            r2 = await client.get("/api/v1/auth/spotify/start")
            r3 = await client.get("/api/v1/auth/soundcloud/start")
    assert r1.status_code == 404
    assert r2.status_code == 404
    assert r3.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/v1/migrations — requires auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_migrations_no_auth(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/migrations")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_migrations_with_auth(app, mock_arq_pool):
    token = _make_valid_token("user_list")
    fake_migrations = [
        {"id": 1, "user_id": "user_list", "from_service": "yandex_music",
         "to_service": "soundcloud", "status": "done", "created_at": datetime(2025, 1, 1)},
    ]
    fake_stats = {"total": 1, "liked": 1, "not_found": 0, "error": 0, "pending": 0, "uncertain": 0}
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.api_v1.get_user_migrations", new_callable=AsyncMock, return_value=fake_migrations):
            with patch("api.routes.api_v1.get_track_stats", new_callable=AsyncMock, return_value=fake_stats):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.get(
                        "/api/v1/migrations",
                        headers={"Authorization": f"Bearer {token}"},
                    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# GET /api/v1/migrations/{id} — requires auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_migration_not_found(app, mock_arq_pool):
    token = _make_valid_token("user_notfound")
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.api_v1.get_migration", new_callable=AsyncMock, return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/migrations/9999",
                    headers={"Authorization": f"Bearer {token}"},
                )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_migration_wrong_user(app, mock_arq_pool):
    token = _make_valid_token("user_a")
    # Migration exists but owned by user_b
    fake_migration = {
        "id": 1, "user_id": "user_b", "from_service": "yandex_music",
        "to_service": "soundcloud", "status": "done", "created_at": datetime(2025, 1, 1),
    }
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.api_v1.get_migration", new_callable=AsyncMock, return_value=fake_migration):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/migrations/1",
                    headers={"Authorization": f"Bearer {token}"},
                )
    # Route checks migration["user_id"] != user_id → 404
    assert response.status_code == 404
