"""
Настройка loguru. Импортировать один раз в точке входа.
"""
import sys
from loguru import logger
from config import settings


def setup_logger() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> — {message}",
        colorize=True,
    )
    logger.add(
        "migration.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )
