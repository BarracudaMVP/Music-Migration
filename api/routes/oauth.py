"""Web OAuth routes — redirect/callback machine for Yandex, Spotify, SoundCloud.

No HTML auth pages here. OAuth is purely a redirect/callback flow.
The web UI (Jinja2) and SPA both trigger these redirects; UI lives in templates / SPA.

State is stored in Redis (not cookies or session) — unified pattern for all providers.
Redis keys:
  oauth_state:{provider}:{state}  TTL 600s  JSON payload (flow_from, flow_to, code_verifier)
  oauth_code:{code}               TTL 30s   user_id  (short-lived, for MM-81 JWT exchange)
"""
from __future__ import annotations

import json
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.db import (
    delete_user_session,
    load_user_session,
    save_soundcloud_token,
    save_spotify_token,
    save_yandex_token,
)

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
# Yandex OAuth
# ---------------------------------------------------------------------------


@router.get("/auth/yandex")
async def auth_yandex_start(request: Request, flow_from: str = "", flow_to: str = ""):
    """Redirect user to Yandex OAuth. Requires YANDEX_REDIRECT_URI to be configured."""
    from bot.oauth.yandex import get_callback_auth_url
    from config import settings

    if not settings.yandex_redirect_uri:
        return RedirectResponse(
            f"/?error={quote('YANDEX_REDIRECT_URI не настроен')}",
            status_code=303,
        )
    _ensure_user_id(request)
    state = f"web_{uuid.uuid4().hex[:16]}"
    await _state_save("ym", state, {"flow_from": flow_from, "flow_to": flow_to})
    return RedirectResponse(get_callback_auth_url(state), status_code=303)


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


@router.get("/auth/yandex/callback")
async def auth_yandex_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
):
    """Callback from Yandex OAuth. Handles web (state=web_*) and bot (state=bot_*) flows."""
    from bot.oauth.yandex import exchange_code_callback
    from config import settings
    from core.yandex.client import YandexMusicClient

    if error:
        return RedirectResponse(
            f"/?error={quote(f'Яндекс отклонил авторизацию: {error}')}",
            status_code=303,
        )

    # Bot flow: state managed by bot (not stored in Redis by us)
    if state.startswith("bot_"):
        try:
            token = await exchange_code_callback(code)
            await YandexMusicClient(token, proxy_url=settings.ym_proxy_url or None).init()
        except Exception as e:
            return RedirectResponse(f"/?error={quote(str(e)[:120])}", status_code=303)

        state_id = state[4:]  # strip "bot_" prefix
        from api.main import get_arq_pool

        arq = get_arq_pool()
        if arq:
            await arq.setex(f"ym_auth:{state_id}", 300, token)
        return HTMLResponse(
            content=(
                "<!doctype html><html><head><meta charset=utf-8>"
                "<title>Авторизация завершена</title>"
                "<meta name=viewport content='width=device-width,initial-scale=1'>"
                "<style>body{font-family:sans-serif;text-align:center;padding:3rem;color:#1f2937}"
                ".ok{font-size:3rem}.msg{margin:1rem 0 2rem;color:#374151}"
                "a{display:inline-block;background:#6366f1;color:#fff;padding:.75rem 1.5rem;"
                "border-radius:.75rem;text-decoration:none;font-weight:600}</style></head>"
                "<body><div class=ok>✓</div>"
                "<p class=msg>Яндекс Музыка подключена!<br>Вернитесь в Telegram и нажмите "
                "<b>✓ Я авторизовался</b>.</p>"
                "<a href='https://t.me'>Открыть Telegram</a></body></html>"
            )
        )

    # Web flow: validate state from Redis
    payload = await _state_get("ym", state)
    if payload is None:
        return RedirectResponse(
            f"/?error={quote('Ошибка безопасности: state не совпадает')}",
            status_code=303,
        )

    try:
        token = await exchange_code_callback(code)
        await YandexMusicClient(token, proxy_url=settings.ym_proxy_url or None).init()
    except Exception as e:
        return RedirectResponse(f"/?error={quote(str(e)[:120])}", status_code=303)

    user_id = _ensure_user_id(request)
    await save_yandex_token(user_id, token)
    request.session["ym_connected"] = True
    # Short-lived code for future JWT exchange (MM-81)
    await _issue_oauth_code(user_id)

    pf = payload.get("flow_from", "")
    pt = payload.get("flow_to", "")
    next_url = f"/?pf={quote(pf)}&pt={quote(pt)}" if pf else "/"
    return RedirectResponse(next_url, status_code=303)


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
# SoundCloud OAuth
# ---------------------------------------------------------------------------


