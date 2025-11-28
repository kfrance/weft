"""Tests for temporary worktree management."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lw_coder.temp_worktree import TempWorktreeError, create_temp_worktree, remove_temp_worktree


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)

    # Create initial commit
    (repo / "test.txt").write_text("test content")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True, capture_output=True)

    return repo


def test_create_temp_worktree(git_repo: Path) -> None:
    """Test creating a temporary detached HEAD worktree."""
    worktree_path = create_temp_worktree(git_repo)

    # Verify worktree was created
    assert worktree_path.exists()
    assert worktree_path.is_dir()

    # Verify it's in the expected location
    assert worktree_path.parent == git_repo / ".lw_coder" / "worktrees"
    assert worktree_path.name.startswith("temp-")

    # Verify worktree is registered
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(worktree_path) in result.stdout

    # Verify it's detached
    assert "detached" in result.stdout.lower() or "HEAD detached" in result.stdout

    # Clean up
    remove_temp_worktree(git_repo, worktree_path)


def test_remove_temp_worktree(git_repo: Path) -> None:
    """Test removing a temporary worktree."""
    worktree_path = create_temp_worktree(git_repo)
    assert worktree_path.exists()

    remove_temp_worktree(git_repo, worktree_path)

    # Verify worktree was removed
    assert not worktree_path.exists()

    # Verify it's no longer registered
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=git_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(worktree_path) not in result.stdout


def test_remove_nonexistent_worktree(git_repo: Path) -> None:
    """Test removing a worktree that doesn't exist."""
    worktree_path = git_repo / ".lw_coder" / "worktrees" / "temp-nonexistent"

    # Should not raise an error
    remove_temp_worktree(git_repo, worktree_path)


def test_create_temp_worktree_creates_parent_dirs(git_repo: Path) -> None:
    """Test that create_temp_worktree creates parent directories if needed."""
    # Remove .lw_coder directory if it exists
    lw_coder_dir = git_repo / ".lw_coder"
    if lw_coder_dir.exists():
        import shutil
        shutil.rmtree(lw_coder_dir)

    worktree_path = create_temp_worktree(git_repo)

    # Verify parent directories were created
    assert worktree_path.parent.exists()
    assert worktree_path.exists()

    # Clean up
    remove_temp_worktree(git_repo, worktree_path)
