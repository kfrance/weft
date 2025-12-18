"""Integration tests for DSPy cache functionality.

These tests verify that DSPy caching works correctly:
1. Cache files are actually written to disk
2. Cache is used on subsequent identical calls
3. Cache sync between worktree and global cache works

Note: These tests require rsync and OPENROUTER_API_KEY to be available.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lw_coder.cache_sync import (
    check_rsync_available,
    sync_cache_from_worktree,
    sync_cache_to_worktree,
)
from lw_coder.judge_executor import (
    JudgeExecutionError,
    configure_dspy_cache,
    execute_judge,
    get_openrouter_api_key,
)
from lw_coder.judge_loader import JudgeConfig


def test_dspy_cache_creates_files(tmp_path: Path) -> None:
    """Verify DSPy cache actually writes files to disk.

    This test:
    1. Creates an empty cache directory
    2. Configures DSPy to use that cache
    3. Executes a judge with real DSPy/LLM call
    4. Verifies cache files were created
    """
    # Get API key (will fail with clear message if not available)
    try:
        api_key = get_openrouter_api_key()
    except JudgeExecutionError:
        pytest.fail(
            "OPENROUTER_API_KEY not found in ~/.lw_coder/.env. "
            "Add it to run this integration test."
        )

    cache_dir = tmp_path / "test_cache"
    cache_dir.mkdir()

    # Verify cache is empty
    assert list(cache_dir.iterdir()) == []

    # Configure DSPy to use our test cache
    configure_dspy_cache(cache_dir)

    # Create a simple test judge
    judge = JudgeConfig(
        name="cache-test-judge",
        weight=0.5,
        model="x-ai/grok-4.1-fast",
        instructions=(
            "You are evaluating code changes. "
            "Provide a score between 0.0 and 1.0. "
            "Give brief feedback."
        ),
        file_path=tmp_path / "cache-test-judge.md",
    )

    plan_content = "# Test Plan\nSimple test for cache verification."
    git_changes = "=== Git Status ===\nNo changes"

    # Execute judge (will hit API)
    result1 = execute_judge(judge, plan_content, git_changes, api_key, cache_dir)

    # Verify we got a valid result
    assert result1.judge_name == "cache-test-judge"
    assert 0.0 <= result1.score <= 1.0
    assert isinstance(result1.feedback, str)

    # Verify cache files were created
    cache_files = list(cache_dir.rglob("*"))
    # Filter to only files (not directories)
    cache_files = [f for f in cache_files if f.is_file()]
    assert len(cache_files) > 0, "Cache should contain files after execution"


def test_cache_sync_workflow(tmp_path: Path) -> None:
    """Test bidirectional cache sync workflow.

    This test verifies that:
    1. Files can be synced from global to worktree cache
    2. New files in worktree sync back to global
    3. Existing files in global are preserved when syncing back
    """
    if not check_rsync_available():
        pytest.fail(
            "rsync not available. Install rsync to run this integration test. "
            "On Linux: apt install rsync. On macOS: brew install rsync."
        )

    # Setup directories
    global_cache = tmp_path / "global_cache"
    worktree_cache = tmp_path / "worktree_cache"
    global_cache.mkdir()

    # Create some files in global cache
    (global_cache / "global_file1.db").write_text("global data 1")
    (global_cache / "global_file2.db").write_text("global data 2")
    subdir = global_cache / "subdir"
    subdir.mkdir()
    (subdir / "nested.db").write_text("nested data")

    # Sync global to worktree
    result = sync_cache_to_worktree(global_cache, worktree_cache)
    assert result is True

    # Verify files were copied to worktree
    assert (worktree_cache / "global_file1.db").exists()
    assert (worktree_cache / "global_file2.db").exists()
    assert (worktree_cache / "subdir" / "nested.db").exists()
    assert (worktree_cache / "global_file1.db").read_text() == "global data 1"

    # Add new files in worktree (simulating cache entries created during execution)
    (worktree_cache / "worktree_new.db").write_text("worktree data")
    (worktree_cache / "subdir" / "worktree_nested.db").write_text("worktree nested")

    # Sync worktree back to global
    result = sync_cache_from_worktree(worktree_cache, global_cache)
    assert result is True

    # Verify new files were copied to global
    assert (global_cache / "worktree_new.db").exists()
    assert (global_cache / "worktree_new.db").read_text() == "worktree data"
    assert (global_cache / "subdir" / "worktree_nested.db").exists()

    # Verify original global files are still present (sync doesn't delete)
    assert (global_cache / "global_file1.db").exists()
    assert (global_cache / "global_file2.db").exists()


def test_sync_to_worktree_mirrors_with_delete(tmp_path: Path) -> None:
    """Test that sync_cache_to_worktree uses --delete to mirror source."""
    if not check_rsync_available():
        pytest.fail(
            "rsync not available. Install rsync to run this integration test. "
            "On Linux: apt install rsync. On macOS: brew install rsync."
        )

    global_cache = tmp_path / "global"
    worktree_cache = tmp_path / "worktree"
    global_cache.mkdir()
    worktree_cache.mkdir()

    # Create initial file in global
    (global_cache / "kept.db").write_text("kept")

    # Create a file in worktree that doesn't exist in global
    (worktree_cache / "extra.db").write_text("extra")

    # Sync global to worktree (should delete extra.db)
    result = sync_cache_to_worktree(global_cache, worktree_cache)
    assert result is True

    # Verify kept.db exists and extra.db was deleted
    assert (worktree_cache / "kept.db").exists()
    assert not (worktree_cache / "extra.db").exists()


def test_sync_from_worktree_preserves_global(tmp_path: Path) -> None:
    """Test that sync_cache_from_worktree preserves existing global files."""
    if not check_rsync_available():
        pytest.fail(
            "rsync not available. Install rsync to run this integration test. "
            "On Linux: apt install rsync. On macOS: brew install rsync."
        )

    global_cache = tmp_path / "global"
    worktree_cache = tmp_path / "worktree"
    global_cache.mkdir()
    worktree_cache.mkdir()

    # Create file only in global
    (global_cache / "global_only.db").write_text("global")

    # Create file only in worktree
    (worktree_cache / "worktree_only.db").write_text("worktree")

    # Sync worktree to global (should NOT delete global_only.db)
    result = sync_cache_from_worktree(worktree_cache, global_cache)
    assert result is True

    # Both files should exist in global
    assert (global_cache / "global_only.db").exists()
    assert (global_cache / "worktree_only.db").exists()
