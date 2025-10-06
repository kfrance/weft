"""Logging configuration for lw_coder."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


_LOG_DIR = Path.home() / ".lw_coder" / "logs"
_LOG_FILE = _LOG_DIR / "lw_coder.log"
_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_logger_configured = False


def configure_logging(debug: bool = False) -> None:
    """Configure logging with console and rotating file handlers.

    Args:
        debug: If True, set logging level to DEBUG; otherwise INFO.
    """
    global _logger_configured
    if _logger_configured:
        return

    # Ensure log directory exists
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Determine log level
    level = logging.DEBUG if debug else logging.INFO

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Check for existing handlers to prevent duplication
    has_console_handler = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, TimedRotatingFileHandler)
        for h in root_logger.handlers
    )
    has_file_handler = any(
        isinstance(h, TimedRotatingFileHandler) and str(h.baseFilename) == str(_LOG_FILE)
        for h in root_logger.handlers
    )

    # Console handler
    if not has_console_handler:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # Rotating file handler (daily rotation, 30 days retention)
    if not has_file_handler:
        file_handler = TimedRotatingFileHandler(
            _LOG_FILE,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    _logger_configured = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)
