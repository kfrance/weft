"""Unit tests for judge executor module.

These tests verify internal logic using mocks and controlled inputs.
They do not make any external API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.judge_executor import (
    get_cache_dir,
)


def test_get_cache_dir_global(tmp_path: Path, monkeypatch) -> None:
    """Test cache directory returns global path when not in worktree."""
    # Change to a non-worktree directory to avoid detection from test environment
    monkeypatch.chdir(tmp_path)

    # When not in a worktree, should return global cache
    cache_dir = get_cache_dir()
    assert cache_dir == Path.home() / ".lw_coder" / "dspy_cache"
    assert isinstance(cache_dir, Path)


def test_get_cache_dir_in_worktree(tmp_path: Path, monkeypatch) -> None:
    """Test cache directory returns worktree-local path when in worktree."""
    # Create a fake worktree path structure
    worktree_path = tmp_path / "project" / ".lw_coder" / "worktrees" / "my-plan"
    worktree_path.mkdir(parents=True)

    # Change to the worktree directory
    monkeypatch.chdir(worktree_path)

    cache_dir = get_cache_dir()

    # Should return worktree-local cache path
    expected = worktree_path / ".lw_coder" / "dspy_cache"
    assert cache_dir == expected


def test_get_cache_dir_in_worktree_subdirectory(tmp_path: Path, monkeypatch) -> None:
    """Test cache directory works from subdirectory within worktree."""
    # Create a fake worktree path structure with a subdirectory
    worktree_root = tmp_path / "project" / ".lw_coder" / "worktrees" / "my-plan"
    subdir = worktree_root / "src" / "module"
    subdir.mkdir(parents=True)

    # Change to a subdirectory within the worktree
    monkeypatch.chdir(subdir)

    cache_dir = get_cache_dir()

    # Should return worktree-local cache path (relative to worktree root)
    expected = worktree_root / ".lw_coder" / "dspy_cache"
    assert cache_dir == expected
