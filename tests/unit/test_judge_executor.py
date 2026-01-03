"""Unit tests for judge executor module.

These tests verify internal logic using mocks and controlled inputs.
They do not make any external API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft.judge_executor import (
    get_cache_dir,
)


def test_get_cache_dir_always_returns_global(tmp_path: Path, monkeypatch) -> None:
    """Test cache directory always returns global path regardless of location.

    The cache directory should always be ~/.weft/dspy_cache/ whether called
    from a worktree, a worktree subdirectory, or any other directory.
    The SDK sandbox grants write access to this global location.
    """
    # Test from a non-worktree directory
    monkeypatch.chdir(tmp_path)
    cache_dir = get_cache_dir()
    expected = Path.home() / ".weft" / "dspy_cache"
    assert cache_dir == expected
    assert isinstance(cache_dir, Path)

    # Test from a simulated worktree directory
    worktree_path = tmp_path / "project" / ".weft" / "worktrees" / "my-plan"
    worktree_path.mkdir(parents=True)
    monkeypatch.chdir(worktree_path)
    cache_dir = get_cache_dir()
    assert cache_dir == expected  # Still global cache

    # Test from a subdirectory within worktree
    subdir = worktree_path / "src" / "module"
    subdir.mkdir(parents=True)
    monkeypatch.chdir(subdir)
    cache_dir = get_cache_dir()
    assert cache_dir == expected  # Still global cache
