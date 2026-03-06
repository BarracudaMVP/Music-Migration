"""FastAPI/Starlette middleware для веб-приложения."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

# Пути, которые не проверяются middleware
_EXEMPT_PREFIXES = ("/admin", "/auth", "/health", "/api", "/static")


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
