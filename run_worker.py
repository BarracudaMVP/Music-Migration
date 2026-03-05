"""Entry point for the ARQ migration worker."""
from arq import run_worker

from worker.main import WorkerSettings

if __name__ == "__main__":
    run_worker(WorkerSettings)
