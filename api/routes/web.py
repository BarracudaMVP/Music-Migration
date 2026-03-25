"""Web UI routes — Jinja2 + HTMX."""
from __future__ import annotations

import os
import tempfile
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.background import BackgroundTask
from fastapi.templating import Jinja2Templates

from api.routes.oauth import _ensure_user_id, _session_user_id
from core.db import (
    clear_service_token,
    create_migration,
    get_migration,
    get_track_stats,
    get_track_stats_batch,
    get_tracks_page,
    load_user_session,
    save_user_session,
    save_user_lang,
)
from core.services.registry import ServiceRegistry
from core.soundcloud.client import SoundCloudClient
from core.i18n import t as _t, detect_lang_web

templates = Jinja2Templates(directory="api/templates")
router = APIRouter()


# ---------------------------------------------------------------------------
# i18n helpers
# ---------------------------------------------------------------------------

def get_lang(request: Request) -> str:
    return detect_lang_web(request)


_SERVICE_ICONS = {
    "yandex_music": '<svg viewBox="59 0 23 22" xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" aria-label="Yandex Music"><path d="M81.1901 8.3856L81.1043 7.959L77.4764 7.32521L79.5845 4.47313L79.3394 4.20499L76.2385 5.69197L76.6307 1.74294L76.3121 1.56011L74.4246 4.75346L72.3043 0H71.9366L72.4391 4.59501L67.1076 0.329086L66.6541 0.463157L70.76 5.61884L62.6341 2.91302L62.2664 3.32742L69.5221 7.45928L59.5087 8.28809L59.3984 8.90969L69.804 10.0432L61.1266 17.2222L61.4943 17.7219L71.8263 12.103L69.7795 22H70.4046L74.3633 12.6881L76.7778 19.9767L77.2068 19.6476L76.214 12.2371L79.9767 16.503L80.2218 16.113L77.3416 10.8233L81.3617 12.3102L81.3984 11.8593L77.7951 9.20222L81.1901 8.3856Z" fill="#FFBC0D"/></svg>',
    "spotify": '<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" fill="#1ED760" aria-label="Spotify"><path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"/></svg>',
    "soundcloud": '<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" fill="#FF3300" aria-label="SoundCloud"><path d="M23.999 14.165c-.052 1.796-1.612 3.169-3.4 3.169h-8.18a.68.68 0 0 1-.675-.683V7.862a.747.747 0 0 1 .452-.724s.75-.513 2.333-.513a5.364 5.364 0 0 1 2.763.755 5.433 5.433 0 0 1 2.57 3.54c.282-.08.574-.121.868-.12.884 0 1.73.358 2.347.992s.948 1.49.922 2.373ZM10.721 8.421c.247 2.98.427 5.697 0 8.672a.264.264 0 0 1-.53 0c-.395-2.946-.22-5.718 0-8.672a.264.264 0 0 1 .53 0ZM9.072 9.448c.285 2.659.37 4.986-.006 7.655a.277.277 0 0 1-.55 0c-.331-2.63-.256-5.02 0-7.655a.277.277 0 0 1 .556 0Zm-1.663-.257c.27 2.726.39 5.171 0 7.904a.266.266 0 0 1-.532 0c-.38-2.69-.257-5.21 0-7.904a.266.266 0 0 1 .532 0Zm-1.647.77a26.108 26.108 0 0 1-.008 7.147a.272.272 0 0 1-.542 0a27.955 27.955 0 0 1 0-7.147a.275.275 0 0 1 .55 0Zm-1.67 1.769c.421 1.865.228 3.5-.029 5.388a.257.257 0 0 1-.514 0c-.21-1.858-.398-3.549 0-5.389a.272.272 0 0 1 .543 0Zm-1.655-.273c.388 1.897.26 3.508-.01 5.412-.026.28-.514.283-.54 0-.244-1.878-.347-3.54-.01-5.412a.283.283 0 0 1 .56 0Zm-1.668.911c.4 1.268.257 2.292-.026 3.572a.257.257 0 0 1-.514 0c-.241-1.262-.354-2.312-.023-3.572a.283.283 0 0 1 .563 0Z"/></svg>',
    "file": '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" fill="none" stroke="#6B7280" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-label="File"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
}


