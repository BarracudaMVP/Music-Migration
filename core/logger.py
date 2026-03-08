"""
Loguru setup. Import once at the entry point of each service.

LOG_FORMAT env var controls output mode:
  pretty  — colored human-readable output to stderr (default, local dev)
  json    — newline-delimited JSON to stdout (Docker / Promtail)
"""
import sys
from loguru import logger
from config import settings


def setup_logger(service: str = "app") -> None:
    logger.remove()

    if settings.log_format == "json":
        # Docker: single JSON sink → stdout (Promtail scrapes stdout)
        logger.add(
            sys.stdout,
            level=settings.log_level,
            serialize=True,
            colorize=False,
            filter=lambda record: _inject_service(record, service),
        )
    else:
        # Local dev: single colored sink → stderr
        logger.add(
            sys.stderr,
            level=settings.log_level,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                f"<magenta>{service}</magenta> | "
                "<cyan>{name}</cyan>:<cyan>{line}</cyan> — {message}"
            ),
            colorize=True,
            filter=lambda record: _inject_service(record, service),
        )


def _inject_service(record: dict, service: str) -> bool:
    """Inject `service` into every log record's extra dict."""
    record["extra"].setdefault("service", service)
    return True
