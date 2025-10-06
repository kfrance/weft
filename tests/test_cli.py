"""Tests for CLI interface.

This module tests the command-line interface including:
- Plan validation through CLI invocation
- Error handling and exit codes
- Debug flag functionality
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.conftest import write_plan


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_dir = Path(__file__).resolve().parent.parent / "src"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(src_dir)
        if not existing_pythonpath
        else f"{str(src_dir)}{os.pathsep}{existing_pythonpath}"
    )
    return subprocess.run(
        [sys.executable, "-m", "lw_coder.cli", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=30,
    )


def test_cli_success(git_repo):
    repo = git_repo
    plan_path = repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-cli-success",
            "status": "draft",
        },
        body="# Refactor API\n\nEnsure docstrings are accurate."
    )

    result = _run_cli("code", str(plan_path))

    assert result.returncode == 0
    assert "Plan validation succeeded" in result.stderr
    assert "Worktree prepared at" in result.stderr
    assert result.stdout == ""


def test_cli_failure_invalid_sha(git_repo):
    repo = git_repo
    plan_path = repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": "f" * 40,
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-cli-invalid",
            "status": "draft",
        },
    )

    result = _run_cli("code", str(plan_path))

    assert result.returncode == 1
    assert "Plan validation failed" in result.stderr
    assert "does not exist" in result.stderr
    assert result.stdout == ""


def test_cli_debug_flag(git_repo):
    repo = git_repo
    plan_path = repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": repo.latest_commit(),
            "evaluation_notes": ["Debug flag test"],
            "plan_id": "plan-debug-test",
            "status": "draft",
        },
        body="# Debug Test Plan\n\nValidate debug logging."
    )

    result = _run_cli("code", str(plan_path), "--debug")

    assert result.returncode == 0
    assert "Plan validation succeeded" in result.stderr
    assert "Worktree prepared at" in result.stderr
    assert result.stdout == ""


def test_cli_plan_command_success(git_repo):
    repo = git_repo
    plan_path = repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": repo.latest_commit(),
            "evaluation_notes": ["Plan command test"],
            "plan_id": "plan-command-test",
            "status": "draft",
        },
        body="# Plan Command Test\n\nTest the plan subcommand."
    )

    result = _run_cli("plan", str(plan_path))

    assert result.returncode == 0
    assert "Plan validation succeeded" in result.stderr
    assert "Worktree prepared at" in result.stderr
    assert result.stdout == ""


def test_cli_plan_command_reuses_worktree(git_repo):
    """Test that running plan command twice reuses the same worktree."""
    repo = git_repo
    plan_path = repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": repo.latest_commit(),
            "evaluation_notes": ["Reuse worktree test"],
            "plan_id": "plan-reuse-test",
            "status": "draft",
        },
        body="# Reuse Worktree Test\n\nTest worktree reuse."
    )

    # Run first time
    result1 = _run_cli("plan", str(plan_path))
    assert result1.returncode == 0

    # Run second time
    result2 = _run_cli("plan", str(plan_path))
    assert result2.returncode == 0
    assert "Worktree prepared at" in result2.stderr


def test_cli_code_command_with_worktree(git_repo):
    """Test that code command creates and reports worktree path."""
    repo = git_repo
    plan_path = repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": repo.latest_commit(),
            "evaluation_notes": ["Code with worktree test"],
            "plan_id": "code-worktree-test",
            "status": "draft",
        },
        body="# Code Command Test\n\nTest code command with worktree."
    )

    result = _run_cli("code", str(plan_path))

    assert result.returncode == 0
    assert "Plan validation succeeded" in result.stderr
    assert "Worktree prepared at" in result.stderr
    worktree_path = repo.path / ".lw_coder" / "worktrees" / "code-worktree-test"
    assert worktree_path.exists()
