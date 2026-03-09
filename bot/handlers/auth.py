import re

import httpx
from loguru import logger
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot.states import AuthFlow
from bot.api_client import api_client
from core.i18n import t, detect_lang_tg, format_eta

router = Router()

_SC_TOKEN_RE = re.compile(r"^\d-[A-Za-z0-9\-]+$")


async def _get_lang(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("lang", "ru")


# ---------------------------------------------------------------------------
# Entry point — check saved session, then show FROM selection
# ---------------------------------------------------------------------------

async def start_auth(message: Message, state: FSMContext) -> None:
    """Called from start.py on /migrate. Validates saved session or starts auth."""
    user_id = str(message.from_user.id)
    session = await api_client.get_session(user_id)

    # Ensure lang is set in state (restore from session or detect from Telegram)
    data = await state.get_data()
    if "lang" not in data:
        lang = detect_lang_tg(message.from_user.language_code)
        if session and session.get("lang"):
            lang = session["lang"]
        await state.update_data(lang=lang)

    if session:
        await state.update_data(
            yandex_token=session.get("yandex_token", ""),
            soundcloud_token=session.get("soundcloud_token", ""),
            spotify_token=session.get("spotify_token"),
        )

    await _show_from_selection(message, state)


async def _show_from_selection(message: Message, state: FSMContext) -> None:
    lang = await _get_lang(state)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("bot_service_yandex", lang), callback_data="service:from:yandex_music")],
        [InlineKeyboardButton(text=t("bot_service_spotify", lang), callback_data="service:from:spotify")],
    ])
    await message.answer(t("bot_select_from", lang), reply_markup=kb)
    await state.set_state(AuthFlow.selecting_from)


