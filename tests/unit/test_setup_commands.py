"""Tests for setup_commands module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from weft.setup_commands import (
    SetupCommand,
    SetupConfigError,
    SetupExecutionError,
    load_setup_commands,
    run_setup_commands,
)


class TestLoadSetupCommands:
    """Tests for load_setup_commands function."""

    def test_valid_config_single_command(self, tmp_path: Path) -> None:
        """Test loading a single valid setup command."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[[code.setup]]
name = "start-services"
command = "docker-compose up -d"
"""
        )

        commands = load_setup_commands(tmp_path)

        assert len(commands) == 1
        assert commands[0].name == "start-services"
        assert commands[0].command == "docker-compose up -d"
        assert commands[0].working_dir is None
        assert commands[0].continue_on_failure is False

    def test_valid_config_multiple_commands(self, tmp_path: Path) -> None:
        """Test loading multiple valid setup commands."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[[code.setup]]
name = "build-deps"
command = "npm install"
working_dir = "./frontend"
continue_on_failure = true

[[code.setup]]
name = "start-db"
command = "docker-compose up -d postgres"
"""
        )

        commands = load_setup_commands(tmp_path)

        assert len(commands) == 2
        assert commands[0].name == "build-deps"
        assert commands[0].command == "npm install"
        assert commands[0].working_dir == "./frontend"
        assert commands[0].continue_on_failure is True
        assert commands[1].name == "start-db"
        assert commands[1].command == "docker-compose up -d postgres"
        assert commands[1].working_dir is None
        assert commands[1].continue_on_failure is False

    def test_no_config_file_returns_empty(self, tmp_path: Path) -> None:
        """Test returns empty list when no config file exists."""
        commands = load_setup_commands(tmp_path)
        assert commands == []

    def test_no_code_section_returns_empty(self, tmp_path: Path) -> None:
        """Test returns empty list when no [code] section."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[worktree.file_sync]
patterns = [".env"]
"""
        )

        commands = load_setup_commands(tmp_path)
        assert commands == []

    def test_no_setup_in_code_section_returns_empty(self, tmp_path: Path) -> None:
        """Test returns empty list when [code] has no setup entries."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[code]
# No setup array
"""
        )

        commands = load_setup_commands(tmp_path)
        assert commands == []

    def test_missing_name_raises_error(self, tmp_path: Path) -> None:
        """Test missing 'name' field raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
command = "echo test"
"""
        )

        with pytest.raises(SetupConfigError, match="Missing required 'name' field"):
            load_setup_commands(tmp_path)

    def test_missing_command_raises_error(self, tmp_path: Path) -> None:
        """Test missing 'command' field raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
name = "my-setup"
"""
        )

        with pytest.raises(SetupConfigError, match="Missing required 'command' field"):
            load_setup_commands(tmp_path)

    def test_empty_name_raises_error(self, tmp_path: Path) -> None:
        """Test empty name field raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
name = "   "
command = "echo test"
"""
        )

        with pytest.raises(SetupConfigError, match="'name' cannot be empty"):
            load_setup_commands(tmp_path)

    def test_empty_command_raises_error(self, tmp_path: Path) -> None:
        """Test empty command field raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
name = "my-setup"
command = ""
"""
        )

        with pytest.raises(SetupConfigError, match="'command' cannot be empty"):
            load_setup_commands(tmp_path)

    def test_whitespace_only_command_raises_error(self, tmp_path: Path) -> None:
        """Test whitespace-only command field raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
name = "my-setup"
command = "   "
"""
        )

        with pytest.raises(SetupConfigError, match="'command' cannot be empty"):
            load_setup_commands(tmp_path)

    def test_unknown_keys_raises_error(self, tmp_path: Path) -> None:
        """Test unknown keys in config raise error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
name = "my-setup"
command = "echo test"
unknown_key = "value"
another_unknown = 123
"""
        )

        with pytest.raises(SetupConfigError, match="Unknown keys"):
            load_setup_commands(tmp_path)

    def test_non_string_name_raises_error(self, tmp_path: Path) -> None:
        """Test non-string name raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
name = 123
command = "echo test"
"""
        )

        with pytest.raises(SetupConfigError, match="'name' must be a string"):
            load_setup_commands(tmp_path)

    def test_non_string_command_raises_error(self, tmp_path: Path) -> None:
        """Test non-string command raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
