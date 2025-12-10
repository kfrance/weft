"""Configuration module for loading user settings from ~/.lw_coder/config.toml.

This module provides centralized configuration loading for lw_coder, handling:
- Model defaults for commands (plan, code, finalize)
- Hooks configuration
- Graceful error handling for missing or corrupted config files

Model Selection Precedence Chain:
1. CLI `--model` flag (highest priority) - user explicitly specifies model
2. config.toml `[defaults]` section - user's persistent preference
3. Hardcoded defaults (lowest priority) - fallback when nothing configured

Example config.toml:
    [defaults]
    plan_model = "opus"
    code_model = "sonnet"
    finalize_model = "haiku"

    [hooks.plan_file_created]
    command = "code-oss ${worktree_path}"
    enabled = true
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .logging_config import get_logger

# Try to import tomllib (Python 3.11+) or tomli (fallback)
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]


logger = get_logger(__name__)

# Configuration file path
CONFIG_PATH = Path.home() / ".lw_coder" / "config.toml"

# Valid model names
VALID_MODELS = {"sonnet", "opus", "haiku"}


def load_config() -> dict[str, Any]:
    """Load all configuration sections from ~/.lw_coder/config.toml.

    Returns:
        Dictionary containing all configuration sections, or empty dict if:
        - Config file does not exist (expected case, no error)
        - Config file cannot be read (I/O error, logged as warning)
        - Config file has invalid TOML syntax (logged as error with guidance)

    Note:
        This function never raises exceptions. It fails gracefully and returns
        an empty dict to allow commands to continue with hardcoded defaults.
    """
    if not CONFIG_PATH.exists():
        logger.debug("No config file at %s, using defaults", CONFIG_PATH)
        return {}

    try:
        content = CONFIG_PATH.read_bytes()
    except OSError as exc:
        logger.warning("Failed to read config file at %s: %s", CONFIG_PATH, exc)
        return {}

    try:
        config = tomllib.loads(content.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        # Extract line number if available
        lineno = getattr(exc, "lineno", "?")
        logger.error(
            "Failed to parse config file: %s\n"
            "TOML syntax error at line %s: %s\n"
            "Fix the syntax error or remove the file to use defaults.",
            CONFIG_PATH,
            lineno,
            exc,
        )
        return {}

    logger.debug("Loaded config from %s", CONFIG_PATH)
    return config


def get_model_defaults() -> dict[str, str]:
    """Load model defaults from the [defaults] section of config.toml.

    Returns:
        Dictionary mapping model keys to model names, e.g.:
        {"plan_model": "opus", "code_model": "sonnet", "finalize_model": "haiku"}

        Returns empty dict if:
        - Config file does not exist
        - Config file has errors
        - [defaults] section is missing

    Note:
        Invalid model values in config are logged as warnings but still returned.
        Callers should validate and fall back to hardcoded defaults.
    """
    config = load_config()
    defaults = config.get("defaults", {})

    if not isinstance(defaults, dict):
        logger.warning(
            "[defaults] section in config.toml should be a table, got %s",
            type(defaults).__name__,
)
        return {}

    # Validate model values and log warnings for invalid ones
    model_keys = ["plan_model", "code_model", "finalize_model"]
    result = {}

    for key in model_keys:
        if key in defaults:
            value = defaults[key]
            if not isinstance(value, str):
                logger.warning(
                    "Config %s should be a string, got %s, ignoring",
                    key,
                    type(value).__name__,
                )
                continue

            if value not in VALID_MODELS:
                logger.warning(
                    "Config %s has invalid value '%s'. "
                    "Valid models: %s. Using default instead.",
                    key,
                    value,
                    ", ".join(sorted(VALID_MODELS)),
                )
                # Don't include invalid values in result
                continue

            result[key] = value

    return result
