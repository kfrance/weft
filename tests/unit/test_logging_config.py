"""Tests for logging configuration.

This module tests the logging infrastructure including:
- Idempotency of logging configuration (prevents duplicate handlers)
"""

from __future__ import annotations

import logging

from lw_coder.logging_config import configure_logging


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
