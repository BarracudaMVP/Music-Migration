"""Telegram notifications from the worker — direct Bot API calls via httpx."""
from __future__ import annotations

import httpx
from loguru import logger

from config import settings
from core.i18n import t


async def notify_telegram(user_id: str, text: str) -> None:
    """
    Send a Telegram message to the user.
    Only works if user_id is a numeric Telegram ID.
    Web users (web_*) are silently skipped.
    """
    if not settings.telegram_bot_token:
        return

    try:
        tg_id = int(user_id)
    except ValueError:
        return  # web user, not linked to Telegram

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": tg_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    f"Telegram notify failed for {user_id}: {resp.status_code} {resp.text[:100]}"
                )
    except Exception as e:
        logger.warning(f"Telegram notify error for {user_id}: {e}")


def migration_done_text(
    migration_id: int,
    tracks: dict,
    artists: dict | None = None,
    lang: str = "ru",
) -> str:
    liked = tracks.get("liked", 0)
    not_found = tracks.get("not_found", 0)
    errors = tracks.get("error", 0)
    total = sum(tracks.values())

    web_url = settings.api_base_url.rstrip("/")
    text = t("notif_done", lang).format(
        id=migration_id, liked=liked, nf=not_found, err=errors, total=total,
    )
    if artists:
        followed = artists.get("followed", 0)
        art_nf = artists.get("not_found", 0)
        text += t("notif_done_artists", lang).format(followed=followed, nf=art_nf)

    text += f'\n<a href="{web_url}/migrate/{migration_id}/result">{t("notif_done_link", lang)}</a>'
    return text


def migration_failed_text(migration_id: int, lang: str = "ru") -> str:
    return t("notif_failed", lang).format(id=migration_id)
