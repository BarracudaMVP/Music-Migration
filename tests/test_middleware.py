"""Unit tests for AllowedUsersWebMiddleware."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from api.middleware import AllowedUsersWebMiddleware


def _make_request(user_id: str | None = None, path: str = "/"):
    request = MagicMock()
    request.url.path = path
    request.session = {}
    if user_id is not None:
        request.session["user_id"] = user_id
    return request


async def _call_next(request):
    response = MagicMock()
    response.status_code = 200
    return response


# ---------------------------------------------------------------------------
# No ALLOWED_USERS configured
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_allowed_users_passes_all():
    """When ALLOWED_USERS is empty, all requests pass through."""
    mw = AllowedUsersWebMiddleware(app=MagicMock())

    with patch("config.settings") as mock_settings:
        mock_settings.get_allowed_users.return_value = set()
        response = await mw.dispatch(_make_request(user_id="123456"), _call_next)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Exempt paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/admin/login", "/auth/yandex", "/api/migrations", "/health"])
@pytest.mark.asyncio
async def test_exempt_paths_always_pass(path):
    """Exempt paths bypass the check even with ALLOWED_USERS set."""
    mw = AllowedUsersWebMiddleware(app=MagicMock())

    with patch("config.settings") as mock_settings:
        mock_settings.get_allowed_users.return_value = {999}
        response = await mw.dispatch(_make_request(user_id="123456", path=path), _call_next)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# web_* user IDs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_web_user_id_passes():
    """Web users (web_* prefix) are never blocked."""
    mw = AllowedUsersWebMiddleware(app=MagicMock())

    with patch("config.settings") as mock_settings:
        mock_settings.get_allowed_users.return_value = {999}
        response = await mw.dispatch(_make_request(user_id="web_abc123"), _call_next)

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Telegram user ID access control
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_telegram_user_in_allowed_list_passes():
    """Telegram user_id in ALLOWED_USERS → allowed."""
    mw = AllowedUsersWebMiddleware(app=MagicMock())

    with patch("config.settings") as mock_settings:
        mock_settings.get_allowed_users.return_value = {123456, 789}
        response = await mw.dispatch(_make_request(user_id="123456"), _call_next)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_telegram_user_not_in_allowed_list_redirected():
    """Telegram user_id NOT in ALLOWED_USERS → session cleared + redirect."""
    from starlette.responses import RedirectResponse

    mw = AllowedUsersWebMiddleware(app=MagicMock())
    request = _make_request(user_id="999999")

    with patch("config.settings") as mock_settings:
        mock_settings.get_allowed_users.return_value = {111111}
        response = await mw.dispatch(request, _call_next)

    assert isinstance(response, RedirectResponse)
    assert response.status_code == 303
    assert request.session == {}  # session was cleared


# ---------------------------------------------------------------------------
# Unauthenticated (no user_id in session)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_session_passes():
    """No user_id in session → pass through (auth handled by routes)."""
    mw = AllowedUsersWebMiddleware(app=MagicMock())

    with patch("config.settings") as mock_settings:
        mock_settings.get_allowed_users.return_value = {111}
        response = await mw.dispatch(_make_request(user_id=None), _call_next)

    assert response.status_code == 200
