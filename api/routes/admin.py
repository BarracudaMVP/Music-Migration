"""Admin UI routes — protected by session password."""
from __future__ import annotations
import contextlib
import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select

from config import settings
from core.db import load_user_session, set_user_role
from core.db.models import Migration, Track, UserSession
from core.db.session import AsyncSessionLocal
from core.services.base import Capability
from core.services.registry import ServiceRegistry

templates = Jinja2Templates(directory="api/templates")
router = APIRouter(prefix="/admin")

# ---------------------------------------------------------------------------
# Брутфорс защита /admin/login
# ---------------------------------------------------------------------------

_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60  # 15 минут
_login_attempts: dict[str, tuple[int, float]] = {}  # ip → (count, first_fail_ts)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host or "unknown")


def _is_locked_out(ip: str) -> bool:
    if ip not in _login_attempts:
        return False
    count, first = _login_attempts[ip]
    if time.time() - first > _LOCKOUT_SECONDS:
        del _login_attempts[ip]
        return False
    return count >= _MAX_LOGIN_ATTEMPTS


def _record_fail(ip: str) -> int:
    """Записывает неудачную попытку, возвращает текущий счётчик."""
    if ip in _login_attempts:
        count, first = _login_attempts[ip]
        _login_attempts[ip] = (count + 1, first)
        return count + 1
    _login_attempts[ip] = (1, time.time())
    return 1


def _reset_attempts(ip: str) -> None:
    _login_attempts.pop(ip, None)

_STATUS_LABEL = {
    "pending": "В очереди",
    "running": "Выполняется",
    "done": "Завершена",
    "failed": "Ошибка",
    "cancelled": "Отменена",
}


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

async def _is_admin(request: Request) -> bool:
    """True если пользователь — суперадмин (пароль) или имеет роль admin в БД."""
    if request.session.get("is_admin") is True:
        return True
    user_id = request.session.get("user_id")
    if user_id:
        session = await load_user_session(user_id)
        if session and session.get("role") == "admin":
            return True
    return False


async def _require_admin(request: Request) -> RedirectResponse | None:
    if not await _is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    return None


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if await _is_admin(request):
        return RedirectResponse("/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        request, "admin/login.html", {"error": error}
    )


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    ip = _client_ip(request)

    if _is_locked_out(ip):
        return RedirectResponse(
            "/admin/login?error=Слишком+много+попыток.+Попробуй+через+15+минут.",
            status_code=303,
        )

    if password == settings.admin_password:
        _reset_attempts(ip)
        request.session["is_admin"] = True
        return RedirectResponse("/admin/dashboard", status_code=303)

    count = _record_fail(ip)
    remaining = max(0, _MAX_LOGIN_ATTEMPTS - count)
    msg = f"Неверный+пароль.+Осталось+попыток:+{remaining}" if remaining else "Аккаунт+заблокирован+на+15+минут."
    return RedirectResponse(f"/admin/login?error={msg}", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.pop("is_admin", None)
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def admin_index(request: Request):
    return RedirectResponse("/admin/dashboard", status_code=303)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if redir := await _require_admin(request):
        return redir

    async with AsyncSessionLocal() as s:
        total_migrations = (await s.execute(select(func.count()).select_from(Migration))).scalar()
        total_users = (await s.execute(select(func.count()).select_from(UserSession))).scalar()
        total_tracks = (await s.execute(select(func.count()).select_from(Track))).scalar()

        status_rows = await s.execute(
            select(Migration.status, func.count().label("cnt"))
            .group_by(Migration.status)
        )
        by_status = {row.status: row.cnt for row in status_rows}

        track_status_rows = await s.execute(
            select(Track.status, func.count().label("cnt"))
            .group_by(Track.status)
        )
        tracks_by_status = {row.status: row.cnt for row in track_status_rows}

        recent = (await s.execute(
            select(Migration).order_by(desc(Migration.created_at)).limit(10)
        )).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "total_migrations": total_migrations,
            "total_users": total_users,
            "total_tracks": total_tracks,
            "by_status": by_status,
            "tracks_by_status": tracks_by_status,
            "status_label": _STATUS_LABEL,
            "recent": recent,
        },
    )


# ---------------------------------------------------------------------------
# Migrations list
# ---------------------------------------------------------------------------

@router.get("/migrations", response_class=HTMLResponse)
async def migrations_list(request: Request, status: str = "", user_id: str = ""):
    if redir := await _require_admin(request):
        return redir

    async with AsyncSessionLocal() as s:
        q = select(Migration).order_by(desc(Migration.created_at))
        if status:
            q = q.where(Migration.status == status)
        if user_id:
            q = q.where(Migration.user_id == user_id)
        rows = (await s.execute(q.limit(200))).scalars().all()

    migrations = [
        {
            "id": m.id,
            "user_id": m.user_id,
            "from_service": m.from_service or "",
            "to_service": m.to_service or "",
            "status": m.status,
            "status_label": _STATUS_LABEL.get(m.status, m.status),
            "created_at": m.created_at,
        }
        for m in rows
    ]
    return templates.TemplateResponse(
        request,
        "admin/migrations.html",
        {
            "migrations": migrations,
            "filter_status": status,
            "filter_user": user_id,
            "status_options": list(_STATUS_LABEL.keys()),
        },
    )


# ---------------------------------------------------------------------------
# Migration detail
# ---------------------------------------------------------------------------

