"""Tests for MM-97: Admin SPA — JWT role claim + admin-only endpoints."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
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


def _make_token(user_id: str = "user1", role: str = "user") -> str:
    from api.security import create_access_token
    return create_access_token(user_id, role=role)


ADMIN_SESSION = {
    "yandex_token": "", "soundcloud_token": "", "spotify_token": None,
    "spotify_refresh_token": None, "soundcloud_refresh_token": None,
    "lang": "ru", "role": "admin",
}

USER_SESSION = {
    "yandex_token": "tok", "soundcloud_token": "", "spotify_token": None,
    "spotify_refresh_token": None, "soundcloud_refresh_token": None,
    "lang": "ru", "role": "user",
}

FAKE_STATS = {
    "total_migrations": 5,
    "total_users": 2,
    "by_status": {"done": 3, "running": 1, "pending": 1},
    "recent": [],
}

FAKE_MIGRATIONS_PAGE = ([
    {"id": 1, "user_id": "user1", "from_service": "yandex_music", "to_service": "spotify",
     "status": "done", "user_migration_number": 1, "created_at": None, "result_path": None},
], 1)

FAKE_USERS_PAGE = ([
    {"user_id": "user1", "role": "user", "migration_count": 1},
    {"user_id": "admin1", "role": "admin", "migration_count": 0},
], 2)


# ---------------------------------------------------------------------------
# JWT role claim in exchange_code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_includes_role_in_jwt(app, mock_arq_pool):
    """exchange_code must create JWT with role from DB session."""
    import jwt as pyjwt
    from config import settings

    mock_arq_pool.get = AsyncMock(return_value=b"user_admin")

    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
            with patch("api.routes.api_v1.load_user_session", new_callable=AsyncMock, return_value=ADMIN_SESSION):
                with patch("api.routes.api_v1.save_spa_refresh_token", new_callable=AsyncMock):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.post("/api/v1/auth/exchange", json={"code": "some_code"})

    assert response.status_code == 200
    data = response.json()
    payload = pyjwt.decode(data["access_token"], settings.jwt_secret_key, algorithms=["HS256"])
    assert payload["role"] == "admin"
    assert payload["sub"] == "user_admin"


@pytest.mark.asyncio
async def test_exchange_code_role_user_by_default(app, mock_arq_pool):
    """exchange_code with user session → JWT role=user."""
    import jwt as pyjwt
    from config import settings

    mock_arq_pool.get = AsyncMock(return_value=b"regular_user")

    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
            with patch("api.routes.api_v1.load_user_session", new_callable=AsyncMock, return_value=USER_SESSION):
                with patch("api.routes.api_v1.save_spa_refresh_token", new_callable=AsyncMock):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.post("/api/v1/auth/exchange", json={"code": "some_code"})

    assert response.status_code == 200
    payload = pyjwt.decode(
        response.json()["access_token"], settings.jwt_secret_key, algorithms=["HS256"]
    )
    assert payload["role"] == "user"


# ---------------------------------------------------------------------------
# GET /api/v1/stats — require_admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_no_auth_returns_401(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/stats")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_stats_role_user_returns_403(app):
    token = _make_token("user1", role="user")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/stats", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_stats_role_admin_returns_200(app):
    token = _make_token("admin1", role="admin")
    with patch("api.routes.api_v1.get_admin_stats", new_callable=AsyncMock, return_value=FAKE_STATS):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/v1/stats", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["total_migrations"] == 5
    assert data["total_users"] == 2
    assert "by_status" in data
    assert "recent" in data


# ---------------------------------------------------------------------------
# GET /api/v1/users — require_admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_users_no_auth_returns_401(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/users")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_users_role_user_returns_403(app):
    token = _make_token("user1", role="user")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_users_role_admin_returns_200(app):
    token = _make_token("admin1", role="admin")
    with patch("api.routes.api_v1.get_all_users_paginated", new_callable=AsyncMock, return_value=FAKE_USERS_PAGE):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert len(data["users"]) == 2
    assert "page" in data
    assert "pages" in data


# ---------------------------------------------------------------------------
# GET /api/v1/migrations — admin sees all, user sees own
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migrations_admin_sees_all(app):
    """Admin without user_id filter sees all migrations."""
    token = _make_token("admin1", role="admin")
    with patch("api.routes.api_v1.get_all_migrations_paginated", new_callable=AsyncMock, return_value=FAKE_MIGRATIONS_PAGE):
        with patch("api.routes.api_v1.get_track_stats", new_callable=AsyncMock, return_value={}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.get("/api/v1/migrations", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "migrations" in data
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_migrations_admin_filter_by_user_id(app):
    """Admin with user_id filter sees that user's migrations."""
    token = _make_token("admin1", role="admin")
    with patch(
        "api.routes.api_v1.get_all_migrations_paginated",
        new_callable=AsyncMock,
        return_value=FAKE_MIGRATIONS_PAGE,
    ) as mock_paginated:
        with patch("api.routes.api_v1.get_track_stats", new_callable=AsyncMock, return_value={}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.get(
                    "/api/v1/migrations?user_id=user1",
                    headers={"Authorization": f"Bearer {token}"},
                )
    assert r.status_code == 200
    call_kwargs = mock_paginated.call_args.kwargs
    assert call_kwargs.get("user_id") == "user1"


@pytest.mark.asyncio
async def test_migrations_user_sees_only_own(app):
    """Regular user ignores user_id filter and sees only their own migrations."""
    token = _make_token("user1", role="user")
    own_migration = {
        "id": 10, "user_id": "user1", "from_service": "yandex_music", "to_service": "spotify",
        "status": "done", "user_migration_number": 1, "created_at": None,
    }
    with patch("api.routes.api_v1.get_user_migrations", new_callable=AsyncMock, return_value=[own_migration]):
        with patch("api.routes.api_v1.get_track_stats", new_callable=AsyncMock, return_value={}):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.get(
                    "/api/v1/migrations?user_id=admin1",
                    headers={"Authorization": f"Bearer {token}"},
                )
    assert r.status_code == 200
    data = r.json()
    assert len(data["migrations"]) == 1
    assert data["migrations"][0]["user_id"] == "user1"


# ---------------------------------------------------------------------------
# GET /api/v1/migrations/{id} — admin bypasses ownership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_detail_user_cannot_see_others(app):
    """User cannot see another user's migration."""
    token = _make_token("user1", role="user")
    other_migration = {
        "id": 99, "user_id": "other_user", "from_service": "yandex_music", "to_service": "spotify",
        "status": "done", "created_at": None, "result_path": None,
        "soundcloud_user_id": None, "user_migration_number": 1,
    }
    with patch("api.routes.api_v1.get_migration", new_callable=AsyncMock, return_value=other_migration):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/api/v1/migrations/99", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_migration_detail_admin_bypasses_ownership(app):
    """Admin can see any migration regardless of ownership."""
    token = _make_token("admin1", role="admin")
    other_migration = {
        "id": 99, "user_id": "other_user", "from_service": "yandex_music", "to_service": "spotify",
        "status": "done", "created_at": None, "result_path": None,
        "soundcloud_user_id": None, "user_migration_number": 1,
    }
    with patch("api.routes.api_v1.get_migration", new_callable=AsyncMock, return_value=other_migration):
        with patch("api.routes.api_v1.get_track_stats", new_callable=AsyncMock, return_value={}):
            with patch("api.main.get_arq_pool", return_value=None):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    r = await client.get(
                        "/api/v1/migrations/99",
                        headers={"Authorization": f"Bearer {token}"},
                    )
    assert r.status_code == 200
    assert r.json()["migration"]["user_id"] == "other_user"
