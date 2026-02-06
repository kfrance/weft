"""Tests for code_command module.

Focused tests for the code_command module. Per CLAUDE.md, we don't test
interactive commands extensively - integration smoke tests cover the happy path.
These tests focus on:
- Pure function tests (_filter_env_vars)
- Sandbox dependency check integration tests (check_sandbox_dependencies in host_runner)
- Critical error path tests with minimal mocking
- Patch capture workflow test (happy path with mocked SDK and CLI)
- File sync command scope tests
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any
import pytest

import weft.code_command as code_command
import weft.host_runner as host_runner
from weft.code_command import (
    _filter_env_vars,
    run_code_command,
)
from weft.sandbox import SandboxDependencyError
from weft.patch_utils import EmptyPatchError, PatchCaptureError
from weft.plan_validator import PlanValidationError
from weft.worktree.file_sync import FileSyncConfig
from weft.worktree_utils import WorktreeError
from tests.helpers import write_plan


def test_run_code_command_validation_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with plan validation failure."""
    # Setup
    plan_path = tmp_path / "plan.md"

    # Mock sandbox dependency check to pass (test doesn't depend on real bubblewrap)
    monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

    # Mock load_plan_metadata to raise PlanValidationError
    def mock_load_plan_metadata(path):
        raise PlanValidationError("Invalid git_sha")

    # Apply monkeypatch
    monkeypatch.setattr(code_command, "load_plan_metadata", mock_load_plan_metadata)

    # Execute
    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    # Assert
    assert exit_code == 1
    assert "Plan validation failed" in caplog.text
    assert "Invalid git_sha" in caplog.text


def test_run_code_command_worktree_failure(monkeypatch, caplog, git_repo) -> None:
    """Test run_code_command with worktree preparation failure.

    Uses git_repo fixture for real git operations. Mocks load_prompts (required
    for claude-code tool to proceed) and ensure_worktree (the failing component).
    """
    plan_path = git_repo.path / "test-plan.md"
    write_plan(plan_path, {
        "git_sha": git_repo.latest_commit(),
        "plan_id": "test-plan-fail",
        "status": "draft",
    })

    # Mock sandbox dependency check to pass (test doesn't depend on real bubblewrap)
    monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

    # Mock load_prompts so we can reach the worktree preparation step
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

    # Mock the failing component
    def mock_ensure_worktree(metadata):
        raise WorktreeError("Failed to create worktree")

    monkeypatch.setattr(code_command, "ensure_worktree", mock_ensure_worktree)

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "Worktree preparation failed" in caplog.text
    assert "Failed to create worktree" in caplog.text