def _svc_name(service_id: str, lang: str) -> str:
    """Return localized service display name."""
    return _t(f"svc_{service_id}", lang)


def _render(template: str, request: Request, ctx: dict) -> templates.TemplateResponse:
    """Shortcut: inject lang + t() into every template context."""
    lang = get_lang(request)
    ctx["lang"] = lang
    ctx["t"] = lambda key: _t(key, lang)
    ctx.setdefault("has_migrations", False)
    ctx.setdefault("service_icons", _SERVICE_ICONS)
    return templates.TemplateResponse(request, template, ctx)


_STATUS_LABEL_RU = {
    "pending": "В очереди",
    "running": "Выполняется",
    "done": "Завершён",
    "failed": "Ошибка",
    "cancelled": "Отменён",
}
_STATUS_LABEL_EN = {
    "pending": "Queued",
    "running": "Running",
    "done": "Completed",
    "failed": "Failed",
    "cancelled": "Cancelled",
}

def _status_label(status: str, lang: str) -> str:
    labels = _STATUS_LABEL_EN if lang == "en" else _STATUS_LABEL_RU
    return labels.get(status, status)


# ---------------------------------------------------------------------------
# Language switcher
# ---------------------------------------------------------------------------

@router.get("/set-lang", response_class=HTMLResponse)
async def set_lang(request: Request, lang: str = "ru", next: str = "/"):
    if lang not in ("ru", "en"):
        lang = "ru"
    request.session["lang"] = lang
    user_id = _session_user_id(request)
    if user_id:
        await save_user_lang(user_id, lang)
    return RedirectResponse(next, status_code=303)


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, error: str = ""):
    from sqlalchemy import select, func
    from core.db.models import Migration
    from core.db.session import AsyncSessionLocal

    user_id = _ensure_user_id(request)

    # Unique FROM services from transfer matrix
    lang = get_lang(request)
    matrix = ServiceRegistry.get_matrix()
    seen_from: set[str] = set()
    from_services: dict[str, str] = {}
    for pair in matrix:
        if pair["from"] not in seen_from:
            seen_from.add(pair["from"])
            from_services[pair["from"]] = _svc_name(pair["from"], lang)
    # Add file_csv as a FROM option (file import not in registry matrix)
    from_services["file"] = _svc_name("file", lang)

    # Check if user has any migrations for nav
    has_migrations = False
    try:
        async with AsyncSessionLocal() as s:
            count = await s.scalar(
                select(func.count()).select_from(Migration).where(Migration.user_id == user_id)
            )
            has_migrations = bool(count and count > 0)
    except Exception:
        pass

    return _render("index.html", request, {
        "from_services": from_services,
        "has_migrations": has_migrations,
        "error": error,
    })


# ---------------------------------------------------------------------------
# Flow HTMX fragments (MM-49)
# ---------------------------------------------------------------------------

@router.get("/api/flow/to-step", response_class=HTMLResponse)
async def flow_to_step(request: Request, from_service: str = Query(..., alias="from")):
    """HTMX: returns TO service cards for the selected FROM service."""
    from core.services.base import Capability

    lang = get_lang(request)
    to_services: dict[str, str] = {}

    if from_service == "file":
        # File import can target any service with WRITE_LIKED_TRACKS
        for adapter in ServiceRegistry.all():
            if adapter.id != "file" and adapter.can(Capability.WRITE_LIKED_TRACKS):
                to_services[adapter.id] = _svc_name(adapter.id, lang)
    else:
        matrix = ServiceRegistry.get_matrix()
        for pair in matrix:
            if pair["from"] == from_service and pair["to"] not in to_services:
                to_services[pair["to"]] = _svc_name(pair["to"], lang)

    return _render("fragments/flow_to.html", request, {
        "from_service": from_service,
        "to_services": to_services,
    })


