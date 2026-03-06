"""ARQ WorkerSettings — entry point for the migration worker process."""
from arq.connections import RedisSettings
from arq.cron import cron

from config import settings
from worker.tasks import run_migration_job, run_file_migration_job, check_sc_tokens_job


class WorkerSettings:
    functions = [run_migration_job, run_file_migration_job, check_sc_tokens_job]
    cron_jobs = [
        cron(check_sc_tokens_job, hour=9, minute=0),  # ежедневно в 09:00 UTC
    ]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 6 * 3600   # 6 hours
    keep_result = 3600