def test_filter_env_vars_with_patterns(monkeypatch) -> None:
    """Test _filter_env_vars with wildcard patterns."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "key123")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://api.openrouter.ai")
    monkeypatch.setenv("OTHER_VAR", "value")

    result = _filter_env_vars(["OPENROUTER_*"])

    assert "OPENROUTER_API_KEY" in result
    assert "OPENROUTER_BASE_URL" in result
    assert "OTHER_VAR" not in result


def test_filter_env_vars_with_star(monkeypatch) -> None:
    """Test _filter_env_vars with * pattern (all vars)."""
    monkeypatch.setenv("VAR1", "value1")
    monkeypatch.setenv("VAR2", "value2")

    result = _filter_env_vars(["*"])

    assert "VAR1" in result
    assert "VAR2" in result
    assert len(result) > 2  # Should include all env vars


def test_filter_env_vars_no_matches(monkeypatch) -> None:
    """Test _filter_env_vars when no vars match."""
    result = _filter_env_vars(["NONEXISTENT_*"])

    assert result == {}


class TestSandboxDependencyCheck:
    """Tests for sandbox dependency check integration in code command.

    Unit tests for check_sandbox_dependencies() itself are in test_sandbox.py.
    These tests verify that code_command properly handles the error when
    build_host_command raises SandboxDependencyError.
    """

    def test_run_code_command_fails_on_missing_sandbox_deps(
        self, monkeypatch, caplog, git_repo
    ) -> None:
        """Verify run_code_command fails when sandbox deps are missing.

        The check is now in build_host_command (host_runner.py), so we mock
        check_sandbox_dependencies there to raise SandboxDependencyError.
        """
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-sandbox-deps",
            "status": "draft",
        })

        # Mock check_sandbox_dependencies to raise
        def mock_check_deps() -> None:
            raise SandboxDependencyError(
                "Missing sandbox dependency: bubblewrap (bwrap). "
                "Weft sandbox requires this to be installed for filesystem isolation. "
                "Install with: sudo apt install bubblewrap"
            )

        monkeypatch.setattr(host_runner, "check_sandbox_dependencies", mock_check_deps)

        # Mock prompts so we can reach the build_host_command step
        mock_prompts = {
            "main_prompt": "Main prompt content",
            "code_review_auditor": "Code review prompt",
            "plan_alignment_checker": "Plan alignment prompt",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        # Create worktree
        worktree_path = git_repo.path / ".weft" / "worktrees" / "test-sandbox-deps"
        worktree_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        caplog.set_level(logging.ERROR)
        exit_code = run_code_command(plan_path)

        assert exit_code == 1
        assert "Sandbox dependency check failed" in caplog.text
        assert "bubblewrap" in caplog.text or "bwrap" in caplog.text


def test_run_code_command_fails_on_sandbox_config_error(
    monkeypatch, caplog, git_repo
) -> None:
    """Verify run_code_command fails when sandbox config is invalid.

    This test ensures that invalid sandbox configuration in .weft/config.toml
    is caught and reported with an appropriate error message.
    """
    from weft.sandbox import SandboxConfigError

    plan_path = git_repo.path / "test-plan.md"
    write_plan(plan_path, {
        "git_sha": git_repo.latest_commit(),
        "plan_id": "test-sandbox-config-error",
        "status": "draft",
    })

    # Mock sandbox dependency check to pass
    monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

    # Mock load_sandbox_config to raise SandboxConfigError
    def mock_load_sandbox_config(path):
        raise SandboxConfigError("Invalid TOML in config file: unexpected EOF")

    monkeypatch.setattr(code_command, "load_sandbox_config", mock_load_sandbox_config)

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "Failed to load sandbox configuration" in caplog.text
    assert "Invalid TOML" in caplog.text


def test_code_command_error_when_sha_mismatch(git_repo, caplog, monkeypatch) -> None:
    """Test run_code_command errors when plan SHA doesn't match HEAD.

    This is a critical safety feature that prevents coding against stale code.
    Uses git_repo fixture for real git operations - minimal mocking.
    """
    # Mock sandbox dependency check to pass (test doesn't depend on real bubblewrap)
    monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

    initial_sha = git_repo.latest_commit()
    extra_file = git_repo.path / "extra.txt"
    extra_file.write_text("extra", encoding="utf-8")
    git_repo.run("add", "extra.txt")
    git_repo.run("commit", "-m", "extra commit")
    head_sha = git_repo.latest_commit()
    assert head_sha != initial_sha

    plan_path = git_repo.path / "plan-mismatch.md"
    write_plan(
        plan_path,
        {
            "git_sha": initial_sha,
            "plan_id": "plan-mismatch",
            "status": "coding",
        },
    )

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "does not match repository HEAD" in caplog.text
    assert "uncommitted changes" in caplog.text or "rebasing" in caplog.text


class TestCodeCommandPatchCapture:
    """Tests for patch capture integration in code command."""

    def test_code_command_fails_on_empty_patch(self, monkeypatch, caplog, git_repo) -> None:
        """Test code command fails when SDK session produces no changes.

        Mocks the SDK session to succeed but capture_ai_patch raises EmptyPatchError
        because no files were modified.
        """
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-empty-patch",
            "status": "draft",
        })

        # Mock sandbox dependency check to pass (test doesn't depend on real bubblewrap)
        monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

        # Mock all the components needed to reach the patch capture step
        mock_prompts = {
            "main_prompt": "Main prompt content",
            "code_review_auditor": "Code review prompt",
            "plan_alignment_checker": "Plan alignment prompt",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        # Create a mock worktree path
        worktree_path = git_repo.path / ".weft" / "worktrees" / "test-empty-patch"
        worktree_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        # Mock capture_ai_patch to raise EmptyPatchError
        def mock_capture_ai_patch(wt_path):
            raise EmptyPatchError("SDK session produced no changes.")

        monkeypatch.setattr(code_command, "capture_ai_patch", mock_capture_ai_patch)

        caplog.set_level(logging.ERROR)
        exit_code = run_code_command(plan_path)

        assert exit_code == 1
        assert "no changes" in caplog.text.lower()

    def test_code_command_fails_on_patch_capture_error(self, monkeypatch, caplog, git_repo) -> None:
        """Test code command fails when patch capture encounters a git error.

        Mocks capture_ai_patch to raise PatchCaptureError simulating git failure.
        """
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-patch-error",
            "status": "draft",
        })

        # Mock sandbox dependency check to pass (test doesn't depend on real bubblewrap)
        monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

        mock_prompts = {
            "main_prompt": "Main prompt content",
            "code_review_auditor": "Code review prompt",
            "plan_alignment_checker": "Plan alignment prompt",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        worktree_path = git_repo.path / ".weft" / "worktrees" / "test-patch-error"
        worktree_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        def mock_capture_ai_patch(wt_path):
            raise PatchCaptureError("Git command failed: mock error")

        monkeypatch.setattr(code_command, "capture_ai_patch", mock_capture_ai_patch)

        caplog.set_level(logging.ERROR)
        exit_code = run_code_command(plan_path)

        assert exit_code == 1
        assert "Failed to capture AI changes" in caplog.text

    def test_code_command_patch_capture_workflow(self, monkeypatch, caplog, git_repo) -> None:
        """Test happy path: SDK session creates changes, patch is captured.

        This test verifies the complete patch capture workflow:
        - SDK session runs and creates file changes
        - Patch is captured and saved to session directory
        - Worktree has no staged changes after capture
        - code_sdk_complete hook is called after patch is saved
        """
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-workflow",
            "status": "draft",
        })

        # Mock sandbox dependency check to pass (test doesn't depend on real bubblewrap)
        monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

        # Mock prompts
        mock_prompts = {
            "main_prompt": "Implement the feature",
            "code_review_auditor": "Code review prompt",
            "plan_alignment_checker": "Plan alignment prompt",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        # Track worktree path and simulate file changes in SDK session
        worktree_paths_used: list[Path] = []

        def mock_ensure_worktree(metadata: Any) -> Path:
            """Create a real worktree for the test."""
            worktree_path = git_repo.path / ".weft" / "worktrees" / metadata.plan_id
            worktree_path.mkdir(parents=True, exist_ok=True)

            # Initialize as a git worktree
            git_repo.run("worktree", "add", str(worktree_path), "HEAD")
            worktree_paths_used.append(worktree_path)
            return worktree_path

        monkeypatch.setattr(code_command, "ensure_worktree", mock_ensure_worktree)

        # Mock SDK session to create file changes in the worktree
        def mock_sdk_session(*args: Any, **kwargs: Any) -> str:
            """Simulate SDK session that creates file changes."""
            worktree_path = kwargs.get("worktree_path") or args[0]
            # Create a new file to simulate AI-generated changes
            new_file = worktree_path / "new_feature.py"
            new_file.write_text("def new_feature():\n    return 'implemented'\n", encoding="utf-8")
            return "mock-session-id-workflow"

        monkeypatch.setattr(code_command, "run_sdk_session_sync", mock_sdk_session)

        # Track hook calls
        hook_calls: list[tuple[str, dict]] = []

        def mock_trigger_hook(hook_name: str, context: dict) -> None:
            hook_calls.append((hook_name, context.copy()))

        monkeypatch.setattr(code_command, "trigger_hook", mock_trigger_hook)

        # Mock subprocess.run to skip CLI resume (returns success)
        original_subprocess_run = subprocess.run

        def mock_subprocess_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
            # Skip actual CLI execution but allow git commands
            if isinstance(cmd, list) and len(cmd) > 0:
                if cmd[0] == "git":
                    return original_subprocess_run(cmd, *args, **kwargs)
                # For CLI resume commands (claude -r ...), return success
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            return original_subprocess_run(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

        # Execute
        caplog.set_level(logging.INFO)
        exit_code = run_code_command(plan_path)

        # Verify exit code
        assert exit_code == 0, f"Expected success, got exit code {exit_code}"

        # Verify patch file exists in session directory
        session_dir = git_repo.path / ".weft" / "sessions" / "test-workflow" / "code"
        patch_path = session_dir / "ai_changes.patch"
        assert patch_path.exists(), f"Patch file should exist at {patch_path}"

        # Verify patch content contains the changes
        patch_content = patch_path.read_text(encoding="utf-8")
        assert "new_feature.py" in patch_content, "Patch should contain new_feature.py"
        assert "def new_feature" in patch_content, "Patch should contain the function definition"

        # Verify worktree has no staged changes
        assert len(worktree_paths_used) > 0, "Should have used a worktree"
        worktree_path = worktree_paths_used[0]
        result = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.stdout.strip() == "", "Worktree should have no staged changes after capture"

        # Verify code_sdk_complete hook was called
        sdk_complete_calls = [c for c in hook_calls if c[0] == "code_sdk_complete"]
        assert len(sdk_complete_calls) == 1, "code_sdk_complete hook should be called exactly once"

        # Verify hook context
        hook_context = sdk_complete_calls[0][1]
        assert "worktree_path" in hook_context
        assert "plan_path" in hook_context
        assert "plan_id" in hook_context
        assert hook_context["plan_id"] == "test-workflow"

        # Cleanup worktree
        try:
            git_repo.run("worktree", "remove", "--force", str(worktree_path))
        except subprocess.CalledProcessError:
            pass  # Cleanup is best-effort


# =============================================================================
# Tests for permission bypass flags in CLI resume command
# =============================================================================


class TestCodeCommandPermissionFlags:
    """Tests for permission bypass flags in code command's CLI resume command."""

    def test_cli_resume_with_empty_disallowed_commands(self, monkeypatch, git_repo) -> None:
        """Test CLI resume command works correctly when disallowed_commands is empty.

        When the [sandbox] section has no disallowed_commands, only --dangerously-skip-permissions
        should be added, without --disallowed-tools.
        """
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-empty-disallowed",
            "status": "draft",
        })

        # Create config.toml WITHOUT disallowed_commands
        config_dir = git_repo.path / ".weft"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.toml"
        config_path.write_text("""
[sandbox]
# No disallowed_commands configured
""")

        # Mock sandbox dependency check
        monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

        # Mock prompts
        mock_prompts = {
            "main_prompt": "Main prompt",
            "code_review_auditor": "Code review",
            "plan_alignment_checker": "Plan alignment",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        # Create worktree
        worktree_path = git_repo.path / ".weft" / "worktrees" / "test-empty-disallowed"
        worktree_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        # Track the command passed to host_runner_config
        captured_commands: list[str] = []

        def mock_host_runner_config(**kwargs):
            if "command" in kwargs:
                captured_commands.append(kwargs["command"])
            return kwargs

        monkeypatch.setattr(code_command, "host_runner_config", mock_host_runner_config)
        monkeypatch.setattr(code_command, "build_host_command", lambda config: (["echo"], {}))

        # Mock subprocess to return failure (stop execution after command is built)
        import subprocess as sp
        original_run = sp.run

        def mock_subprocess_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and len(cmd) > 0:
                if cmd[0] == "git":
                    return original_run(cmd, *args, **kwargs)
                return sp.CompletedProcess(cmd, returncode=1, stdout="", stderr="")
            return original_run(cmd, *args, **kwargs)

        monkeypatch.setattr(sp, "run", mock_subprocess_run)

        # Execute
        run_code_command(plan_path)

        # Verify we captured the CLI resume command
        assert len(captured_commands) > 0, "Should have captured at least one command"

        # Find the CLI resume command (claude -r ...)
        cli_resume_commands = [cmd for cmd in captured_commands if "claude -r" in cmd]
        assert len(cli_resume_commands) == 1, "Should have exactly one CLI resume command"

        cli_resume_cmd = cli_resume_commands[0]

        # Verify --dangerously-skip-permissions is present
        assert "--dangerously-skip-permissions" in cli_resume_cmd, (
            "CLI resume command must include --dangerously-skip-permissions for weft's sandbox"
        )

        # Verify --disallowed-tools is NOT present when disallowed_commands is empty
        assert "--disallowed-tools" not in cli_resume_cmd, (
            "CLI resume command should NOT include --disallowed-tools when no disallowed_commands configured"
        )

    def test_cli_resume_includes_permission_bypass_flags(self, monkeypatch, git_repo) -> None:
        """Test that CLI resume command includes --dangerously-skip-permissions and --disallowed-tools.

        The CLI resume command (claude -r <session_id> ...) is built directly in code_command.py,
        not through the executor. This test verifies that it includes the permission bypass flags
        for running inside weft's bwrap sandbox.
        """
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-permission-flags",
            "status": "draft",
        })

        # Create config.toml with disallowed_commands
        config_dir = git_repo.path / ".weft"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.toml"
        config_path.write_text("""
[sandbox]
disallowed_commands = ["git add:*", "git commit:*"]
""")

        # Mock sandbox dependency check
        monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

        # Mock prompts
        mock_prompts = {
            "main_prompt": "Main prompt",
            "code_review_auditor": "Code review",
            "plan_alignment_checker": "Plan alignment",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        # Create worktree
        worktree_path = git_repo.path / ".weft" / "worktrees" / "test-permission-flags"
        worktree_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        # Track the command passed to host_runner_config
        captured_commands: list[str] = []

        def mock_host_runner_config(**kwargs):
            if "command" in kwargs:
                captured_commands.append(kwargs["command"])
            return kwargs

        monkeypatch.setattr(code_command, "host_runner_config", mock_host_runner_config)
        monkeypatch.setattr(code_command, "build_host_command", lambda config: (["echo"], {}))

        # Mock subprocess to return failure (stop execution after command is built)
        import subprocess as sp
        original_run = sp.run

        def mock_subprocess_run(cmd, *args, **kwargs):
            if isinstance(cmd, list) and len(cmd) > 0:
                if cmd[0] == "git":
                    return original_run(cmd, *args, **kwargs)
                return sp.CompletedProcess(cmd, returncode=1, stdout="", stderr="")
            return original_run(cmd, *args, **kwargs)

        monkeypatch.setattr(sp, "run", mock_subprocess_run)

        # Execute
        run_code_command(plan_path)

        # Verify we captured the CLI resume command
        assert len(captured_commands) > 0, "Should have captured at least one command"

        # Find the CLI resume command (claude -r ...)
        cli_resume_commands = [cmd for cmd in captured_commands if "claude -r" in cmd]
        assert len(cli_resume_commands) == 1, "Should have exactly one CLI resume command"

        cli_resume_cmd = cli_resume_commands[0]

        # CRITICAL: Verify permission bypass flags are present
        assert "--dangerously-skip-permissions" in cli_resume_cmd, (
            "CLI resume command must include --dangerously-skip-permissions for weft's sandbox"
        )
        assert "--disallowed-tools" in cli_resume_cmd, (
            "CLI resume command must include --disallowed-tools from sandbox config"
        )
        assert "Bash(git add:*)" in cli_resume_cmd, (
            "CLI resume command should include disallowed command patterns"
        )
        assert "Bash(git commit:*)" in cli_resume_cmd, (
            "CLI resume command should include disallowed command patterns"
        )


class TestCodeCommandFileSync:
    """Tests for file sync command scope in code_command."""

    def test_file_sync_called_when_code_in_commands(self, monkeypatch, git_repo) -> None:
        """Test that sync_files_to_worktree is called when 'code' is in commands list."""
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-file-sync",
            "status": "draft",
        })

        # Mock sandbox dependency check
        monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

        # Mock prompts
        mock_prompts = {
            "main_prompt": "Main prompt",
            "code_review_auditor": "Code review",
            "plan_alignment_checker": "Plan alignment",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        # Create worktree
        worktree_path = git_repo.path / ".weft" / "worktrees" / "test-file-sync"
        worktree_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        # Mock config to include "code" in commands
        mock_config = FileSyncConfig(enabled=True, commands=["code"], patterns=[".env"])
        monkeypatch.setattr(code_command, "load_repo_config", lambda r: {})
        monkeypatch.setattr(code_command, "validate_worktree_file_sync_config", lambda c: mock_config)

        # Track sync_files_to_worktree calls
        sync_calls: list[tuple] = []

        def mock_sync(repo_root, worktree, cleanup):
            sync_calls.append((repo_root, worktree, cleanup))
            return 0

        monkeypatch.setattr(code_command, "sync_files_to_worktree", mock_sync)

        # Mock SDK to fail early (we only care about testing file sync call)
        def mock_sdk(*args, **kwargs):
            raise code_command.SDKRunnerError("Intentional test stop")

        monkeypatch.setattr(code_command, "run_sdk_session_sync", mock_sdk)

        # Execute (will fail at SDK stage, but file sync should have been called)
        run_code_command(plan_path)

        # Verify sync_files_to_worktree was called
        assert len(sync_calls) == 1
        assert sync_calls[0][0] == git_repo.path  # repo_root

    def test_file_sync_skipped_when_code_not_in_commands(self, monkeypatch, git_repo, caplog) -> None:
        """Test that sync_files_to_worktree is NOT called when 'code' is not in commands list."""
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-no-sync",
            "status": "draft",
        })

        monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

        mock_prompts = {
            "main_prompt": "Main prompt",
            "code_review_auditor": "Code review",
            "plan_alignment_checker": "Plan alignment",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        worktree_path = git_repo.path / ".weft" / "worktrees" / "test-no-sync"
        worktree_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        # Mock config with commands=["plan"] (no "code")
        mock_config = FileSyncConfig(enabled=True, commands=["plan"], patterns=[".env"])
        monkeypatch.setattr(code_command, "load_repo_config", lambda r: {})
        monkeypatch.setattr(code_command, "validate_worktree_file_sync_config", lambda c: mock_config)

        # Track sync_files_to_worktree calls
        sync_calls: list[tuple] = []

        def mock_sync(repo_root, worktree, cleanup):
            sync_calls.append((repo_root, worktree, cleanup))
            return 0

        monkeypatch.setattr(code_command, "sync_files_to_worktree", mock_sync)

        # Mock SDK to fail early
        def mock_sdk(*args, **kwargs):
            raise code_command.SDKRunnerError("Intentional test stop")

        monkeypatch.setattr(code_command, "run_sdk_session_sync", mock_sdk)

        caplog.set_level(logging.DEBUG)
        run_code_command(plan_path)

        # Verify sync_files_to_worktree was NOT called
        assert len(sync_calls) == 0
        assert "File sync skipped: 'code' not in commands list" in caplog.text

    def test_file_sync_skipped_when_commands_empty(self, monkeypatch, git_repo, caplog) -> None:
        """Test that sync_files_to_worktree is NOT called when commands is empty."""
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-empty-commands",
            "status": "draft",
        })

        monkeypatch.setattr(host_runner, "check_sandbox_dependencies", lambda: None)

        mock_prompts = {
            "main_prompt": "Main prompt",
            "code_review_auditor": "Code review",
            "plan_alignment_checker": "Plan alignment",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        worktree_path = git_repo.path / ".weft" / "worktrees" / "test-empty-commands"
        worktree_path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        # Mock config with commands=[] (empty)
        mock_config = FileSyncConfig(enabled=True, commands=[], patterns=[".env"])
        monkeypatch.setattr(code_command, "load_repo_config", lambda r: {})
        monkeypatch.setattr(code_command, "validate_worktree_file_sync_config", lambda c: mock_config)

        sync_calls: list[tuple] = []

        def mock_sync(repo_root, worktree, cleanup):
            sync_calls.append((repo_root, worktree, cleanup))
            return 0

        monkeypatch.setattr(code_command, "sync_files_to_worktree", mock_sync)

        def mock_sdk(*args, **kwargs):
            raise code_command.SDKRunnerError("Intentional test stop")

        monkeypatch.setattr(code_command, "run_sdk_session_sync", mock_sdk)

        caplog.set_level(logging.DEBUG)
        run_code_command(plan_path)

        # Verify sync_files_to_worktree was NOT called
        assert len(sync_calls) == 0
        assert "File sync skipped: 'code' not in commands list" in caplog.text
