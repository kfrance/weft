"""Integration tests for finalize command flow.

Tests the finalize command orchestration with mocked executor in an isolated
test environment. These tests verify the full workflow without running the
interactive Claude Code session.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.helpers import GitRepo, write_plan
from weft.finalize_command import run_finalize_command
from weft.init_command import run_init_command


@pytest.fixture
def initialized_repo(git_repo: GitRepo) -> GitRepo:
    """Create a git repo with weft initialized.

    Runs `weft init --yes` to set up `.weft/prompts/active/` with finalize prompts.
    """
    with patch("weft.init_command.find_repo_root", return_value=git_repo.path):
        result = run_init_command(force=False, yes=True)
        assert result == 0, "Failed to initialize weft"

    return git_repo


@pytest.fixture
def plan_with_worktree(initialized_repo: GitRepo) -> tuple[GitRepo, Path, Path, str]:
    """Create a plan file with an associated worktree.

    Returns:
        Tuple of (repo, plan_path, worktree_path, plan_id)
    """
    plan_id = "test-finalize-plan"

    # Create a plan file
    plan_path = initialized_repo.path / ".weft" / "tasks" / f"{plan_id}.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    write_plan(
        plan_path,
        {
            "plan_id": plan_id,
            "git_sha": initialized_repo.latest_commit(),
            "status": "coding",
            "evaluation_notes": [],
        },
        body="# Test Plan\n\nThis is a test plan for finalize integration tests.",
    )

    # Create a worktree for the plan
    worktree_path = initialized_repo.path / ".weft" / "worktrees" / plan_id
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Create branch and worktree
    initialized_repo.run("checkout", "-b", plan_id)
    initialized_repo.run("checkout", "main")
    initialized_repo.run("worktree", "add", str(worktree_path), plan_id)

    # Add uncommitted changes in the worktree
    test_file = worktree_path / "new_feature.py"
    test_file.write_text("# New feature implementation\nprint('Hello from finalize test')")

    return initialized_repo, plan_path, worktree_path, plan_id


def test_finalize_flow_orchestration(plan_with_worktree, monkeypatch):
    """Test the finalize command orchestration with mocked executor.

    Verifies:
    - Worktree directory no longer exists after completion (when user confirms cleanup)
    - Branch still exists after completion (preserved)
    - Plan status is set to "done"
    """
    repo, plan_path, worktree_path, plan_id = plan_with_worktree

    # Mock find_repo_root to return the test repo
    from weft import finalize_command
    monkeypatch.setattr(finalize_command, "find_repo_root", lambda: repo.path)

    # Track subprocess calls and capture plan status before cleanup
    subprocess_calls = []
    captured_plan_status = None
    original_run = subprocess.run

    def mock_subprocess_run(args, **kwargs):
        subprocess_calls.append((args, kwargs))

        # Git commands should pass through
        if args and args[0] == "git":
            # Before worktree remove, capture the plan status from the moved plan file
            if "worktree" in args and "remove" in args:
                nonlocal captured_plan_status
                moved_plan = worktree_path / ".weft" / "tasks" / f"{plan_id}.md"
                if moved_plan.exists():
                    content = moved_plan.read_text()
                    # Extract status from front matter
                    import re
                    match = re.search(r'^status:\s*["\']?(\w+)["\']?', content, re.MULTILINE)
                    if match:
                        captured_plan_status = match.group(1)
            return original_run(args, **kwargs)

        # Executor command - return success
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    # Mock executor
    from weft.executors import ExecutorRegistry
    mock_executor = SimpleNamespace(
        check_auth=lambda: None,
        build_command=lambda p, model: f'claude --model {model} "$(cat {p})"',
        get_env_vars=lambda factory_dir: {}
    )
    monkeypatch.setattr(ExecutorRegistry, "get_executor", lambda tool: mock_executor)

    # Mock user confirmation to return True (since worktree will have uncommitted changes)
    monkeypatch.setattr(
        finalize_command, "_confirm_cleanup_with_changes",
        lambda worktree_path, modified, untracked: True
    )

    # Run the finalize command
    exit_code = run_finalize_command(plan_path, tool="claude-code")

    # Assertions
    assert exit_code == 0, "Finalize command should succeed"

    # Verify worktree no longer exists
    assert not worktree_path.exists(), "Worktree should be removed after successful finalize"

    # Verify branch still exists (preserved)
    branch_result = repo.run("branch", "--list", plan_id)
    assert plan_id in branch_result.stdout, "Branch should still exist after finalize (preserved)"

    # Verify plan status was set to "done" (captured before worktree removal)
    assert captured_plan_status == "done", f"Plan status should be 'done', got '{captured_plan_status}'"
