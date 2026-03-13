"""Tests for MM-79: OAuth routes refactoring (api/routes/oauth.py)."""
import json
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
    pool.setex = AsyncMock()
    pool.get = AsyncMock(return_value=None)
    pool.delete = AsyncMock()
    return pool


@pytest.fixture(autouse=True)
def ensure_services_registered():
    from core.services.registry import ServiceRegistry
    from core.services.yandex.adapter import YandexMusicAdapter
    from core.services.soundcloud.adapter import SoundCloudAdapter
    from core.services.file.adapter import FileAdapter
    for adapter in [YandexMusicAdapter(), SoundCloudAdapter(), FileAdapter()]:
        ServiceRegistry.register(adapter)


# ---------------------------------------------------------------------------
# _ensure_user_id / _session_user_id moved to oauth.py
# ---------------------------------------------------------------------------

def test_session_user_id_returns_none_when_no_session():
    from api.routes.oauth import _session_user_id
    mock_request = MagicMock()
    mock_request.session = {}
    assert _session_user_id(mock_request) is None


def test_session_user_id_returns_value():
    from api.routes.oauth import _session_user_id
    mock_request = MagicMock()
    mock_request.session = {"user_id": "web_abc123"}
    assert _session_user_id(mock_request) == "web_abc123"


def test_ensure_user_id_creates_new_id():
    from api.routes.oauth import _ensure_user_id
    mock_request = MagicMock()
    mock_request.session = {}
    with patch("config.settings.dev_mode", False):
        uid = _ensure_user_id(mock_request)
    assert uid.startswith("web_")
    assert mock_request.session["user_id"] == uid


def test_ensure_user_id_reuses_existing():
    from api.routes.oauth import _ensure_user_id
    mock_request = MagicMock()
    mock_request.session = {"user_id": "web_existing123"}
    with patch("config.settings.dev_mode", False):
        uid = _ensure_user_id(mock_request)
    assert uid == "web_existing123"


def test_ensure_user_id_dev_mode():
    from api.routes.oauth import _ensure_user_id
    mock_request = MagicMock()
    mock_request.session = {}
    with patch("config.settings.dev_mode", True):
        uid = _ensure_user_id(mock_request)
    assert uid == "dev_user"
    assert mock_request.session["user_id"] == "dev_user"


# ---------------------------------------------------------------------------
# State helpers: Redis-based
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_state_save_and_get(mock_arq_pool):
    """State saved to Redis and retrieved correctly."""
    stored = {}

    async def fake_setex(key, ttl, value):
        stored[key] = value

    async def fake_get(key):
        val = stored.get(key)
        return val.encode() if isinstance(val, str) else val

    async def fake_delete(key):
        stored.pop(key, None)

    mock_arq_pool.setex = fake_setex
    mock_arq_pool.get = fake_get
    mock_arq_pool.delete = fake_delete

    import api.main as _main
    _main._arq_pool = mock_arq_pool
    try:
        from api.routes.oauth import _state_save, _state_get
        payload = {"flow_from": "yandex_music", "flow_to": "soundcloud"}
        await _state_save("ym", "test_state_123", payload)
        result = await _state_get("ym", "test_state_123")
    finally:
        _main._arq_pool = None

    assert result == payload
    # Key deleted after get
    assert "oauth_state:ym:test_state_123" not in stored


@pytest.mark.asyncio
async def test_state_get_missing_returns_none(mock_arq_pool):
    """_state_get returns None when state not in Redis."""
    mock_arq_pool.get = AsyncMock(return_value=None)
    import api.main as _main
    _main._arq_pool = mock_arq_pool
    try:
        from api.routes.oauth import _state_get
        result = await _state_get("ym", "nonexistent")
    finally:
        _main._arq_pool = None
    assert result is None


@pytest.mark.asyncio
async def test_issue_oauth_code_stores_user_id(mock_arq_pool):
    """_issue_oauth_code saves user_id to Redis with 30s TTL."""
    stored = {}

    async def fake_setex(key, ttl, value):
        stored[key] = (ttl, value)

    mock_arq_pool.setex = fake_setex
    import api.main as _main
    _main._arq_pool = mock_arq_pool
    try:
        from api.routes.oauth import _issue_oauth_code
        code = await _issue_oauth_code("web_user123")
    finally:
        _main._arq_pool = None

    assert len(code) == 32  # uuid4 hex
    key = f"oauth_code:{code}"
    assert key in stored
    ttl, val = stored[key]
    assert ttl == 30
    assert val == "web_user123"


# ---------------------------------------------------------------------------
# Yandex OAuth start
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_yandex_start_no_redirect_uri(app, mock_arq_pool):
    """GET /auth/yandex without YANDEX_REDIRECT_URI → redirect /?error=..."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("config.settings.yandex_redirect_uri", ""):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/auth/yandex", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")


@pytest.mark.asyncio
async def test_auth_yandex_start_redirects_to_yandex(app, mock_arq_pool):
    """GET /auth/yandex with YANDEX_REDIRECT_URI → redirect to Yandex OAuth."""
    mock_arq_pool.setex = AsyncMock()
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("config.settings.yandex_redirect_uri", "https://example.com/callback"):
            with patch("api.main.get_arq_pool", return_value=mock_arq_pool):
                with patch("bot.oauth.yandex.get_callback_auth_url", return_value="https://oauth.yandex.ru/authorize?state=web_xxx"):
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        response = await client.get("/auth/yandex", follow_redirects=False)
    assert response.status_code == 303
    assert "oauth.yandex.ru" in response.headers["location"]


# ---------------------------------------------------------------------------
# SoundCloud OAuth start
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_soundcloud_start_no_client_id(app, mock_arq_pool):
    """GET /auth/soundcloud without SC_CLIENT_ID → redirect /?error=..."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("config.settings.sc_client_id", ""):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/auth/soundcloud", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")


# ---------------------------------------------------------------------------
# Spotify OAuth start
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auth_spotify_start_no_client_id(app, mock_arq_pool):
    """GET /auth/spotify without SPOTIFY_CLIENT_ID → redirect /?error=..."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("config.settings.spotify_client_id", ""):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/auth/spotify", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/?error=")


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_clears_session_and_redirects(app, mock_arq_pool):
    """POST /auth/logout → 303 redirect to /."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.oauth.delete_user_session", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


# ---------------------------------------------------------------------------
# Session key: ym_connected (not ym_token)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flow_rest_ym_connected_via_session(app, mock_arq_pool):
    """flow_rest reads ym_connected (not ym_token) for auth status."""
    # Patch load_user_session to return a DB session with yandex_token
    db_session_mock = {"yandex_token": "fake_token", "soundcloud_token": "fake_sc"}
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        with patch("api.routes.web.load_user_session", new_callable=AsyncMock, return_value=db_session_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/flow/rest?from=yandex_music&to=soundcloud")
    assert response.status_code == 200
    # When DB has tokens, both services appear connected (no disabled button)
    assert "disabled" not in response.text or "from_connected" not in response.text


# GET /auth page removed (MM-75/81) — OAuth is redirect-only machinery, no HTML page


@pytest.mark.asyncio
async def test_post_auth_yandex_removed(app, mock_arq_pool):
    """POST /auth/yandex (manual code form) is removed — should 404 or 405."""
    with patch("api.main.create_pool", new_callable=AsyncMock, return_value=mock_arq_pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/auth/yandex", data={"code": "test123"}, follow_redirects=False)
    assert response.status_code in (404, 405)
