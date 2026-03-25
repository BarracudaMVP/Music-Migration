"""Public JSON API v1 for SPA frontend (MM-81).

All endpoints return JSON. Auth via Bearer JWT (except OAuth redirects/callbacks).
Parallel to old Jinja2 web UI — both work simultaneously during transition.

Routes:
  POST /api/v1/auth/exchange               exchange oauth_code → {access_token, refresh_token}
  POST /api/v1/auth/refresh                refresh_token → {access_token}
  POST /api/v1/auth/logout                 invalidate refresh_token
  GET  /api/v1/auth/me                     current user info

  GET  /api/v1/auth/yandex                 redirect → Yandex OAuth provider
  GET  /api/v1/auth/yandex/callback        Yandex OAuth callback
  GET  /api/v1/auth/spotify                redirect → Spotify OAuth provider
  GET  /api/v1/auth/spotify/callback       Spotify OAuth callback
  GET  /api/v1/auth/soundcloud             redirect → SoundCloud OAuth provider (PKCE)
  GET  /api/v1/auth/soundcloud/callback    SoundCloud OAuth callback

  GET  /api/v1/services               list services
  GET  /api/v1/services/matrix        transfer matrix

  POST /api/v1/migrations             start migration (JSON body)
  GET  /api/v1/migrations             list user migrations
  GET  /api/v1/migrations/{id}        migration status + stats
  GET  /api/v1/migrations/{id}/tracks paginated track list
  GET  /api/v1/migrations/{id}/export download CSV/JSON
  GET  /api/v1/migrations/{id}/stream SSE real-time progress
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from api.routes.oauth import (
    _ensure_user_id,
    _issue_oauth_code,
    _state_get,
    _state_save,
)
from api.security import create_access_token, create_refresh_token, get_current_user, get_current_user_role, require_admin
from core.db import (
    create_migration,
    delete_user_session,
    get_migration,
    get_track_stats,
    get_tracks_page,
    get_user_id_by_spa_refresh_token,
    get_user_migrations,
    load_user_session,
    revoke_spa_refresh_token,
    save_soundcloud_token,
    save_spa_refresh_token,
    save_spotify_token,
    save_yandex_token,
)
from core.db.crud import get_admin_stats, get_all_migrations_paginated, get_all_users_paginated
from core.services.registry import ServiceRegistry

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# Auth — code exchange
# ---------------------------------------------------------------------------


class ExchangeRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/auth/exchange", response_model=TokenResponse)
async def exchange_code(body: ExchangeRequest):
    """Exchange short-lived oauth_code (from OAuth callback) for JWT tokens."""
    from api.main import get_arq_pool
    from config import settings

    arq = get_arq_pool()
    if not arq:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    raw = await arq.get(f"oauth_code:{body.code}")
    if not raw:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    await arq.delete(f"oauth_code:{body.code}")
    user_id = raw.decode() if isinstance(raw, bytes) else raw

    db_session = await load_user_session(user_id)
    role = db_session.get("role") or "user" if db_session else "user"
    access_token = create_access_token(user_id, role=role)
    refresh_token = create_refresh_token()
    await save_spa_refresh_token(user_id, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_ttl,
    )


@router.post("/auth/refresh", response_model=AccessTokenResponse)
async def refresh_token(body: RefreshRequest):
    """Exchange refresh token for a new access token."""
    from config import settings

    user_id = await get_user_id_by_spa_refresh_token(body.refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    db_session = await load_user_session(user_id)
    role = db_session.get("role") or "user" if db_session else "user"
    access_token = create_access_token(user_id, role=role)
    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_ttl,
    )


@router.post("/auth/logout", status_code=204)
async def logout(user_id: str = Depends(get_current_user)):
    """Invalidate the refresh token (logout)."""
    await revoke_spa_refresh_token(user_id)


@router.get("/auth/me")
async def get_me(user_id: str = Depends(get_current_user)):
    """Return current user info and connected service status."""
    db_session = await load_user_session(user_id)
    if not db_session:
        return {
            "user_id": user_id,
            "ym_connected": False,
            "sc_connected": False,
            "spotify_connected": False,
            "lang": "ru",
            "role": "user",
        }
    return {
        "user_id": user_id,
        "ym_connected": bool(db_session.get("yandex_token")),
        "sc_connected": bool(db_session.get("soundcloud_token")),
        "spotify_connected": bool(db_session.get("spotify_token")),
        "lang": db_session.get("lang", "ru"),
        "role": db_session.get("role", "user"),
    }


# ---------------------------------------------------------------------------
# Auth — OAuth start + callbacks (no Bearer — browser navigates here)
# ---------------------------------------------------------------------------


@router.get("/auth/yandex")
async def yandex_oauth_start(request: Request, flow_from: str = "", flow_to: str = ""):
    """Redirect browser to Yandex OAuth provider."""
    import uuid
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


@router.get("/auth/yandex/callback")
async def yandex_oauth_callback(
    request: Request, code: str = "", state: str = "", error: str = ""
):
    """Callback from Yandex OAuth (web flow only; bot flow stays at /auth/yandex/bot)."""
    from bot.oauth.yandex import exchange_code_callback
    from config import settings
    from core.yandex.client import YandexMusicClient

    if error:
        return RedirectResponse(
            f"/?error={quote(f'Яндекс отклонил авторизацию: {error}')}",
            status_code=303,
        )
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
    code = await _issue_oauth_code(user_id)

    from config import settings
    pf = payload.get("flow_from", "")
    pt = payload.get("flow_to", "")
    base = (settings.web_base_url or settings.api_base_url).rstrip("/")
    qs = f"&flow_from={quote(pf)}&flow_to={quote(pt)}" if pf else ""
    return RedirectResponse(f"{base}/auth/callback?code={code}{qs}", status_code=303)


@router.get("/auth/spotify")
async def spotify_oauth_start(request: Request, flow_from: str = "", flow_to: str = ""):
    """Redirect browser to Spotify OAuth provider."""
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
async def spotify_oauth_callback(
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

    code = await _issue_oauth_code(user_id)
    from config import settings
    pf = payload.get("flow_from", "")
    pt = payload.get("flow_to", "")
    base = (settings.web_base_url or settings.api_base_url).rstrip("/")
    qs = f"&flow_from={quote(pf)}&flow_to={quote(pt)}" if pf else ""
    return RedirectResponse(f"{base}/auth/callback?code={code}{qs}", status_code=303)


@router.get("/auth/soundcloud")
async def soundcloud_oauth_start(request: Request, flow_from: str = "", flow_to: str = ""):
    """Redirect browser to SoundCloud OAuth (PKCE flow)."""
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
        "sc", state,
        {"code_verifier": code_verifier, "flow_from": flow_from, "flow_to": flow_to},
    )
    return RedirectResponse(get_auth_url(state, code_challenge), status_code=303)


@router.get("/auth/soundcloud/callback")
async def soundcloud_oauth_callback(
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

    code = await _issue_oauth_code(user_id)
    from config import settings
    pf = payload.get("flow_from", "")
    pt = payload.get("flow_to", "")
    base = (settings.web_base_url or settings.api_base_url).rstrip("/")
    qs = f"&flow_from={quote(pf)}&flow_to={quote(pt)}" if pf else ""
    return RedirectResponse(f"{base}/auth/callback?code={code}{qs}", status_code=303)


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------


@router.get("/services")
async def list_services():
    """List all registered music services with their capabilities."""
    services = []
    for adapter in ServiceRegistry.all():
        services.append({
            "id": adapter.id,
            "name": adapter.id.replace("_", " ").title(),
            "capabilities": [c.name for c in adapter.capabilities],
        })
    return services


@router.get("/services/matrix")
async def get_matrix():
    """Return the transfer matrix (which from→to pairs are supported)."""
    return ServiceRegistry.get_matrix()


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


class StartMigrationRequest(BaseModel):
    from_service: str
    to_service: str
    content_types: list[str] = ["tracks"]
    limit: int = 0
    skip_already_migrated: bool = True
    like_tracks: bool = False
    spotify_playlist_mode: bool = False
    spotify_playlist_name: str = "Music Migration"
    export_fmt: str = "csv"
    tracks_override: list[dict] | None = None  # for file import: parsed on frontend


@router.post("/migrations", status_code=201)
async def start_migration(
    body: StartMigrationRequest,
    user_id: str = Depends(get_current_user),
):
    """Start a new migration job. Returns {migration_id}."""
    from api.main import get_arq_pool

    arq = get_arq_pool()
    if not arq:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    db_session = await load_user_session(user_id)
    if not db_session:
        raise HTTPException(status_code=401, detail="No session found")

    # Validate matrix
    matrix = ServiceRegistry.get_matrix()
    valid_pairs = {(p["from"], p["to"]) for p in matrix}
    if (body.from_service, body.to_service) not in valid_pairs:
        # File import is special case
        if body.from_service != "file":
            raise HTTPException(status_code=400, detail="Invalid from/to service combination")

    mode = "full" if any(ct in body.content_types for ct in ("playlists", "artists")) else "tracks"

    migration_id = await create_migration(user_id, body.from_service, body.to_service)
    token_ym = db_session.get("yandex_token") or ""
    token_sc = db_session.get("soundcloud_token") or ""
    token_sp = db_session.get("spotify_token") or ""
    token_sp_refresh = db_session.get("spotify_refresh_token") or ""
    token_sc_refresh = db_session.get("soundcloud_refresh_token") or ""

    # File import via SoundCloud: use dedicated job with tracks list
    if body.from_service == "file" and body.to_service == "soundcloud":
        if not body.tracks_override:
            raise HTTPException(status_code=400, detail="tracks_override required for file import")
        await arq.enqueue_job("run_file_migration_job",
            migration_id=migration_id,
            sc_token=token_sc,
            tracks=body.tracks_override,
            user_id=user_id,
            track_limit=body.limit or None,
            like_tracks=body.like_tracks,
        )
        return {"migration_id": migration_id}

    job_kwargs = dict(
        migration_id=migration_id,
        user_id=user_id,
        yandex_token=token_ym,
        soundcloud_token=token_sc,
        track_limit=body.limit or None,
        skip_already_migrated=body.skip_already_migrated,
        like_tracks=body.like_tracks,
        mode=mode,
    )

    if body.to_service == "yandex_music":
        await arq.enqueue_job("run_yandex_migration_job", **{
            **job_kwargs,
            "tracks_override": body.tracks_override,
        })
    elif body.to_service == "spotify":
        await arq.enqueue_job("run_spotify_write_job", **{
            **job_kwargs,
            "spotify_token": token_sp,
            "spotify_refresh_token": token_sp_refresh,
            "playlist_mode": body.spotify_playlist_mode,
            "playlist_name": body.spotify_playlist_name,
            "tracks_override": body.tracks_override,
        })
    else:
        if body.from_service == "spotify":
            await arq.enqueue_job("run_spotify_migration_job", **{
                **job_kwargs,
                "spotify_token": token_sp,
            })
        else:
            await arq.enqueue_job("run_migration_job", **{
                **job_kwargs,
                "soundcloud_refresh_token": token_sc_refresh,
            })

    return {"migration_id": migration_id}


# ---------------------------------------------------------------------------
# Admin endpoints — require role=admin
# ---------------------------------------------------------------------------


@router.get("/stats")
async def get_stats(_user_id: str = Depends(require_admin)):
    """Admin: aggregate stats (total migrations, users, by status, recent 10)."""
    return await get_admin_stats()


@router.get("/users")
async def list_users(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    _user_id: str = Depends(require_admin),
):
    """Admin: paginated list of all users with migration counts."""
    users, total = await get_all_users_paginated(page=page, per_page=per_page)
    return {
        "users": users,
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


@router.get("/migrations")
async def list_migrations(
    user_id: str = Depends(get_current_user),
    role: str = Depends(get_current_user_role),
    filter_user_id: str = Query(default="", alias="user_id"),
    status_filter: str = Query(default="", alias="status"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    """List migrations. Admin can filter by user_id/status and see all; users see only their own."""
    if role == "admin":
        target_user = filter_user_id or None
        migrations, total = await get_all_migrations_paginated(
            status=status_filter or None,
            user_id=target_user,
            page=page,
            per_page=per_page,
        )
        for m in migrations:
            m["created_at"] = m["created_at"].isoformat() if m["created_at"] else None
    else:
        all_migrations = await get_user_migrations(user_id)
        for m in all_migrations:
            m["created_at"] = m["created_at"].isoformat() if m["created_at"] else None
        if status_filter:
            all_migrations = [m for m in all_migrations if m.get("status") == status_filter]
        total = len(all_migrations)
        start = (page - 1) * per_page
        migrations = all_migrations[start:start + per_page]
    for m in migrations:
        m["stats"] = await get_track_stats(m["id"])
    return {
        "migrations": migrations,
        "total": total,
        "page": page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }


@router.get("/migrations/{migration_id}")
async def get_migration_status(
    migration_id: int,
    user_id: str = Depends(get_current_user),
    role: str = Depends(get_current_user_role),
):
    """Get migration status, stats, and current track. Admin can view any migration."""
    from api.main import get_arq_pool

    migration = await get_migration(migration_id)
    if not migration:
        raise HTTPException(status_code=404, detail="Migration not found")
    if role != "admin" and migration["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Migration not found")

    stats = await get_track_stats(migration_id)

    # Current track from Redis
    current_track = None
    arq = get_arq_pool()
    if arq:
        raw = await arq.get(f"migration_progress:{migration_id}")
        if raw:
            current_track = (raw.decode() if isinstance(raw, bytes) else raw)

    migration["created_at"] = migration["created_at"].isoformat() if migration["created_at"] else None

    return {
        "migration": migration,
        "stats": stats,
        "current_track": current_track,
    }


@router.get("/migrations/{migration_id}/tracks")
async def get_migration_tracks(
    migration_id: int,
    status_filter: str = Query(default="", alias="status"),
    page: int = Query(default=1, ge=1),
    user_id: str = Depends(get_current_user),
):
    """Paginated list of tracks for a migration."""
    migration = await get_migration(migration_id)
    if not migration or migration["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Migration not found")

    page_size = 50
    tracks, total = await get_tracks_page(
        migration_id,
        status=status_filter or None,
        page=page,
        per_page=page_size,
    )
    return {
        "tracks": tracks,
        "total": total,
        "page": page,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/migrations/{migration_id}/export")
async def export_migration(
    migration_id: int,
    fmt: str = Query(default="csv"),
    user_id: str = Depends(get_current_user),
):
    """Export migration results as CSV or JSON file."""
    from core.export import export_library

    migration = await get_migration(migration_id)
    if not migration or migration["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Migration not found")

    db_session = await load_user_session(user_id)
    if not db_session:
        raise HTTPException(status_code=401, detail="No session")

    from_service = migration.get("from_service", "")
    token = (
        db_session.get("yandex_token")
        or db_session.get("soundcloud_token")
        or db_session.get("spotify_token")
        or ""
    )

    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=f".{fmt}", mode="w", encoding="utf-8"
    )
    tmp.close()
    try:
        await export_library(from_service, token, fmt=fmt, output_path=tmp.name)
    except Exception as e:
        os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=str(e))

    filename = f"migration_{migration_id}.{fmt}"
    return FileResponse(
        tmp.name,
        media_type="text/csv" if fmt == "csv" else "application/json",
        filename=filename,
        background=BackgroundTask(os.unlink, tmp.name),
    )


@router.get("/migrations/{migration_id}/stream")
async def stream_migration_progress(
    migration_id: int,
    user_id: str = Depends(get_current_user),
):
    """SSE endpoint: pushes migration stats every second until done/failed."""
    from api.main import get_arq_pool

    migration = await get_migration(migration_id)
    if not migration or migration["user_id"] != user_id:
        raise HTTPException(status_code=404, detail="Migration not found")

    async def event_generator():
        while True:
            m = await get_migration(migration_id)
            stats = await get_track_stats(migration_id)
            current_track = None
            arq = get_arq_pool()
            if arq:
                raw = await arq.get(f"migration_progress:{migration_id}")
                if raw:
                    current_track = raw.decode() if isinstance(raw, bytes) else raw

            data = json.dumps({
                "status": m["status"] if m else "unknown",
                "stats": stats,
                "current_track": current_track,
            })
            yield f"data: {data}\n\n"

            if not m or m["status"] in ("done", "failed", "cancelled"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )
