"""
Loguru setup. Import once at the entry point of each service.
Produces:
  - Colored human-readable output to stderr (local dev)
  - JSON output to stdout (Docker → Promtail → Loki)
"""
import sys
from loguru import logger
from config import settings


def setup_logger(service: str = "app") -> None:
    """
    Configure loguru sinks.

    Args:
        service: Service name tag included in every log record
                 (e.g. "api", "worker", "bot").
    """
    logger.remove()

    # --- Human-readable stderr (local dev / docker logs) ---
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            f"<magenta>{service}</magenta> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — {{message}}"
        ),
        colorize=True,
    )

    # --- JSON stdout (Promtail scrapes Docker stdout) ---
    logger.add(
        sys.stdout,
        level=settings.log_level,
        serialize=True,          # outputs newline-delimited JSON
        colorize=False,
        filter=lambda record: _inject_service(record, service),
    )


def _inject_service(record: dict, service: str) -> bool:
    """Inject `service` into every log record's extra dict."""
    record["extra"].setdefault("service", service)
    return True
