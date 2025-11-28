"""Tests for run_manager module."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.run_manager import (
    RUN_RETENTION_DAYS,
    RunManagerError,
    copy_coding_droids,
    create_run_directory,
    prune_old_runs,
)


def test_create_run_directory_success(tmp_path: Path) -> None:
    """Test successful creation of run directory."""
    repo_root = tmp_path
    plan_id = "test-plan"

    run_dir = create_run_directory(repo_root, plan_id)

    # Verify directory structure
    assert run_dir.exists()
    assert run_dir.is_dir()
    assert ".lw_coder/runs" in str(run_dir)
    assert plan_id in str(run_dir)

    # Verify timestamp format in directory name
    timestamp_part = run_dir.name
    assert len(timestamp_part) >= 15  # YYYYMMDD_HHMMSS format


def test_create_run_directory_race_condition(tmp_path: Path, monkeypatch) -> None:
    """Test run directory creation with race condition (dir exists)."""
    repo_root = tmp_path
    plan_id = "test-plan"

    # Create a directory that will cause FileExistsError on first attempt
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    existing_dir = repo_root / ".lw_coder" / "runs" / plan_id / timestamp
    existing_dir.mkdir(parents=True, exist_ok=True)

    # Should create directory with microseconds appended
    run_dir = create_run_directory(repo_root, plan_id)

    assert run_dir.exists()
    assert run_dir != existing_dir
    assert len(run_dir.name) > len(timestamp)  # Has microseconds


def test_create_run_directory_os_error(tmp_path: Path, monkeypatch) -> None:
    """Test run directory creation with OSError."""
    repo_root = tmp_path
    plan_id = "test-plan"

    # Make mkdir fail with OSError
    original_mkdir = Path.mkdir

    def failing_mkdir(self, *args, **kwargs):
        if ".lw_coder/runs" in str(self):
            raise OSError("Permission denied")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", failing_mkdir)

    with pytest.raises(RunManagerError, match="Failed to create run directory"):
        create_run_directory(repo_root, plan_id)


def test_copy_coding_droids_success(tmp_path: Path) -> None:
    """Test successful copying of coding droids."""
    # Create mock source droids directory
    mock_src_dir = tmp_path / "src"
    mock_droids_dir = mock_src_dir / "droids"
    mock_droids_dir.mkdir(parents=True)

    # Create some droid files
    (mock_droids_dir / "code-reviewer.md").write_text("# Code Reviewer")
    (mock_droids_dir / "test-writer.md").write_text("# Test Writer")

    # Create plan subdirectory with a droid (should be skipped)
    plan_dir = mock_droids_dir / "plan"
    plan_dir.mkdir()
    (plan_dir / "plan-droid.md").write_text("# Plan Droid")

    # Create run directory
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # Mock get_lw_coder_src_dir to return our test directory
    with patch("lw_coder.run_manager.get_lw_coder_src_dir", return_value=mock_src_dir):
        result_dir = copy_coding_droids(run_dir)

    # Verify droids were copied
    assert result_dir == run_dir / "droids"
    assert (result_dir / "code-reviewer.md").exists()
    assert (result_dir / "test-writer.md").exists()

    # Verify plan droid was skipped
    assert not (result_dir / "plan" / "plan-droid.md").exists()


def test_copy_coding_droids_nested_structure(tmp_path: Path) -> None:
    """Test copying droids with nested directory structure."""
    # Create mock source droids with nested structure
    mock_src_dir = tmp_path / "src"
    mock_droids_dir = mock_src_dir / "droids"
    nested_dir = mock_droids_dir / "specialized"
    nested_dir.mkdir(parents=True)

    # Create nested droid file
    (nested_dir / "security-auditor.md").write_text("# Security Auditor")

    # Create run directory
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    with patch("lw_coder.run_manager.get_lw_coder_src_dir", return_value=mock_src_dir):
        result_dir = copy_coding_droids(run_dir)

    # Verify nested structure preserved
    assert (result_dir / "specialized" / "security-auditor.md").exists()


def test_copy_coding_droids_source_not_found(tmp_path: Path) -> None:
    """Test copying droids when source directory doesn't exist."""
    mock_src_dir = tmp_path / "src"
    mock_src_dir.mkdir()

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    with patch("lw_coder.run_manager.get_lw_coder_src_dir", return_value=mock_src_dir):
        with pytest.raises(RunManagerError, match="Source droids directory not found"):
            copy_coding_droids(run_dir)


def test_prune_old_runs_no_runs_directory(tmp_path: Path) -> None:
    """Test pruning when runs directory doesn't exist."""
    repo_root = tmp_path

    count = prune_old_runs(repo_root)

    assert count == 0


