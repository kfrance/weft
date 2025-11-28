"""Tests for plan path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.plan_resolver import PlanResolver


def test_resolve_absolute_path_existing(tmp_path):
    """Test resolving an absolute path to an existing file."""
    plan_file = tmp_path / "test.md"
    plan_file.write_text("# Test Plan\n")

    result = PlanResolver.resolve(plan_file)
    assert result == plan_file.resolve()


def test_resolve_absolute_path_nonexistent(tmp_path):
    """Test resolving an absolute path to a non-existent file raises error."""
    plan_file = tmp_path / "nonexistent.md"

    with pytest.raises(FileNotFoundError) as exc_info:
        PlanResolver.resolve(plan_file)

    assert "Plan file not found" in str(exc_info.value)
    assert str(plan_file) in str(exc_info.value)


def test_resolve_relative_path_existing(tmp_path, monkeypatch):
    """Test resolving a relative path to an existing file."""
    monkeypatch.chdir(tmp_path)
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    plan_file = subdir / "test.md"
    plan_file.write_text("# Test Plan\n")

    result = PlanResolver.resolve("subdir/test.md", cwd=tmp_path)
    assert result == plan_file.resolve()


def test_resolve_relative_path_nonexistent(tmp_path):
    """Test resolving a relative path to non-existent file raises error."""
    with pytest.raises(FileNotFoundError) as exc_info:
        PlanResolver.resolve("subdir/nonexistent.md", cwd=tmp_path)

    assert "Plan file not found" in str(exc_info.value)


def test_resolve_plan_id_existing(tmp_path, monkeypatch):
    """Test resolving a plan ID to an existing plan file."""
    # Create a real git repository (git rev-parse needs actual repo)
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)

    # Create tasks directory and plan file
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "fix-subagent.md"
    plan_file.write_text("# Fix Subagent\n")

    # Change to the repository directory
    monkeypatch.chdir(tmp_path)

    result = PlanResolver.resolve("fix-subagent", cwd=tmp_path)
    assert result == plan_file.resolve()


def test_resolve_plan_id_nonexistent(tmp_path, monkeypatch):
    """Test resolving a non-existent plan ID raises error."""
    # Create a real git repository
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True, capture_output=True)

    # Create tasks directory (but no plan file)
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Change to the repository directory
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError) as exc_info:
        PlanResolver.resolve("nonexistent-plan", cwd=tmp_path)

    assert "Plan file not found" in str(exc_info.value)
    assert "nonexistent-plan" in str(exc_info.value)


def test_resolve_plan_id_not_in_git_repo(tmp_path, monkeypatch):
    """Test resolving a plan ID outside a git repository raises error."""
    # Don't create .git directory
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError) as exc_info:
        PlanResolver.resolve("some-plan", cwd=tmp_path)

    assert "not in a git repository" in str(exc_info.value)


def test_resolve_string_input(tmp_path):
    """Test that PlanResolver accepts string input."""
    plan_file = tmp_path / "test.md"
    plan_file.write_text("# Test Plan\n")

    result = PlanResolver.resolve(str(plan_file))
    assert result == plan_file.resolve()


def test_resolve_path_input(tmp_path):
    """Test that PlanResolver accepts Path input."""
    plan_file = tmp_path / "test.md"
    plan_file.write_text("# Test Plan\n")

    result = PlanResolver.resolve(plan_file)
    assert result == plan_file.resolve()


def test_resolve_with_backslash_separator(tmp_path, monkeypatch):
    """Test resolving paths with backslash separators (Windows-style)."""
    import sys
    if sys.platform != "win32":
        # Skip on non-Windows platforms (backslash is not a separator)
        pytest.skip("Backslash path separator only supported on Windows")

    monkeypatch.chdir(tmp_path)
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    plan_file = subdir / "test.md"
    plan_file.write_text("# Test Plan\n")

    # Use backslash separator
    result = PlanResolver.resolve("subdir\\test.md", cwd=tmp_path)
    assert result == plan_file.resolve()


def test_resolve_default_cwd(tmp_path, monkeypatch):
    """Test that PlanResolver uses current directory by default."""
    monkeypatch.chdir(tmp_path)
    plan_file = tmp_path / "test.md"
    plan_file.write_text("# Test Plan\n")

    # Don't provide cwd argument - should use Path.cwd()
    result = PlanResolver.resolve(plan_file)
    assert result == plan_file.resolve()
