"""Tests for code_command module."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from lw_coder.code_command import run_code_command
from lw_coder.plan_validator import PlanMetadata, PlanValidationError
from lw_coder.worktree_utils import WorktreeError

from tests.conftest import write_plan


def test_run_code_command_success(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test successful execution of run_code_command."""
    # Setup
    plan_path = tmp_path / "plan.md"
    worktree_path = tmp_path / "worktree"

    # Mock load_plan_metadata
    mock_metadata = PlanMetadata(
        plan_text="# Test Plan",
        git_sha="a" * 40,
        evaluation_notes=["Test note"],
        plan_path=plan_path,
        repo_root=tmp_path,
        plan_id="test-plan",
        status="draft",
    )

    # Track calls to verify correct arguments
    load_plan_calls = []
    ensure_worktree_calls = []

    def mock_load_plan_metadata(path):
        load_plan_calls.append(path)
        return mock_metadata

    def mock_ensure_worktree(metadata):
        ensure_worktree_calls.append(metadata)
        return worktree_path

    # Apply monkeypatches
    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", mock_load_plan_metadata
    )
    monkeypatch.setattr(
        lw_coder.code_command, "ensure_worktree", mock_ensure_worktree
    )

    # Execute
    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path)

    # Assert
    assert exit_code == 0
    assert "Plan validation succeeded" in caplog.text
    assert str(plan_path) in caplog.text
    assert "Worktree prepared at" in caplog.text
    assert str(worktree_path) in caplog.text

    # Verify mocked functions were called with correct arguments
    assert len(load_plan_calls) == 1
    assert load_plan_calls[0] == plan_path
    assert len(ensure_worktree_calls) == 1
    assert ensure_worktree_calls[0] == mock_metadata


def test_run_code_command_validation_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with plan validation failure."""
    # Setup
    plan_path = tmp_path / "plan.md"

    # Mock load_plan_metadata to raise PlanValidationError
    def mock_load_plan_metadata(path):
        raise PlanValidationError("Invalid git_sha")

    # Apply monkeypatch
    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", mock_load_plan_metadata
    )

    # Execute
    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    # Assert
    assert exit_code == 1
    assert "Plan validation failed" in caplog.text
    assert "Invalid git_sha" in caplog.text


def test_run_code_command_worktree_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with worktree preparation failure."""
    # Setup
    plan_path = tmp_path / "plan.md"

    # Mock load_plan_metadata
    mock_metadata = PlanMetadata(
        plan_text="# Test Plan",
        git_sha="b" * 40,
        evaluation_notes=["Test note"],
        plan_path=plan_path,
        repo_root=tmp_path,
        plan_id="test-plan-fail",
        status="draft",
    )

    def mock_load_plan_metadata(path):
        return mock_metadata

    # Mock ensure_worktree to raise WorktreeError
    def mock_ensure_worktree(metadata):
        raise WorktreeError("Failed to create worktree")

    # Apply monkeypatches
    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", mock_load_plan_metadata
    )
    monkeypatch.setattr(
        lw_coder.code_command, "ensure_worktree", mock_ensure_worktree
    )

    # Execute
    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path)

    # Assert
    assert exit_code == 1
    # Should see the validation success message
    assert "Plan validation succeeded" in caplog.text
    # But then the worktree failure
    assert "Worktree preparation failed" in caplog.text
    assert "Failed to create worktree" in caplog.text


def test_run_code_command_with_string_path(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command accepts string paths."""
    # Setup
    plan_path = tmp_path / "plan.md"
    plan_path_str = str(plan_path)
    worktree_path = tmp_path / "worktree"

    # Mock load_plan_metadata
    mock_metadata = PlanMetadata(
        plan_text="# Test Plan",
        git_sha="c" * 40,
        evaluation_notes=["Test note"],
        plan_path=plan_path,
        repo_root=tmp_path,
        plan_id="test-plan-str",
        status="draft",
    )

    def mock_load_plan_metadata(path):
        # Verify it receives a Path object
        assert isinstance(path, Path)
        return mock_metadata

    # Mock ensure_worktree
    def mock_ensure_worktree(metadata):
        return worktree_path

    # Apply monkeypatches
    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", mock_load_plan_metadata
    )
    monkeypatch.setattr(
        lw_coder.code_command, "ensure_worktree", mock_ensure_worktree
    )

    # Execute with string path
    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path_str)

    # Assert
    assert exit_code == 0
    assert "Plan validation succeeded" in caplog.text
    assert "Worktree prepared at" in caplog.text


def test_run_code_command_integration_with_real_functions(git_repo, caplog, tmp_path: Path) -> None:
    """Integration test: run_code_command with real load_plan_metadata and ensure_worktree.

    This test verifies the complete workflow without mocking, ensuring:
    1. Real plan validation works
    2. Real worktree creation succeeds
    3. Logging messages are produced correctly
    4. Exit code is correct

    This complements the unit tests that use mocks.
    """
    # Setup: Create a valid plan file in the git repo
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_path = tasks_dir / "integration-test.md"

    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["Integration test note"],
            "plan_id": "integration-test",
            "status": "draft",
        },
        body="# Integration Test Plan\n\nThis tests the full workflow."
    )

    # Execute: Run the actual code_command with no mocks
    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path)

    # Assert: Verify success
    assert exit_code == 0

    # Verify log messages
    assert "Plan validation succeeded for" in caplog.text
    assert str(plan_path) in caplog.text
    assert "Worktree prepared at" in caplog.text

    # Verify worktree was actually created
    expected_worktree = git_repo.path / ".lw_coder" / "worktrees" / "integration-test"
    assert expected_worktree.exists()
    assert expected_worktree.is_dir()

    # Verify worktree has .git file
    git_file = expected_worktree / ".git"
    assert git_file.exists()
    assert "gitdir:" in git_file.read_text()

    # Verify worktree is at correct commit
    import subprocess
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=expected_worktree,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == git_repo.latest_commit()

    # Verify worktree contains actual repository content (not just metadata)
    readme_file = expected_worktree / "README.md"
    assert readme_file.exists(), "Worktree should contain README.md from repository"
    assert readme_file.read_text() == "seed\n", "Worktree content should match repository"

    # Verify it's a valid Git worktree by checking we can run git commands in it
    git_status = subprocess.run(
        ["git", "status", "--short"],
        cwd=expected_worktree,
        capture_output=True,
        text=True,
        check=True,
    )
    # Worktree should have clean status (no modifications)
    assert git_status.stdout.strip() == "", "Worktree should be clean"
