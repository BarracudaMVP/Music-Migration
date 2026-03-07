"""FastAPI application — Music Migration API."""
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from api.middleware import AllowedUsersWebMiddleware
from api.routes import admin, auth, migrations, reports, services, sessions, web
from config import settings
from core.logger import setup_logger
from core.services.file.adapter import FileAdapter
from core.services.registry import ServiceRegistry
from core.services.soundcloud.adapter import SoundCloudAdapter
from core.services.spotify.adapter import SpotifyAdapter
from core.services.yandex.adapter import YandexMusicAdapter

setup_logger("api")

app = FastAPI(title="Music Migration API", version="9.0.0")

# Порядок важен: первый добавленный = innermost = выполняется после SessionMiddleware
# AllowedUsersWebMiddleware должен видеть сессию → добавляем до SessionMiddleware
app.add_middleware(AllowedUsersWebMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(migrations.router, prefix="/api/migrations", tags=["migrations"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(services.router, prefix="/api/services", tags=["services"])
app.include_router(web.router, tags=["web"])
app.include_router(admin.router, tags=["admin"])

_arq_pool = None


@app.on_event("startup")
async def startup() -> None:
    global _arq_pool
    _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    for adapter in [YandexMusicAdapter(), SoundCloudAdapter(), FileAdapter(), SpotifyAdapter()]:
        ServiceRegistry.register(adapter)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _arq_pool:
        await _arq_pool.close()


def get_arq_pool():
    return _arq_pool


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "version": "9.0.0"}
