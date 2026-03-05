from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.states import MigrationFlow
from core.db import get_track_stats

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

    stats = await get_track_stats(migration_id)
    total = sum(stats.values())
    liked = stats.get("liked", 0)
    pending = stats.get("pending", 0)
    not_found = stats.get("not_found", 0)
    errors = stats.get("error", 0)

    done = liked + not_found + errors
    percent = int(done / total * 100) if total else 0

    await message.answer(
        f"Прогресс миграции #{migration_id}:\n\n"
        f"Обработано: {done}/{total} ({percent}%)\n"
        f"Перенесено: {liked}\n"
        f"Не найдено: {not_found}\n"
        f"В очереди:  {pending}\n"
        f"Ошибок:     {errors}",
    )
