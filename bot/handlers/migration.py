import asyncio

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from bot.states import AuthFlow, MigrationFlow
from bot.api_client import api_client

router = Router()

_POLL_INTERVAL = 15  # секунд между опросами статуса


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
        f"Миграция запущена ({mode_label})...\n"
        "Загружаю треки из Яндекс Музыки, подожди немного."
    )

    await state.set_state(MigrationFlow.in_progress)
    await state.update_data(progress_msg_id=progress_msg.message_id)

    try:
        migration_id = await api_client.start_migration(user_id, ym_token, sc_token, mode)
    except Exception as e:
        logger.exception(f"Не удалось запустить миграцию: {e}")
        await progress_msg.edit_text(
            f"Не удалось запустить миграцию:\n<code>{e}</code>\n\nПопробуй /migrate снова.",
            parse_mode="HTML",
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


@router.message(MigrationFlow.in_progress)
async def migration_in_progress(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    msg_id = data.get("progress_msg_id")
    await message.answer(
        "Миграция уже идёт. Используй /status для проверки прогресса.\n"
        f"Сообщение с прогрессом: #{msg_id}"
    )


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
        pending = tracks.get("pending", 0)
        not_found = tracks.get("not_found", 0)
        errors = tracks.get("error", 0)
        done = liked + not_found + errors

        if mig_status in ("done", "error"):
            # Финальный отчёт
            artists = data.get("artists", {})
            text = _build_final_text(migration_id, tracks, artists)
            try:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=progress_msg_id, text=text, parse_mode="HTML"
                )
            except TelegramBadRequest:
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            await state.clear()
            return

        # Промежуточный прогресс
        if total:
            percent = int(done / total * 100)
            bar = _progress_bar(percent)
            text = (
                f"Идёт миграция...\n\n"
                f"{bar} {percent}%\n"
                f"{done} / {total} треков\n\n"
                f"Перенесено: {liked} | Не найдено: {not_found} | Ошибок: {errors}"
            )
        else:
            text = "Идёт миграция... Загружаю треки."

        if text != last_text:
            last_text = text
            try:
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=progress_msg_id, text=text
                )
            except TelegramBadRequest:
                pass


def _build_final_text(migration_id: int, tracks: dict, artists: dict) -> str:
    liked = tracks.get("liked", 0)
    not_found = tracks.get("not_found", 0)
    errors = tracks.get("error", 0)
    total = sum(tracks.values())

    text = (
        "Миграция завершена!\n\n"
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
    if not_found > 0:
        text += f"\nСписок не найденных: <code>not_found_{migration_id}.txt</code> на сервере."
    return text


def _progress_bar(percent: int, length: int = 20) -> str:
    filled = int(length * percent / 100)
    return "█" * filled + "░" * (length - filled)
