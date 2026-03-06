"""ARQ WorkerSettings — entry point for the migration worker process."""
from arq.connections import RedisSettings

from config import settings
from worker.tasks import run_migration_job, run_file_migration_job


class WorkerSettings:
    functions = [run_migration_job, run_file_migration_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 6 * 3600   # 6 hours
    keep_result = 3600
