"""Tests for finalize_command module.

This module tests the finalize command functionality, including:
- Unit tests for private helper functions
- Integration tests for the main run_finalize_command function
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import lw_coder.finalize_command as finalize_command
from lw_coder.finalize_command import (
    FinalizeCommandError,
    run_finalize_command,
)


# =============================================================================
# Unit tests for helper functions
# =============================================================================


def test_move_plan_to_worktree_success(tmp_path: Path) -> None:
    """Test successful plan file move to worktree."""
    # Setup
    plan_path = tmp_path / "test-plan.md"
    plan_path.write_text("# Test Plan")

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Execute
    finalize_command._move_plan_to_worktree(plan_path, worktree_path, "test-plan")

    # Assert
    dest_file = worktree_path / ".lw_coder" / "tasks" / "test-plan.md"
    assert dest_file.exists()
    assert dest_file.read_text() == "# Test Plan"
    # Verify source file no longer exists
    assert not plan_path.exists()


# =============================================================================
# Integration tests for run_finalize_command
# =============================================================================


def test_run_finalize_command_no_uncommitted_changes(monkeypatch, tmp_path: Path, caplog, mock_executor_factory) -> None:
    """Test finalize command fails when there are no uncommitted changes."""
    # Setup
    plan_path = tmp_path / "test-plan.md"
    plan_content = """---
plan_id: test-plan
git_sha: abcd1234abcd1234abcd1234abcd1234abcd1234
status: coding
evaluation_notes: []
---

# Test Plan
"""
    plan_path.write_text(plan_content)

    # Mock dependencies
    monkeypatch.setattr(finalize_command, "find_repo_root", lambda start_path=None: tmp_path)
    monkeypatch.setattr(
        finalize_command, "validate_worktree_exists",
        lambda repo_root, plan_id: tmp_path / "worktree"
    )
    monkeypatch.setattr(finalize_command, "has_uncommitted_changes", lambda path: False)

    # Mock executor
    from lw_coder.executors import ExecutorRegistry
    mock_executor = mock_executor_factory("claude-code")
    monkeypatch.setattr(ExecutorRegistry, "get_executor", lambda tool: mock_executor)

    # Execute
    caplog.set_level(logging.ERROR)
    exit_code = run_finalize_command(plan_path, tool="claude-code")

    # Assert
    assert exit_code == 1
    assert "No uncommitted changes" in caplog.text


def test_run_finalize_command_invalid_plan_file(monkeypatch, tmp_path: Path, caplog, mock_executor_factory) -> None:
    """Test finalize command fails with invalid plan file."""
    # Setup - plan file without proper YAML frontmatter
    plan_path = tmp_path / "test-plan.md"
    plan_path.write_text("# Invalid Plan - no frontmatter")

    # Mock dependencies
    monkeypatch.setattr(finalize_command, "find_repo_root", lambda start_path=None: tmp_path)

    # Mock executor
    from lw_coder.executors import ExecutorRegistry
    mock_executor = mock_executor_factory("claude-code")
    monkeypatch.setattr(ExecutorRegistry, "get_executor", lambda tool: mock_executor)

    # Execute
    caplog.set_level(logging.ERROR)
    exit_code = run_finalize_command(plan_path, tool="claude-code")

    # Assert
    assert exit_code == 1


def test_run_finalize_command_auth_failure(monkeypatch, tmp_path: Path, caplog) -> None:
    """Test finalize command fails when executor authentication fails."""
    # Setup
    plan_path = tmp_path / "test-plan.md"
    plan_content = """---
plan_id: test-plan
git_sha: abcd1234abcd1234abcd1234abcd1234abcd1234
status: coding
evaluation_notes: []
---

