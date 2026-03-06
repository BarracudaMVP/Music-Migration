"""Web UI routes — Jinja2 + HTMX."""
from __future__ import annotations

import os
import tempfile
import uuid
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.background import BackgroundTask
from fastapi.templating import Jinja2Templates

from core.db import (
    create_migration,
    get_migration,
    get_track_stats,
    get_tracks_page,
    load_user_session,
    save_user_session,
    delete_user_session,
)
from core.db.crud import get_all_tracks
from core.services.registry import ServiceRegistry

templates = Jinja2Templates(directory="api/templates")
router = APIRouter()

_STATUS_LABEL = {
    "pending": "В очереди",
    "running": "Выполняется",
    "done": "Завершён",
    "failed": "Ошибка",
    "cancelled": "Отменён",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_user_id(request: Request) -> str | None:
    return request.session.get("user_id")


def _ensure_user_id(request: Request) -> str:
    """Return existing or create a new anonymous web user ID."""
    uid = request.session.get("user_id")
    if not uid:
        uid = f"web_{uuid.uuid4().hex[:12]}"
        request.session["user_id"] = uid
    return uid


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def index(request: Request, error: str = ""):
    user_id = _ensure_user_id(request)
    db_session = await load_user_session(user_id)
    matrix = ServiceRegistry.get_matrix()
    services = {a.id: a.name for a in ServiceRegistry.all()}
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "authed": db_session is not None,
            "matrix": matrix,
            "services": services,
            "error": error,
        },
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@router.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request, error: str = ""):
    user_id = _ensure_user_id(request)
    db_session = await load_user_session(user_id)
    ym_done = bool(request.session.get("ym_token") or (db_session and db_session.get("yandex_token")))

    from bot.oauth.yandex import get_auth_url
    return templates.TemplateResponse(
        "auth.html",
        {
            "request": request,
            "ym_auth_url": get_auth_url(),
            "ym_done": ym_done,
            "error": error,
        },
    )


@router.post("/auth/yandex", response_class=HTMLResponse)
async def auth_yandex(request: Request, code: str = Form(...)):
    _ensure_user_id(request)
    try:
        from bot.oauth.yandex import exchange_code
        from core.yandex.client import YandexMusicClient
        from config import settings

        token = await exchange_code(code)
        client = await YandexMusicClient(token, proxy_url=settings.ym_proxy_url or None).init()
        account = client._client.me.account if client._client.me else None
        login = (
            getattr(account, "login", None)
            or getattr(account, "display_name", None)
            or "пользователь"
        )
        request.session["ym_token"] = token
        request.session["ym_login"] = login
    except Exception as e:
        return RedirectResponse(f"/auth?error={quote(str(e)[:120])}", status_code=303)
    return RedirectResponse("/auth", status_code=303)


@router.post("/auth/soundcloud", response_class=HTMLResponse)
async def auth_soundcloud(request: Request, sc_token: str = Form(...)):
    user_id = _ensure_user_id(request)
    try:
        from core.soundcloud.client import SoundCloudClient

        sc = await SoundCloudClient(sc_token).init()
        await sc.close()
    except Exception as e:
        return RedirectResponse(f"/auth?error={quote(str(e)[:120])}", status_code=303)

    ym_token = request.session.get("ym_token", "")
    await save_user_session(user_id, ym_token, sc_token)
    # Clear temp session keys
    request.session.pop("ym_token", None)
    request.session.pop("ym_login", None)
    return RedirectResponse("/", status_code=303)


@router.post("/auth/logout")
async def logout(request: Request):
    user_id = _session_user_id(request)
    if user_id:
        await delete_user_session(user_id)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