@router.get("/migrations/{migration_id}", response_class=HTMLResponse)
async def migration_detail(request: Request, migration_id: int, track_status: str = ""):
    if redir := await _require_admin(request):
        return redir

    async with AsyncSessionLocal() as s:
        migration = await s.get(Migration, migration_id)
        if migration is None:
            return RedirectResponse("/admin/migrations", status_code=303)

        track_q = select(Track).where(Track.migration_id == migration_id)
        if track_status:
            track_q = track_q.where(Track.status == track_status)
        track_q = track_q.order_by(Track.status, Track.ym_artist).limit(500)
        tracks = (await s.execute(track_q)).scalars().all()

        stats_rows = await s.execute(
            select(Track.status, func.count().label("cnt"))
            .where(Track.migration_id == migration_id)
            .group_by(Track.status)
        )
        stats = {row.status: row.cnt for row in stats_rows}

    return templates.TemplateResponse(
        request,
        "admin/migration_detail.html",
        {
            "migration": migration,
            "status_label": _STATUS_LABEL.get(migration.status, migration.status),
            "tracks": tracks,
            "stats": stats,
            "filter_status": track_status,
            "track_status_options": ["pending", "liked", "in_playlist", "not_found", "error"],
        },
    )


# ---------------------------------------------------------------------------
# Cancel / restart migration
# ---------------------------------------------------------------------------

@router.post("/migrations/{migration_id}/cancel")
async def cancel_migration(request: Request, migration_id: int):
    if not await _is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    from sqlalchemy import update
    from api.main import get_arq_pool
    from arq.jobs import Job

    # Abort the running ARQ job if we know its id
    arq_pool = get_arq_pool()
    if arq_pool:
        job_id_b = await arq_pool.get(f"migration_job:{migration_id}")
        if job_id_b:
            job_id = job_id_b.decode() if isinstance(job_id_b, bytes) else job_id_b
            with contextlib.suppress(Exception):
                await Job(job_id, arq_pool).abort(timeout=2)
            await arq_pool.delete(f"migration_job:{migration_id}")

    async with AsyncSessionLocal() as s:
        await s.execute(
            update(Migration)
            .where(Migration.id == migration_id, Migration.status.in_(["pending", "running"]))
            .values(status="cancelled")
        )
        await s.commit()
    return RedirectResponse(f"/admin/migrations/{migration_id}", status_code=303)


@router.post("/migrations/{migration_id}/restart")
async def restart_migration(request: Request, migration_id: int):
    if not await _is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    from api.main import get_arq_pool
    from sqlalchemy import update
    from core.db import load_user_session

    async with AsyncSessionLocal() as s:
        migration = await s.get(Migration, migration_id)
        if migration is None:
            return RedirectResponse("/admin/migrations", status_code=303)

        db_session = await load_user_session(migration.user_id)
        if not db_session:
            return RedirectResponse(
                f"/admin/migrations/{migration_id}?error=no_session", status_code=303
            )

        await s.execute(
            update(Migration)
            .where(Migration.id == migration_id)
            .values(status="pending")
        )
        # Reset failed/not_found/error tracks back to pending for resume
        await s.execute(
            update(Track)
            .where(Track.migration_id == migration_id, Track.status.in_(["error"]))
            .values(status="pending")
        )
        await s.commit()

    arq = get_arq_pool()
    job = await arq.enqueue_job(
        "run_migration_job",
        migration_id,
        db_session["yandex_token"],
        db_session["soundcloud_token"],
        "tracks",
        migration.user_id,
    )
    if job:
        await arq.set(f"migration_job:{migration_id}", job.job_id, ex=86400)
    return RedirectResponse(f"/admin/migrations/{migration_id}", status_code=303)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request):
    if redir := await _require_admin(request):
        return redir

    async with AsyncSessionLocal() as s:
        sessions = (await s.execute(
            select(UserSession).order_by(desc(UserSession.updated_at))
        )).scalars().all()

        # count migrations per user
        counts_rows = await s.execute(
            select(Migration.user_id, func.count().label("cnt"))
            .group_by(Migration.user_id)
        )
        counts = {row.user_id: row.cnt for row in counts_rows}

    users = [
        {
            "user_id": u.user_id,
            "role": u.role,
            "updated_at": u.updated_at,
            "migration_count": counts.get(u.user_id, 0),
        }
        for u in sessions
    ]
    return templates.TemplateResponse(
        request, "admin/users.html", {"users": users}
    )


@router.post("/users/{user_id}/set-role")
async def admin_set_user_role(request: Request, user_id: str, role: str = Form(...)):
    if not await _is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    if role in ("user", "admin"):
        await set_user_role(user_id, role)
    return RedirectResponse("/admin/users", status_code=303)


# ---------------------------------------------------------------------------
# Service registry
# ---------------------------------------------------------------------------

@router.get("/services", response_class=HTMLResponse)
async def services_view(request: Request):
    if redir := await _require_admin(request):
        return redir

    adapters = [
        {
            "id": a.id,
            "name": a.name,
            "capabilities": [c.name for c in Capability if a.can(c)],
        }
        for a in ServiceRegistry.all()
    ]
    matrix = ServiceRegistry.get_matrix()
    return templates.TemplateResponse(
        request, "admin/services.html", {"adapters": adapters, "matrix": matrix}
    )
