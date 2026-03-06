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

router = Router()

_POLL_INTERVAL = 15  # секунд между опросами статуса
_NOT_FOUND_PREVIEW = 30  # треков в превью-списке

# Кнопка для отмены во время миграции
_KB_CANCEL = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="Отключиться от переноса", callback_data="migration:detach"),
]])


def _kb_result(migration_id: int, not_found: int) -> InlineKeyboardMarkup:
    """Клавиатура финального сообщения."""
    web_url = settings.api_base_url.rstrip("/")
    rows = []
    if not_found > 0:
        rows.append([InlineKeyboardButton(
            text=f"Ненайденные треки ({not_found})",
            callback_data=f"migration:not_found:{migration_id}",
        )])
    rows.append([InlineKeyboardButton(
        text="Открыть в браузере",
        url=f"{web_url}/migrate/{migration_id}/tracks",
    )])
    rows.append([InlineKeyboardButton(
        text="Новый перенос",
        callback_data="migration:new",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Старт миграции
# ---------------------------------------------------------------------------

@router.callback_query(AuthFlow.confirming, F.data.startswith("start_migration"))
async def on_start_migration(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    mode = callback.data.split(":")[-1]  # "tracks" или "full"

    data = await state.get_data()
    ym_token = data["yandex_token"]
    sc_token = data["soundcloud_token"]
    user_id = str(callback.from_user.id)

    mode_label = "треки + плейлисты + артисты" if mode == "full" else "только треки"
    progress_msg = await callback.message.answer(
        f"Перенос запущен ({mode_label})...\n"
        "Загружаю треки из Яндекс Музыки, подожди немного.",
        reply_markup=_KB_CANCEL,
    )

    await state.set_state(MigrationFlow.in_progress)
    await state.update_data(progress_msg_id=progress_msg.message_id)

    try:
        migration_id = await api_client.start_migration(user_id, ym_token, sc_token, mode)
    except Exception as e:
        logger.exception(f"Не удалось запустить миграцию: {e}")
        await progress_msg.edit_text(
            f"Не удалось запустить перенос:\n<code>{e}</code>\n\nПопробуй /migrate снова.",
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
    await state.clear()
    await callback.message.edit_text("Отменено. Напиши /migrate чтобы начать заново.")


# ---------------------------------------------------------------------------
# Управление во время миграции
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "migration:detach")
async def on_detach(callback: CallbackQuery, state: FSMContext) -> None:
    """Пользователь отключается от отслеживания — задача на сервере продолжится."""
    await callback.answer()
    current = await state.get_state()
    if current != MigrationFlow.in_progress:
        await callback.answer("Активного переноса нет.", show_alert=True)
        return
    await state.clear()
    try:
        await callback.message.edit_text(
            "Отключились от переноса. Задача продолжит работу на сервере.\n"
            "Используй /status или /history в браузере для проверки.",
            reply_markup=None,
        )
    except TelegramBadRequest:
        pass


@router.message(MigrationFlow.in_progress)
async def migration_in_progress(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    msg_id = data.get("progress_msg_id")
    await message.answer(
        "Перенос уже идёт. Используй /status для проверки прогресса.\n"
        f"Сообщение с прогрессом: #{msg_id}"
    )


# ---------------------------------------------------------------------------
# Callbacks финального сообщения
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("migration:not_found:"))
async def on_show_not_found(callback: CallbackQuery) -> None:
    await callback.answer()
    migration_id = int(callback.data.split(":")[-1])

    try:
        tracks = await api_client.get_not_found_tracks(migration_id)
    except Exception as e:
        await callback.answer(f"Не удалось загрузить список: {e}", show_alert=True)
        return

    if not tracks:
        await callback.answer("Ненайденных треков нет.", show_alert=True)
        return

    preview = tracks[:_NOT_FOUND_PREVIEW]
    text = f"<b>Ненайденные треки ({len(tracks)}):</b>\n\n"
    text += "\n".join(f"• {t}" for t in preview)
    if len(tracks) > _NOT_FOUND_PREVIEW:
        remaining = len(tracks) - _NOT_FOUND_PREVIEW
        web_url = settings.api_base_url.rstrip("/")
        text += (
            f"\n\n<i>...и ещё {remaining} треков.</i>\n"
            f'Полный список: <a href="{web_url}/migrate/{migration_id}/tracks?status=not_found">в браузере</a>'
        )

    await callback.message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(F.data == "migration:new")
async def on_new_migration(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    from bot.handlers.auth import start_auth
    await start_auth(callback.message, state)


# ---------------------------------------------------------------------------
# Цикл опроса прогресса
# ---------------------------------------------------------------------------

async def _poll_migration(
    bot,
    chat_id: int,
    progress_msg_id: int,
    migration_id: int,
    state: FSMContext,
) -> None:
    """Опрашивает API каждые N секунд, обновляет сообщение с прогрессом."""
    last_text = ""

    while True:
        await asyncio.sleep(_POLL_INTERVAL)

        # Если пользователь отключился — останавливаем слежение
        if await state.get_state() != MigrationFlow.in_progress:
            return

        try:
            data = await api_client.get_migration_status(migration_id)
        except Exception as e:
            logger.warning(f"Ошибка опроса миграции #{migration_id}: {e}")
            continue

        migration = data.get("migration", {})
        tracks = data.get("tracks", {})
        mig_status = migration.get("status", "running")

        total = sum(tracks.values()) if tracks else 0
        liked = tracks.get("liked", 0)
        not_found = tracks.get("not_found", 0)
        errors = tracks.get("error", 0)
        done = liked + not_found + errors

        if mig_status in ("done", "failed", "cancelled"):
            text = _build_final_text(migration_id, tracks, data.get("artists", {}))
            kb = _kb_result(migration_id, not_found)
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            except TelegramBadRequest:
                await bot.send_message(
                    chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=kb
                )
            await state.clear()
            return

        # Промежуточный прогресс
        if total:
            percent = int(done / total * 100)
            bar = _progress_bar(percent)
            text = (
                f"Идёт перенос...\n\n"
                f"{bar} {percent}%\n"
                f"{done} / {total} треков\n\n"
                f"Перенесено: {liked} | Не найдено: {not_found} | Ошибок: {errors}"
            )
        else:
            text = "Идёт перенос... Загружаю треки."

        if text != last_text:
            last_text = text
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg_id,
                    text=text,
                    reply_markup=_KB_CANCEL,
                )
            except TelegramBadRequest:
                pass


def _build_final_text(migration_id: int, tracks: dict, artists: dict) -> str:
    liked = tracks.get("liked", 0)
    not_found = tracks.get("not_found", 0)
    errors = tracks.get("error", 0)
    total = sum(tracks.values())

    text = (
        "Перенос завершён!\n\n"
        "<b>Треки:</b>\n"
        f"  Перенесено:  <b>{liked}</b>\n"
        f"  Не найдено:  <b>{not_found}</b>\n"
        f"  Ошибок:      <b>{errors}</b>\n"
        f"  Всего:       <b>{total}</b>\n"
    )
    if artists:
        followed = artists.get("followed", 0)
        art_not_found = artists.get("not_found", 0)
        text += (
            "\n<b>Артисты:</b>\n"
            f"  Подписок:   <b>{followed}</b>\n"
            f"  Не найдено: <b>{art_not_found}</b>\n"
        )
    return text


def _progress_bar(percent: int, length: int = 20) -> str:
    filled = int(length * percent / 100)
    return "█" * filled + "░" * (length - filled)
