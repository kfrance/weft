"""Tests for home_env module."""

import os
from pathlib import Path

import pytest

from lw_coder.home_env import HomeEnvError, load_home_env


def test_load_home_env_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful loading of ~/.lw_coder/.env."""
    # Setup: Create home directory with .lw_coder/.env
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    lw_coder_dir = home_dir / ".lw_coder"
    lw_coder_dir.mkdir()
    env_file = lw_coder_dir / ".env"
    env_file.write_text("OPENROUTER_API_KEY=test-key-123\n")

    # Mock Path.home() to return our test home directory
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    # Clear any existing env var
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # Execute
    result_path = load_home_env()

    # Assert
    assert result_path == env_file
    assert os.getenv("OPENROUTER_API_KEY") == "test-key-123"


def test_load_home_env_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test error when ~/.lw_coder/.env doesn't exist."""
    # Setup: Create home directory without .lw_coder/.env
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    # Mock Path.home()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    # Execute and assert
    with pytest.raises(HomeEnvError, match="Environment file not found"):
        load_home_env()


def test_load_home_env_missing_lw_coder_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test error when ~/.lw_coder directory doesn't exist."""
    # Setup: Create home directory without .lw_coder
    home_dir = tmp_path / "home"
    home_dir.mkdir()

    # Mock Path.home()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    # Execute and assert
    with pytest.raises(HomeEnvError, match="Environment file not found"):
        load_home_env()


def test_load_home_env_is_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test error when ~/.lw_coder/.env is a directory instead of a file."""
    # Setup: Create ~/.lw_coder/.env as a directory
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    lw_coder_dir = home_dir / ".lw_coder"
    lw_coder_dir.mkdir()
    env_path = lw_coder_dir / ".env"
    env_path.mkdir()  # Create as directory instead of file

    # Mock Path.home()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    # Execute and assert
    with pytest.raises(HomeEnvError, match="Environment path is not a file"):
        load_home_env()


def test_load_home_env_unreadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test error when ~/.lw_coder/.env exists but is not readable."""
    # Setup: Create unreadable .env file
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    lw_coder_dir = home_dir / ".lw_coder"
    lw_coder_dir.mkdir()
    env_file = lw_coder_dir / ".env"
    env_file.write_text("TEST=1\n")

    # Make file unreadable
    env_file.chmod(0o000)

    # Mock Path.home()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    try:
        # Execute and assert
        with pytest.raises(HomeEnvError, match="Cannot read environment file"):
            load_home_env()
    finally:
        # Cleanup: Restore permissions so pytest can clean up the directory
        env_file.chmod(0o644)


def test_load_home_env_with_multiple_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test loading multiple environment variables from ~/.lw_coder/.env."""
    # Setup
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    lw_coder_dir = home_dir / ".lw_coder"
    lw_coder_dir.mkdir()
    env_file = lw_coder_dir / ".env"
    env_file.write_text(
        """OPENROUTER_API_KEY=key-123
ANTHROPIC_API_KEY=key-456
DEBUG=true
"""
    )

    # Mock Path.home()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    # Clear existing env vars
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)

    # Execute
    load_home_env()

    # Assert all variables are loaded
    assert os.getenv("OPENROUTER_API_KEY") == "key-123"
    assert os.getenv("ANTHROPIC_API_KEY") == "key-456"
    assert os.getenv("DEBUG") == "true"


def test_load_home_env_respects_existing_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that load_home_env doesn't override existing environment variables."""
    # Setup
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    lw_coder_dir = home_dir / ".lw_coder"
    lw_coder_dir.mkdir()
    env_file = lw_coder_dir / ".env"
    env_file.write_text("EXISTING_VAR=from-file\n")

    # Mock Path.home()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    # Set existing variable
    monkeypatch.setenv("EXISTING_VAR", "from-env")

    # Execute
    load_home_env()

    # Assert existing variable is not overridden (override=False in load_dotenv)
    assert os.getenv("EXISTING_VAR") == "from-env"


def test_load_home_env_empty_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that an empty ~/.lw_coder/.env file is handled gracefully."""
    # Setup
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    lw_coder_dir = home_dir / ".lw_coder"
    lw_coder_dir.mkdir()
    env_file = lw_coder_dir / ".env"
    env_file.write_text("")  # Empty file

    # Mock Path.home()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    # Execute - should succeed even with empty file
    result_path = load_home_env()

    # Assert
    assert result_path == env_file


def test_load_home_env_error_message_includes_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that error messages include the expected path for user guidance."""
    # Setup: home directory without .lw_coder
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    expected_path = home_dir / ".lw_coder" / ".env"

    # Execute and assert
    with pytest.raises(HomeEnvError) as exc_info:
        load_home_env()

    error_message = str(exc_info.value)
    assert str(expected_path) in error_message
    assert "~/.lw_coder/.env" in error_message
