"""Tests for config_loader module."""

from pathlib import Path

import pytest

from lw_coder.config_loader import CodeConfig, ConfigLoaderError, load_code_config


def test_load_code_config_happy_path(tmp_path: Path) -> None:
    """Test successful config loading with default values."""
    # Setup: Create config file and .env
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
forward_env = ["OPENROUTER_*"]
docker_build_args = []
docker_run_args = []
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=test\n")

    # Execute
    config = load_code_config(tmp_path)

    # Assert
    assert isinstance(config, CodeConfig)
    assert config.env_file == tmp_path / ".env"
    assert config.forward_env == ["OPENROUTER_*"]
    assert config.docker_build_args == []
    assert config.docker_run_args == []


def test_load_code_config_missing_config_file(tmp_path: Path) -> None:
    """Test error when config file doesn't exist."""
    with pytest.raises(ConfigLoaderError, match="Configuration file not found"):
        load_code_config(tmp_path)


def test_load_code_config_missing_code_table(tmp_path: Path) -> None:
    """Test error when [code] table is missing."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[other]
key = "value"
"""
    )

    with pytest.raises(ConfigLoaderError, match="Missing required \\[code\\] table"):
        load_code_config(tmp_path)


def test_load_code_config_missing_env_file(tmp_path: Path) -> None:
    """Test error when specified .env file doesn't exist."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
"""
    )

    # Don't create the .env file

    with pytest.raises(ConfigLoaderError, match="Environment file not found"):
        load_code_config(tmp_path)


def test_load_code_config_unknown_keys(tmp_path: Path) -> None:
    """Test error when config contains unknown keys."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
unknown_field = "value"
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    with pytest.raises(ConfigLoaderError, match="Unknown keys in \\[code\\] section"):
        load_code_config(tmp_path)


def test_load_code_config_forward_env_wildcard_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test warning when forward_env contains wildcard '*'."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
forward_env = ["*"]
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    # Execute
    config = load_code_config(tmp_path)

    # Assert warning was logged
    assert any(
        "forward_env contains '*'" in record.message for record in caplog.records
    )
    assert config.forward_env == ["*"]


def test_load_code_config_env_file_wrong_type(tmp_path: Path) -> None:
    """Test error when env_file is not a string."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = 123
"""
    )

    with pytest.raises(ConfigLoaderError, match="env_file must be a string"):
        load_code_config(tmp_path)


def test_load_code_config_forward_env_not_list(tmp_path: Path) -> None:
    """Test error when forward_env is not a list."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
forward_env = "OPENROUTER_*"
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    with pytest.raises(ConfigLoaderError, match="forward_env must be a list"):
        load_code_config(tmp_path)


def test_load_code_config_forward_env_non_string_items(tmp_path: Path) -> None:
    """Test error when forward_env list contains non-string items."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
forward_env = ["OPENROUTER_*", 123]
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    with pytest.raises(ConfigLoaderError, match="forward_env must be a list of strings"):
        load_code_config(tmp_path)


def test_load_code_config_docker_build_args_not_list(tmp_path: Path) -> None:
    """Test error when docker_build_args is not a list."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
docker_build_args = "not a list"
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    with pytest.raises(ConfigLoaderError, match="docker_build_args must be a list"):
        load_code_config(tmp_path)


def test_load_code_config_docker_build_args_non_string_items(tmp_path: Path) -> None:
    """Test error when docker_build_args contains non-string items."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
docker_build_args = ["--arg", 123]
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    with pytest.raises(
        ConfigLoaderError, match="docker_build_args must be a list of strings"
    ):
        load_code_config(tmp_path)


def test_load_code_config_docker_run_args_not_list(tmp_path: Path) -> None:
    """Test error when docker_run_args is not a list."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
docker_run_args = 456
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    with pytest.raises(ConfigLoaderError, match="docker_run_args must be a list"):
        load_code_config(tmp_path)


