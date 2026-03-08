import asyncio

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from bot.states import AuthFlow, MigrationFlow
from bot.api_client import api_client
from config import settings
from core.i18n import t

router = Router()

_POLL_INTERVAL = 15  # seconds between status polls
_NOT_FOUND_PREVIEW = 30  # tracks shown inline


async def _get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "ru")


def _kb_cancel(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("bot_btn_detach", lang), callback_data="migration:detach"),
    ]])


def _kb_result(migration_id: int, not_found: int, lang: str) -> InlineKeyboardMarkup:
    web_url = settings.api_base_url.rstrip("/")
    rows = []
    if not_found > 0:
        rows.append([InlineKeyboardButton(
            text=t("bot_btn_not_found", lang).format(n=not_found),
            callback_data=f"migration:not_found:{migration_id}",
        )])
    rows.append([InlineKeyboardButton(
        text=t("bot_btn_open_browser", lang),
        url=f"{web_url}/migrate/{migration_id}/tracks",
    )])
    rows.append([InlineKeyboardButton(
        text=t("bot_btn_new_transfer", lang),
        callback_data="migration:new",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Start migration
# ---------------------------------------------------------------------------

@router.callback_query(AuthFlow.confirming, F.data.startswith("start_migration"))
async def on_start_migration(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    mode = callback.data.split(":")[-1]  # "tracks" or "full"
    lang = await _get_lang(state)

    data = await state.get_data()
    ym_token = data.get("yandex_token", "")
    sc_token = data["soundcloud_token"]
    from_service = data.get("from_service", "yandex_music")
    spotify_token = data.get("spotify_token")
    user_id = str(callback.from_user.id)

    if from_service == "spotify":
        start_key = "bot_migration_started_spotify"
    elif mode == "full":
        start_key = "bot_migration_started_full"
    else:
        start_key = "bot_migration_started_tracks"
    progress_msg = await callback.message.answer(t(start_key, lang), reply_markup=_kb_cancel(lang))

    await state.set_state(MigrationFlow.in_progress)
    await state.update_data(progress_msg_id=progress_msg.message_id)

    try:
        migration_id = await api_client.start_migration(
            user_id, ym_token, sc_token, mode,
            from_service=from_service,
            spotify_token=spotify_token,
        )
    except Exception as e:
        logger.exception(f"Failed to start migration: {e}")
        await progress_msg.edit_text(
            t("bot_migration_fail_start", lang).format(e=e),
            parse_mode="HTML",
            reply_markup=None,
        )
        await state.clear()
        return

    await state.update_data(migration_id=migration_id)

    asyncio.create_task(
        _poll_migration(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            progress_msg_id=progress_msg.message_id,
            migration_id=migration_id,
            state=state,
        )
    )


@router.callback_query(AuthFlow.confirming, F.data == "cancel_migration")
async def on_cancel_migration(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang = await _get_lang(state)
    await state.clear()
    await callback.message.edit_text(t("bot_cancel_confirm", lang))


# ---------------------------------------------------------------------------
# Controls during migration
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "migration:detach")
async def on_detach(callback: CallbackQuery, state: FSMContext) -> None:
    """User detaches from tracking — job continues on server."""
    await callback.answer()
    current = await state.get_state()
    lang = await _get_lang(state)
    if current != MigrationFlow.in_progress:
        await callback.answer(t("bot_detach_no_active", lang), show_alert=True)
        return
    await state.clear()
    try:
        await callback.message.edit_text(t("bot_detach_msg", lang), reply_markup=None)
    except TelegramBadRequest:
        pass


@router.message(MigrationFlow.in_progress)
async def migration_in_progress(message: Message, state: FSMContext) -> None:
    lang = await _get_lang(state)
    await message.answer(t("bot_already_in_progress", lang))


# ---------------------------------------------------------------------------
# Final message callbacks
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("migration:not_found:"))
async def on_show_not_found(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang = await _get_lang(state)
    migration_id = int(callback.data.split(":")[-1])

    try:
        tracks = await api_client.get_not_found_tracks(migration_id)
    except Exception as e:
        await callback.answer(t("bot_not_found_error", lang).format(e=e), show_alert=True)
        return

    if not tracks:
        await callback.answer(t("bot_not_found_none", lang), show_alert=True)
        return

    preview = tracks[:_NOT_FOUND_PREVIEW]
    text = t("bot_not_found_list", lang).format(n=len(tracks))
    text += "\n".join(f"• {tr}" for tr in preview)
    if len(tracks) > _NOT_FOUND_PREVIEW:
        remaining = len(tracks) - _NOT_FOUND_PREVIEW
        web_url = settings.api_base_url.rstrip("/")
        text += t("bot_not_found_more", lang).format(
            n=remaining,
            url=f"{web_url}/migrate/{migration_id}/tracks?status=not_found",
        )

    await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(F.data == "migration:new")
async def on_new_migration(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    from bot.handlers.auth import start_auth
    await start_auth(callback.message, state)


# ---------------------------------------------------------------------------
# Progress poll loop
# ---------------------------------------------------------------------------

async def _poll_migration(
    bot,
    chat_id: int,
    progress_msg_id: int,
    migration_id: int,
    state: FSMContext,
) -> None:
    """Poll API every N seconds and update the progress message."""
    last_text = ""

    while True:
        await asyncio.sleep(_POLL_INTERVAL)

        if await state.get_state() != MigrationFlow.in_progress:
            return

        state_data = await state.get_data()
        lang = state_data.get("lang", "ru")

        try:
            data = await api_client.get_migration_status(migration_id)
        except Exception as e:
            logger.warning(f"Poll error migration #{migration_id}: {e}")
            continue

        migration = data.get("migration", {})
        tracks = data.get("tracks", {})
        current_track = data.get("current_track")
        mig_status = migration.get("status", "running")

        total = sum(tracks.values()) if tracks else 0
        liked = tracks.get("liked", 0)
        not_found = tracks.get("not_found", 0)
        errors = tracks.get("error", 0)
        done = liked + not_found + errors

        if mig_status in ("done", "failed", "cancelled"):
            text = _build_final_text(tracks, data.get("artists", {}), lang)
            kb = _kb_result(migration_id, not_found, lang)
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            except TelegramBadRequest:
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=kb)
            await state.clear()
            return

        # Intermediate progress
        if total:
            percent = int(done / total * 100)
            bar = _progress_bar(percent)
            text = t("bot_progress_bar", lang).format(
                bar=bar, pct=percent, done=done, total=total,
                liked=liked, nf=not_found, err=errors,
            )
        else:
            text = t("bot_progress_loading", lang)

        if current_track:
            text += f"\n\n♪ {current_track}"

        if text != last_text:
            last_text = text
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg_id,
                    text=text,
                    reply_markup=_kb_cancel(lang),
                )
            except TelegramBadRequest:
                pass


def _build_final_text(tracks: dict, artists: dict, lang: str) -> str:
    liked = tracks.get("liked", 0)
    not_found = tracks.get("not_found", 0)
    errors = tracks.get("error", 0)
    total = sum(tracks.values())

    text = t("bot_done_tracks", lang).format(
        liked=liked, nf=not_found, err=errors, total=total,
    )
    if artists:
        followed = artists.get("followed", 0)
        art_not_found = artists.get("not_found", 0)
        text += t("bot_done_artists", lang).format(followed=followed, nf=art_not_found)
    return text


def _progress_bar(percent: int, length: int = 20) -> str:
    filled = int(length * percent / 100)
    return "\u2588" * filled + "\u2591" * (length - filled)
