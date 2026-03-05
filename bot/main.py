import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from config import settings
from core.logger import setup_logger
from bot.handlers import start, auth, migration, status
from bot.middlewares import AllowedUsersMiddleware


async def _set_commands(bot) -> None:
    from aiogram.types import BotCommand, BotCommandScopeDefault
    commands = [
        BotCommand(command="migrate", description="Начать перенос музыки"),
        BotCommand(command="status",  description="Статус текущей миграции"),
        BotCommand(command="cancel",  description="Отменить текущее действие"),
        BotCommand(command="help",    description="Помощь"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    logger.info("Команды бота установлены")


async def main() -> None:
    setup_logger()

    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")

    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware — проверка доступа (до всех хендлеров)
    dp.message.middleware(AllowedUsersMiddleware())
    dp.callback_query.middleware(AllowedUsersMiddleware())

    # Регистрируем роутеры в нужном порядке
    dp.include_router(start.router)
    dp.include_router(auth.router)
    dp.include_router(migration.router)
    dp.include_router(status.router)

    await _set_commands(bot)
    logger.info("Бот запущен. Ожидаю сообщения...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
