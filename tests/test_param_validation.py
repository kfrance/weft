"""Tests for parameter validation module."""

from __future__ import annotations

import pytest

from lw_coder.param_validation import (
    ParameterValidationError,
    get_effective_model,
    validate_tool_model_compatibility,
)


def test_validate_tool_model_compatibility_claude_code_with_model() -> None:
    """Test validation passes for claude-code with valid models."""
    # Should not raise for valid models
    validate_tool_model_compatibility("claude-code", "sonnet")
    validate_tool_model_compatibility("claude-code", "opus")
    validate_tool_model_compatibility("claude-code", "haiku")


def test_validate_tool_model_compatibility_claude_code_without_model() -> None:
    """Test validation passes for claude-code without model."""
    # Should not raise when model is None
    validate_tool_model_compatibility("claude-code", None)


def test_validate_tool_model_compatibility_droid_without_model() -> None:
    """Test validation passes for droid without model."""
    # Should not raise when model is None for droid
    validate_tool_model_compatibility("droid", None)


def test_validate_tool_model_compatibility_droid_with_model_raises_error() -> None:
    """Test validation raises error for droid with model."""
    with pytest.raises(ParameterValidationError) as exc_info:
        validate_tool_model_compatibility("droid", "sonnet")

    assert "cannot be used with --tool droid" in str(exc_info.value)
    assert "does not support model selection" in str(exc_info.value)


def test_validate_tool_model_compatibility_invalid_tool_raises_error() -> None:
    """Test validation raises error for invalid tool."""
    with pytest.raises(ParameterValidationError) as exc_info:
        validate_tool_model_compatibility("invalid-tool", None)

    assert "Unknown tool 'invalid-tool'" in str(exc_info.value)
    assert "Available tools:" in str(exc_info.value)


def test_get_effective_model_claude_code_with_explicit_model() -> None:
    """Test get_effective_model returns explicit model for claude-code."""
    assert get_effective_model("claude-code", "opus") == "opus"
    assert get_effective_model("claude-code", "haiku") == "haiku"


def test_get_effective_model_claude_code_defaults_to_sonnet() -> None:
    """Test get_effective_model defaults to sonnet for claude-code when no model specified."""
    assert get_effective_model("claude-code", None) == "sonnet"


def test_get_effective_model_droid_returns_none() -> None:
    """Test get_effective_model returns None for droid."""
    assert get_effective_model("droid", None) is None
    # Even if a model is passed (though validation would prevent this), it returns as-is
    assert get_effective_model("droid", "sonnet") == "sonnet"


def test_get_effective_model_other_tool_returns_as_is() -> None:
    """Test get_effective_model returns model as-is for other tools."""
    # For any tool other than claude-code, model is returned as-is
    assert get_effective_model("some-other-tool", "model") == "model"
    assert get_effective_model("some-other-tool", None) is None


def test_validate_all_valid_claude_code_model_combinations() -> None:
    """Test all valid model combinations for claude-code."""
    valid_models = ["sonnet", "opus", "haiku", None]
    for model in valid_models:
        # Should not raise
        validate_tool_model_compatibility("claude-code", model)


def test_validate_droid_rejects_all_models() -> None:
    """Test droid rejects all model specifications."""
    invalid_models = ["sonnet", "opus", "haiku", "gpt-4", "unknown"]
    for model in invalid_models:
        with pytest.raises(ParameterValidationError) as exc_info:
            validate_tool_model_compatibility("droid", model)
        assert "cannot be used with --tool droid" in str(exc_info.value)


def test_validate_invalid_model() -> None:
    """Test validation rejects invalid model names."""
    invalid_models = ["gpt-4", "unknown", "claude", ""]
    for model in invalid_models:
        with pytest.raises(ParameterValidationError) as exc_info:
            validate_tool_model_compatibility("claude-code", model)
        assert f"Unknown model '{model}'" in str(exc_info.value)
        assert "Available models:" in str(exc_info.value)