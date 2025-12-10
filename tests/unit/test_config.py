"""Tests for config module - configuration loading from ~/.lw_coder/config.toml."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lw_coder.config import (
    CONFIG_PATH,
    VALID_MODELS,
    get_model_defaults,
    load_config,
)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_valid_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading a valid TOML config file."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / ".lw_coder" / "config.toml")

        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
[defaults]
plan_model = "opus"
code_model = "sonnet"
finalize_model = "haiku"

[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = true
"""
        )

        config = load_config()

        assert "defaults" in config
        assert config["defaults"]["plan_model"] == "opus"
        assert config["defaults"]["code_model"] == "sonnet"
        assert config["defaults"]["finalize_model"] == "haiku"
        assert "hooks" in config
        assert "plan_file_created" in config["hooks"]

    def test_load_config_handles_multiple_sections(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading config with [defaults] + [hooks.*] in same file."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / ".lw_coder" / "config.toml")

        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
[defaults]
plan_model = "opus"

[hooks.plan_file_created]
command = "echo test"
enabled = true

[hooks.code_sdk_complete]
command = "echo done"
enabled = false
"""
        )

        config = load_config()

        assert "defaults" in config
        assert config["defaults"]["plan_model"] == "opus"
        assert "hooks" in config
        assert "plan_file_created" in config["hooks"]
        assert "code_sdk_complete" in config["hooks"]

    def test_load_config_missing_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that missing config file returns empty dict with no error logged."""
        # Point to a non-existent config file
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml")

        config = load_config()

        # Should return empty dict silently
        assert config == {}

    def test_load_config_corrupted_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that corrupted TOML returns empty dict and logs ERROR with guidance."""
        import logging

        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / ".lw_coder" / "config.toml")

        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("invalid [ toml syntax")

        caplog.set_level(logging.ERROR)
        config = load_config()

        # Should return empty dict
        assert config == {}
        # Should log error with guidance
        assert "Failed to parse config file" in caplog.text
        assert "TOML syntax error" in caplog.text
        assert "Fix the syntax error or remove the file" in caplog.text

    def test_load_config_permission_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that permission/IO errors return empty dict with warning."""
        import logging

        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / ".lw_coder" / "config.toml")

        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text("[defaults]\nplan_model = 'opus'")

        # Mock read_bytes to raise OSError
        def raise_oserror(*args, **kwargs):
            raise OSError("Permission denied")

        with patch.object(Path, "read_bytes", raise_oserror):
            caplog.set_level(logging.WARNING)
            config = load_config()

        # Should return empty dict
        assert config == {}
        # Should log warning
        assert "Failed to read config file" in caplog.text


class TestGetModelDefaults:
    """Tests for get_model_defaults function."""

    def test_get_model_defaults_valid_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test extracting [defaults] section successfully."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / ".lw_coder" / "config.toml")

        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
[defaults]
plan_model = "opus"
code_model = "sonnet"
finalize_model = "haiku"
"""
        )

        defaults = get_model_defaults()

        assert defaults["plan_model"] == "opus"
        assert defaults["code_model"] == "sonnet"
        assert defaults["finalize_model"] == "haiku"

    def test_get_model_defaults_partial_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test handling incomplete defaults (e.g., only plan_model set)."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / ".lw_coder" / "config.toml")

        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
[defaults]
plan_model = "opus"
"""
        )

        defaults = get_model_defaults()

        assert defaults["plan_model"] == "opus"
        assert "code_model" not in defaults
        assert "finalize_model" not in defaults

    def test_get_model_defaults_missing_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns empty dict when no config file exists."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml")

        defaults = get_model_defaults()

        assert defaults == {}

    def test_get_model_defaults_missing_defaults_section(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test returns empty dict when [defaults] section is missing."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / ".lw_coder" / "config.toml")

        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "echo test"
enabled = true
"""
        )

        defaults = get_model_defaults()

        assert defaults == {}

    def test_get_model_defaults_invalid_model_values(
        self, tmp_path: Path,monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test logs warning for invalid model values (e.g., 'gpt-4')."""
        import logging

        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / ".lw_coder" / "config.toml")

        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.toml"
        config_file.write_text(
            """
[defaults]
plan_model = "gpt-4"
code_model = "sonnet"
"""
        )

        caplog.set_level(logging.WARNING)
        defaults = get_model_defaults()

        # Invalid model should not be included in result
        assert "plan_model" not in defaults
        # Valid model should still be included
        assert defaults["code_model"] == "sonnet"
        # Should log warning about invalid model
        assert "invalid value 'gpt-4'" in caplog.text
        assert "Valid models:" in caplog.text


class TestValidModels:
    """Tests for VALID_MODELS constant."""

    def test_valid_models_contains_expected_values(self) -> None:
        """Test that VALID_MODELS contains sonnet, opus, and haiku."""
        assert "sonnet" in VALID_MODELS
        assert "opus" in VALID_MODELS
        assert "haiku" in VALID_MODELS
        assert len(VALID_MODELS) == 3