# Test Plan
"""
    plan_path.write_text(plan_content)

    # Mock executor with failing auth
    from lw_coder.executors import ExecutorError, ExecutorRegistry

    def mock_check_auth():
        raise ExecutorError("Authentication failed: API key not found")

    mock_executor = SimpleNamespace(
        check_auth=mock_check_auth,
        build_command=lambda p, model: f'claude --model {model} "$(cat {p})"',
        get_env_vars=lambda factory_dir: None
    )
    monkeypatch.setattr(ExecutorRegistry, "get_executor", lambda tool: mock_executor)

    # Execute
    caplog.set_level(logging.ERROR)
    exit_code = run_finalize_command(plan_path, tool="claude-code")

    # Assert
    assert exit_code == 1
    assert "Authentication failed" in caplog.text


def test_run_finalize_command_cleanup_on_success(monkeypatch, tmp_path: Path, caplog, mock_executor_factory) -> None:
    """Test finalize command cleans up worktree and branch on successful exit."""
    # Setup
    plan_path = tmp_path / "test-plan.md"
    plan_content = """---
plan_id: test-plan
git_sha: abcd1234abcd1234abcd1234abcd1234abcd1234
status: coding
evaluation_notes: []
---

# Test Plan
"""
    plan_path.write_text(plan_content)

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Mock dependencies
    monkeypatch.setattr(finalize_command, "find_repo_root", lambda start_path=None: tmp_path)
    monkeypatch.setattr(
        finalize_command, "validate_worktree_exists",
        lambda repo_root, plan_id: worktree_path
    )
    monkeypatch.setattr(finalize_command, "has_uncommitted_changes", lambda path: True)
    monkeypatch.setattr(
        finalize_command, "load_prompt_template",
        lambda tool, template_name: "Finalize workflow for {PLAN_ID}"
    )
    monkeypatch.setattr(finalize_command, "host_runner_config", lambda **kwargs: kwargs)
    monkeypatch.setattr(finalize_command, "build_host_command", lambda config: (["echo"], {}))

    # Mock verification to return True
    monkeypatch.setattr(finalize_command, "verify_branch_merged_to_main", lambda repo_root, branch: True)

    # Mock subprocess for executor (successful exit)
    mock_result = SimpleNamespace(returncode=0)
    subprocess_calls = []

    def mock_subprocess_run(*args, **kwargs):
        subprocess_calls.append((args, kwargs))
        # First call is the executor, return success
        if len(subprocess_calls) == 1:
            return mock_result
        # Subsequent calls are cleanup commands
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    # Mock executor
    from lw_coder.executors import ExecutorRegistry
    mock_executor = mock_executor_factory("claude-code")
    monkeypatch.setattr(ExecutorRegistry, "get_executor", lambda tool: mock_executor)

    # Execute
    caplog.set_level(logging.INFO)
    exit_code = run_finalize_command(plan_path, tool="claude-code")

    # Assert
    assert exit_code == 0
    assert "Successfully cleaned up worktree and branch" in caplog.text

    # Verify cleanup commands were called
    assert len(subprocess_calls) >= 2  # executor + worktree remove + branch delete
    # Check that git worktree remove was called
    cleanup_calls = subprocess_calls[1:]
    worktree_remove_called = any(
        "worktree" in str(call[0]) and "remove" in str(call[0])
        for call in cleanup_calls
    )
    assert worktree_remove_called


def test_run_finalize_command_no_cleanup_on_failure(monkeypatch, tmp_path: Path, caplog, mock_executor_factory) -> None:
    """Test finalize command does not clean up worktree and branch on failure."""
    # Setup
    plan_path = tmp_path / "test-plan.md"
    plan_content = """---
plan_id: test-plan
git_sha: abcd1234abcd1234abcd1234abcd1234abcd1234
status: coding
evaluation_notes: []
---

