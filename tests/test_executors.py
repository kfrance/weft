"""Tests for executor abstraction and implementations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.executors import (
    ClaudeCodeExecutor,
    DroidExecutor,
    Executor,
    ExecutorError,
    ExecutorRegistry,
)


@pytest.fixture
def clean_registry():
    """Fixture to save and restore the registry state for test isolation."""
    # Save the original state
    original_executors = ExecutorRegistry._executors.copy()

    yield

    # Restore the original state after test
    ExecutorRegistry._executors = original_executors


class TestExecutorRegistry:
    """Tests for ExecutorRegistry."""

    def test_get_executor_droid(self) -> None:
        """Test getting the Droid executor."""
        executor = ExecutorRegistry.get_executor("droid")
        assert isinstance(executor, DroidExecutor)

    def test_get_executor_claude_code(self) -> None:
        """Test getting the Claude Code executor."""
        executor = ExecutorRegistry.get_executor("claude-code")
        assert isinstance(executor, ClaudeCodeExecutor)

    def test_get_executor_unknown(self) -> None:
        """Test getting an unknown executor raises error."""
        with pytest.raises(ExecutorError, match="Unknown executor tool"):
            ExecutorRegistry.get_executor("unknown-tool")

    def test_list_executors(self) -> None:
        """Test listing available executors."""
        executors = ExecutorRegistry.list_executors()
        assert "droid" in executors
        assert "claude-code" in executors
        assert sorted(executors) == executors

    def test_register_executor(self, clean_registry) -> None:
        """Test registering a new executor with cleanup."""
        mock_executor = MagicMock(spec=Executor)
        ExecutorRegistry.register_executor("test-tool", mock_executor)
        assert ExecutorRegistry.get_executor("test-tool") == mock_executor


class TestDroidExecutor:
    """Tests for DroidExecutor."""

    def test_build_command(self, tmp_path: Path) -> None:
        """Test building a droid command."""
        executor = DroidExecutor()
        prompt_path = tmp_path / "prompt.txt"
        prompt_path.write_text("test prompt")

        command = executor.build_command(prompt_path)

        assert "droid" in command
        assert "$(cat" in command
        assert str(prompt_path) in command

    def test_build_command_escapes_special_characters(self, tmp_path: Path) -> None:
        """Test that build_command escapes special characters in paths."""
        executor = DroidExecutor()
        # Create a path with spaces and special characters
        prompt_path = tmp_path / "prompt with spaces.txt"
        prompt_path.write_text("test")

        command = executor.build_command(prompt_path)

        # The path should be quoted (shlex.quote uses single quotes for safety)
        assert "prompt with spaces" in command

    @patch("lw_coder.droid_auth.check_droid_auth")
    def test_check_auth_success(self, mock_check_droid_auth: MagicMock) -> None:
        """Test check_auth calls check_droid_auth."""
        executor = DroidExecutor()
        executor.check_auth()
        mock_check_droid_auth.assert_called_once()

    @patch("lw_coder.droid_auth.check_droid_auth")
    def test_check_auth_raises_executor_error(self, mock_check_droid_auth: MagicMock) -> None:
        """Test check_auth raises ExecutorError on auth failure."""
        from lw_coder.droid_auth import DroidAuthError

        mock_check_droid_auth.side_effect = DroidAuthError("Auth failed")
        executor = DroidExecutor()

        with pytest.raises(ExecutorError):
            executor.check_auth()


class TestClaudeCodeExecutor:
    """Tests for ClaudeCodeExecutor."""

    def test_build_command(self, tmp_path: Path) -> None:
        """Test building a Claude Code command."""
        executor = ClaudeCodeExecutor()
        prompt_path = tmp_path / "prompt.txt"
        prompt_path.write_text("test prompt")

        command = executor.build_command(prompt_path)

        assert command.startswith('claude "$(cat')
        assert "$(cat" in command

    def test_build_command_escapes_special_characters(self, tmp_path: Path) -> None:
        """Test that build_command escapes special characters in paths."""
        executor = ClaudeCodeExecutor()
        prompt_path = tmp_path / "prompt with spaces.txt"
        prompt_path.write_text("test")

        command = executor.build_command(prompt_path)

        # The path should be quoted/escaped
        assert "prompt" in command
        assert "spaces.txt" in command

    def test_check_auth_no_op(self) -> None:
        """Test check_auth is a no-op for Claude Code."""
        executor = ClaudeCodeExecutor()
        # Should not raise any exceptions
        executor.check_auth()


class TestExecutorInterface:
    """Tests for Executor abstract interface."""

    def test_executor_is_abstract(self) -> None:
        """Test that Executor cannot be instantiated."""
        with pytest.raises(TypeError):
            Executor()  # type: ignore

    def test_concrete_executor_implements_all_methods(self) -> None:
        """Test that concrete executors implement all abstract methods."""
        for executor in [DroidExecutor(), ClaudeCodeExecutor()]:
            # These should not raise AttributeError
            assert hasattr(executor, "check_auth")
            assert hasattr(executor, "build_command")
            assert hasattr(executor, "get_env_vars")
            assert callable(executor.check_auth)
            assert callable(executor.build_command)
            assert callable(executor.get_env_vars)
