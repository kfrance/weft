"""Tests for executor abstraction and implementations."""

from __future__ import annotations

import shlex
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weft.executors import (
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

        command = executor.build_command(prompt_path, model="sonnet")

        assert "droid" in command
        assert "$(cat" in command
        assert str(prompt_path) in command

    def test_build_command_escapes_special_characters(self, tmp_path: Path) -> None:
        """Test that build_command escapes special characters in paths."""
        executor = DroidExecutor()
        # Create a path with spaces and special characters
        prompt_path = tmp_path / "prompt with spaces.txt"
        prompt_path.write_text("test")

        command = executor.build_command(prompt_path, model="sonnet")

        # The path should be quoted (shlex.quote uses single quotes for safety)
        assert "prompt with spaces" in command

    @patch("weft.droid_auth.check_droid_auth")
    def test_check_auth_success(self, mock_check_droid_auth: MagicMock) -> None:
        """Test check_auth calls check_droid_auth."""
        executor = DroidExecutor()
        executor.check_auth()
        mock_check_droid_auth.assert_called_once()

    @patch("weft.droid_auth.check_droid_auth")
    def test_check_auth_raises_executor_error(self, mock_check_droid_auth: MagicMock) -> None:
        """Test check_auth raises ExecutorError on auth failure."""
        from weft.droid_auth import DroidAuthError

        mock_check_droid_auth.side_effect = DroidAuthError("Auth failed")
        executor = DroidExecutor()

        with pytest.raises(ExecutorError):
            executor.check_auth()


class TestClaudeCodeExecutor:
    """Tests for ClaudeCodeExecutor."""

    @pytest.mark.parametrize("model", ["sonnet", "haiku", "opus"])
    def test_build_command(self, tmp_path: Path, model: str) -> None:
        """Test building a Claude Code command with different models."""
        executor = ClaudeCodeExecutor()
        prompt_path = tmp_path / "prompt.txt"
        prompt_path.write_text("test prompt")

        command = executor.build_command(prompt_path, model=model)

        assert command.startswith('claude --model')
        assert f"--model {model}" in command
        assert f"claude --model {model}" in command
        assert "$(cat" in command

    def test_build_command_escapes_special_characters(self, tmp_path: Path) -> None:
        """Test that build_command escapes special characters in paths."""
        executor = ClaudeCodeExecutor()
        prompt_path = tmp_path / "prompt with spaces.txt"
        prompt_path.write_text("test")

        command = executor.build_command(prompt_path, model="sonnet")

        # The path should be quoted/escaped
        assert "prompt" in command
        assert "spaces.txt" in command

    def test_check_auth_no_op(self) -> None:
        """Test check_auth is a no-op for Claude Code."""
        executor = ClaudeCodeExecutor()
        # Should not raise any exceptions
        executor.check_auth()

    def test_build_command_rejects_shell_metacharacters(self, tmp_path: Path) -> None:
        """Test that build_command rejects model parameters with shell metacharacters."""
        executor = ClaudeCodeExecutor()
        prompt_path = tmp_path / "prompt.txt"
        prompt_path.write_text("test prompt")

        # Test various shell metacharacter injection attempts
        shell_metachar_attempts = [
            "sonnet;rm",
            "sonnet|cat",
            "sonnet&echo",
            "sonnet`whoami`",
            "sonnet$(whoami)",
            "sonnet*",
            "sonnet?",
        ]

        for malicious_model in shell_metachar_attempts:
            with pytest.raises(ValueError, match="Must be one of"):
                executor.build_command(prompt_path, model=malicious_model)

    def test_build_command_rejects_flag_injection_attempts(self, tmp_path: Path) -> None:
        """Test that build_command rejects model parameters that look like flags."""
        executor = ClaudeCodeExecutor()
        prompt_path = tmp_path / "prompt.txt"
        prompt_path.write_text("test prompt")

        # Test various flag injection attempts
        flag_injection_attempts = [
            "--help",
            "-h",
            "--api-key=stolen",
            "-model-override",
        ]

        for malicious_model in flag_injection_attempts:
            with pytest.raises(ValueError, match="Must be one of"):
                executor.build_command(prompt_path, model=malicious_model)

    def test_build_command_rejects_whitespace_in_model(self, tmp_path: Path) -> None:
        """Test that build_command rejects model parameters containing whitespace."""
        executor = ClaudeCodeExecutor()
        prompt_path = tmp_path / "prompt.txt"
        prompt_path.write_text("test prompt")

        # Test various whitespace injection attempts (including Unicode whitespace)
        whitespace_attempts = [
            "sonnet --api-key=stolen",
            "sonnet\t--help",
            "sonnet\n--debug",
            "son net",
            "sonnet\u00a0--help",  # Non-breaking space
            "sonnet\u200b--help",  # Zero-width space
        ]

        for malicious_model in whitespace_attempts:
            with pytest.raises(ValueError, match="Must be one of"):
                executor.build_command(prompt_path, model=malicious_model)

    def test_build_command_rejects_empty_model(self, tmp_path: Path) -> None:
        """Test that build_command rejects empty model parameter."""
        executor = ClaudeCodeExecutor()
        prompt_path = tmp_path / "prompt.txt"
        prompt_path.write_text("test prompt")

        with pytest.raises(ValueError, match="cannot be empty"):
            executor.build_command(prompt_path, model="")

    def test_build_command_produces_safe_commands(self, tmp_path: Path) -> None:
        """Test that valid model names produce safe commands without unexpected flags."""
        executor = ClaudeCodeExecutor()
        prompt_path = tmp_path / "prompt.txt"
        prompt_path.write_text("test prompt")

        # Test all valid model values
        for safe_model in ClaudeCodeExecutor.VALID_MODELS:
            command = executor.build_command(prompt_path, model=safe_model)

            # Verify command structure is correct
            assert command.startswith("claude --model")
            assert f"--model {shlex.quote(safe_model)}" in command or f"--model '{safe_model}'" in command

            # Ensure no extra flags were injected
            # Count occurrences of '--' - should only be in '--model' flag
            assert command.count("--") == 1, f"Unexpected flags in command: {command}"


class TestExecutorInterface:
    """Tests for Executor abstract interface."""

    pass
