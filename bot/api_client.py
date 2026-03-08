"""
HTTP-клиент бота для обращения к FastAPI.
Используется вместо прямых вызовов core/* в handlers.
"""
from __future__ import annotations

import httpx
from loguru import logger

from config import settings


class MigrationApiClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self._base_url = (base_url or settings.api_base_url).rstrip("/")
        self._token = token or settings.api_internal_token
        self._headers = {"X-Internal-Token": self._token} if self._token else {}

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def exchange_yandex_code(self, code: str) -> dict:
        """Обменивает код Яндекса на токен. Возвращает {token, login}."""
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.post(
                f"{self._base_url}/api/auth/yandex/token",
                json={"code": code},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def validate_soundcloud_token(self, token: str) -> dict:
        """Проверяет SC-токен. Возвращает {user_id, username}."""
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.post(
                f"{self._base_url}/api/auth/soundcloud/validate",
                json={"token": token},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    async def get_session(self, user_id: str) -> dict | None:
        """Загружает сессию. None если не найдена."""
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.get(
                f"{self._base_url}/api/sessions/{user_id}",
                timeout=10,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def save_session(self, user_id: str, ym_token: str, sc_token: str) -> None:
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.put(
                f"{self._base_url}/api/sessions/{user_id}",
                json={"yandex_token": ym_token, "soundcloud_token": sc_token},
                timeout=10,
            )
            resp.raise_for_status()

    async def delete_session(self, user_id: str) -> None:
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.delete(
                f"{self._base_url}/api/sessions/{user_id}",
                timeout=10,
            )
            resp.raise_for_status()

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    async def start_migration(
        self,
        user_id: str,
        ym_token: str,
        sc_token: str,
        mode: str = "tracks",
        from_service: str = "yandex_music",
        to_service: str = "soundcloud",
        spotify_token: str | None = None,
        spotify_refresh_token: str | None = None,
    ) -> int:
        """Запускает миграцию. Возвращает migration_id."""
        body: dict = {
            "user_id": user_id,
            "yandex_token": ym_token,
            "soundcloud_token": sc_token,
            "mode": mode,
            "from_service": from_service,
            "to_service": to_service,
        }
        if spotify_token:
            body["spotify_token"] = spotify_token
        if spotify_refresh_token:
            body["spotify_refresh_token"] = spotify_refresh_token
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.post(
                f"{self._base_url}/api/migrations",
                json=body,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["migration_id"]

    async def get_migration_status(self, migration_id: int) -> dict:
        """Возвращает {migration, tracks, artists}."""
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.get(
                f"{self._base_url}/api/migrations/{migration_id}",
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_not_found_tracks(self, migration_id: int) -> list[str]:
        """Возвращает список ненайденных треков (plain text → list[str])."""
        async with httpx.AsyncClient(headers=self._headers) as client:
            resp = await client.get(
                f"{self._base_url}/api/reports/{migration_id}/not-found",
                timeout=30,
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            return [line for line in resp.text.splitlines() if line.strip()]


# Глобальный singleton — используется в handlers
api_client = MigrationApiClient()
