"""FastAPI application — Music Migration API."""
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.sessions import SessionMiddleware

from api.routes import api_v1, bot_auth, migrations, reports, services, sessions
from config import settings
from core.logger import setup_logger
from core.services.file.adapter import FileAdapter
from core.services.registry import ServiceRegistry
from core.services.soundcloud.adapter import SoundCloudAdapter
from core.services.spotify.adapter import SpotifyAdapter
from core.services.yandex.adapter import YandexMusicAdapter

setup_logger("api")

if settings.dev_mode:
    logger.warning(
        "⚠️  DEV_MODE is enabled — fake auth available at /dev/login. "
        "NEVER run with DEV_MODE=true in production."
    )

app = FastAPI(title="Music Migration API", version="9.0.0")

# CORS — allow SPA frontend origins (JWT in Authorization header, not cookies)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SessionMiddleware — required for OAuth state flow (_ensure_user_id in api_v1.py)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# Public JSON API v1 for SPA frontend (MM-81)
app.include_router(api_v1.router, tags=["api_v1"])

# Public bot OAuth redirect routes (no X-Internal-Token required)
app.include_router(bot_auth.router_public, tags=["bot_auth_public"])

# Internal API — always available (used by bot and worker)
app.include_router(bot_auth.router, prefix="/api/auth", tags=["bot_auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(migrations.router, prefix="/api/migrations", tags=["migrations"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(services.router, prefix="/api/services", tags=["services"])

_arq_pool = None


@app.on_event("startup")
async def startup() -> None:
    global _arq_pool
    _arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    for adapter in [YandexMusicAdapter(), SoundCloudAdapter(), FileAdapter(), SpotifyAdapter()]:
        ServiceRegistry.register(adapter)
    if settings.initial_admin_user_id:
        from core.db.crud import set_user_role
        await set_user_role(settings.initial_admin_user_id, "admin")
        logger.info(f"Bootstrap: set role=admin for user {settings.initial_admin_user_id}")


@app.on_event("shutdown")
async def shutdown() -> None:
    if _arq_pool:
        await _arq_pool.close()


def get_arq_pool():
    return _arq_pool


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "version": "9.0.0"}
