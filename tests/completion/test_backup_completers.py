"""Tests for backup plan completers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lw_coder.completion.completers import complete_backup_plans
from lw_coder.plan_backup import create_backup

from conftest import GitRepo, write_plan


def test_complete_backup_plans_returns_correct_format(git_repo: GitRepo) -> None:
    """Test that complete_backup_plans returns correct format with status."""
    # Setup: Create backups
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Plan with existing file
    plan1 = tasks_dir / "feature-auth.md"
    write_plan(
        plan1,
        {
            "plan_id": "feature-auth",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "feature-auth")

    # Plan with missing file
    plan2 = tasks_dir / "feature-export.md"
    write_plan(
        plan2,
        {
            "plan_id": "feature-export",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "feature-export")
    plan2.unlink()

    # Execute: Get completions
    with patch("lw_coder.repo_utils.find_repo_root", return_value=git_repo.path):
        completions = complete_backup_plans(prefix="", parsed_args=None)

    # Verify: Returns both plans with status indicators
    assert len(completions) == 2
    assert "feature-auth (exists)" in completions
    assert "feature-export (missing)" in completions


def test_complete_backup_plans_status_indicators(git_repo: GitRepo) -> None:
    """Test status indicators (exists/missing) are correct."""
    # Setup: Create plan with existing file
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "my-plan.md"
    write_plan(
        plan_file,
        {
            "plan_id": "my-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "my-plan")

    # Execute: Get completions (file exists)
    with patch("lw_coder.repo_utils.find_repo_root", return_value=git_repo.path):
        completions = complete_backup_plans(prefix="", parsed_args=None)

    assert "my-plan (exists)" in completions

    # Delete file and check again
    plan_file.unlink()

    with patch("lw_coder.repo_utils.find_repo_root", return_value=git_repo.path):
        completions = complete_backup_plans(prefix="", parsed_args=None)

    assert "my-plan (missing)" in completions


def test_complete_backup_plans_prefix_filtering(git_repo: GitRepo) -> None:
    """Test that completions are filtered by prefix."""
    # Setup: Create multiple backups
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    for plan_id in ["feature-auth", "feature-export", "bugfix-login"]:
        plan_file = tasks_dir / f"{plan_id}.md"
        write_plan(
            plan_file,
            {
                "plan_id": plan_id,
                "status": "draft",
                "git_sha": "0" * 40,
                "evaluation_notes": [],
            },
        )
        create_backup(git_repo.path, plan_id)

    # Execute: Get completions with "feature" prefix
    with patch("lw_coder.repo_utils.find_repo_root", return_value=git_repo.path):
        completions = complete_backup_plans(prefix="feature", parsed_args=None)

    # Verify: Only feature plans returned
    assert len(completions) == 2
    assert any("feature-auth" in c for c in completions)
    assert any("feature-export" in c for c in completions)
    assert not any("bugfix" in c for c in completions)


def test_complete_backup_plans_returns_empty_when_no_backups(git_repo: GitRepo) -> None:
    """Test that empty list is returned when no backups exist."""
    # Execute: Get completions with no backups
    with patch("lw_coder.repo_utils.find_repo_root", return_value=git_repo.path):
        completions = complete_backup_plans(prefix="", parsed_args=None)

    # Verify: Empty list
    assert completions == []


def test_complete_backup_plans_handles_errors_gracefully(git_repo: GitRepo) -> None:
    """Test that errors are handled gracefully and return empty list."""
    # Execute: Force an error by patching find_repo_root to raise
    with patch("lw_coder.repo_utils.find_repo_root", side_effect=Exception("Test error")):
        completions = complete_backup_plans(prefix="", parsed_args=None)

    # Verify: Returns empty list on error
    assert completions == []
