"""Structured logging configuration."""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import structlog
from structlog.stdlib import add_log_level, filter_by_level

from .config import get_config

config = get_config()


def get_log_level() -> str:
    """Get log level from config or environment."""
    return os.getenv("LOG_LEVEL", config.app.log_level)


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
) -> None:
    """Configure structured logging."""

    log_level = log_level or get_log_level()

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    processors = [
        filter_by_level,
        add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ]

    if log_file:
        log_path = log_dir / log_file
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(getattr(logging, log_level.upper()))
        logging.root.addHandler(file_handler)

    structlog.configure(
        wrapper_class=structlog.stdlib.RealProxyLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        processors=processors,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


class LoggingMixin:
    """Mixin class for adding logging to components."""

    @property
    def logger(self):
        """Get logger for this class."""
        return structlog.get_logger(self.__class__.__name__)


def get_logger(name: str):
    """Get a logger with the given name."""
    return structlog.get_logger(name)


setup_logging()
