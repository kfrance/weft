"""Utilities for checking Droid CLI authentication."""

from __future__ import annotations

import json
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


class DroidAuthError(Exception):
    """Raised when Droid authentication is not properly configured."""


def check_droid_auth() -> Path:
    """Check if Droid authentication is properly configured.

    Returns:
        Path to the auth.json file if authentication is valid.

    Raises:
        DroidAuthError: If authentication is not properly configured.
    """
    auth_file = Path.home() / ".factory" / "auth.json"

    if not auth_file.exists():
        raise DroidAuthError(
            "Droid authentication required. Please run 'droid' once to login via browser."
        )

    logger.debug("Checking Droid authentication file at %s", auth_file)

    try:
        with open(auth_file, "r", encoding="utf-8") as f:
            auth_data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise DroidAuthError(
            f"Failed to read Droid authentication file at {auth_file}: {exc}"
        ) from exc

    # Check for required keys
    required_keys = {"access_token", "refresh_token"}
    missing_keys = required_keys - set(auth_data.keys())

    if missing_keys:
        raise DroidAuthError(
            f"Droid authentication file is missing required keys: {', '.join(sorted(missing_keys))}. "
            "Please run 'droid' once to login via browser."
        )

    # Validate token values are non-empty strings
    for key in required_keys:
        value = auth_data[key]
        if not isinstance(value, str):
            raise DroidAuthError(
                f"Droid authentication key '{key}' must be a string. "
                "Please run 'droid' once to login via browser."
            )
        if not value.strip():
            raise DroidAuthError(
                f"Droid authentication key '{key}' cannot be empty. "
                "Please run 'droid' once to login via browser."
            )

    logger.debug("Droid authentication check passed")
    return auth_file
