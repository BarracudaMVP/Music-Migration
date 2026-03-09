"""
SoundCloud OAuth 2.0 — Authorization Code Flow with PKCE (OAuth 2.1).

Настройка на soundcloud.com/you/apps:
  1. Create new app
  2. Redirect URI: {WEB_BASE_URL}/auth/soundcloud/callback
  3. Client ID и Client Secret → в .env

SC_CLIENT_ID=
SC_CLIENT_SECRET=
SC_REDIRECT_URI=https://yourdomain.com/auth/soundcloud/callback
"""
import base64
import hashlib
import secrets
from urllib.parse import urlencode

import aiohttp

from config import settings

# Note: auth endpoint has no /oauth/ prefix; token endpoint does
_AUTH_URL = "https://secure.soundcloud.com/authorize"
_TOKEN_URL = "https://secure.soundcloud.com/oauth/token"


def generate_state() -> str:
    return secrets.token_urlsafe(16)


def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256 method."""
    verifier = secrets.token_urlsafe(64)  # 86 URL-safe chars
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def get_auth_url(state: str, code_challenge: str) -> str:
    params = {
        "client_id": settings.sc_client_id,
        "redirect_uri": settings.sc_redirect_uri,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, code_verifier: str) -> dict:
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
                "code_verifier": code_verifier,
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
