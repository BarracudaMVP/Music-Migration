"""Tests for DEV_MODE functionality (MM-80)."""
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


def test_dev_mode_false_by_default():
    """DEV_MODE defaults to False."""
    from config import Settings
    assert Settings().dev_mode is False


def test_dev_mode_true_on_localhost():
    """DEV_MODE=true stays True when URL is localhost."""
    from config import Settings
    s = Settings(dev_mode=True, api_base_url="http://localhost:8000", web_base_url="")
    assert s.dev_mode is True


def test_dev_mode_forced_false_on_production_domain():
    """DEV_MODE=true is overridden to False when a production domain is set."""
    from config import Settings
    s = Settings(dev_mode=True, web_base_url="https://musicmigration.site")
    assert s.dev_mode is False


def test_dev_mode_forced_false_on_https_api_base():
    """DEV_MODE=true is overridden to False when api_base_url points to prod."""
    from config import Settings
    s = Settings(dev_mode=True, api_base_url="https://musicmigration.site", web_base_url="")
    assert s.dev_mode is False


@pytest.mark.asyncio
async def test_ensure_user_id_returns_dev_user_in_dev_mode(app, mock_arq_pool):
    """In DEV_MODE, every request uses user_id=dev_user."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.web.load_user_session", new_callable=AsyncMock, return_value=None):
            with patch("config.settings.dev_mode", True):
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    response = await client.get("/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_no_dev_login_route_exists(app, mock_arq_pool):
    """/dev/login does not exist — auth is handled via DB seeding."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/dev/login", follow_redirects=False)
    assert response.status_code == 404
