"""OAuth helpers + bot-specific routes.

Web OAuth start/callback routes moved to api_v1.py under /api/v1/auth/* (MM-81).

This module provides:
- Session helpers (_session_user_id, _ensure_user_id) — imported by web.py
- Redis state helpers (_state_save, _state_get, _issue_oauth_code) — imported by api_v1.py
- GET  /auth/yandex/bot               — Yandex OAuth start for Telegram bot
- GET  /api/auth/yandex/poll/{state}  — bot polls for Yandex token (internal)
- POST /auth/logout                   — web session logout

Redis keys:
  oauth_state:{provider}:{state}  TTL 600s  JSON payload (flow_from, flow_to, code_verifier)
  oauth_code:{code}               TTL 30s   user_id  (short-lived, for JWT exchange)
  ym_auth:{state_id}              TTL 300s  yandex token (for bot poll flow)
"""
from __future__ import annotations

import json
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from core.db import delete_user_session

router = APIRouter()

# ---------------------------------------------------------------------------
# Session helpers (used here and imported by web.py)
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
        uid = f"web_{uuid.uuid4().hex[:12]}"
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

    code = uuid.uuid4().hex
    arq = get_arq_pool()
    if arq:
        await arq.setex(f"oauth_code:{code}", 30, user_id)
    return code


# ---------------------------------------------------------------------------
# Yandex OAuth — bot flow only (web flow → api_v1.py /api/v1/auth/yandex)
# ---------------------------------------------------------------------------


@router.get("/auth/yandex/bot")
async def auth_yandex_bot_start(request: Request, state: str = ""):
    """Start Yandex OAuth for Telegram bot flow. state must begin with 'bot_'."""
    from bot.oauth.yandex import get_callback_auth_url
    from config import settings

    if not settings.yandex_redirect_uri or not state.startswith("bot_"):
        return RedirectResponse(
            f"/?error={quote('Некорректный запрос авторизации')}",
            status_code=303,
        )
    return RedirectResponse(get_callback_auth_url(state), status_code=303)


@router.get("/api/auth/yandex/poll/{state_id}")
async def poll_yandex_bot_token(state_id: str, request: Request):
    """Internal: bot polls this to get Yandex token after web OAuth (MM-44)."""
    from api.deps import verify_internal_token
    from api.main import get_arq_pool

    x_internal_token = request.headers.get("x-internal-token", "")
    await verify_internal_token(x_internal_token)

    arq = get_arq_pool()
    if not arq:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    raw = await arq.get(f"ym_auth:{state_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Token not found")

    await arq.delete(f"ym_auth:{state_id}")
    token = raw.decode() if isinstance(raw, bytes) else raw
    return {"token": token}


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/auth/logout")
async def logout(request: Request):
    user_id = _session_user_id(request)
    if user_id:
        await delete_user_session(user_id)
    request.session.clear()
    return RedirectResponse("/", status_code=303)
