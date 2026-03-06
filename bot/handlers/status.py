from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.states import MigrationFlow
from bot.api_client import api_client
from config import settings

router = Router()


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext) -> None:
    current = await state.get_state()

    if current != MigrationFlow.in_progress:
        await message.answer("Миграция сейчас не запущена. Напиши /migrate чтобы начать.")
        return

    data = await state.get_data()
    migration_id = data.get("migration_id")

    if not migration_id:
        await message.answer("Миграция запущена, статистика пока недоступна.")
        return

    try:
        status_data = await api_client.get_migration_status(migration_id)
    except Exception as e:
        await message.answer(f"Не удалось получить статус: {e}")
        return

    tracks = status_data.get("tracks", {})
    total = sum(tracks.values())
    liked = tracks.get("liked", 0)
    pending = tracks.get("pending", 0)
    not_found = tracks.get("not_found", 0)
    errors = tracks.get("error", 0)

    done = liked + not_found + errors
    percent = int(done / total * 100) if total else 0

    web_url = settings.api_base_url.rstrip("/")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Открыть в браузере",
            url=f"{web_url}/migrate/{migration_id}/tracks",
        )
    ]])

    await message.answer(
        f"Прогресс миграции #{migration_id}:\n\n"
        f"Обработано: {done}/{total} ({percent}%)\n"
        f"Перенесено: {liked}\n"
        f"Не найдено: {not_found}\n"
        f"В очереди:  {pending}\n"
        f"Ошибок:     {errors}",
        reply_markup=kb,
    )
