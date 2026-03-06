"""Telegram-уведомления из воркера — прямые запросы к Bot API через httpx."""
from __future__ import annotations

import httpx
from loguru import logger

from config import settings


async def notify_telegram(user_id: str, text: str) -> None:
    """
    Отправляет Telegram-сообщение пользователю.
    Работает только если user_id — числовой Telegram ID.
    Веб-пользователи (web_*) молча пропускаются.
    """
    if not settings.telegram_bot_token:
        return

    try:
        tg_id = int(user_id)
    except ValueError:
        return  # web-пользователь, Telegram не связан

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


def migration_done_text(migration_id: int, tracks: dict, artists: dict | None = None) -> str:
    liked = tracks.get("liked", 0)
    not_found = tracks.get("not_found", 0)
    errors = tracks.get("error", 0)
    total = sum(tracks.values())

    web_url = settings.api_base_url.rstrip("/")
    text = (
        f"Перенос #{migration_id} завершён!\n\n"
        f"Перенесено:  <b>{liked}</b>\n"
        f"Не найдено:  <b>{not_found}</b>\n"
        f"Ошибок:      <b>{errors}</b>\n"
        f"Всего:       <b>{total}</b>\n"
    )
    if artists:
        followed = artists.get("followed", 0)
        art_nf = artists.get("not_found", 0)
        text += f"\nАртистов подписок: <b>{followed}</b>, не найдено: <b>{art_nf}</b>\n"

    text += f'\n<a href="{web_url}/migrate/{migration_id}/result">Открыть результат</a>'
    return text


def migration_failed_text(migration_id: int) -> str:
    return (
        f"Перенос #{migration_id} завершился с ошибкой.\n\n"
        "Попробуй запустить снова через /migrate"
    )


