"""Environment variable configuration for the code command.

This module provides functionality to load environment variables from the
[code.env] section of .weft/config.toml. These variables are injected into
both setup commands and the Claude Code session.

Configuration Example:
    [code.env]
    DATABASE_URL = "postgres://localhost:5432/dev"
    DEBUG = "true"
    MY_CUSTOM_VAR = "value"

Key Behavior:
    - Values are literal strings only (no variable expansion)
    - Config values override existing environment variables
    - Empty [code.env] section is valid (no env vars injected)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .logging_config import get_logger
from .worktree.file_sync import load_repo_config, FileSyncError

logger = get_logger(__name__)

# Valid environment variable name pattern
# Must start with letter or underscore, followed by letters, digits, or underscores
_ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CodeEnvError(Exception):
    """Exception for [code.env] configuration errors."""


def _validate_env_key(key: str) -> None:
    """Validate that a key is a valid environment variable name.

    Args:
        key: The environment variable name to validate.

    Raises:
        CodeEnvError: If the key is not a valid environment variable name.
    """
    if not _ENV_VAR_NAME_PATTERN.match(key):
        raise CodeEnvError(
            f"[code.env] invalid key '{key}': "
            f"environment variable names must start with a letter or underscore "
            f"and contain only letters, digits, and underscores"
        )


def _validate_env_value(key: str, value: Any) -> None:
    """Validate that a value is a string.

    Args:
        key: The environment variable name (for error messages).
        value: The value to validate.

    Raises:
        CodeEnvError: If the value is not a string.
    """
    if not isinstance(value, str):
        raise CodeEnvError(
            f"[code.env] key '{key}': value must be a string, got {type(value).__name__}"
        )


def load_code_env(repo_root: Path) -> dict[str, str]:
    """Load environment variables from [code.env] section of config.toml.

    Parses the [code.env] section from .weft/config.toml and validates
    all keys and values.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Dictionary of environment variable name to value mappings.
        Returns empty dict if [code.env] section is missing.

    Raises:
        CodeEnvError: If configuration is invalid (bad key names or non-string values).
    """
    try:
        config = load_repo_config(repo_root)
    except FileSyncError as exc:
        raise CodeEnvError(f"Failed to load repository config: {exc}") from exc

    if not config:
        logger.debug("No repo config found, no code.env")
        return {}

    # Get the code section
    code_section = config.get("code")
    if code_section is None:
        logger.debug("No [code] section in config, no code.env")
        return {}

    if not isinstance(code_section, dict):
        raise CodeEnvError("[code] section must be a table")

    # Get the env section
    env_section = code_section.get("env")
    if env_section is None:
        logger.debug("No [code.env] section in config")
        return {}

    if not isinstance(env_section, dict):
        raise CodeEnvError(
            "[code.env] must be a table with key-value pairs, "
            "e.g., [code.env]\\nMY_VAR = \"value\""
        )

    # Validate and collect all environment variables
    env_vars: dict[str, str] = {}
    for key, value in env_section.items():
        _validate_env_key(key)
        _validate_env_value(key, value)
        env_vars[key] = value

    if env_vars:
        logger.debug("Loaded %d environment variable(s) from [code.env]", len(env_vars))

    return env_vars