def test_load_code_config_docker_run_args_non_string_items(tmp_path: Path) -> None:
    """Test error when docker_run_args contains non-string items."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
docker_run_args = [true, false]
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    with pytest.raises(
        ConfigLoaderError, match="docker_run_args must be a list of strings"
    ):
        load_code_config(tmp_path)


def test_load_code_config_defaults(tmp_path: Path) -> None:
    """Test that default values are applied correctly."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    # Minimal config - only [code] table, relying on defaults
    config_file.write_text("[code]\n")

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    config = load_code_config(tmp_path)

    assert config.env_file == tmp_path / ".env"
    assert config.forward_env == ["OPENROUTER_*"]
    assert config.docker_build_args == []
    assert config.docker_run_args == []


def test_load_code_config_custom_env_path(tmp_path: Path) -> None:
    """Test loading config with custom env file path."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = "config/custom.env"
"""
    )

    custom_env_dir = tmp_path / "config"
    custom_env_dir.mkdir()
    env_file = custom_env_dir / "custom.env"
    env_file.write_text("CUSTOM=1\n")

    config = load_code_config(tmp_path)

    assert config.env_file == tmp_path / "config" / "custom.env"


def test_load_code_config_multiple_forward_patterns(tmp_path: Path) -> None:
    """Test config with multiple forward_env patterns."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
forward_env = ["OPENROUTER_*", "ANTHROPIC_*", "DEBUG"]
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    config = load_code_config(tmp_path)

    assert config.forward_env == ["OPENROUTER_*", "ANTHROPIC_*", "DEBUG"]


def test_load_code_config_with_docker_args(tmp_path: Path) -> None:
    """Test config with docker build and run arguments."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text(
        """
[code]
env_file = ".env"
docker_build_args = ["--build-arg", "VERSION=1.0"]
docker_run_args = ["--memory", "4g", "--cpus", "2"]
"""
    )

    env_file = tmp_path / ".env"
    env_file.write_text("TEST=1\n")

    config = load_code_config(tmp_path)

    assert config.docker_build_args == ["--build-arg", "VERSION=1.0"]
    assert config.docker_run_args == ["--memory", "4g", "--cpus", "2"]


def test_load_code_config_invalid_toml(tmp_path: Path) -> None:
    """Test error when config file contains invalid TOML."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    config_file.write_text("invalid toml [ [ [")

    with pytest.raises(ConfigLoaderError, match="Failed to parse configuration file"):
        load_code_config(tmp_path)


def test_load_code_config_path_traversal_protection(tmp_path: Path) -> None:
    """Test that path traversal attempts are blocked."""
    config_dir = tmp_path / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    # Try to access a file outside the repo using relative path
    config_file.write_text(
        """
[code]
env_file = "../../outside.env"
"""
    )

    with pytest.raises(
        ConfigLoaderError, match="resolves outside repository"
    ):
        load_code_config(tmp_path)


def test_load_code_config_symlink_path_traversal_protection(tmp_path: Path) -> None:
    """Test that symlink-based path traversal attempts are blocked."""
    # Create a directory outside the repo
    outside_dir = tmp_path.parent / "outside"
    outside_dir.mkdir(exist_ok=True)
    outside_env = outside_dir / "secret.env"
    outside_env.write_text("SECRET_KEY=leaked\n")

    # Create repo directory
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # Create config directory
    config_dir = repo_dir / ".lw_coder"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    # Create a symlink inside the repo that points outside
    symlink_path = repo_dir / "sneaky_link"
    symlink_path.symlink_to(outside_env)

    # Try to reference the symlink in config
    config_file.write_text(
        """
[code]
env_file = "sneaky_link"
"""
    )

    # Should be blocked because the symlink resolves outside repo_root
    with pytest.raises(
        ConfigLoaderError, match="resolves outside repository"
    ):
        load_code_config(repo_dir)