# Test Plan
"""
    plan_path.write_text(plan_content)

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Mock dependencies
    monkeypatch.setattr(finalize_command, "find_repo_root", lambda start_path=None: tmp_path)
    monkeypatch.setattr(
        finalize_command, "validate_worktree_exists",
        lambda repo_root, plan_id: worktree_path
    )
    monkeypatch.setattr(finalize_command, "has_uncommitted_changes", lambda path: True)
    monkeypatch.setattr(
        finalize_command, "load_prompt_template",
        lambda tool, template_name: "Finalize workflow for {PLAN_ID}"
    )
    monkeypatch.setattr(finalize_command, "host_runner_config", lambda **kwargs: kwargs)
    monkeypatch.setattr(finalize_command, "build_host_command", lambda config: (["echo"], {}))

    # Mock subprocess for executor (failure exit)
    mock_result = SimpleNamespace(returncode=1)
    subprocess_calls = []

    def mock_subprocess_run(*args, **kwargs):
        subprocess_calls.append((args, kwargs))
        return mock_result

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    # Mock executor
    from lw_coder.executors import ExecutorRegistry
    mock_executor = mock_executor_factory("claude-code")
    monkeypatch.setattr(ExecutorRegistry, "get_executor", lambda tool: mock_executor)

    # Execute
    caplog.set_level(logging.INFO)
    exit_code = run_finalize_command(plan_path, tool="claude-code")

    # Assert
    assert exit_code == 1
    assert "Worktree and branch left intact for manual recovery" in caplog.text

    # Verify only executor was called, no cleanup commands
    assert len(subprocess_calls) == 1


def test_run_finalize_command_no_cleanup_if_verification_fails(monkeypatch, tmp_path: Path, caplog, mock_executor_factory) -> None:
    """Test finalize command does not clean up if branch verification fails."""
    # Setup
    plan_path = tmp_path / "test-plan.md"
    plan_content = """---
plan_id: test-plan
git_sha: abcd1234abcd1234abcd1234abcd1234abcd1234
status: coding
evaluation_notes: []
---

# Test Plan
"""
    plan_path.write_text(plan_content)

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Mock dependencies
    monkeypatch.setattr(finalize_command, "find_repo_root", lambda start_path=None: tmp_path)
    monkeypatch.setattr(
        finalize_command, "validate_worktree_exists",
        lambda repo_root, plan_id: worktree_path
    )
    monkeypatch.setattr(finalize_command, "has_uncommitted_changes", lambda path: True)
    monkeypatch.setattr(
        finalize_command, "load_prompt_template",
        lambda tool, template_name: "Finalize workflow for {PLAN_ID}"
    )
    monkeypatch.setattr(finalize_command, "host_runner_config", lambda **kwargs: kwargs)
    monkeypatch.setattr(finalize_command, "build_host_command", lambda config: (["echo"], {}))

    # Mock verification to return False (branch not merged)
    monkeypatch.setattr(finalize_command, "verify_branch_merged_to_main", lambda repo_root, branch: False)

    # Mock subprocess for executor (successful exit)
    mock_result = SimpleNamespace(returncode=0)
    subprocess_calls = []

    def mock_subprocess_run(*args, **kwargs):
        subprocess_calls.append((args, kwargs))
        return mock_result

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    # Mock executor
    from lw_coder.executors import ExecutorRegistry
    mock_executor = mock_executor_factory("claude-code")
    monkeypatch.setattr(ExecutorRegistry, "get_executor", lambda tool: mock_executor)

    # Execute
    caplog.set_level(logging.WARNING)
    exit_code = run_finalize_command(plan_path, tool="claude-code")

    # Assert
    assert exit_code == 1
    assert "was not merged into main - skipping cleanup" in caplog.text

    # Verify only executor was called, no cleanup commands
    assert len(subprocess_calls) == 1


# Integration tests for backup cleanup functionality


def test_backup_cleanup_called_after_successful_finalize(monkeypatch, tmp_path: Path, caplog, mock_executor_factory) -> None:
    """Test that cleanup_backup is called after successful finalize."""
    from unittest.mock import Mock

    # Setup plan file
    plan_path = tmp_path / "test-plan.md"
    plan_content = """---
plan_id: test-plan
git_sha: abcd1234abcd1234abcd1234abcd1234abcd1234
status: implemented
evaluation_notes: []
---

