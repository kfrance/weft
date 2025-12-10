"""Shared parameter validation for CLI commands.

This module provides validation functions for tool/model parameter compatibility,
preventing duplicate validation logic across commands.

Model Selection Precedence Chain:
1. CLI `--model` flag (highest priority) - user explicitly specifies model
2. config.toml `[defaults]` section - user's persistent preference
3. Hardcoded defaults (lowest priority) - fallback when nothing configured

Hardcoded Defaults (for backwards compatibility):
- plan: sonnet
- code: sonnet
- finalize: haiku
"""

from __future__ import annotations

from .config import VALID_MODELS, get_model_defaults
from .executors import ExecutorRegistry
from .logging_config import get_logger

logger = get_logger(__name__)

# Hardcoded command defaults for backwards compatibility
# These are used when neither CLI flag nor config.toml provides a model
COMMAND_DEFAULTS = {
    "plan": "sonnet",
    "code": "sonnet",
    "finalize": "haiku",
}


class ParameterValidationError(Exception):
    """Raised when parameter validation fails."""


def validate_tool_model_compatibility(tool: str, model: str | None) -> None:
    """Validate tool and model parameter compatibility.

    Ensures that:
    - The tool is a valid executor name
    - If model is specified with 'droid' tool, raises an error
    - Model defaults to 'sonnet' for claude-code if not specified

    Args:
        tool: Name of the coding tool (e.g., "claude-code", "droid").
        model: Optional model variant (e.g., "sonnet", "opus", "haiku").

    Raises:
        ParameterValidationError: If parameters are incompatible or invalid.
    """
    # Validate tool is a registered executor
    available_tools = ExecutorRegistry.list_executors()
    if tool not in available_tools:
        raise ParameterValidationError(
            f"Unknown tool '{tool}'. Available tools: {', '.join(available_tools)}"
        )

    # Check for incompatible parameter combinations first
    # (before validating model value, since droid doesn't support ANY model)
    if tool == "droid" and model is not None:
        raise ParameterValidationError(
            "The --model parameter cannot be used with --tool droid. "
            "Droid does not support model selection."
        )

    # Validate model if specified (uses VALID_MODELS from config module)
    if model is not None and model not in VALID_MODELS:
        raise ParameterValidationError(
            f"Unknown model '{model}'. Available models: {', '.join(sorted(VALID_MODELS))}"
        )

    # Log validation result
    if model:
        logger.debug("Validated parameters: tool=%s, model=%s", tool, model)
    else:
        logger.debug("Validated parameters: tool=%s (no model specified)", tool)


def get_effective_model(model: str | None, command: str) -> str | None:
    """Get the effective model using 3-tier precedence chain.

    Precedence (highest to lowest):
    1. CLI `--model` flag - user explicitly specifies model
    2. config.toml `[defaults]` section - user's persistent preference
    3. Hardcoded defaults - fallback when nothing configured

    Args:
        model: Optional explicit model parameter from CLI flag.
        command: Name of the command ("plan", "code", "finalize").

    Returns:
        The effective model to use. Always returns a valid model string
        for known commands, never None.
    """
    # Priority 1: CLI flag takes precedence
    if model is not None:
        logger.debug("Using CLI model '%s' for %s command", model, command)
        return model

    # Priority 2: Check config.toml defaults
    config_defaults = get_model_defaults()
    config_key = f"{command}_model"

    if config_key in config_defaults:
        config_model = config_defaults[config_key]
        logger.debug(
            "Using config.toml model '%s' for %s command", config_model, command
        )
        return config_model

    # Priority 3: Fall back to hardcoded defaults
    if command in COMMAND_DEFAULTS:
        default_model = COMMAND_DEFAULTS[command]
        logger.debug(
            "Using hardcoded default model '%s' for %s command", default_model, command
        )
        return default_model

    # Unknown command: return None (caller should handle)
    logger.warning("Unknown command '%s' for model resolution", command)
    return None