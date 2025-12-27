"""Headless mode detection for non-interactive execution."""

import os


def is_headless() -> bool:
    """Check if running in headless mode via WEFT_HEADLESS env var."""
    return os.environ.get("WEFT_HEADLESS", "").lower() in ("1", "true", "yes")
