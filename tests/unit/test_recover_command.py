"""Tests for recover-plan command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from lw_coder.plan_backup import create_backup
from lw_coder.recover_command import run_recover_command

from conftest import GitRepo, write_plan


def test_list_backups_displays_correct_format(git_repo: GitRepo, capsys) -> None:
    """Test that listing backups displays correct format."""
    # Setup: Create backups
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

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
    plan2.unlink()  # Delete to show "missing" status

    # Execute: List backups (cwd must be inside repo)
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id=None, force=False)

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: Output format
    captured = capsys.readouterr()
    assert "Found 2 backed-up plan(s)" in captured.out
    assert "feature-auth" in captured.out
    assert "feature-export" in captured.out
    assert "exists" in captured.out
    assert "missing" in captured.out


def test_list_backups_shows_empty_message(git_repo: GitRepo, capsys) -> None:
    """Test that listing shows message when no backups exist."""
    # Execute: List backups with no backups
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id=None, force=False)

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: Output message
    captured = capsys.readouterr()
    assert "No backed-up plans found" in captured.out


def test_recovery_with_valid_plan_id(git_repo: GitRepo, capsys) -> None:
    """Test recovery with valid plan_id."""
    # Setup: Create backup then delete file
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "my-feature.md"
    write_plan(
        plan_file,
        {
            "plan_id": "my-feature",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Feature Body",
    )
    create_backup(git_repo.path, "my-feature")
    plan_file.unlink()

    # Execute: Recover plan
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id="my-feature", force=False)

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: File restored
    assert plan_file.exists()
    assert "# Feature Body" in plan_file.read_text(encoding="utf-8")

    # Verify: Success message
    captured = capsys.readouterr()
    assert "Successfully recovered plan" in captured.out
    assert "my-feature" in captured.out


def test_recovery_strips_status_suffix_from_input(git_repo: GitRepo) -> None:
    """Test that recovery strips status suffix from tab completion input."""
    # Setup: Create backup then delete file
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "my-feature.md"
    write_plan(
        plan_file,
        {
            "plan_id": "my-feature",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "my-feature")
    plan_file.unlink()

    # Execute: Recover with status suffix
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id="my-feature (missing)", force=False)

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: File restored (suffix was stripped)
    assert plan_file.exists()


def test_recovery_force_flag_behavior(git_repo: GitRepo) -> None:
    """Test --force flag overwrites existing file."""
    # Setup: Create backup with original content
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "my-feature.md"
    write_plan(
        plan_file,
        {
            "plan_id": "my-feature",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Original Content",
    )
    original_content = plan_file.read_text(encoding="utf-8")
    create_backup(git_repo.path, "my-feature")

    # Modify file
    write_plan(
        plan_file,
        {
            "plan_id": "my-feature",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Modified Content",
    )

    # Execute: Recover with force
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id="my-feature", force=True)

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: File overwritten
    assert plan_file.read_text(encoding="utf-8") == original_content


def test_recovery_error_for_missing_backup(git_repo: GitRepo, caplog) -> None:
    """Test error handling when backup doesn't exist."""
    # Execute: Try to recover non-existent backup
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id="nonexistent", force=False)

    # Verify: Exit code 1
    assert exit_code == 1

    # Verify: Error message in logs
    assert "No backup found" in caplog.text


def test_recovery_error_when_file_exists_without_force(git_repo: GitRepo, caplog) -> None:
    """Test error when file exists and --force not provided."""
    # Setup: Create backup with existing file
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "my-feature.md"
    write_plan(
        plan_file,
        {
            "plan_id": "my-feature",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "my-feature")

    # Execute: Try to recover without force
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id="my-feature", force=False)

    # Verify: Exit code 1
    assert exit_code == 1

    # Verify: Error message suggests --force (check logs)
    assert "already exists" in caplog.text
    assert "--force" in caplog.text
