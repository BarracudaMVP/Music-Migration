"""
CLI для запуска миграции на сервере без Telegram бота.

Использование:
    python cli.py --ym-token=<token> --sc-token=<token>

Или через .env (YANDEX_TOKEN и SOUNDCLOUD_TOKEN):
    python cli.py
"""
import asyncio
import argparse

from core.logger import setup_logger
from config import settings


async def main(ym_token: str, sc_token: str) -> None:
    from migration.sc_tracks import run_migration

    async def progress(current: int, total: int, track: str) -> None:
        print(f"  [{current}/{total}] {track}", flush=True)

    print("Запускаю миграцию треков Яндекс Музыка → SoundCloud...")
    migration_id, stats = await run_migration(
        yandex_token=ym_token,
        soundcloud_token=sc_token,
        user_id="cli",
        progress_callback=progress,
    )
    print(f"\nМиграция #{migration_id} завершена.")
    print(f"  Перенесено:   {stats.liked}")
    print(f"  Не найдено:   {stats.not_found}")
    print(f"  Сомнительных: {stats.uncertain}")
    print(f"  Ошибок:       {stats.errors}")
    if stats.not_found + stats.uncertain > 0:
        print(f"  Список не найденных: not_found_{migration_id}.txt")


if __name__ == "__main__":
    setup_logger()

    parser = argparse.ArgumentParser(description="Migrate Yandex Music → SoundCloud")
    parser.add_argument("--ym-token", default=settings.yandex_token, help="Яндекс Музыка токен")
    parser.add_argument("--sc-token", default=settings.soundcloud_token, help="SoundCloud OAuth токен")
    args = parser.parse_args()

    if not args.ym_token:
        print("Ошибка: укажи --ym-token или задай YANDEX_TOKEN в .env")
        raise SystemExit(1)
    if not args.sc_token:
        print("Ошибка: укажи --sc-token или задай SOUNDCLOUD_TOKEN в .env")
        raise SystemExit(1)

    asyncio.run(main(args.ym_token, args.sc_token))
