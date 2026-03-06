"""Entry point for the ARQ migration worker."""
import asyncio

from arq import run_worker

from core.logger import setup_logger
from worker.main import WorkerSettings

if __name__ == "__main__":
    setup_logger("worker")
    # Python 3.10+ no longer creates an event loop implicitly — create one explicitly
    # so that ARQ's synchronous run_worker() can find it via get_event_loop().
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    run_worker(WorkerSettings)