@router.get("/api/flow/rest", response_class=HTMLResponse)
async def flow_rest(
    request: Request,
    from_service: str = Query(..., alias="from"),
    to_service: str = Query(..., alias="to"),
):
    """HTMX: returns content-types + auth status + settings for a FROM→TO pair."""
    from core.services.base import Capability
    from config import settings as cfg

    user_id = _ensure_user_id(request)
    db_session = await load_user_session(user_id)

    is_from_file = from_service == "file"
    is_to_file = to_service == "file"

    try:
        from_adapter = ServiceRegistry.get(from_service) if not is_from_file else None
        to_adapter = ServiceRegistry.get(to_service) if not is_to_file else None
    except KeyError:
        return HTMLResponse("<p class='text-red-600 text-sm'>Неизвестный сервис.</p>")

    # Content types availability (overridden in template when file is involved)
    content_types = []
    if not is_from_file and not is_to_file:
        ct_defs = [
            ("tracks",    Capability.READ_LIKED_TRACKS,   Capability.WRITE_LIKED_TRACKS),
            ("playlists", Capability.READ_PLAYLISTS,       Capability.WRITE_PLAYLISTS),
            ("artists",   Capability.READ_LIKED_ARTISTS,   Capability.WRITE_LIKED_ARTISTS),
        ]
        for ct_id, read_cap, write_cap in ct_defs:
            available = from_adapter.can(read_cap) and to_adapter.can(write_cap)
            content_types.append({"id": ct_id, "available": available, "checked": available})
        # Tracks always checked
        content_types[0]["checked"] = True

    # Auth status per service
    def _connected(service_id: str) -> bool:
        if service_id == "yandex_music":
            return bool(
                request.session.get("ym_connected")
                or (db_session and db_session.get("yandex_token"))
            )
        if service_id == "soundcloud":
            return bool(
                request.session.get("sc_connected")
                or (db_session and db_session.get("soundcloud_token"))
            )
        if service_id == "spotify":
            return bool(
                request.session.get("spotify_connected")
                or (db_session and db_session.get("spotify_token"))
            )
        return True  # file_csv needs no auth

    lang = get_lang(request)
    return _render("fragments/flow_rest.html", request, {
        "from_service": from_service,
        "to_service": to_service,
        "from_name": _svc_name(from_service, lang),
        "to_name": _svc_name(to_service, lang),
        "content_types": content_types,
        "from_connected": _connected(from_service),
        "to_connected": _connected(to_service),
        "spotify_enabled": bool(cfg.spotify_client_id),
        "sc_enabled": bool(cfg.sc_client_id),
        "is_from_file": is_from_file,
        "is_to_file": is_to_file,
        "spotify_bot_configured": bool(cfg.spotify_bot_token),
    })


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

_SESSION_FLAG: dict[str, str] = {
    "yandex_music": "ym_connected",
    "soundcloud": "sc_connected",
    "spotify": "spotify_connected",
}


async def _validate_service_token(service: str, token: str) -> str | None:
    """Quick token validation against the live API.
    Returns a human-readable error string, or None if OK.
    """
    if not token or service == "file":
        return None
    from config import settings as _cfg

    if service == "spotify":
        try:
            from core.spotify.client import SpotifyClient
            client = await SpotifyClient(token).init()
            await client.close()
        except ValueError as e:
            return str(e)

    elif service == "yandex_music":
        try:
            from core.yandex.client import YandexMusicClient
            await YandexMusicClient(token, proxy_url=_cfg.ym_proxy_url or None).init()
        except ValueError as e:
            return str(e)

    elif service == "soundcloud":
        # SC init() swallows /me errors; we do a lightweight 401 check manually
        try:
            import aiohttp
            auth = token if token.startswith("OAuth ") else f"OAuth {token}"
            async with aiohttp.ClientSession(headers={"Authorization": auth}) as _s:
                async with _s.get("https://api.soundcloud.com/me") as resp:
                    if resp.status == 401:
                        return "Невалидный SoundCloud токен"
        except Exception:
            pass  # network error — don't block the migration

    return None


