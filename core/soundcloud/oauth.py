"""
SoundCloud OAuth 2.0 — Authorization Code Flow.

Настройка на soundcloud.com/you/apps:
  1. Create new app
  2. Redirect URI: {API_BASE_URL}/auth/soundcloud/callback
  3. Client ID и Client Secret → в .env

SC_CLIENT_ID=
SC_CLIENT_SECRET=
SC_REDIRECT_URI=https://yourdomain.com/auth/soundcloud/callback
"""
import secrets
from urllib.parse import urlencode

import aiohttp

from config import settings

_AUTH_URL = "https://secure.soundcloud.com/oauth/authorize"
_TOKEN_URL = "https://secure.soundcloud.com/oauth/token"


def generate_state() -> str:
    return secrets.token_urlsafe(16)


def get_auth_url(state: str) -> str:
    params = {
        "client_id": settings.sc_client_id,
        "redirect_uri": settings.sc_redirect_uri,
        "response_type": "code",
        "scope": "*",
        "state": state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Обменивает код на {access_token, refresh_token, expires_in, ...}."""
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.sc_client_id,
                "client_secret": settings.sc_client_secret,
                "redirect_uri": settings.sc_redirect_uri,
                "code": code,
            },
        )
        body = await resp.json(content_type=None)

    if "access_token" in body:
        return body

    error = body.get("error_description") or body.get("error") or str(body)
    raise ValueError(f"SoundCloud вернул ошибку: {error}")


async def refresh_access_token(refresh_token: str) -> dict:
    """Обновляет access_token по refresh_token."""
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.sc_client_id,
                "client_secret": settings.sc_client_secret,
                "refresh_token": refresh_token,
            },
        )
        body = await resp.json(content_type=None)

    if "access_token" in body:
        return body

    error = body.get("error_description") or body.get("error") or str(body)
    raise ValueError(f"SoundCloud refresh error: {error}")