def test_prune_old_runs_removes_old_directories(tmp_path: Path) -> None:
    """Test that old run directories are pruned."""
    repo_root = tmp_path
    runs_dir = repo_root / ".lw_coder" / "runs" / "test-plan"
    runs_dir.mkdir(parents=True)

    # Create old directory (simulated by setting mtime)
    old_dir = runs_dir / "20200101_120000"
    old_dir.mkdir()
    old_timestamp = time.time() - (RUN_RETENTION_DAYS + 1) * 24 * 60 * 60

    # Create recent directory
    recent_dir = runs_dir / "20250101_120000"
    recent_dir.mkdir()

    # Set modification times
    import os
    os.utime(old_dir, (old_timestamp, old_timestamp))

    count = prune_old_runs(repo_root)

    assert count == 1
    assert not old_dir.exists()
    assert recent_dir.exists()


def test_prune_old_runs_skips_active_run(tmp_path: Path) -> None:
    """Test that active run directory is not pruned."""
    repo_root = tmp_path
    runs_dir = repo_root / ".lw_coder" / "runs" / "test-plan"
    runs_dir.mkdir(parents=True)

    # Create old directory
    old_dir = runs_dir / "20200101_120000"
    old_dir.mkdir()
    old_timestamp = time.time() - (RUN_RETENTION_DAYS + 1) * 24 * 60 * 60

    import os
    os.utime(old_dir, (old_timestamp, old_timestamp))

    # Mark it as active
    count = prune_old_runs(repo_root, active_run_dir=old_dir)

    assert count == 0
    assert old_dir.exists()


def test_prune_old_runs_removes_empty_plan_directories(tmp_path: Path) -> None:
    """Test that empty plan directories are removed after pruning."""
    repo_root = tmp_path
    runs_dir = repo_root / ".lw_coder" / "runs" / "test-plan"
    runs_dir.mkdir(parents=True)

    # Create old directory
    old_dir = runs_dir / "20200101_120000"
    old_dir.mkdir()
    old_timestamp = time.time() - (RUN_RETENTION_DAYS + 1) * 24 * 60 * 60

    import os
    os.utime(old_dir, (old_timestamp, old_timestamp))

    prune_old_runs(repo_root)

    # Verify plan directory was also removed
    assert not runs_dir.exists()


def test_prune_old_runs_handles_partial_failures(tmp_path: Path, monkeypatch) -> None:
    """Test that pruning continues even if some deletions fail."""
    repo_root = tmp_path
    runs_dir = repo_root / ".lw_coder" / "runs" / "test-plan"
    runs_dir.mkdir(parents=True)

    # Create two old directories
    old_dir1 = runs_dir / "20200101_120000"
    old_dir1.mkdir()
    old_dir2 = runs_dir / "20200102_120000"
    old_dir2.mkdir()

    old_timestamp = time.time() - (RUN_RETENTION_DAYS + 1) * 24 * 60 * 60
    import os
    os.utime(old_dir1, (old_timestamp, old_timestamp))
    os.utime(old_dir2, (old_timestamp, old_timestamp))

    # Make deletions of a specific directory fail
    original_rmtree = __import__("shutil").rmtree

    def failing_rmtree(path, *args, **kwargs):
        # Fail only for old_dir1
        if str(path) == str(old_dir1):
            raise OSError("Simulated failure")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("shutil.rmtree", failing_rmtree)

    # Should still prune the second directory
    count = prune_old_runs(repo_root)

    assert count == 1
    assert old_dir1.exists()  # Failed to delete
    assert not old_dir2.exists()  # Successfully deleted


def test_prune_old_runs_raises_on_all_failures(tmp_path: Path, monkeypatch) -> None:
    """Test that RunManagerError is raised when all pruning operations fail."""
    repo_root = tmp_path
    runs_dir = repo_root / ".lw_coder" / "runs" / "test-plan"
    runs_dir.mkdir(parents=True)

    # Create old directory
    old_dir = runs_dir / "20200101_120000"
    old_dir.mkdir()
    old_timestamp = time.time() - (RUN_RETENTION_DAYS + 1) * 24 * 60 * 60

    import os
    os.utime(old_dir, (old_timestamp, old_timestamp))

    # Make all deletions fail
    def failing_rmtree(path, *args, **kwargs):
        raise OSError("Simulated failure")

    monkeypatch.setattr("shutil.rmtree", failing_rmtree)

    with pytest.raises(RunManagerError, match="Pruning failed"):
        prune_old_runs(repo_root)
