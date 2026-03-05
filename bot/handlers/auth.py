import re

import httpx
from loguru import logger
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from bot.states import AuthFlow
from bot.api_client import api_client

router = Router()

_SC_TOKEN_RE = re.compile(r"^\d-[A-Za-z0-9\-]+$")

_SC_INSTRUCTIONS = (
    "<b>Как получить токен SoundCloud:</b>\n\n"
    "1. Открой <a href='https://soundcloud.com'>soundcloud.com</a> в браузере\n"
    "2. Войди в аккаунт\n"
    "3. Нажми <b>F12</b> → вкладка <b>Application</b>\n"
    "4. Слева: <b>Cookies → https://soundcloud.com</b>\n"
    "5. Найди <code>oauth_token</code>, скопируй значение\n"
    "   (начинается с <code>2-</code> или <code>3-</code>)\n\n"
    "Сообщение с токеном сразу удалится из чата."
)


# ---------------------------------------------------------------------------
# Точка входа — проверяем сохранённую сессию
# ---------------------------------------------------------------------------

async def start_auth(message: Message, state: FSMContext) -> None:
    """
    Вызывается из start.py при /migrate.
    Если есть сохранённая сессия — тихо проверяем токены и переходим к миграции.
    """
    user_id = str(message.from_user.id)
    session = await api_client.get_session(user_id)

    if not session:
        await _ask_yandex_token(message, state)
        return

    # Проверяем YM токен
    try:
        from core.yandex.client import YandexMusicClient
        await YandexMusicClient(session["yandex_token"]).init()
        logger.info(f"Сохранённый YM токен актуален для user_id={user_id}")
    except Exception:
        await api_client.delete_session(user_id)
        logger.warning(f"YM токен истёк для user_id={user_id}, запрашиваю заново")
        await message.answer("Токен Яндекс Музыки истёк. Нужно авторизоваться заново.")
        await _ask_yandex_token(message, state)
        return

    # Проверяем SC токен
    try:
        from core.soundcloud.client import SoundCloudClient
        sc = await SoundCloudClient(session["soundcloud_token"]).init()
        await sc.close()
        logger.info(f"Сохранённый SC токен актуален для user_id={user_id}")
    except Exception:
        await api_client.delete_session(user_id)
        logger.warning(f"SC токен истёк для user_id={user_id}, запрашиваю заново")
        await message.answer("Токен SoundCloud истёк. Нужно ввести новый.")
        await _ask_soundcloud_token(message, state, ym_token=session["yandex_token"])
        return

    await state.update_data(
        yandex_token=session["yandex_token"],
        soundcloud_token=session["soundcloud_token"],
    )
    await _show_confirmation(message, state)


@router.callback_query(F.data == "auth:new_tokens")
async def on_new_tokens(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await _ask_yandex_token(callback.message, state)


# ---------------------------------------------------------------------------
# Шаг 1 — Яндекс Музыка (OAuth)
# ---------------------------------------------------------------------------

async def _ask_yandex_token(message: Message, state: FSMContext) -> None:
    from bot.oauth.yandex import get_auth_url
    auth_url = get_auth_url()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Войти через Яндекс", url=auth_url)
    ]])
    await message.answer(
        "<b>Шаг 1 из 2 — Яндекс Музыка</b>\n\n"
        "1. Нажми кнопку ниже и войди в свой аккаунт Яндекса\n"
        "2. После входа Яндекс покажет короткий код — скопируй его\n"
        "3. Отправь код сюда",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.set_state(AuthFlow.waiting_yandex_token)


@router.message(AuthFlow.waiting_yandex_token)
async def receive_yandex_token(message: Message, state: FSMContext) -> None:
    code = message.text.strip() if message.text else ""

    try:
        await message.delete()
    except Exception:
        pass

    if not code:
        await message.answer("Код не должен быть пустым. Попробуй ещё раз:")
        return

    status_msg = await message.answer("Проверяю...")

    try:
        result = await api_client.exchange_yandex_code(code)
        token = result["token"]
        await state.update_data(yandex_token=token)
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", str(e))
        await status_msg.edit_text(
            f"Ошибка: {detail}\n\nПопробуй войти через кнопку снова и скопировать новый код:"
        )
        return
    except Exception as e:
        await status_msg.edit_text(
            f"Ошибка: {e}\n\nПопробуй войти через кнопку снова и скопировать новый код:"
        )
        return

    await status_msg.edit_text("Яндекс Музыка подключена!")
    await _ask_soundcloud_token(message, state)


# ---------------------------------------------------------------------------
# Шаг 2 — SoundCloud
# ---------------------------------------------------------------------------

async def _ask_soundcloud_token(message: Message, state: FSMContext, ym_token: str = None) -> None:
    if ym_token:
        await state.update_data(yandex_token=ym_token)
    await message.answer(
        f"<b>Шаг 2 из 2 — SoundCloud</b>\n\n{_SC_INSTRUCTIONS}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await state.set_state(AuthFlow.waiting_soundcloud_token)


@router.message(AuthFlow.waiting_soundcloud_token)
async def receive_soundcloud_token(message: Message, state: FSMContext) -> None:
    token = message.text.strip() if message.text else ""

    try:
        await message.delete()
    except Exception:
        pass

    if not token:
        await message.answer("Токен не должен быть пустым. Попробуй ещё раз:")
        return

    if not _SC_TOKEN_RE.match(token):
        await message.answer(
            "Токен выглядит неверно — должен начинаться с <code>2-</code> или <code>3-</code>.\n"
            "Попробуй скопировать снова:",
            parse_mode="HTML",
        )
        return

    status_msg = await message.answer("Проверяю токен SoundCloud...")

    try:
        await api_client.validate_soundcloud_token(token)
        await state.update_data(soundcloud_token=token)
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", str(e))
        await status_msg.edit_text(
            f"Не удалось подключиться к SoundCloud: {detail}\n\nПопробуй ещё раз:"
        )
        return
    except Exception as e:
        await status_msg.edit_text(
            f"Не удалось подключиться к SoundCloud: {e}\n\nПопробуй ещё раз:"
        )
        return

    # Сохраняем сессию
    data = await state.get_data()
    user_id = str(message.from_user.id)
    await api_client.save_session(user_id, data["yandex_token"], token)

    await status_msg.edit_text("SoundCloud подключён! Сессия сохранена.")
    await _show_confirmation(message, state)


# ---------------------------------------------------------------------------
# Экран подтверждения
# ---------------------------------------------------------------------------

async def _show_confirmation(message: Message, state: FSMContext) -> None:
    loading = await message.answer("Получаю информацию об аккаунте...")

    data = await state.get_data()
    ym_token = data["yandex_token"]

    track_count = playlist_count = artist_count = "?"
    try:
        from core.yandex.client import YandexMusicClient
        ym_client = await YandexMusicClient(ym_token).init()
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
        [InlineKeyboardButton(text="Только треки", callback_data="start_migration:tracks")],
        [InlineKeyboardButton(text="Треки + плейлисты + артисты", callback_data="start_migration:full")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_migration")],
    ])

    await loading.edit_text(
        "<b>Всё готово! Что перенести?</b>\n\n"
        f"Лайкнутых треков:   <b>{track_count}</b>\n"
        f"Плейлистов:         <b>{playlist_count}</b>\n"
        f"Лайкнутых артистов: <b>{artist_count}</b>\n\n"
        "5000 треков ≈ 3–4 часа. Бот пришлёт уведомление когда закончит.",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.set_state(AuthFlow.confirming)
