"""FastAPI/Starlette middleware для веб-приложения."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

# Пути, которые не проверяются middleware
_EXEMPT_PREFIXES = ("/admin", "/auth", "/health", "/api", "/static")

# Пути внутреннего API — всегда доступны (бот, воркер)
_API_PREFIXES = ("/api", "/health")


def _get_client_ip(request: Request) -> str:
    """Return real client IP, honoring X-Forwarded-For from nginx proxy."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else ""


class WebIPWhitelistMiddleware(BaseHTTPMiddleware):
    """
    Restricts web UI and admin to specific IPs when WEB_ALLOWED_IPS is set.
    API routes (/api/*, /health) are always accessible.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        from config import settings

        allowed_ips_str = settings.web_allowed_ips.strip()
        if not allowed_ips_str:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in _API_PREFIXES):
            return await call_next(request)

        allowed = {ip.strip() for ip in allowed_ips_str.split(",") if ip.strip()}
        client_ip = _get_client_ip(request)
        if client_ip not in allowed:
            return Response(status_code=403, content="Forbidden")

        return await call_next(request)


class AllowedUsersWebMiddleware(BaseHTTPMiddleware):
    """
    Если ALLOWED_USERS задан — проверяет числовые (Telegram) user_id из сессии.
    Веб-пользователи с user_id вида 'web_*' пропускаются всегда.
    Незалогиненные пользователи пропускаются (auth-редирект у маршрутов).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        from config import settings

        allowed = settings.get_allowed_users()
        if not allowed:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        user_id_str: str = request.session.get("user_id", "")
        if user_id_str and not user_id_str.startswith("web_"):
            try:
                uid = int(user_id_str)
                if uid not in allowed:
                    request.session.clear()
                    return RedirectResponse("/?error=access_denied", status_code=303)
            except ValueError:
                pass

        return await call_next(request)
