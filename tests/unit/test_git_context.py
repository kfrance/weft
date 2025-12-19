"""Tests for git context gathering."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from weft.git_context import GitContextError, gather_git_context


def test_gather_git_context_basic(tmp_path: Path) -> None:
    """Test gathering git context from a worktree with changes."""
    # Create a git repo
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    subprocess.run(["git", "init"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=worktree, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=worktree, check=True)

    # Create and commit plan.md
    plan_file = worktree / "plan.md"
    plan_file.write_text("# Test Plan\nObjectives here.")

    subprocess.run(["git", "add", "plan.md"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=worktree, check=True, capture_output=True)

    # Make some changes
    test_file = worktree / "test.py"
    test_file.write_text("def test():\n    pass\n")

    plan_content, git_changes = gather_git_context(worktree)

    assert "Test Plan" in plan_content
    assert "Objectives here" in plan_content
    assert "Git Status" in git_changes
    assert "test.py" in git_changes


def test_gather_git_context_no_changes(tmp_path: Path) -> None:
    """Test gathering git context from worktree with no changes."""
    # Create a git repo
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    subprocess.run(["git", "init"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=worktree, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=worktree, check=True)

    # Create and commit plan.md
    plan_file = worktree / "plan.md"
    plan_file.write_text("# Test Plan\nNo changes.")

    subprocess.run(["git", "add", "plan.md"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=worktree, check=True, capture_output=True)

    plan_content, git_changes = gather_git_context(worktree)

    assert "Test Plan" in plan_content
    assert "no changes" in git_changes.lower()


def test_gather_git_context_worktree_not_found(tmp_path: Path) -> None:
    """Test gathering context from non-existent worktree."""
    worktree = tmp_path / "nonexistent"

    with pytest.raises(GitContextError, match="Worktree not found"):
        gather_git_context(worktree)


def test_gather_git_context_plan_not_found(tmp_path: Path) -> None:
    """Test gathering context when plan.md doesn't exist."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    subprocess.run(["git", "init"], cwd=worktree, check=True, capture_output=True)

    with pytest.raises(GitContextError, match="plan.md not found"):
        gather_git_context(worktree)


def test_gather_git_context_with_diff(tmp_path: Path) -> None:
    """Test gathering context with git diff output."""
    # Create a git repo
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    subprocess.run(["git", "init"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=worktree, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=worktree, check=True)

    # Create plan.md
    plan_file = worktree / "plan.md"
    plan_file.write_text("# Test Plan")

    subprocess.run(["git", "add", "plan.md"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=worktree, check=True, capture_output=True)

    # Create and stage a new file
    test_file = worktree / "test.py"
    test_file.write_text("def hello():\n    print('hello')\n")
    subprocess.run(["git", "add", "test.py"], cwd=worktree, check=True)

    plan_content, git_changes = gather_git_context(worktree)

    assert "Git Diff" in git_changes
    assert "+def hello()" in git_changes or "def hello()" in git_changes


def test_gather_git_context_changed_file_contents(tmp_path: Path) -> None:
    """Test that changed file contents are included in context."""
    # Create a git repo
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    subprocess.run(["git", "init"], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=worktree, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=worktree, check=True)

    # Create plan.md
    plan_file = worktree / "plan.md"
    plan_file.write_text("# Test Plan")

    subprocess.run(["git", "add", "plan.md"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=worktree, check=True, capture_output=True)

    # Create a new file with specific content
    test_file = worktree / "module.py"
    test_content = "# This is a test module\n\ndef calculate(x):\n    return x * 2\n"
    test_file.write_text(test_content)

    plan_content, git_changes = gather_git_context(worktree)

    assert "Changed File Contents" in git_changes
    assert "module.py" in git_changes
    assert "def calculate(x)" in git_changes
    assert "return x * 2" in git_changes
