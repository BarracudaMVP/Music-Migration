"""OAuth utility helpers (no routes — all routes moved).

Bot-specific routes moved to bot_auth.py (MM-82).
Web OAuth start/callback routes were moved to api_v1.py under /api/v1/auth/* (MM-81).

This module provides shared utility functions:
- Session helpers (_session_user_id, _ensure_user_id)
- Redis state helpers (_state_save, _state_get, _issue_oauth_code) — imported by api_v1.py

Redis keys:
  oauth_state:{provider}:{state}  TTL 600s  JSON payload (flow_from, flow_to, code_verifier)
  oauth_code:{code}               TTL 30s   user_id  (short-lived, for JWT exchange)
  ym_auth:{state_id}              TTL 300s  yandex token (for bot poll flow)
"""
from __future__ import annotations

import json
import secrets

from fastapi import Request


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _session_user_id(request: Request) -> str | None:
    return request.session.get("user_id")


def _ensure_user_id(request: Request) -> str:
    """Return existing or create a new anonymous web user ID.

    In DEV_MODE always returns a fixed 'dev_user' so the pre-seeded DB session
    is picked up automatically on every browser visit.
    """
    from config import settings as cfg

    if cfg.dev_mode:
        request.session["user_id"] = "dev_user"
        return "dev_user"
    uid = request.session.get("user_id")
    if not uid:
        uid = f"web_{secrets.token_hex(16)}"
        request.session["user_id"] = uid
    return uid


# ---------------------------------------------------------------------------
# Redis state helpers — unified for all providers
# ---------------------------------------------------------------------------


async def _state_save(provider: str, state: str, payload: dict, ttl: int = 600) -> None:
    """Save OAuth state payload to Redis."""
    from api.main import get_arq_pool

    arq = get_arq_pool()
    if arq:
        await arq.setex(f"oauth_state:{provider}:{state}", ttl, json.dumps(payload))


async def _state_get(provider: str, state: str) -> dict | None:
    """Retrieve and delete OAuth state payload from Redis."""
    from api.main import get_arq_pool

    arq = get_arq_pool()
    if not arq:
        return None
    raw = await arq.get(f"oauth_state:{provider}:{state}")
    if raw is None:
        return None
    await arq.delete(f"oauth_state:{provider}:{state}")
    return json.loads(raw.decode() if isinstance(raw, bytes) else raw)


async def _issue_oauth_code(user_id: str) -> str:
    """Generate a short-lived (30s) code in Redis for JWT exchange (MM-81)."""
    from api.main import get_arq_pool

    code = secrets.token_hex(16)
    arq = get_arq_pool()
    if arq:
        await arq.setex(f"oauth_code:{code}", 30, user_id)
    return code