name = "my-setup"
command = 123
"""
        )

        with pytest.raises(SetupConfigError, match="'command' must be a string"):
            load_setup_commands(tmp_path)

    def test_non_string_working_dir_raises_error(self, tmp_path: Path) -> None:
        """Test non-string working_dir raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
name = "my-setup"
command = "echo test"
working_dir = 123
"""
        )

        with pytest.raises(SetupConfigError, match="'working_dir' must be a string"):
            load_setup_commands(tmp_path)

    def test_non_boolean_continue_on_failure_raises_error(self, tmp_path: Path) -> None:
        """Test non-boolean continue_on_failure raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[[code.setup]]
name = "my-setup"
command = "echo test"
continue_on_failure = "yes"
"""
        )

        with pytest.raises(SetupConfigError, match="'continue_on_failure' must be a boolean"):
            load_setup_commands(tmp_path)

    def test_code_section_not_table_raises_error(self, tmp_path: Path) -> None:
        """Test [code] section that is not a table raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
code = "not a table"
"""
        )

        with pytest.raises(SetupConfigError, match="\\[code\\] section must be a table"):
            load_setup_commands(tmp_path)

    def test_setup_not_array_raises_error(self, tmp_path: Path) -> None:
        """Test [code.setup] that is not an array raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code]