@router.callback_query(AuthFlow.selecting_from, F.data == "service:from:yandex_music")
async def on_select_from_ym(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(from_service="yandex_music")

    data = await state.get_data()
    user_id = str(callback.from_user.id)
    lang = await _get_lang(state)

    # If we have a saved YM token, validate it
    if data.get("yandex_token"):
        try:
            from core.yandex.client import YandexMusicClient
            from config import settings
            await YandexMusicClient(data["yandex_token"], proxy_url=settings.ym_proxy_url or None).init()
            logger.info(f"Saved YM token valid for user_id={user_id}")
            # Also validate SC token
            if data.get("soundcloud_token"):
                try:
                    from core.soundcloud.client import SoundCloudClient
                    sc = await SoundCloudClient(data["soundcloud_token"]).init()
                    await sc.close()
                    logger.info(f"Saved SC token valid for user_id={user_id}")
                    await _show_confirmation(callback.message, state)
                    return
                except Exception:
                    await api_client.delete_session(user_id)
                    logger.warning(f"SC token expired for user_id={user_id}")
                    await callback.message.answer(t("bot_sc_expired", lang))
            await _ask_soundcloud_token(callback.message, state)
        except Exception:
            await api_client.delete_session(user_id)
            logger.warning(f"YM token expired for user_id={user_id}")
            await callback.message.answer(t("bot_ym_expired", lang))
            await _ask_yandex_token(callback.message, state)
    else:
        await _ask_yandex_token(callback.message, state)


@router.callback_query(AuthFlow.selecting_from, F.data == "service:from:spotify")
async def on_select_from_spotify(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(from_service="spotify")

    data = await state.get_data()
    lang = await _get_lang(state)

    if not data.get("spotify_token"):
        from config import settings
        web_url = settings.api_base_url.rstrip("/")
        await callback.message.answer(
            t("bot_spotify_no_token", lang).format(url=web_url),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        await state.clear()
        return

    await _show_confirmation_spotify(callback.message, state)


@router.callback_query(F.data == "auth:new_tokens")
async def on_new_tokens(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _ask_yandex_token(callback.message, state)


@router.callback_query(F.data == "auth:new_tokens")
async def on_new_tokens(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _ask_yandex_token(callback.message, state)


# ---------------------------------------------------------------------------
# Step 1 — Yandex Music (OAuth)
# ---------------------------------------------------------------------------

async def _ask_yandex_token(message: Message, state: FSMContext) -> None:
    lang = await _get_lang(state)
    from bot.oauth.yandex import get_auth_url
    auth_url = get_auth_url()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t("bot_ym_login_btn", lang), url=auth_url)
    ]])
    await message.answer(t("bot_ym_step1", lang), parse_mode="HTML", reply_markup=kb)
    await state.set_state(AuthFlow.waiting_yandex_token)


@router.message(AuthFlow.waiting_yandex_token)
async def receive_yandex_token(message: Message, state: FSMContext) -> None:
    code = message.text.strip() if message.text else ""
    lang = await _get_lang(state)

    try:
        await message.delete()
    except Exception:
        pass

    if not code:
        await message.answer(t("bot_code_empty", lang))
        return

    status_msg = await message.answer(t("bot_checking", lang))

    try:
        result = await api_client.exchange_yandex_code(code)
        token = result["token"]
        await state.update_data(yandex_token=token)
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", str(e))
        await status_msg.edit_text(t("bot_ym_error", lang).format(detail=detail))
        return
    except Exception as e:
        await status_msg.edit_text(t("bot_ym_error", lang).format(detail=str(e)))
        return

    await status_msg.edit_text(t("bot_ym_ok", lang))
    await _ask_soundcloud_token(message, state)


# ---------------------------------------------------------------------------
# Step 2 — SoundCloud
# ---------------------------------------------------------------------------

async def _ask_soundcloud_token(message: Message, state: FSMContext, ym_token: str = None) -> None:
    lang = await _get_lang(state)
    if ym_token:
        await state.update_data(yandex_token=ym_token)
    instructions = t("bot_sc_instructions", lang)
    await message.answer(
        t("bot_sc_step2", lang).format(instructions=instructions),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await state.set_state(AuthFlow.waiting_soundcloud_token)


@router.message(AuthFlow.waiting_soundcloud_token)
async def receive_soundcloud_token(message: Message, state: FSMContext) -> None:
    token = message.text.strip() if message.text else ""
    lang = await _get_lang(state)

    try:
        await message.delete()
    except Exception:
        pass

    if not token:
        await message.answer(t("bot_sc_token_empty", lang))
        return

    if not _SC_TOKEN_RE.match(token):
        await message.answer(t("bot_sc_token_invalid", lang), parse_mode="HTML")
        return

    status_msg = await message.answer(t("bot_sc_checking", lang))

    try:
        await api_client.validate_soundcloud_token(token)
        await state.update_data(soundcloud_token=token)
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", str(e))
        await status_msg.edit_text(t("bot_sc_error", lang).format(detail=detail))
        return
    except Exception as e:
        await status_msg.edit_text(t("bot_sc_error", lang).format(detail=str(e)))
        return

    data = await state.get_data()
    user_id = str(message.from_user.id)
    await api_client.save_session(user_id, data["yandex_token"], token)

    # Persist lang preference to DB
    try:
        from core.db import save_user_lang
        await save_user_lang(user_id, lang)
    except Exception:
        pass

    await status_msg.edit_text(t("bot_sc_ok", lang))
    await _show_confirmation(message, state)


# ---------------------------------------------------------------------------
# Confirmation screens
# ---------------------------------------------------------------------------

async def _show_confirmation(message: Message, state: FSMContext) -> None:
    """Yandex Music → SoundCloud confirmation."""
    lang = await _get_lang(state)
    loading = await message.answer(t("bot_loading_account", lang))

    data = await state.get_data()
    ym_token = data["yandex_token"]

    track_count = playlist_count = artist_count = "?"
    try:
        from core.yandex.client import YandexMusicClient
        from config import settings
        ym_client = await YandexMusicClient(ym_token, proxy_url=settings.ym_proxy_url or None).init()
        track_count = len(await ym_client.get_liked_tracks())
        playlist_count = len(await ym_client.get_playlists())
        artist_count = len(await ym_client.get_liked_artists())
        await state.update_data(
            track_count=track_count,
            playlist_count=playlist_count,
            artist_count=artist_count,
        )
    except Exception:
        pass

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("bot_btn_tracks_only", lang), callback_data="select_mode:tracks")],
        [InlineKeyboardButton(text=t("bot_btn_full", lang), callback_data="select_mode:full")],
        [InlineKeyboardButton(text=t("bot_btn_cancel", lang), callback_data="cancel_migration")],
    ])

    from config import settings as _cfg
    eta = format_eta(track_count, "soundcloud", lang, _cfg.sc_rate_limit_sleep) \
        if isinstance(track_count, int) else ""

    await loading.edit_text(
        t("bot_confirm", lang).format(
            tracks=track_count,
            playlists=playlist_count,
            artists=artist_count,
            eta=eta,
        ),
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.set_state(AuthFlow.confirming)


async def _show_confirmation_spotify(message: Message, state: FSMContext) -> None:
    """Spotify → SoundCloud confirmation."""
    lang = await _get_lang(state)
    loading = await message.answer(t("bot_loading_account", lang))

    data = await state.get_data()
    spotify_token = data["spotify_token"]

    track_count = "?"
    try:
        from core.spotify.client import SpotifyClient
        sp_client = SpotifyClient(spotify_token)
        tracks = await sp_client.get_liked_tracks()
        track_count = len(tracks)
        await state.update_data(track_count=track_count)
    except Exception:
        pass

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("bot_btn_tracks_only", lang), callback_data="select_mode:tracks")],
        [InlineKeyboardButton(text=t("bot_btn_cancel", lang), callback_data="cancel_migration")],
    ])

    from config import settings as _cfg
    eta = format_eta(track_count, "soundcloud", lang, _cfg.sc_rate_limit_sleep) \
        if isinstance(track_count, int) else ""

    await loading.edit_text(
        t("bot_confirm_spotify", lang).format(tracks=track_count, eta=eta),
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.set_state(AuthFlow.confirming)