@router.post("/migrate")
async def start_migrate(
    request: Request,
    from_service: str = Form(...),
    to_service: str = Form(...),
    track_limit: int = Form(0),
    skip_already_migrated: bool = Form(False),
    like_tracks: bool = Form(False),
    spotify_playlist_mode: bool = Form(False),
    export_fmt: str = Form("csv"),
    file: Optional[UploadFile] = File(None),
):
    from api.main import get_arq_pool

    # Parse content_types from raw form (multiple checkbox values)
    form_data = await request.form()
    content_types = list(form_data.getlist("content_types"))
    if not content_types:
        content_types = ["tracks"]
    mode = "full" if any(ct in content_types for ct in ("playlists", "artists")) else "tracks"

    user_id = _session_user_id(request)
    if not user_id:
        return RedirectResponse("/", status_code=303)

    db_session = await load_user_session(user_id)
    if not db_session:
        return RedirectResponse("/", status_code=303)

    is_from_file = from_service == "file"
    is_to_file = to_service == "file"

    # Validate that the selected from→to pair is supported (skip for file_csv)
    if not is_from_file and not is_to_file:
        matrix = ServiceRegistry.get_matrix()
        supported = {(e["from"], e["to"]) for e in matrix}
        if (from_service, to_service) not in supported:
            return RedirectResponse(
                f"/?error={quote(f'Направление {from_service} \u2192 {to_service} не поддерживается')}",
                status_code=303,
            )

    ym_token = db_session.get("yandex_token") or ""
    sc_token = db_session.get("soundcloud_token") or ""
    spotify_token = db_session.get("spotify_token") or ""
    spotify_refresh_token = db_session.get("spotify_refresh_token")

    # Токен для сервиса
    def _token_for(service: str) -> str:
        if service == "yandex_music":
            return ym_token
        if service == "soundcloud":
            return sc_token
        if service == "spotify":
            return spotify_token
        return ""

    # Проверяем наличие нужных токенов
    def _missing_token(service: str) -> str | None:
        if service == "file":
            return None
        if service == "yandex_music" and not ym_token:
            return "Сначала подключи Яндекс Музыку"
        if service == "soundcloud" and not sc_token:
            return "Сначала подключи SoundCloud"
        if service == "spotify" and not spotify_token:
            return "Сначала подключи Spotify"
        return None

    async def _check_token(service: str, pf: str, pt: str) -> RedirectResponse | None:
        """Validate live token. On failure — clear from DB/session, return redirect."""
        tok = _token_for(service)
        err = await _validate_service_token(service, tok)
        if err:
            await clear_service_token(user_id, service)
            flag = _SESSION_FLAG.get(service)
            if flag:
                request.session.pop(flag, None)
            msg = f"{err}. Авторизуйтесь заново."
            return RedirectResponse(
                f"/?error={quote(msg)}&pf={pf}&pt={pt}", status_code=303
            )
        return None

    # Case 1: Export to file — async via ARQ worker (MM-78)
    if is_to_file:
        err = _missing_token(from_service)
        if err:
            return RedirectResponse(f"/?error={quote(err)}", status_code=303)
        redir = await _check_token(from_service, from_service, "file")
        if redir:
            return redir

        source_token = _token_for(from_service)
        migration_id = await create_migration(user_id, from_service=from_service, to_service="file")
        arq = get_arq_pool()
        job = await arq.enqueue_job(
            "run_export_job",
            migration_id, from_service, source_token, export_fmt, user_id,
        )
        if job:
            await arq.set(f"migration_job:{migration_id}", job.job_id, ex=86400)
        return RedirectResponse(f"/migrate/{migration_id}", status_code=303)

    # Check rate limit before creating any migration
    from api.deps import check_migration_rate_limit
    if not await check_migration_rate_limit(user_id):
        return RedirectResponse(
            f"/?error={quote('Слишком много переносов. Попробуй через час.')}",
            status_code=303,
        )

    # Case 2: Import from file
    if is_from_file:
        err = _missing_token(to_service)
        if err:
            return RedirectResponse(f"/?error={quote(err)}", status_code=303)
        redir = await _check_token(to_service, "file", to_service)
        if redir:
            return redir

        if file is None or not file.filename:
            return RedirectResponse(f"/?error={quote('Выбери файл для загрузки')}", status_code=303)

        content = await file.read()
        if len(content) > _MAX_UPLOAD_BYTES:
            return RedirectResponse(
                f"/?error={quote('Файл слишком большой (максимум 10 МБ)')}", status_code=303
            )

        suffix = ".json" if (file.filename or "").lower().endswith(".json") else ".csv"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        tracks: list[dict] = []
        try:
            os.write(fd, content)
            os.close(fd)
            from core.services.file.adapter import FileAdapter as _FA
            _fa = _FA()
            columns = await _fa.get_columns(tmp_path)
            auto_map = _fa.detect_column_mapping(columns)
            artist_col = auto_map.get("artist_col") or "artist"
            title_col = auto_map.get("title_col") or "title"
            tracks = await _fa.import_tracks(tmp_path, artist_col=artist_col, title_col=title_col)
        except Exception as e:
            return RedirectResponse(f"/?error={quote(str(e)[:120])}", status_code=303)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if not tracks:
            return RedirectResponse(f"/?error={quote('Файл не содержит треков')}", status_code=303)

        arq = get_arq_pool()
        limit = track_limit if track_limit and track_limit > 0 else None
        migration_id = await create_migration(user_id, from_service="file", to_service=to_service)

        if to_service == "soundcloud":
            job = await arq.enqueue_job(
                "run_file_migration_job",
                migration_id, sc_token, tracks, user_id,
                track_limit=limit, like_tracks=like_tracks,
            )
        elif to_service == "yandex_music":
            job = await arq.enqueue_job(
                "run_yandex_migration_job",
                migration_id, "", "file", ym_token, user_id,
                track_limit=None, skip_already_migrated=skip_already_migrated,
                tracks_override=tracks,
            )
        elif to_service == "spotify":
            job = await arq.enqueue_job(
                "run_spotify_write_job",
                migration_id, "", "file",
                spotify_token, spotify_refresh_token, user_id,
                track_limit=None, skip_already_migrated=skip_already_migrated,
                tracks_override=tracks,
                playlist_mode=spotify_playlist_mode,
            )
        else:
            return RedirectResponse(
                f"/?error={quote(f'Направление file_csv → {to_service} не поддерживается')}",
                status_code=303,
            )

        if job:
            await arq.set(f"migration_job:{migration_id}", job.job_id, ex=86400)
        return RedirectResponse(f"/migrate/{migration_id}", status_code=303)

    # Case 3: Normal migration
    for svc in (from_service, to_service):
        err = _missing_token(svc)
        if err:
            return RedirectResponse(f"/?error={quote(err)}", status_code=303)
    for svc in (from_service, to_service):
        redir = await _check_token(svc, from_service, to_service)
        if redir:
            return redir

    migration_id = await create_migration(user_id, from_service=from_service, to_service=to_service)
    arq = get_arq_pool()
    job_mode = "full" if mode == "full" else "tracks"
    limit = track_limit if track_limit and track_limit > 0 else None
    skip = skip_already_migrated
    like = like_tracks

    if to_service == "yandex_music":
        source_token = spotify_token if from_service == "spotify" else sc_token
        job = await arq.enqueue_job(
            "run_yandex_migration_job",
            migration_id, source_token, from_service, ym_token, user_id,
            track_limit=limit, skip_already_migrated=skip,
        )
    elif to_service == "spotify":
        source_token = sc_token if from_service == "soundcloud" else ym_token
        job = await arq.enqueue_job(
            "run_spotify_write_job",
            migration_id, source_token, from_service,
            spotify_token, spotify_refresh_token, user_id,
            track_limit=limit, skip_already_migrated=skip,
            playlist_mode=spotify_playlist_mode,
        )
    elif from_service == "spotify":
        job = await arq.enqueue_job(
            "run_spotify_migration_job",
            migration_id, spotify_token, sc_token, job_mode, user_id,
            track_limit=limit, skip_already_migrated=skip, like_tracks=like,
        )
    else:
        job = await arq.enqueue_job(
            "run_migration_job",
            migration_id, ym_token, sc_token, job_mode, user_id,
            track_limit=limit, skip_already_migrated=skip, like_tracks=like,
        )

    if job:
        await arq.set(f"migration_job:{migration_id}", job.job_id, ex=86400)
    return RedirectResponse(f"/migrate/{migration_id}", status_code=303)