@router.post("/migrate")
async def start_migrate(
    request: Request,
    from_service: str = Form(...),
    to_service: str = Form(...),
    mode: str = Form("full"),
):
    from api.main import get_arq_pool

    user_id = _session_user_id(request)
    if not user_id:
        return RedirectResponse("/auth", status_code=303)

    db_session = await load_user_session(user_id)
    if not db_session:
        return RedirectResponse("/auth", status_code=303)

    # Validate that the selected from→to pair is supported by the service registry
    matrix = ServiceRegistry.get_matrix()
    supported = {(e["from"], e["to"]) for e in matrix}
    if (from_service, to_service) not in supported:
        return RedirectResponse(
            f"/?error={quote(f'Направление {from_service} → {to_service} не поддерживается')}",
            status_code=303,
        )

    from api.deps import check_migration_rate_limit
    if not await check_migration_rate_limit(user_id):
        return RedirectResponse(
            f"/?error={quote('Слишком много переносов. Попробуй через час.')}",
            status_code=303,
        )

    migration_id = await create_migration(user_id)
    arq = get_arq_pool()
    job_mode = "full" if mode == "full" else "tracks"
    job = await arq.enqueue_job(
        "run_migration_job",
        migration_id,
        db_session["yandex_token"],
        db_session["soundcloud_token"],
        job_mode,
        user_id,
    )
    if job:
        await arq.set(f"migration_job:{migration_id}", job.job_id, ex=86400)
    return RedirectResponse(f"/migrate/{migration_id}", status_code=303)


@router.get("/migrate/{migration_id}", response_class=HTMLResponse)
async def migration_progress(request: Request, migration_id: int):
    migration = await get_migration(migration_id)
    if migration is None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "progress.html",
        {"request": request, "migration_id": migration_id, "migration": migration},
    )


@router.get("/migrate/{migration_id}/status-fragment", response_class=HTMLResponse)
async def migration_status_fragment(request: Request, migration_id: int):
    """HTMX partial — polled every 3 s from progress.html."""
    migration = await get_migration(migration_id)
    if migration is None:
        return HTMLResponse("<p>Миграция не найдена.</p>")

    stats = await get_track_stats(migration_id)
    done = migration["status"] in ("done", "failed", "cancelled")
    status_label = _STATUS_LABEL.get(migration["status"], migration["status"])

    return templates.TemplateResponse(
        "fragments/status.html",
        {
            "request": request,
            "migration_id": migration_id,
            "migration": migration,
            "status_label": status_label,
            "stats": stats,
            "done": done,
        },
    )


@router.get("/migrate/{migration_id}/result", response_class=HTMLResponse)
async def migration_result(request: Request, migration_id: int):
    migration = await get_migration(migration_id)
    if migration is None:
        return RedirectResponse("/", status_code=303)
    stats = await get_track_stats(migration_id)
    status_label = _STATUS_LABEL.get(migration["status"], migration["status"])
    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "migration_id": migration_id,
            "migration": migration,
            "status_label": status_label,
            "stats": stats,
        },
    )


