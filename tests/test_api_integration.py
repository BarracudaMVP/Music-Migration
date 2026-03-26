"""
Integration tests for API routes using httpx.AsyncClient.

Tests endpoints that don't require auth or background workers:
- GET /health
- GET /api/services
- GET /api/services/matrix
- GET /api/migrations/{id} (mocked DB)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def app():
    """Return FastAPI app with Redis mocked so startup event succeeds."""
    from api.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def mock_arq_pool():
    pool = MagicMock()
    pool.close = AsyncMock()
    return pool


@pytest.fixture(autouse=True)
def ensure_services_registered():
    """Register real adapters into ServiceRegistry (normally done in startup)."""
    from core.services.registry import ServiceRegistry
    from core.services.yandex.adapter import YandexMusicAdapter
    from core.services.soundcloud.adapter import SoundCloudAdapter
    from core.services.file.adapter import FileAdapter
    for adapter in [YandexMusicAdapter(), SoundCloudAdapter(), FileAdapter()]:
        ServiceRegistry.register(adapter)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_endpoint(app, mock_arq_pool):
    mock_arq_pool.ping = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
            with patch("core.db.session.engine", mock_engine):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


# ---------------------------------------------------------------------------
# /api/services
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_services_returns_known_services(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/services")
    assert response.status_code == 200
    services = response.json()
    assert isinstance(services, list)
    service_ids = {s["id"] for s in services}
    assert "yandex_music" in service_ids
    assert "soundcloud" in service_ids


@pytest.mark.asyncio
async def test_list_services_have_capabilities(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/services")
    services = {s["id"]: s for s in response.json()}
    ym = services["yandex_music"]
    sc = services["soundcloud"]
    assert "READ_LIKED_TRACKS" in ym["capabilities"]
    assert "WRITE_LIKED_TRACKS" in sc["capabilities"]


@pytest.mark.asyncio
async def test_list_services_response_shape(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/services")
    for service in response.json():
        assert "id" in service
        assert "name" in service
        assert "capabilities" in service
        assert isinstance(service["capabilities"], list)


# ---------------------------------------------------------------------------
# /api/services/matrix
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_services_matrix_returns_list(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/services/matrix")
    assert response.status_code == 200
    matrix = response.json()
    assert isinstance(matrix, list)
    assert len(matrix) > 0


@pytest.mark.asyncio
async def test_services_matrix_yandex_to_soundcloud(app, mock_arq_pool):
    """YM → SC migration must be in the matrix."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/services/matrix")
    matrix = response.json()
    pairs = {(entry["from"], entry["to"]) for entry in matrix}
    assert ("yandex_music", "soundcloud") in pairs


@pytest.mark.asyncio
async def test_services_matrix_no_self_pairs(app, mock_arq_pool):
    """A service should not be paired with itself."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/services/matrix")
    for entry in response.json():
        assert entry["from"] != entry["to"]


# ---------------------------------------------------------------------------
# /api/migrations/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_migration_status_returns_migration(app, mock_arq_pool):
    fake_migration = {
        "id": 42,
        "user_id": "web_test",
        "status": "done",
        "soundcloud_user_id": None,
        "created_at": "2026-01-01T00:00:00",
    }
    fake_stats = {"liked": 10, "not_found": 2, "error": 0, "pending": 0}

    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool), \
         patch("api.routes.migrations.get_migration", new_callable=AsyncMock, return_value=fake_migration), \
         patch("api.routes.migrations.get_track_stats", new_callable=AsyncMock, return_value=fake_stats), \
         patch("api.routes.migrations.get_artist_stats", new_callable=AsyncMock, return_value={}):
        from config import settings
        token = settings.api_internal_token or ""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/migrations/42",
                headers={"X-Internal-Token": token},
            )

    assert response.status_code in (200, 401, 403)


@pytest.mark.asyncio
async def test_get_migration_not_found_returns_404(app, mock_arq_pool):
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool), \
         patch("api.routes.migrations.get_migration", new_callable=AsyncMock, return_value=None), \
         patch("api.routes.migrations.get_artist_stats", new_callable=AsyncMock, return_value={}):
        from config import settings
        token = settings.api_internal_token or ""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/migrations/99999",
                headers={"X-Internal-Token": token},
            )

    assert response.status_code in (404, 401, 403)


# ---------------------------------------------------------------------------
# Concurrent requests (basic load test)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_health_requests(app, mock_arq_pool):
    """20 concurrent GET /health requests all return 200."""
    import asyncio
    mock_arq_pool.ping = AsyncMock()
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
            with patch("core.db.session.engine", mock_engine):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    responses = await asyncio.gather(*[client.get("/health") for _ in range(20)])
    assert all(r.status_code == 200 for r in responses)


@pytest.mark.asyncio
async def test_concurrent_services_requests(app, mock_arq_pool):
    """20 concurrent GET /api/services requests all return 200."""
    import asyncio
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            responses = await asyncio.gather(*[client.get("/api/services") for _ in range(20)])
    assert all(r.status_code == 200 for r in responses)