@router.get("/migrate/{migration_id}", response_class=HTMLResponse)
async def migration_progress(request: Request, migration_id: int):
    migration = await get_migration(migration_id)
    if migration is None:
        return RedirectResponse("/", status_code=303)
    user_id = _session_user_id(request)
    if user_id and migration.get("user_id") and migration["user_id"] != user_id:
        raise HTTPException(status_code=403)
    return _render("progress.html", request, {
        "migration_id": migration_id, "migration": migration,
    })


@router.get("/migrate/{migration_id}/status-fragment", response_class=HTMLResponse)
async def migration_status_fragment(request: Request, migration_id: int):
    """HTMX partial — polled every 3 s from progress.html."""
    migration = await get_migration(migration_id)
    if migration is None:
        return HTMLResponse("<p>Migration not found.</p>")
    user_id = _session_user_id(request)
    if user_id and migration.get("user_id") and migration["user_id"] != user_id:
        return HTMLResponse("<p>Access denied.</p>", status_code=403)

    stats = await get_track_stats(migration_id)
    done = migration["status"] in ("done", "failed", "cancelled")
    lang = get_lang(request)
    status_label = _status_label(migration["status"], lang)

    current_track = None
    eta = None
    if not done:
        from api.main import get_arq_pool
        arq = get_arq_pool()
        if arq:
            val = await arq.get(f"migration_current_track:{migration_id}")
            if val:
                current_track = val.decode() if isinstance(val, bytes) else val

        if stats:
            pending = stats.get("pending", 0)
            if pending > 0:
                from core.i18n import format_eta
                eta = format_eta(pending, migration.get("to_service") or "soundcloud", lang)

    return _render("fragments/status.html", request, {
        "migration_id": migration_id,
        "migration": migration,
        "status_label": status_label,
        "stats": stats,
        "done": done,
        "current_track": current_track,
        "eta": eta,
    })