_PER_PAGE = 50
_TRACK_STATUS_LABEL = {
    "liked": "Перенесён",
    "not_found": "Не найден",
    "error": "Ошибка",
    "pending": "В очереди",
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

    page = max(1, page)
    tracks, total = await get_tracks_page(
        migration_id,
        status=status or None,
        page=page,
        per_page=_PER_PAGE,
    )
    stats = await get_track_stats(migration_id)
    total_pages = max(1, (total + _PER_PAGE - 1) // _PER_PAGE)
    return templates.TemplateResponse(
        "tracks.html",
        {
            "request": request,
            "migration_id": migration_id,
            "migration": migration,
            "tracks": tracks,
            "stats": stats,
            "status_filter": status,
            "status_label_map": _TRACK_STATUS_LABEL,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        },
    )


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


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request, error: str = ""):
    user_id = _session_user_id(request)
    if not user_id:
        return RedirectResponse("/auth", status_code=303)
    db_session = await load_user_session(user_id)
    if not db_session:
        return RedirectResponse("/auth", status_code=303)
    return templates.TemplateResponse("import.html", {"request": request, "error": error})


@router.post("/import/preview", response_class=HTMLResponse)
async def import_preview(request: Request, file: UploadFile = File(...)):
    """HTMX: загружает файл, сохраняет во временное место, возвращает preview-фрагмент."""
    import tempfile

    from core.services.file.adapter import FileAdapter

    suffix = ".json" if (file.filename or "").lower().endswith(".json") else ".csv"

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        return HTMLResponse(
            '<p class="text-red-600 text-sm">Файл слишком большой (максимум 10 МБ).</p>'
        )

    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        import os
        os.write(fd, content)
        os.close(fd)

        adapter = FileAdapter()
        columns = await adapter.get_columns(tmp_path)
        if not columns:
            os.unlink(tmp_path)
            return HTMLResponse(
                '<p class="text-red-600 text-sm">Не удалось определить колонки. '
                "Проверь формат файла.</p>"
            )

        preview = await adapter.preview_tracks(tmp_path, limit=20)
        auto_map = adapter.detect_column_mapping(columns)

        # Удаляем старый временный файл
        old_tmp = request.session.get("import_tmp")
        if old_tmp:
            try:
                os.unlink(old_tmp)
            except OSError:
                pass

        request.session["import_tmp"] = tmp_path
    except Exception as e:
        try:
            import os
            os.unlink(tmp_path)
        except OSError:
            pass
        return HTMLResponse(f'<p class="text-red-600 text-sm">Ошибка: {e}</p>')

    return templates.TemplateResponse(
        "fragments/import_preview.html",
        {
            "request": request,
            "columns": columns,
            "preview": preview,
            "filename": file.filename,
            "auto_map": auto_map,
        },
    )


@router.post("/import/start")
async def import_start(
    request: Request,
    artist_col: str = Form(...),
    title_col: str = Form(...),
):
    import os

    from api.main import get_arq_pool
    from core.services.file.adapter import FileAdapter

    user_id = _session_user_id(request)
    if not user_id:
        return RedirectResponse("/auth", status_code=303)
    db_session = await load_user_session(user_id)
    if not db_session:
        return RedirectResponse("/auth", status_code=303)

    tmp_path = request.session.get("import_tmp")
    if not tmp_path or not os.path.exists(tmp_path):
        return RedirectResponse(
            f"/import?error={quote('Файл не найден — загрузи его снова')}",
            status_code=303,
        )

    try:
        adapter = FileAdapter()
        tracks = await adapter.import_tracks(tmp_path, artist_col=artist_col, title_col=title_col)
    except Exception as e:
        return RedirectResponse(f"/import?error={quote(str(e)[:120])}", status_code=303)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        request.session.pop("import_tmp", None)

    if not tracks:
        return RedirectResponse(
            f"/import?error={quote('Файл не содержит треков')}",
            status_code=303,
        )

    from api.deps import check_migration_rate_limit
    if not await check_migration_rate_limit(user_id):
        return RedirectResponse(
            f"/import?error={quote('Слишком много переносов. Попробуй через час.')}",
            status_code=303,
        )

    migration_id = await create_migration(user_id)
    arq = get_arq_pool()
    job = await arq.enqueue_job(
        "run_file_migration_job",
        migration_id,
        db_session["soundcloud_token"],
        tracks,
        user_id,
    )
    if job:
        await arq.set(f"migration_job:{migration_id}", job.job_id, ex=86400)

    return RedirectResponse(f"/migrate/{migration_id}", status_code=303)


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
        return RedirectResponse("/auth", status_code=303)

    async with AsyncSessionLocal() as s:
        result = await s.execute(
            select(Migration)
            .where(Migration.user_id == user_id)
            .order_by(desc(Migration.created_at))
            .limit(50)
        )
        rows = result.scalars().all()

    migrations = [
        {
            "id": m.id,
            "status": m.status,
            "status_label": _STATUS_LABEL.get(m.status, m.status),
            "created_at": m.created_at,
        }
        for m in rows
    ]
    return templates.TemplateResponse(
        "history.html",
        {"request": request, "migrations": migrations},
    )
