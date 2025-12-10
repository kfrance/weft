"""Tests for claude_session module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.claude_session import (
    ClaudeSessionError,
    run_headless_session,
    run_interactive_session,
    run_sdk_only_session,
)


class TestRunHeadlessSession:
    """Tests for run_headless_session function."""

    def test_success_returns_output_path(self, tmp_path: Path) -> None:
        """Successful session returns path to output file."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        expected_output = worktree / "output.json"
        expected_output.write_text("{}")

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-123"

            result = run_headless_session(
                worktree_path=worktree,
                prompt="Test prompt",
                model="sonnet",
                expected_output=expected_output,
                sdk_settings_path=sdk_settings,
            )

        assert result == expected_output
        mock_sdk.assert_called_once()

    def test_raises_when_output_missing(self, tmp_path: Path) -> None:
        """Raises ClaudeSessionError when expected output file is not created."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        expected_output = worktree / "missing.json"  # Does not exist
        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-123"

            with pytest.raises(ClaudeSessionError, match="Expected output file not created"):
                run_headless_session(
                    worktree_path=worktree,
                    prompt="Test prompt",
                    model="sonnet",
                    expected_output=expected_output,
                    sdk_settings_path=sdk_settings,
                )

    def test_raises_on_sdk_error(self, tmp_path: Path) -> None:
        """Raises ClaudeSessionError when SDK fails."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        expected_output = worktree / "output.json"
        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        from lw_coder.sdk_runner import SDKRunnerError

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.side_effect = SDKRunnerError("SDK failed")

            with pytest.raises(ClaudeSessionError, match="SDK session failed"):
                run_headless_session(
                    worktree_path=worktree,
                    prompt="Test prompt",
                    model="sonnet",
                    expected_output=expected_output,
                    sdk_settings_path=sdk_settings,
                )

    def test_passes_agents_to_sdk(self, tmp_path: Path) -> None:
        """Agents parameter is passed through to SDK."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        expected_output = worktree / "output.json"
        expected_output.write_text("{}")

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        mock_agents = {"test-agent": MagicMock()}

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-123"

            run_headless_session(
                worktree_path=worktree,
                prompt="Test prompt",
                model="sonnet",
                expected_output=expected_output,
                sdk_settings_path=sdk_settings,
                agents=mock_agents,
            )

        mock_sdk.assert_called_once()
        call_kwargs = mock_sdk.call_args[1]
        assert call_kwargs["agents"] == mock_agents


class TestRunInteractiveSession:
    """Tests for run_interactive_session function."""

    def test_success_returns_session_id_and_path(self, tmp_path: Path) -> None:
        """Successful interactive session returns session_id and output path."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        expected_output = worktree / "feedback.md"
        expected_output.write_text("# Feedback")

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-456"

            with patch("lw_coder.claude_session.subprocess.run") as mock_subprocess:
                session_id, output_path = run_interactive_session(
                    worktree_path=worktree,
                    prompt="Test prompt",
                    model="opus",
                    sdk_settings_path=sdk_settings,
                    expected_output=expected_output,
                )

        assert session_id == "session-456"
        assert output_path == expected_output
        mock_subprocess.assert_called_once()

    def test_returns_none_when_output_missing(self, tmp_path: Path) -> None:
        """Returns None for output_path when expected output is not created."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        expected_output = worktree / "missing.md"  # Does not exist
        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-456"

            with patch("lw_coder.claude_session.subprocess.run"):
                session_id, output_path = run_interactive_session(
                    worktree_path=worktree,
                    prompt="Test prompt",
                    model="opus",
                    sdk_settings_path=sdk_settings,
                    expected_output=expected_output,
                )

        assert session_id == "session-456"
        assert output_path is None  # Missing file returns None, not raise

    def test_works_without_expected_output(self, tmp_path: Path) -> None:
        """Session works when no expected_output is specified."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-789"

            with patch("lw_coder.claude_session.subprocess.run"):
                session_id, output_path = run_interactive_session(
                    worktree_path=worktree,
                    prompt="Test prompt",
                    model="haiku",
                    sdk_settings_path=sdk_settings,
                    expected_output=None,
                )

        assert session_id == "session-789"
        assert output_path is None

    def test_raises_on_sdk_error(self, tmp_path: Path) -> None:
        """Raises ClaudeSessionError when SDK fails."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        from lw_coder.sdk_runner import SDKRunnerError

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.side_effect = SDKRunnerError("SDK failed")

            with pytest.raises(ClaudeSessionError, match="SDK session failed"):
                run_interactive_session(
                    worktree_path=worktree,
                    prompt="Test prompt",
                    model="opus",
                    sdk_settings_path=sdk_settings,
                )

    def test_raises_on_cli_launch_error(self, tmp_path: Path) -> None:
        """Raises ClaudeSessionError when CLI launch fails."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-456"

            with patch("lw_coder.claude_session.subprocess.run") as mock_subprocess:
                mock_subprocess.side_effect = Exception("CLI failed to launch")

                with pytest.raises(ClaudeSessionError, match="Failed to launch CLI"):
                    run_interactive_session(
                        worktree_path=worktree,
                        prompt="Test prompt",
                        model="opus",
                        sdk_settings_path=sdk_settings,
                    )

    def test_cli_command_includes_session_resume(self, tmp_path: Path) -> None:
        """CLI is launched with -r flag to resume session."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-xyz"

            with patch("lw_coder.claude_session.subprocess.run") as mock_subprocess:
                run_interactive_session(
                    worktree_path=worktree,
                    prompt="Test prompt",
                    model="sonnet",
                    sdk_settings_path=sdk_settings,
                )

        # Verify CLI command includes -r for resume
        call_args = mock_subprocess.call_args
        command = call_args[0][0]  # First positional arg
        assert "-r" in command
        assert "session-xyz" in command


class TestRunSdkOnlySession:
    """Tests for run_sdk_only_session function."""

    def test_success_returns_session_id(self, tmp_path: Path) -> None:
        """Successful session returns the session ID."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-only-123"

            result = run_sdk_only_session(
                worktree_path=worktree,
                prompt="Test prompt",
                model="haiku",
                sdk_settings_path=sdk_settings,
            )

        assert result == "session-only-123"

    def test_raises_on_sdk_error(self, tmp_path: Path) -> None:
        """Raises ClaudeSessionError when SDK fails."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        from lw_coder.sdk_runner import SDKRunnerError

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.side_effect = SDKRunnerError("SDK error")

            with pytest.raises(ClaudeSessionError, match="SDK session failed"):
                run_sdk_only_session(
                    worktree_path=worktree,
                    prompt="Test prompt",
                    model="haiku",
                    sdk_settings_path=sdk_settings,
                )

    def test_passes_agents_to_sdk(self, tmp_path: Path) -> None:
        """Agents parameter is passed through to SDK."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        sdk_settings = tmp_path / "sdk_settings.json"
        sdk_settings.write_text("{}")

        mock_agents = {"agent-1": MagicMock()}

        with patch("lw_coder.claude_session.run_sdk_session_sync") as mock_sdk:
            mock_sdk.return_value = "session-123"

            run_sdk_only_session(
                worktree_path=worktree,
                prompt="Test prompt",
                model="haiku",
                sdk_settings_path=sdk_settings,
                agents=mock_agents,
            )

        call_kwargs = mock_sdk.call_args[1]
        assert call_kwargs["agents"] == mock_agents
