"""ARQ WorkerSettings — entry point for the migration worker process."""
from arq.connections import RedisSettings

from config import settings
from core.services.registry import ServiceRegistry
from core.services.yandex.adapter import YandexMusicAdapter
from core.services.soundcloud.adapter import SoundCloudAdapter
from core.services.spotify.adapter import SpotifyAdapter
from core.services.file.adapter import FileAdapter
from worker.tasks import (
    run_migration_job,
    run_file_migration_job,
    run_spotify_migration_job,
    run_yandex_migration_job,
    run_spotify_write_job,
    run_export_job,
)


async def startup(ctx: dict) -> None:
    for adapter in [YandexMusicAdapter(), SoundCloudAdapter(), FileAdapter(), SpotifyAdapter()]:
        ServiceRegistry.register(adapter)


class WorkerSettings:
    on_startup = startup
    functions = [
        run_migration_job,
        run_file_migration_job,
        run_spotify_migration_job,
        run_yandex_migration_job,
        run_spotify_write_job,
        run_export_job,
    ]
    cron_jobs = []
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 2 * 3600   # 2 hours — after this ARQ cancels the job coroutine
    keep_result = 3600
