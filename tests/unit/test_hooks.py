"""Tests for hooks module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.hooks import (
    HookConfigError,
    HookError,
    HookManager,
    substitute_variables,
    trigger_hook,
)


class MockProcessExecutor:
    """Mock process executor for testing."""

    def __init__(self) -> None:
        self.executed_commands: list[str] = []
        self.mock_process = MagicMock()
        self.mock_process.poll.return_value = 0  # Process completed
        self.mock_process.pid = 12345

    def execute(self, command: str) -> MagicMock:
        """Record executed commands and return mock process."""
        self.executed_commands.append(command)
        return self.mock_process


class TestSubstituteVariables:
    """Tests for substitute_variables function."""

    def test_simple_substitution(self) -> None:
        """Test simple variable substitution."""
        result = substitute_variables(
            "code-oss ${worktree_path}",
            {"worktree_path": Path("/tmp/worktree")},
        )
        assert result == "code-oss /tmp/worktree"

    def test_multiple_variables(self) -> None:
        """Test multiple variable substitution."""
        result = substitute_variables(
            "echo ${plan_id} ${repo_root}",
            {"plan_id": "test-plan", "repo_root": Path("/home/user/repo")},
        )
        assert result == "echo test-plan /home/user/repo"

    def test_no_variables(self) -> None:
        """Test command with no variables."""
        result = substitute_variables("ls -la", {})
        assert result == "ls -la"

    def test_path_with_spaces(self) -> None:
        """Test path with spaces is handled correctly."""
        result = substitute_variables(
            "code-oss ${worktree_path}",
            {"worktree_path": Path("/path/with spaces/worktree")},
        )
        assert result == "code-oss /path/with spaces/worktree"

    def test_undefined_variable_raises_error(self) -> None:
        """Test that undefined variable raises HookError."""
        with pytest.raises(HookError, match="Undefined variable"):
            substitute_variables("echo ${undefined}", {"defined": "value"})

    def test_string_variable(self) -> None:
        """Test string variable (not Path)."""
        result = substitute_variables("echo ${plan_id}", {"plan_id": "my-plan"})
        assert result == "echo my-plan"

    def test_repeated_variable(self) -> None:
        """Test same variable used multiple times."""
        result = substitute_variables(
            "${path} ${path}",
            {"path": "/tmp"},
        )
        assert result == "/tmp /tmp"


class TestHookManager:
    """Tests for HookManager class."""

    def test_load_config_missing_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading config when file doesn't exist."""
        # Monkeypatch the config module's CONFIG_PATH
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml")
        manager = HookManager()
        config = manager.load_config()
        assert config == {}

    def test_load_config_valid_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading valid TOML config."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = true

