"""FastAPI application — Music Migration API."""
from fastapi import FastAPI

from api.routes import auth, migrations, reports, sessions
from core.db import init_db

app = FastAPI(title="Music Migration API", version="4.0.0")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(migrations.router, prefix="/api/migrations", tags=["migrations"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])


@app.on_event("startup")
async def startup() -> None:
    await init_db()
