from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.states import AuthFlow, MigrationFlow
from core.i18n import t, detect_lang_tg

router = Router()


async def _get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "ru")


async def _ensure_lang(message: Message, state: FSMContext) -> str:
    """Return lang from state if set, otherwise detect and store it."""
    data = await state.get_data()
    if "lang" in data:
        return data["lang"]
    lang = detect_lang_tg(message.from_user.language_code)
    await state.update_data(lang=lang)
    return lang


def _lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="\U0001f1f7\U0001f1fa Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="\U0001f1ec\U0001f1e7 English", callback_data="lang:en"),
    ]])


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    lang_code = message.from_user.language_code
    if lang_code is None:
        # Can't determine language — ask user to choose
        await message.answer(t("bot_lang_choose", "ru"), reply_markup=_lang_keyboard())
        return
    lang = detect_lang_tg(lang_code)
    await state.update_data(lang=lang)
    await message.answer(t("bot_welcome", lang), parse_mode="HTML")


@router.callback_query(F.data.startswith("lang:"))
async def on_lang_choice(callback: CallbackQuery, state: FSMContext) -> None:
    lang = callback.data.split(":")[1]
    if lang not in ("ru", "en"):
        lang = "ru"
    await state.update_data(lang=lang)

    # Persist to DB if the user has a saved session
    user_id = str(callback.from_user.id)
    try:
        from core.db import save_user_lang
        await save_user_lang(user_id, lang)
    except Exception:
        pass

    await callback.answer()
    confirm_key = "bot_lang_set_en" if lang == "en" else "bot_lang_set_ru"
    await callback.message.edit_text(t(confirm_key, lang))
    await callback.message.answer(t("bot_welcome", lang), parse_mode="HTML")


@router.message(Command("language"))
async def cmd_language(message: Message, state: FSMContext) -> None:
    lang = await _get_lang(state)
    await message.answer(t("bot_lang_choose", lang), reply_markup=_lang_keyboard())


@router.message(Command("migrate"))
async def cmd_migrate(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    lang = await _ensure_lang(message, state)
    if current == MigrationFlow.in_progress:
        await message.answer(t("bot_already_running", lang))
        return
    from bot.handlers.auth import start_auth
    await start_auth(message, state)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    lang = await _get_lang(state)
    if current is None:
        await message.answer(t("bot_cancel_nothing", lang))
        return
    await state.clear()
    await message.answer(t("bot_cancelled", lang))


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext) -> None:
    lang = await _get_lang(state)
    await message.answer(t("bot_help", lang), parse_mode="HTML")