[hooks.code_sdk_complete]
command = "echo done"
enabled = false
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        manager = HookManager()
        config = manager.load_config()
        assert "hooks" in config
        assert "plan_file_created" in config["hooks"]
        assert config["hooks"]["plan_file_created"]["command"] == "code-oss ${worktree_path}"
        assert config["hooks"]["plan_file_created"]["enabled"] is True
        assert config["hooks"]["code_sdk_complete"]["enabled"] is False

    def test_load_config_invalid_toml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test loading invalid TOML returns empty config (config module handles gracefully)."""
        import logging

        config_file = tmp_path / "config.toml"
        config_file.write_text("invalid [ toml syntax")
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        caplog.set_level(logging.ERROR)
        manager = HookManager()
        # Config module handles invalid TOML gracefully by returning empty dict
        config = manager.load_config()
        assert config == {}
        # Error should be logged by config module
        assert "Failed to parse config file" in caplog.text

    def test_load_config_unknown_hook(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading config with unknown hook name."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.unknown_hook]
command = "echo test"
enabled = true
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        manager = HookManager()
        with pytest.raises(HookConfigError, match="Unknown hook"):
            manager.load_config()

    def test_load_config_missing_command(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading config with missing command field."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
enabled = true
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        manager = HookManager()
        with pytest.raises(HookConfigError, match="missing required 'command'"):
            manager.load_config()

    def test_load_config_invalid_enabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading config with non-boolean enabled field."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "echo test"
enabled = "yes"
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        manager = HookManager()
        with pytest.raises(HookConfigError, match="enabled must be a boolean"):
            manager.load_config()

    def test_execute_hook_not_configured(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test executing hook that isn't configured."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml")

        mock_executor = MockProcessExecutor()
        manager = HookManager(executor=mock_executor)

        # No config file, so no hooks configured
        manager.execute_hook("plan_file_created", {"worktree_path": Path("/tmp")})

        # Should not execute anything
        assert len(mock_executor.executed_commands) == 0

    def test_execute_hook_disabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test executing disabled hook."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = false
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        mock_executor = MockProcessExecutor()
        manager = HookManager(executor=mock_executor)

        manager.execute_hook("plan_file_created", {"worktree_path": Path("/tmp")})

        # Should not execute anything
        assert len(mock_executor.executed_commands) == 0

    def test_execute_hook_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test successful hook execution."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = true
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        mock_executor = MockProcessExecutor()
        manager = HookManager(executor=mock_executor)

        manager.execute_hook(
            "plan_file_created",
            {"worktree_path": Path("/tmp/worktree")},
        )

        assert len(mock_executor.executed_commands) == 1
        assert mock_executor.executed_commands[0] == "code-oss /tmp/worktree"

    def test_execute_hook_with_multiple_variables(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test hook execution with multiple variables."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "notify-send 'Plan ${plan_id}' 'Created in ${repo_root}'"
enabled = true
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        mock_executor = MockProcessExecutor()
        manager = HookManager(executor=mock_executor)

        manager.execute_hook(
            "plan_file_created",
            {
                "worktree_path": Path("/tmp/worktree"),
                "plan_id": "test-plan",
                "repo_root": Path("/home/user/repo"),
            },
        )

        assert len(mock_executor.executed_commands) == 1
        assert "test-plan" in mock_executor.executed_commands[0]
        assert "/home/user/repo" in mock_executor.executed_commands[0]

    def test_process_tracking(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that processes are tracked for cleanup."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "echo test"
enabled = true
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        mock_executor = MockProcessExecutor()
        # Mark process as still running
        mock_executor.mock_process.poll.return_value = None

        manager = HookManager(executor=mock_executor)
        manager.execute_hook(
            "plan_file_created",
            {"worktree_path": Path("/tmp")},
        )

        # Process should be tracked
        assert len(manager._processes) == 1

    def test_config_caching(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that config is cached after first load."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "echo test"
enabled = true
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        manager = HookManager()

        # Load config twice
        config1 = manager.load_config()
        config2 = manager.load_config()

        # Should be the same cached object
        assert config1 is config2

    def test_config_force_reload(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test force reload of config."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "echo test"
enabled = true
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        manager = HookManager()

        config1 = manager.load_config()

        # Update config file
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "echo updated"
enabled = true
"""
        )

        # Force reload
        config2 = manager.load_config(force_reload=True)

        assert config1 is not config2
        assert config2["hooks"]["plan_file_created"]["command"] == "echo updated"


class TestTriggerHook:
    """Tests for trigger_hook function."""

    def test_trigger_hook_not_configured(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test trigger_hook with no config gracefully returns."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml")

        # Should not raise, just return silently
        trigger_hook(
            "plan_file_created",
            {"worktree_path": Path("/tmp")},
            console_output=False,
        )

    def test_trigger_hook_with_manager(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test trigger_hook with explicit manager."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "echo test"
enabled = true
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        mock_executor = MockProcessExecutor()
        manager = HookManager(executor=mock_executor)

        trigger_hook(
            "plan_file_created",
            {"worktree_path": Path("/tmp")},
            manager=manager,
            console_output=False,
        )

        assert len(mock_executor.executed_commands) == 1

    def test_trigger_hook_handles_errors(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test trigger_hook handles errors gracefully."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[hooks.plan_file_created]
command = "echo ${undefined_var}"
enabled = true
"""
        )
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", config_file)

        # Should not raise, just log the error
        trigger_hook(
            "plan_file_created",
            {"worktree_path": Path("/tmp")},
            console_output=False,
        )


class TestCleanup:
    """Tests for process cleanup."""

    def test_cleanup_terminates_processes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that cleanup terminates running processes."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml")

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_process.pid = 12345

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_process

        manager = HookManager(executor=mock_executor)
        manager._processes = [mock_process]

        # Call cleanup
        manager._cleanup()

        # Should have called terminate
        mock_process.terminate.assert_called_once()

    def test_cleanup_kills_stubborn_processes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that cleanup kills processes that don't terminate."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml")

        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Still running
        mock_process.pid = 12345
        mock_process.wait.side_effect = subprocess.TimeoutExpired("cmd", 5)

        mock_executor = MagicMock()
        mock_executor.execute.return_value = mock_process

        manager = HookManager(executor=mock_executor)
        manager._processes = [mock_process]

        # Call cleanup
        manager._cleanup()

        # Should have called terminate and then kill
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    def test_prune_completed_removes_finished(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that prune_completed removes finished processes."""
        monkeypatch.setattr("lw_coder.config.CONFIG_PATH", tmp_path / "nonexistent" / "config.toml")

        finished_process = MagicMock()
        finished_process.poll.return_value = 0  # Completed

        running_process = MagicMock()
        running_process.poll.return_value = None  # Still running

        manager = HookManager()
        manager._processes = [finished_process, running_process]

        manager._prune_completed()

        # Only running process should remain
        assert len(manager._processes) == 1
        assert manager._processes[0] is running_process
