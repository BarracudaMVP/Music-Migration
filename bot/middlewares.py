"""
Middleware для бота:
- AllowedUsersMiddleware: пропускает только пользователей из ALLOWED_USERS
"""
from typing import Any, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from config import settings


class AllowedUsersMiddleware(BaseMiddleware):
    """
    Если ALLOWED_USERS задан — отклоняет запросы от остальных пользователей.
    Если ALLOWED_USERS пуст — пропускает всех (open bot).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        allowed = settings.get_allowed_users()
        if not allowed:
            return await handler(event, data)

        user_id = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is not None and user_id not in allowed:
            if isinstance(event, Message):
                await event.answer("У вас нет доступа к этому боту.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Нет доступа.", show_alert=True)
            return  # блокируем обработку

        return await handler(event, data)
