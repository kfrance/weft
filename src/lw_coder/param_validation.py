"""Shared parameter validation for CLI commands.

This module provides validation functions for tool/model parameter compatibility,
preventing duplicate validation logic across commands.
"""

from __future__ import annotations

from .executors import ExecutorRegistry
from .logging_config import get_logger

logger = get_logger(__name__)


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

    # Validate model if specified
    valid_models = {"opus", "sonnet", "haiku"}
    if model is not None and model not in valid_models:
        raise ParameterValidationError(
            f"Unknown model '{model}'. Available models: {', '.join(sorted(valid_models))}"
        )

    # Log validation result
    if model:
        logger.debug("Validated parameters: tool=%s, model=%s", tool, model)
    else:
        logger.debug("Validated parameters: tool=%s (no model specified)", tool)


def get_effective_model(tool: str, model: str | None) -> str:
    """Get the effective model to use based on tool and explicit model parameter.

    Args:
        tool: Name of the coding tool.
        model: Optional explicit model parameter.

    Returns:
        The effective model to use. For claude-code, defaults to "sonnet" if not specified.
        For other tools, returns the model as-is (which may be None).
    """
    if tool == "claude-code" and model is None:
        return "sonnet"
    return model