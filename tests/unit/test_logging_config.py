"""Tests for logging configuration.

This module tests the logging infrastructure including:
- Log directory creation
- Console and file handler configuration
- Log level control via debug flag
- Idempotency of logging configuration
"""

from __future__ import annotations

import logging
from pathlib import Path

from lw_coder.logging_config import configure_logging, get_logger


def test_configure_logging_creates_log_directory(tmp_path, monkeypatch):
    """Test that configure_logging creates the log directory."""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("lw_coder.logging_config._LOG_DIR", log_dir)
    monkeypatch.setattr("lw_coder.logging_config._LOG_FILE", log_dir / "lw_coder.log")

    # Reset the configured flag
    import lw_coder.logging_config
    lw_coder.logging_config._logger_configured = False

    configure_logging()

    assert log_dir.exists()
    assert log_dir.is_dir()


def test_configure_logging_sets_info_level_by_default(tmp_path, monkeypatch):
    """Test that configure_logging sets INFO level by default."""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("lw_coder.logging_config._LOG_DIR", log_dir)
    monkeypatch.setattr("lw_coder.logging_config._LOG_FILE", log_dir / "lw_coder.log")

    # Reset the configured flag and clear handlers
    import lw_coder.logging_config
    lw_coder.logging_config._logger_configured = False
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    configure_logging(debug=False)

    assert root_logger.level == logging.INFO


def test_configure_logging_sets_debug_level_when_requested(tmp_path, monkeypatch):
    """Test that configure_logging sets DEBUG level when debug=True."""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("lw_coder.logging_config._LOG_DIR", log_dir)
    monkeypatch.setattr("lw_coder.logging_config._LOG_FILE", log_dir / "lw_coder.log")

    # Reset the configured flag and clear handlers
    import lw_coder.logging_config
    lw_coder.logging_config._logger_configured = False
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    configure_logging(debug=True)

    assert root_logger.level == logging.DEBUG


def test_configure_logging_idempotent(tmp_path, monkeypatch):
    """Test that configure_logging is idempotent and doesn't add duplicate handlers."""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("lw_coder.logging_config._LOG_DIR", log_dir)
    monkeypatch.setattr("lw_coder.logging_config._LOG_FILE", log_dir / "lw_coder.log")

    # Reset the configured flag and clear handlers
    import lw_coder.logging_config
    lw_coder.logging_config._logger_configured = False
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    configure_logging()
    initial_handler_count = len(root_logger.handlers)

    # Call again
    configure_logging()
    final_handler_count = len(root_logger.handlers)

    assert initial_handler_count == final_handler_count


def test_get_logger_returns_logger():
    """Test that get_logger returns a logger instance."""
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_logging_handlers_configured(tmp_path, monkeypatch):
    """Test that both console and file handlers are configured."""
    log_dir = tmp_path / "logs"
    monkeypatch.setattr("lw_coder.logging_config._LOG_DIR", log_dir)
    monkeypatch.setattr("lw_coder.logging_config._LOG_FILE", log_dir / "lw_coder.log")

    # Reset the configured flag and clear handlers
    import lw_coder.logging_config
    lw_coder.logging_config._logger_configured = False
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    configure_logging()

    # Should have 2 handlers: console and file
    assert len(root_logger.handlers) == 2

    handler_types = {type(h).__name__ for h in root_logger.handlers}
    assert "StreamHandler" in handler_types
    assert "TimedRotatingFileHandler" in handler_types
