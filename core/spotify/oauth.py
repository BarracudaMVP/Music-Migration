"""
Spotify OAuth 2.0 — Authorization Code Flow.

Настройка на developer.spotify.com:
  1. My Apps → Create app
  2. Redirect URI: {API_BASE_URL}/auth/spotify/callback
  3. Права: user-library-read, playlist-read-private, user-follow-read
  4. Client ID и Client Secret → в .env
"""
import base64
import secrets
from urllib.parse import urlencode

import aiohttp

from config import settings

_AUTH_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SCOPES = "user-library-read playlist-read-private user-follow-read"


def generate_state() -> str:
    return secrets.token_urlsafe(16)


def get_auth_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.spotify_client_id,
        "scope": _SCOPES,
        "redirect_uri": settings.spotify_redirect_uri,
        "state": state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def _basic_auth() -> str:
    raw = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
    return base64.b64encode(raw.encode()).decode()


async def exchange_code(code: str) -> dict:
    """Обменивает код на {access_token, refresh_token, expires_in, ...}."""
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.spotify_redirect_uri,
            },
            headers={"Authorization": f"Basic {_basic_auth()}"},
        )
        body = await resp.json(content_type=None)

    if "access_token" in body:
        return body

    error = body.get("error_description") or body.get("error") or str(body)
    raise ValueError(f"Spotify вернул ошибку: {error}")


async def refresh_access_token(refresh_token: str) -> dict:
    """Обновляет access_token по refresh_token."""
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Authorization": f"Basic {_basic_auth()}"},
        )
        body = await resp.json(content_type=None)

    if "access_token" in body:
        return body

    error = body.get("error_description") or body.get("error") or str(body)
    raise ValueError(f"Spotify refresh error: {error}")
