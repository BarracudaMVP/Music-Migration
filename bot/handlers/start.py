from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.states import AuthFlow, MigrationFlow

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Привет! Я перенесу твои треки из Яндекс Музыки в SoundCloud.\n\n"
        "<b>Что умею:</b>\n"
        "• MVP1 — перенести лайкнутые треки\n"
        "• MVP2 — плейлисты и подписки на артистов\n\n"
        "Для начала нужно два токена: от Яндекс Музыки и от SoundCloud.\n\n"
        "Нажми /migrate чтобы начать.",
        parse_mode="HTML",
    )


@router.message(Command("migrate"))
async def cmd_migrate(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current == MigrationFlow.in_progress:
        await message.answer("Миграция уже запущена. Используй /status для проверки.")
        return

    from bot.handlers.auth import start_auth
    await start_auth(message, state)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    await message.answer("Отменено. Напиши /migrate чтобы начать заново.")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Команды:</b>\n"
        "/migrate — начать перенос музыки\n"
        "/status — статус текущей миграции\n"
        "/cancel — отменить текущее действие\n"
        "/help — эта справка",
        parse_mode="HTML",
    )


