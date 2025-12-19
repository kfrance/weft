"""Tests for parameter validation module."""

from __future__ import annotations

from pathlib import Path

import pytest

from weft.param_validation import (
    COMMAND_DEFAULTS,
    ParameterValidationError,
    get_effective_model,
    validate_tool_model_compatibility,
)


class TestValidateToolModelCompatibility:
    """Tests for validate_tool_model_compatibility function."""

    def test_claude_code_with_valid_models(self) -> None:
        """Test validation passes for claude-code with valid models."""
        # Should not raise for valid models
        validate_tool_model_compatibility("claude-code", "sonnet")
        validate_tool_model_compatibility("claude-code", "opus")
        validate_tool_model_compatibility("claude-code", "haiku")

    def test_claude_code_without_model(self) -> None:
        """Test validation passes for claude-code without model."""
        # Should not raise when model is None
        validate_tool_model_compatibility("claude-code", None)

    def test_droid_without_model(self) -> None:
        """Test validation passes for droid without model."""
        # Should not raise when model is None for droid
        validate_tool_model_compatibility("droid", None)

    def test_droid_with_model_raises_error(self) -> None:
        """Test validation raises error for droid with model."""
        with pytest.raises(ParameterValidationError) as exc_info:
            validate_tool_model_compatibility("droid", "sonnet")

        assert "cannot be used with --tool droid" in str(exc_info.value)
        assert "does not support model selection" in str(exc_info.value)

    def test_invalid_tool_raises_error(self) -> None:
        """Test validation raises error for invalid tool."""
        with pytest.raises(ParameterValidationError) as exc_info:
            validate_tool_model_compatibility("invalid-tool", None)

        assert "Unknown tool 'invalid-tool'" in str(exc_info.value)
        assert "Available tools:" in str(exc_info.value)

    @pytest.mark.parametrize("model", ["gpt-4", "unknown", "claude", ""])
    def test_invalid_model_raises_error(self, model: str) -> None:
        """Test validation rejects invalid model names."""
        with pytest.raises(ParameterValidationError) as exc_info:
            validate_tool_model_compatibility("claude-code", model)
        assert f"Unknown model '{model}'" in str(exc_info.value)
        assert "Available models:" in str(exc_info.value)


class TestGetEffectiveModel:
    """Tests for get_effective_model function with 3-tier precedence."""

    @pytest.mark.parametrize(
        "command,cli_model,expected",
        [
            ("plan", "opus", "opus"),
            ("plan", "haiku", "haiku"),
            ("code", "opus", "opus"),
            ("code", "haiku", "haiku"),
            ("finalize", "opus", "opus"),
            ("finalize", "sonnet", "sonnet"),
        ],
        ids=[
            "plan-cli-opus",
            "plan-cli-haiku",
            "code-cli-opus",
            "code-cli-haiku",
            "finalize-cli-opus",
            "finalize-cli-sonnet",
        ],
    )
    def test_cli_priority(self, command: str, cli_model: str, expected: str) -> None:
        """Test that CLI flag has highest priority for all commands."""
        # CLI model should always be returned when provided
        result = get_effective_model(cli_model, command)
        assert result == expected

    @pytest.mark.parametrize(
        "command,config_model,expected",
        [
            ("plan", "opus", "opus"),
            ("plan", "haiku", "haiku"),
            ("code", "opus", "opus"),
            ("code", "haiku", "haiku"),
            ("finalize", "opus", "opus"),
            ("finalize", "sonnet", "sonnet"),
        ],
        ids=[
            "plan-config-opus",
            "plan-config-haiku",
            "code-config-opus",
            "code-config-haiku",
            "finalize-config-opus",
            "finalize-config-sonnet",
        ],
    )
    def test_config_priority(
        self,
        command: str,
        config_model: str,
        expected: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that config.toml overrides hardcoded defaults when no CLI flag."""
        # Set up config file with model default
        monkeypatch.setattr("weft.config.CONFIG_PATH", tmp_path / ".weft" / "config.toml")

        config_dir = tmp_path / ".weft"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text(f"[defaults]\n{command}_model = \"{config_model}\"")

        # No CLI model (None), should use config model
        result = get_effective_model(None, command)
        assert result == expected

    @pytest.mark.parametrize(
        "command,expected_default",
        [
            ("plan", "sonnet"),
            ("code", "sonnet"),
            ("finalize", "haiku"),
        ],
        ids=["plan-default-sonnet", "code-default-sonnet", "finalize-default-haiku"],
    )
    def test_fallback_to_hardcoded(
        self,
        command: str,
        expected_default: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test fallback to hardcoded defaults when no CLI or config."""
        # Point to non-existent config
        monkeypatch.setattr(
            "weft.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml"
        )

        # No CLI model (None), no config -> should use hardcoded default
        result = get_effective_model(None, command)
        assert result == expected_default
        assert result == COMMAND_DEFAULTS[command]

    @pytest.mark.parametrize(
        "command,invalid_config_model",
        [
            ("plan", "gpt-4"),
            ("code", "invalid-model"),
            ("finalize", "claude-3"),
        ],
        ids=["plan-invalid", "code-invalid", "finalize-invalid"],
    )
    def test_invalid_config_value_falls_back(
        self,
        command: str,
        invalid_config_model: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that invalid config value falls back to hardcoded default with warning."""
        import logging

        # Set up config file with invalid model
        monkeypatch.setattr("weft.config.CONFIG_PATH", tmp_path / ".weft" / "config.toml")

        config_dir = tmp_path / ".weft"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text(f"[defaults]\n{command}_model = \"{invalid_config_model}\"")

        caplog.set_level(logging.WARNING)

        # Should fall back to hardcoded default
        result = get_effective_model(None, command)
        assert result == COMMAND_DEFAULTS[command]

        # Should have logged warning about invalid model
        assert "invalid value" in caplog.text

    def test_unknown_command_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that unknown command returns None with warning."""
        import logging

        # Point to non-existent config
        monkeypatch.setattr(
            "weft.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml"
        )

        caplog.set_level(logging.WARNING)
        result = get_effective_model(None, "unknown-command")

        assert result is None
        assert "Unknown command" in caplog.text


