"""JWT utilities for SPA auth (MM-81).

Access token:  JWT, short-lived (JWT_ACCESS_TOKEN_TTL seconds, default 15 min).
               Payload: {"sub": user_id, "exp": timestamp}
               Not stored — validated on every request.

Refresh token: opaque random hex string, stored encrypted in UserSession.spa_refresh_token.
               Long-lived (JWT_REFRESH_TOKEN_TTL seconds, default 30 days).
               Invalidated on logout by deleting from DB.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException, status

from config import settings


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def create_access_token(user_id: str) -> str:
    """Create a signed JWT access token for the given user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jwt_access_token_ttl),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def create_refresh_token() -> str:
    """Create an opaque random refresh token (stored in DB)."""
    return secrets.token_hex(32)


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


def decode_access_token(token: str) -> str | None:
    """Decode and validate a JWT access token. Returns user_id or None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_current_user(authorization: str = Header(default="")) -> str:
    """FastAPI dependency: extracts and validates Bearer JWT, returns user_id.

    In DEV_MODE bypasses auth and always returns "dev_user".
    Raises HTTP 401 if token is missing or invalid.
    """
    from config import settings

    if settings.dev_mode:
        return "dev_user"

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[len("Bearer "):]
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired or invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