# Test Plan
"""
    plan_path.write_text(plan_content)

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Mock cleanup_backup to track calls
    mock_cleanup_backup = Mock()
    monkeypatch.setattr(finalize_command, "cleanup_backup", mock_cleanup_backup)

    # Mock dependencies
    monkeypatch.setattr(finalize_command, "find_repo_root", lambda start_path=None: tmp_path)
    monkeypatch.setattr(
        finalize_command, "validate_worktree_exists",
        lambda repo_root, plan_id: worktree_path
    )
    monkeypatch.setattr(finalize_command, "has_uncommitted_changes", lambda path: True)
    monkeypatch.setattr(
        finalize_command, "load_prompt_template",
        lambda tool, template_name: "Finalize workflow for {PLAN_ID}"
    )
    monkeypatch.setattr(finalize_command, "host_runner_config", lambda **kwargs: kwargs)
    monkeypatch.setattr(finalize_command, "build_host_command", lambda config: (["echo"], {}))

    # Mock verification to return True (branch was merged)
    monkeypatch.setattr(finalize_command, "verify_branch_merged_to_main", lambda repo_root, branch: True)

    # Mock cleanup functions to succeed
    monkeypatch.setattr(finalize_command, "_cleanup_worktree_and_branch", lambda repo_root, worktree_path, plan_id: None)

    # Mock subprocess for executor (successful exit)
    mock_result = SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_result)

    # Mock executor
    from lw_coder.executors import ExecutorRegistry
    mock_executor = mock_executor_factory("claude-code")
    monkeypatch.setattr(ExecutorRegistry, "get_executor", lambda tool: mock_executor)

    # Execute
    exit_code = run_finalize_command(plan_path, tool="claude-code")

    # Assert
    assert exit_code == 0
    mock_cleanup_backup.assert_called_once_with(tmp_path, "test-plan")


def test_finalize_succeeds_with_idempotent_cleanup(monkeypatch, tmp_path: Path, caplog, mock_executor_factory) -> None:
    """Test that finalize succeeds when cleanup is idempotent (ref already gone)."""
    import logging
    from unittest.mock import Mock

    # Setup plan file
    plan_path = tmp_path / "test-plan.md"
    plan_content = """---
plan_id: test-plan
git_sha: abcd1234abcd1234abcd1234abcd1234abcd1234
status: implemented
evaluation_notes: []
---

# Test Plan
"""
    plan_path.write_text(plan_content)

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Track cleanup_backup calls - it should be idempotent and not raise
    cleanup_called = []
    def mock_cleanup_backup_idempotent(repo_root, plan_id):
        cleanup_called.append((repo_root, plan_id))
        # Simulate idempotent behavior - logs but doesn't raise
        import logging
        logging.getLogger("lw_coder.plan_backup").debug(f"Backup reference already deleted: refs/plan-backups/{plan_id}")

    monkeypatch.setattr(finalize_command, "cleanup_backup", mock_cleanup_backup_idempotent)

    # Mock dependencies
    monkeypatch.setattr(finalize_command, "find_repo_root", lambda start_path=None: tmp_path)
    monkeypatch.setattr(
        finalize_command, "validate_worktree_exists",
        lambda repo_root, plan_id: worktree_path
    )
    monkeypatch.setattr(finalize_command, "has_uncommitted_changes", lambda path: True)
    monkeypatch.setattr(
        finalize_command, "load_prompt_template",
        lambda tool, template_name: "Finalize workflow for {PLAN_ID}"
    )
    monkeypatch.setattr(finalize_command, "host_runner_config", lambda **kwargs: kwargs)
    monkeypatch.setattr(finalize_command, "build_host_command", lambda config: (["echo"], {}))

    # Mock verification to return True (branch was merged)
    monkeypatch.setattr(finalize_command, "verify_branch_merged_to_main", lambda repo_root, branch: True)

    # Mock cleanup functions to succeed
    monkeypatch.setattr(finalize_command, "_cleanup_worktree_and_branch", lambda repo_root, worktree_path, plan_id: None)

    # Mock subprocess for executor (successful exit)
    mock_result = SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: mock_result)

    # Mock executor
    from lw_coder.executors import ExecutorRegistry
    mock_executor = mock_executor_factory("claude-code")
    monkeypatch.setattr(ExecutorRegistry, "get_executor", lambda tool: mock_executor)

    # Execute
    caplog.set_level(logging.INFO)
    exit_code = run_finalize_command(plan_path, tool="claude-code")

    # Assert - command should succeed with idempotent cleanup
    assert exit_code == 0
    assert len(cleanup_called) == 1
    assert cleanup_called[0] == (tmp_path, "test-plan")
