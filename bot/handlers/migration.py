import asyncio

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from bot.states import AuthFlow, MigrationFlow

router = Router()

# migration_id → asyncio.Task (для /status и отмены)
_active_tasks: dict[int, asyncio.Task] = {}


@router.callback_query(AuthFlow.confirming, F.data.startswith("start_migration"))
async def on_start_migration(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    mode = callback.data.split(":")[-1]  # "tracks" или "full"
    do_playlists = mode == "full"
    do_artists = mode == "full"

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

    task = asyncio.create_task(
        _run_migration_task(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            progress_msg_id=progress_msg.message_id,
            ym_token=ym_token,
            sc_token=sc_token,
            user_id=user_id,
            state=state,
            do_playlists=do_playlists,
            do_artists=do_artists,
        )
    )
    _active_tasks[callback.from_user.id] = task


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


async def _run_migration_task(
    bot,
    chat_id: int,
    progress_msg_id: int,
    ym_token: str,
    sc_token: str,
    user_id: str,
    state: FSMContext,
    do_playlists: bool = False,
    do_artists: bool = False,
) -> None:
    from migration.tracks import run_migration

    last_edit_text = ""

    async def progress_callback(current: int, total: int, track: str) -> None:
        nonlocal last_edit_text
        percent = int(current / total * 100)
        bar = _progress_bar(percent)
        text = (
            f"Идёт миграция...\n\n"
            f"{bar} {percent}%\n"
            f"{current} / {total} треков\n\n"
            f"Последний: {track[:60]}"
        )
        if text == last_edit_text:
            return
        last_edit_text = text
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg_id,
                text=text,
            )
        except TelegramBadRequest:
            pass  # сообщение не изменилось — ок

    async def on_migration_created(migration_id: int) -> None:
        await state.update_data(migration_id=migration_id)

    try:
        migration_id, stats = await run_migration(
            yandex_token=ym_token,
            soundcloud_token=sc_token,
            user_id=user_id,
            migrate_playlists=do_playlists,
            migrate_artists=do_artists,
            progress_callback=progress_callback,
            on_migration_created=on_migration_created,
        )
        await _send_report(bot, chat_id, progress_msg_id, migration_id, stats)
    except Exception as e:
        logger.exception(f"Ошибка миграции для user {user_id}: {e}")
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg_id,
            text=f"Произошла ошибка во время миграции:\n<code>{e}</code>\n\nПопробуй /migrate снова.",
            parse_mode="HTML",
        )
    finally:
        await state.clear()
        _active_tasks.pop(int(user_id), None)


async def _send_report(bot, chat_id: int, progress_msg_id: int, migration_id: int, stats) -> None:
    t = stats.tracks
    not_found_total = t.not_found + t.uncertain
    text = (
        "Миграция завершена!\n\n"
        "<b>Треки:</b>\n"
        f"  Перенесено:    <b>{t.liked}</b>\n"
        f"  Не найдено:    <b>{t.not_found}</b>\n"
        f"  Сомнительных: <b>{t.uncertain}</b>\n"
        f"  Ошибок:        <b>{t.errors}</b>\n"
        f"  Всего:         <b>{t.total}</b>\n"
    )
    if stats.playlists:
        p = stats.playlists
        text += (
            "\n<b>Плейлисты:</b>\n"
            f"  Создано:  <b>{p.created}</b>\n"
            f"  Ошибок:   <b>{p.errors}</b>\n"
        )
    if stats.artists:
        a = stats.artists
        text += (
            "\n<b>Артисты:</b>\n"
            f"  Подписок: <b>{a.followed}</b>\n"
            f"  Не найдено: <b>{a.not_found}</b>\n"
        )
    if not_found_total > 0:
        text += f"\nСписок не найденных: <code>not_found_{migration_id}.txt</code> на сервере."

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=progress_msg_id,
            text=text,
            parse_mode="HTML",
        )
    except TelegramBadRequest:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")


def _progress_bar(percent: int, length: int = 20) -> str:
    filled = int(length * percent / 100)
    return "█" * filled + "░" * (length - filled)