@router.get("/migrate/{migration_id}/result", response_class=HTMLResponse)
async def migration_result(request: Request, migration_id: int):
    # Deprecated — redirect to migration progress page which now shows results inline
    return RedirectResponse(f"/migrate/{migration_id}", status_code=301)


@router.get("/migrate/{migration_id}/export-file")
async def migration_export_file(request: Request, migration_id: int):
    """Download export file for a completed export migration (to_service=file, MM-78)."""
    from fastapi.responses import Response as FastAPIResponse
    from api.main import get_arq_pool

    migration = await get_migration(migration_id)
    if migration is None:
        raise HTTPException(status_code=404, detail="Migration not found")
    user_id = _session_user_id(request)
    if user_id and migration.get("user_id") and migration["user_id"] != user_id:
        raise HTTPException(status_code=403)
    if migration.get("status") != "done" or not migration.get("result_path"):
        raise HTTPException(status_code=404, detail="Export not ready")

    arq = get_arq_pool()
    if not arq:
        raise HTTPException(status_code=503, detail="Storage unavailable")

    data = await arq.get(f"export_data:{migration_id}")
    if data is None:
        raise HTTPException(status_code=410, detail="Export expired or not found")

    fmt = migration["result_path"]
    media = "text/csv" if fmt == "csv" else "application/json"
    from_svc = migration.get("from_service") or "library"
    filename = f"library_{from_svc}.{fmt}"
    return FastAPIResponse(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_PER_PAGE = 50
_TRACK_STATUS_LABEL_RU = {
    "liked": "Лайкнут",
    "in_playlist": "В плейлисте",
    "not_found": "Не найден",
    "error": "Ошибка",
    "pending": "В очереди",
}
_TRACK_STATUS_LABEL_EN = {
    "liked": "Liked",
    "in_playlist": "In playlist",
    "not_found": "Not found",
    "error": "Error",
    "pending": "Queued",
}


@router.get("/migrate/{migration_id}/tracks", response_class=HTMLResponse)
async def migration_tracks(
    request: Request,
    migration_id: int,
    status: str = "",
    page: int = 1,
):
    migration = await get_migration(migration_id)
    if migration is None:
        return RedirectResponse("/", status_code=303)
    user_id = _session_user_id(request)
    if user_id and migration.get("user_id") and migration["user_id"] != user_id:
        raise HTTPException(status_code=403)

    page = max(1, page)
    tracks, total = await get_tracks_page(
        migration_id,
        status=status or None,
        page=page,
        per_page=_PER_PAGE,
    )
    stats = await get_track_stats(migration_id)
    total_pages = max(1, (total + _PER_PAGE - 1) // _PER_PAGE)
    lang = get_lang(request)
    track_label_map = _TRACK_STATUS_LABEL_EN if lang == "en" else _TRACK_STATUS_LABEL_RU
    to_service = migration.get("to_service") or ""
    return _render("tracks.html", request, {
        "migration_id": migration_id,
        "migration": migration,
        "tracks": tracks,
        "stats": stats,
        "status_filter": status,
        "status_label_map": track_label_map,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "to_service": to_service,
    })


@router.get("/migrate/{migration_id}/tracks-fragment", response_class=HTMLResponse)
async def migration_tracks_fragment(
    request: Request,
    migration_id: int,
    status: str = "",
    page: int = 1,
):
    """HTMX fragment — inline track table on migration page when done."""
    migration = await get_migration(migration_id)
    if migration is None:
        return HTMLResponse("")
    user_id = _session_user_id(request)
    if user_id and migration.get("user_id") and migration["user_id"] != user_id:
        return HTMLResponse("", status_code=403)

    page = max(1, page)
    tracks, total = await get_tracks_page(
        migration_id,
        status=status or None,
        page=page,
        per_page=_PER_PAGE,
    )
    stats = await get_track_stats(migration_id)
    total_pages = max(1, (total + _PER_PAGE - 1) // _PER_PAGE)
    lang = get_lang(request)
    track_label_map = _TRACK_STATUS_LABEL_EN if lang == "en" else _TRACK_STATUS_LABEL_RU
    to_service = migration.get("to_service") or ""
    return _render("fragments/tracks_table.html", request, {
        "migration_id": migration_id,
        "tracks": tracks,
        "stats": stats,
        "status_filter": status,
        "status_label_map": track_label_map,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "to_service": to_service,
    })


@router.get("/migrate/{migration_id}/export")
async def export_migration(migration_id: int, fmt: str = "csv"):
    from core.services.file.adapter import FileAdapter

    fd, tmp = tempfile.mkstemp(suffix=f".{fmt}")
    os.close(fd)
    adapter = FileAdapter()
    path = await adapter.export_tracks(migration_id, tmp, fmt=fmt)
    filename = f"migration_{migration_id}.{fmt}"
    media = "text/csv" if fmt == "csv" else "application/json"
    return FileResponse(path, media_type=media, filename=filename,
                        background=BackgroundTask(os.unlink, path))


# ---------------------------------------------------------------------------
# File Import
# ---------------------------------------------------------------------------

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    from sqlalchemy import select, desc
    from core.db.models import Migration
    from core.db.session import AsyncSessionLocal

    user_id = _session_user_id(request)
    if not user_id:
        return RedirectResponse("/", status_code=303)

    async with AsyncSessionLocal() as s:
        result = await s.execute(
            select(Migration)
            .where(Migration.user_id == user_id)
            .order_by(desc(Migration.created_at))
            .limit(50)
        )
        rows = result.scalars().all()

    lang = get_lang(request)
    migration_ids = [m.id for m in rows]
    batch_stats = await get_track_stats_batch(migration_ids)

    migrations = []
    for m in rows:
        s = batch_stats.get(m.id, {})
        success = s.get("liked", 0) + s.get("in_playlist", 0)
        total = sum(s.values())
        migrations.append({
            "id": m.id,
            "user_migration_number": m.user_migration_number,
            "from_service": m.from_service or "",
            "to_service": m.to_service or "",
            "from_name": _svc_name(m.from_service or "file", lang),
            "to_name": _svc_name(m.to_service or "soundcloud", lang),
            "status": m.status,
            "status_label": _status_label(m.status, lang),
            "created_at": m.created_at,
            "success_count": success,
            "total_count": total,
        })
    return _render("history.html", request, {
        "migrations": migrations,
        "has_migrations": bool(rows),
    })
