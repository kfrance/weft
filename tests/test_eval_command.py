"""Tests for eval command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lw_coder.eval_command import format_judge_results, run_eval_command
from lw_coder.judge_executor import JudgeResult


def test_format_judge_results() -> None:
    """Test formatting of judge results for console output."""
    results = [
        JudgeResult(
            judge_name="test-judge-1",
            score=0.85,
            feedback="Good code quality overall. Some minor issues.",
            weight=0.4,
        ),
        JudgeResult(
            judge_name="test-judge-2",
            score=0.92,
            feedback="Excellent plan compliance.",
            weight=0.6,
        ),
    ]

    plan_id = "test-plan"
    worktree_path = Path(".lw_coder/worktrees/test-plan")

    output = format_judge_results(results, plan_id, worktree_path)

    assert "test-plan" in output
    assert "test-judge-1" in output
    assert "test-judge-2" in output
    assert "0.85" in output
    assert "0.92" in output
    assert "Good code quality overall" in output
    assert "Excellent plan compliance" in output
    assert "Weight:" in output
    assert "Overall Weighted Score" in output


def test_format_judge_results_weighted_score() -> None:
    """Test weighted score calculation in formatted output."""
    results = [
        JudgeResult(
            judge_name="judge-1",
            score=0.8,
            feedback="Feedback 1",
            weight=0.5,
        ),
        JudgeResult(
            judge_name="judge-2",
            score=0.6,
            feedback="Feedback 2",
            weight=0.5,
        ),
    ]

    plan_id = "test-plan"
    worktree_path = Path(".lw_coder/worktrees/test-plan")

    output = format_judge_results(results, plan_id, worktree_path)

    # Weighted score should be (0.8 * 0.5 + 0.6 * 0.5) / (0.5 + 0.5) = 0.7
    assert "0.70" in output


def test_run_eval_command_worktree_not_found(tmp_path: Path, monkeypatch) -> None:
    """Test eval command when worktree doesn't exist."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create a plan file
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    plan_file.write_text(
        """---
plan_id: test-plan
status: coding
---

# Test Plan
"""
    )

    # Don't create worktree
    exit_code = run_eval_command("test-plan")

    assert exit_code == 1


def test_run_eval_command_plan_not_found(tmp_path: Path, monkeypatch) -> None:
    """Test eval command with non-existent plan."""
    monkeypatch.chdir(tmp_path)

    exit_code = run_eval_command("nonexistent-plan")

    assert exit_code == 1


def test_run_eval_command_no_judges(tmp_path: Path, monkeypatch) -> None:
    """Test eval command when no judges are found."""
    monkeypatch.chdir(tmp_path)

    # Create plan file
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    plan_file.write_text(
        """---
plan_id: test-plan
status: coding
---

# Test Plan
"""
    )

    # Create worktree
    worktree_dir = tmp_path / ".lw_coder" / "worktrees" / "test-plan"
    worktree_dir.mkdir(parents=True)

    # Initialize git repo in worktree
    subprocess.run(["git", "init"], cwd=worktree_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=worktree_dir,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=worktree_dir, check=True
    )

    # Create plan.md in worktree
    (worktree_dir / "plan.md").write_text("# Test Plan")
    subprocess.run(["git", "add", "plan.md"], cwd=worktree_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=worktree_dir,
        check=True,
        capture_output=True,
    )

    # Create empty judges directory
    judges_dir = tmp_path / ".lw_coder" / "judges"
    judges_dir.mkdir(parents=True)

    exit_code = run_eval_command("test-plan")

    assert exit_code == 1


def test_run_eval_command_success(tmp_path: Path, monkeypatch, capsys) -> None:
    """Test successful eval command execution with mocked judges."""
    monkeypatch.chdir(tmp_path)

    # Initialize main git repo (required for PlanResolver)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
    )

    # Create plan file
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    plan_file.write_text(
        """---
plan_id: test-plan
status: coding
---

# Test Plan
"""
    )

    # Commit the plan file to satisfy PlanResolver
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add plan"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Create worktree
    worktree_dir = tmp_path / ".lw_coder" / "worktrees" / "test-plan"
    worktree_dir.mkdir(parents=True)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=worktree_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=worktree_dir,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=worktree_dir, check=True
    )

    # Create plan.md
    (worktree_dir / "plan.md").write_text("# Test Plan Content")
    subprocess.run(["git", "add", "plan.md"], cwd=worktree_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=worktree_dir,
        check=True,
        capture_output=True,
    )

    # Create judges directory and judge file
    judges_dir = tmp_path / ".lw_coder" / "judges"
    judges_dir.mkdir(parents=True)
    judge_file = judges_dir / "test-judge.md"
    judge_file.write_text(
        """---
weight: 0.5
model: x-ai/grok-4.1-fast
---

Test judge instructions.
"""
    )

    # Mock the judge orchestrator to return test results
    mock_results = [
        JudgeResult(
            judge_name="test-judge",
            score=0.85,
            feedback="Test feedback",
            weight=0.5,
        )
    ]

    with patch("lw_coder.eval_command.execute_judges_parallel", return_value=mock_results):
        with patch("lw_coder.eval_command.get_openrouter_api_key", return_value="test_key"):
            exit_code = run_eval_command("test-plan")

    assert exit_code == 0

    # Check output
    captured = capsys.readouterr()
    assert "test-plan" in captured.out
    assert "test-judge" in captured.out
    assert "0.85" in captured.out
    assert "Test feedback" in captured.out