setup = "not an array"
"""
        )

        with pytest.raises(SetupConfigError, match="\\[code.setup\\] must be an array"):
            load_setup_commands(tmp_path)


class TestRunSetupCommands:
    """Tests for run_setup_commands function."""

    def test_executes_commands_in_order(self, tmp_path: Path) -> None:
        """Test commands execute in order they are defined."""
        # Create repo root and worktree directories
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        # Create marker file to track execution order
        marker_file = worktree_path / "order.txt"

        commands = [
            SetupCommand(name="first", command=f"echo 1 >> {marker_file}"),
            SetupCommand(name="second", command=f"echo 2 >> {marker_file}"),
            SetupCommand(name="third", command=f"echo 3 >> {marker_file}"),
        ]

        run_setup_commands(
            commands,
            repo_root=repo_root,
            worktree_path=worktree_path,
            plan_id="test-plan",
            plan_path=repo_root / "plan.md",
        )

        # Verify order
        assert marker_file.exists()
        lines = marker_file.read_text().strip().split("\n")
        assert lines == ["1", "2", "3"]

    def test_injects_weft_environment_variables(self, tmp_path: Path) -> None:
        """Test WEFT_* variables are injected into command environment."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()
        plan_path = repo_root / "plan.md"

        # Create a script that captures env vars
        output_file = worktree_path / "env_dump.txt"
        commands = [
            SetupCommand(
                name="dump-env",
                command=f"env | grep WEFT_ > {output_file}",
            )
        ]

        run_setup_commands(
            commands,
            repo_root=repo_root,
            worktree_path=worktree_path,
            plan_id="test-plan-123",
            plan_path=plan_path,
        )

        # Verify env vars were set
        assert output_file.exists()
        env_content = output_file.read_text()
        assert f"WEFT_REPO_ROOT={repo_root.resolve()}" in env_content
        assert f"WEFT_WORKTREE_PATH={worktree_path.resolve()}" in env_content
        assert "WEFT_PLAN_ID=test-plan-123" in env_content
        assert f"WEFT_PLAN_PATH={plan_path.resolve()}" in env_content

    def test_injected_vars_override_existing(self, tmp_path: Path) -> None:
        """Test WEFT_* variables override any existing env vars."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        output_file = worktree_path / "repo_root.txt"
        commands = [
            SetupCommand(
                name="check-override",
                command=f"echo $WEFT_REPO_ROOT > {output_file}",
            )
        ]

        # Set conflicting env var
        with patch.dict(os.environ, {"WEFT_REPO_ROOT": "/original/path"}):
            run_setup_commands(
                commands,
                repo_root=repo_root,
                worktree_path=worktree_path,
                plan_id="test",
                plan_path=repo_root / "plan.md",
            )

        # Verify our value was used, not the original
        content = output_file.read_text().strip()
        assert content == str(repo_root.resolve())

    def test_uses_repo_root_as_default_working_dir(self, tmp_path: Path) -> None:
        """Test commands use repo root as default working directory."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        output_file = worktree_path / "cwd.txt"
        commands = [
            SetupCommand(name="check-cwd", command=f"pwd > {output_file}")
        ]

        run_setup_commands(
            commands,
            repo_root=repo_root,
            worktree_path=worktree_path,
            plan_id="test",
            plan_path=repo_root / "plan.md",
        )

        cwd = output_file.read_text().strip()
        assert cwd == str(repo_root.resolve())

    def test_resolves_custom_working_dir(self, tmp_path: Path) -> None:
        """Test custom working_dir is resolved relative to repo root."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        subdir = repo_root / "services"
        subdir.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        output_file = worktree_path / "cwd.txt"
        commands = [
            SetupCommand(
                name="check-cwd",
                command=f"pwd > {output_file}",
                working_dir="./services",
            )
        ]

        run_setup_commands(
            commands,
            repo_root=repo_root,
            worktree_path=worktree_path,
            plan_id="test",
            plan_path=repo_root / "plan.md",
        )

        cwd = output_file.read_text().strip()
        assert cwd == str(subdir.resolve())

    def test_invalid_working_dir_raises_error(self, tmp_path: Path) -> None:
        """Test non-existent working_dir raises error."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        commands = [
            SetupCommand(
                name="bad-cwd",
                command="echo test",
                working_dir="./nonexistent",
            )
        ]

        with pytest.raises(SetupExecutionError, match="Working directory does not exist"):
            run_setup_commands(
                commands,
                repo_root=repo_root,
                worktree_path=worktree_path,
                plan_id="test",
                plan_path=repo_root / "plan.md",
            )

    def test_working_dir_outside_repo_raises_error(self, tmp_path: Path) -> None:
        """Test working_dir that escapes repo root raises error."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        commands = [
            SetupCommand(
                name="escape-attempt",
                command="echo test",
                working_dir="../outside",
            )
        ]

        with pytest.raises(SetupExecutionError, match="escapes repository root"):
            run_setup_commands(
                commands,
                repo_root=repo_root,
                worktree_path=worktree_path,
                plan_id="test",
                plan_path=repo_root / "plan.md",
            )

    def test_absolute_working_dir_raises_error(self, tmp_path: Path) -> None:
        """Test absolute working_dir raises error with clear message."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        commands = [
            SetupCommand(
                name="absolute-path",
                command="echo test",
                working_dir="/tmp",
            )
        ]

        with pytest.raises(SetupExecutionError, match="relative path.*absolute"):
            run_setup_commands(
                commands,
                repo_root=repo_root,
                worktree_path=worktree_path,
                plan_id="test",
                plan_path=repo_root / "plan.md",
            )

    def test_working_dir_with_dot_and_dotdot(self, tmp_path: Path) -> None:
        """Test working_dir with . and .. that stays within repo works."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        subdir = repo_root / "a" / "b"
        subdir.mkdir(parents=True)
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        output_file = worktree_path / "cwd.txt"
        commands = [
            SetupCommand(
                name="dotdot-within",
                command=f"pwd > {output_file}",
                # a/b/../b/./. resolves to a/b
                working_dir="./a/b/../b/./.",
            )
        ]

        run_setup_commands(
            commands,
            repo_root=repo_root,
            worktree_path=worktree_path,
            plan_id="test",
            plan_path=repo_root / "plan.md",
        )

        cwd = output_file.read_text().strip()
        assert cwd == str(subdir.resolve())

    def test_aborts_on_first_failure_by_default(self, tmp_path: Path) -> None:
        """Test execution aborts on first failure when continue_on_failure=False."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        marker_file = worktree_path / "executed.txt"
        commands = [
            SetupCommand(name="first", command=f"echo first >> {marker_file}"),
            SetupCommand(name="fail", command="exit 1"),
            SetupCommand(name="third", command=f"echo third >> {marker_file}"),
        ]

        with pytest.raises(SetupExecutionError, match="'fail' failed"):
            run_setup_commands(
                commands,
                repo_root=repo_root,
                worktree_path=worktree_path,
                plan_id="test",
                plan_path=repo_root / "plan.md",
            )

        # Only first should have executed
        content = marker_file.read_text()
        assert "first" in content
        assert "third" not in content

    def test_continues_when_continue_on_failure_true(self, tmp_path: Path) -> None:
        """Test execution continues when continue_on_failure=True."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        marker_file = worktree_path / "executed.txt"
        commands = [
            SetupCommand(name="first", command=f"echo first >> {marker_file}"),
            SetupCommand(name="fail", command="exit 1", continue_on_failure=True),
            SetupCommand(name="third", command=f"echo third >> {marker_file}"),
        ]

        # Should not raise
        run_setup_commands(
            commands,
            repo_root=repo_root,
            worktree_path=worktree_path,
            plan_id="test",
            plan_path=repo_root / "plan.md",
        )

        # Both first and third should have executed
        content = marker_file.read_text()
        assert "first" in content
        assert "third" in content

    def test_multiple_failures_first_continues_second_aborts(self, tmp_path: Path) -> None:
        """Test multiple failures: first continues, second aborts."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        marker_file = worktree_path / "executed.txt"
        commands = [
            SetupCommand(name="first", command=f"echo first >> {marker_file}"),
            SetupCommand(name="fail1", command="exit 1", continue_on_failure=True),
            SetupCommand(name="second", command=f"echo second >> {marker_file}"),
            SetupCommand(name="fail2", command="exit 1", continue_on_failure=False),
            SetupCommand(name="third", command=f"echo third >> {marker_file}"),
        ]

        with pytest.raises(SetupExecutionError, match="'fail2' failed"):
            run_setup_commands(
                commands,
                repo_root=repo_root,
                worktree_path=worktree_path,
                plan_id="test",
                plan_path=repo_root / "plan.md",
            )

        content = marker_file.read_text()
        assert "first" in content
        assert "second" in content
        assert "third" not in content

    def test_captures_output_on_failure(self, tmp_path: Path) -> None:
        """Test command output is captured and shown on failure."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        commands = [
            SetupCommand(
                name="verbose-fail",
                command="echo 'stdout message' && echo 'stderr message' >&2 && exit 1",
            )
        ]

        with pytest.raises(SetupExecutionError) as exc_info:
            run_setup_commands(
                commands,
                repo_root=repo_root,
                worktree_path=worktree_path,
                plan_id="test",
                plan_path=repo_root / "plan.md",
            )

        error_message = str(exc_info.value)
        assert "stdout message" in error_message
        assert "stderr message" in error_message
        assert "'verbose-fail' failed" in error_message

    def test_succeeds_silently_when_commands_pass(self, tmp_path: Path) -> None:
        """Test successful commands don't show output."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        marker_file = worktree_path / "done.txt"
        commands = [
            SetupCommand(
                name="quiet-success",
                command=f"echo 'lots of output' && touch {marker_file}",
            )
        ]

        # Should not raise
        run_setup_commands(
            commands,
            repo_root=repo_root,
            worktree_path=worktree_path,
            plan_id="test",
            plan_path=repo_root / "plan.md",
        )

        assert marker_file.exists()

    def test_empty_commands_list_is_noop(self, tmp_path: Path) -> None:
        """Test empty commands list does nothing."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        # Should not raise
        run_setup_commands(
            commands=[],
            repo_root=repo_root,
            worktree_path=worktree_path,
            plan_id="test",
            plan_path=repo_root / "plan.md",
        )

    def test_working_dir_is_file_raises_error(self, tmp_path: Path) -> None:
        """Test working_dir that is a file raises error."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        file_path = repo_root / "not_a_dir.txt"
        file_path.write_text("I am a file")
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        commands = [
            SetupCommand(
                name="file-as-dir",
                command="echo test",
                working_dir="./not_a_dir.txt",
            )
        ]

        with pytest.raises(SetupExecutionError, match="not a directory"):
            run_setup_commands(
                commands,
                repo_root=repo_root,
                worktree_path=worktree_path,
                plan_id="test",
                plan_path=repo_root / "plan.md",
            )

    def test_failure_shows_working_dir_in_error(self, tmp_path: Path) -> None:
        """Test failure error message includes working directory if set."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        subdir = repo_root / "subdir"
        subdir.mkdir()
        worktree_path = tmp_path / "worktree"
        worktree_path.mkdir()

        commands = [
            SetupCommand(
                name="fail-with-dir",
                command="exit 1",
                working_dir="./subdir",
            )
        ]

        with pytest.raises(SetupExecutionError) as exc_info:
            run_setup_commands(
                commands,
                repo_root=repo_root,
                worktree_path=worktree_path,
                plan_id="test",
                plan_path=repo_root / "plan.md",
            )

        assert "Working directory: ./subdir" in str(exc_info.value)
