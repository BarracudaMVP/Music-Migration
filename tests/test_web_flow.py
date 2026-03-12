"""Tests for HTMX flow endpoints (MM-62)."""
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
    return pool


@pytest.fixture(autouse=True)
def ensure_services_registered():
    from core.services.registry import ServiceRegistry
    from core.services.yandex.adapter import YandexMusicAdapter
    from core.services.soundcloud.adapter import SoundCloudAdapter
    from core.services.file.adapter import FileAdapter
    for adapter in [YandexMusicAdapter(), SoundCloudAdapter(), FileAdapter()]:
        ServiceRegistry.register(adapter)


@pytest.mark.asyncio
async def test_flow_to_step_returns_html(app, mock_arq_pool):
    """GET /api/flow/to-step?from=yandex_music → 200 with HTML fragment."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/flow/to-step?from=yandex_music")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_flow_to_step_missing_param_returns_422(app, mock_arq_pool):
    """GET /api/flow/to-step without ?from → 422 (required query param)."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/flow/to-step")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_flow_rest_returns_html(app, mock_arq_pool):
    """GET /api/flow/rest?from=yandex_music&to=soundcloud → 200 with HTML fragment."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.web.load_user_session", new_callable=AsyncMock, return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/flow/rest?from=yandex_music&to=soundcloud")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_flow_rest_missing_params_returns_422(app, mock_arq_pool):
    """GET /api/flow/rest without required params → 422."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/flow/rest?from=yandex_music")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_flow_to_step_file_returns_html(app, mock_arq_pool):
    """GET /api/flow/to-step?from=file → 200 with TO services that support write."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/flow/to-step?from=file")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_flow_rest_from_file_returns_html(app, mock_arq_pool):
    """GET /api/flow/rest?from=file&to=soundcloud → 200 with file picker."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.web.load_user_session", new_callable=AsyncMock, return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/flow/rest?from=file&to=soundcloud")
    assert response.status_code == 200
    body = response.text
    assert "flow-file-input" in body  # file picker present


@pytest.mark.asyncio
async def test_flow_rest_to_file_returns_html(app, mock_arq_pool):
    """GET /api/flow/rest?from=yandex_music&to=file → 200 with export_fmt selector."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.web.load_user_session", new_callable=AsyncMock, return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/flow/rest?from=yandex_music&to=file")
    assert response.status_code == 200
    body = response.text
    assert "export_fmt" in body  # format selector present



@pytest.mark.asyncio
async def test_index_includes_file_from_service(app, mock_arq_pool):
    """GET / → index includes file as a FROM option."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.web.load_user_session", new_callable=AsyncMock, return_value=None):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/")
    assert response.status_code == 200
    body = response.text
    # file button should appear in FROM step
    assert 'data-from="file"' in body