@router.get("/auth/soundcloud")
async def auth_soundcloud_start(request: Request, flow_from: str = "", flow_to: str = ""):
    """Redirect user to SoundCloud OAuth (PKCE flow)."""
    from config import settings
    from core.soundcloud.oauth import generate_pkce_pair, generate_state, get_auth_url

    if not settings.sc_client_id:
        return RedirectResponse(
            f"/?error={quote('SoundCloud не настроен (отсутствует SC_CLIENT_ID)')}",
            status_code=303,
        )
    _ensure_user_id(request)
    state = generate_state()
    code_verifier, code_challenge = generate_pkce_pair()
    await _state_save(
        "sc",
        state,
        {"code_verifier": code_verifier, "flow_from": flow_from, "flow_to": flow_to},
    )
    return RedirectResponse(get_auth_url(state, code_challenge), status_code=303)


@router.get("/auth/soundcloud/callback")
async def auth_soundcloud_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
):
    """Callback from SoundCloud OAuth."""
    from core.soundcloud.oauth import exchange_code

    if error:
        return RedirectResponse(
            f"/?error={quote(f'SoundCloud отклонил авторизацию: {error}')}",
            status_code=303,
        )

    payload = await _state_get("sc", state)
    if payload is None or not payload.get("code_verifier"):
        return RedirectResponse(
            f"/?error={quote('Ошибка безопасности: state не совпадает')}",
            status_code=303,
        )

    user_id = _ensure_user_id(request)
    try:
        token_data = await exchange_code(code, payload["code_verifier"])
        await save_soundcloud_token(
            user_id,
            token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
        )
        request.session["sc_connected"] = True
    except Exception as e:
        return RedirectResponse(f"/?error={quote(str(e)[:120])}", status_code=303)

    await _issue_oauth_code(user_id)
    pf = payload.get("flow_from", "")
    pt = payload.get("flow_to", "")
    next_url = f"/?pf={quote(pf)}&pt={quote(pt)}" if pf else "/"
    return RedirectResponse(next_url, status_code=303)


# ---------------------------------------------------------------------------
# Spotify OAuth
# ---------------------------------------------------------------------------


@router.get("/auth/spotify")
async def auth_spotify_start(request: Request, flow_from: str = "", flow_to: str = ""):
    """Redirect user to Spotify OAuth."""
    from config import settings
    from core.spotify.oauth import generate_state, get_auth_url

    if not settings.spotify_client_id:
        return RedirectResponse(
            f"/?error={quote('Spotify не настроен (отсутствует SPOTIFY_CLIENT_ID)')}",
            status_code=303,
        )
    _ensure_user_id(request)
    state = generate_state()
    await _state_save("sp", state, {"flow_from": flow_from, "flow_to": flow_to})
    return RedirectResponse(get_auth_url(state), status_code=303)


@router.get("/auth/spotify/callback")
async def auth_spotify_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
):
    """Callback from Spotify OAuth."""
    from core.spotify.client import SpotifyClient
    from core.spotify.oauth import exchange_code

    if error:
        return RedirectResponse(
            f"/?error={quote(f'Spotify отклонил авторизацию: {error}')}",
            status_code=303,
        )

    payload = await _state_get("sp", state)
    if payload is None:
        return RedirectResponse(
            f"/?error={quote('Ошибка безопасности: state не совпадает')}",
            status_code=303,
        )

    user_id = _ensure_user_id(request)
    try:
        token_data = await exchange_code(code)
        client = await SpotifyClient(token_data["access_token"]).init()
        await client.close()
        await save_spotify_token(
            user_id,
            token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
        )
        request.session["spotify_connected"] = True
    except Exception as e:
        return RedirectResponse(f"/?error={quote(str(e)[:120])}", status_code=303)

    await _issue_oauth_code(user_id)
    pf = payload.get("flow_from", "")
    pt = payload.get("flow_to", "")
    next_url = f"/?pf={quote(pf)}&pt={quote(pt)}" if pf else "/"
    return RedirectResponse(next_url, status_code=303)


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
