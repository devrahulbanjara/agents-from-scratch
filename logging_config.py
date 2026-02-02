import sys
from pathlib import Path

from loguru import logger as _logger

_logger.remove()

logger = _logger


def setup_logging(log_level: str = "INFO", log_file: Path | None = None):
    logger.add(
        sink=sys.stderr,
        level=log_level.upper(),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    )

    if log_file:
        logger.add(
            sink=log_file,
            level=log_level.upper(),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
            rotation="10 MB",
        )
