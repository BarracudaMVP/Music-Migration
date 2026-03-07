from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.states import MigrationFlow
from bot.api_client import api_client
from config import settings
from core.i18n import t

router = Router()


async def _get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "ru")


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    lang = await _get_lang(state)

    if current != MigrationFlow.in_progress:
        await message.answer(t("bot_status_not_running", lang))
        return

    data = await state.get_data()
    migration_id = data.get("migration_id")

    if not migration_id:
        await message.answer(t("bot_status_no_stats", lang))
        return

    try:
        status_data = await api_client.get_migration_status(migration_id)
    except Exception as e:
        await message.answer(t("bot_status_fail", lang).format(e=e))
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
            text=t("bot_btn_open_browser", lang),
            url=f"{web_url}/migrate/{migration_id}/tracks",
        )
    ]])

    await message.answer(
        t("bot_status_msg", lang).format(
            id=migration_id, done=done, total=total, pct=percent,
            liked=liked, nf=not_found, pending=pending, err=errors,
        ),
        reply_markup=kb,
    )
