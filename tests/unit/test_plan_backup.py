"""Tests for plan backup module."""

from __future__ import annotations

import subprocess

import pytest

from lw_coder.plan_backup import (
    BackupExistsError,
    BackupNotFoundError,
    PlanBackupError,
    cleanup_backup,
    create_backup,
    list_backups,
    recover_backup,
)

from conftest import GitRepo, write_plan


def test_create_backup_creates_orphan_commit_and_ref(git_repo: GitRepo) -> None:
    """Test that create_backup creates an orphan commit and reference."""
    # Setup: Create a plan file
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Test Plan Body",
    )

    # Execute: Create backup
    create_backup(git_repo.path, "test-plan")

    # Verify: Reference exists
    result = git_repo.run("show-ref", "refs/plan-backups/test-plan")
    assert "refs/plan-backups/test-plan" in result.stdout

    # Verify: Commit is orphan (has no parents)
    commit_sha = result.stdout.split()[0]
    result = git_repo.run("rev-list", "--parents", "-n", "1", commit_sha)
    # Output format: "<commit_sha>" (no parent) or "<commit_sha> <parent_sha>"
    parts = result.stdout.strip().split()
    assert len(parts) == 1, "Commit should have no parents (orphan)"

    # Verify: Commit message
    result = git_repo.run("log", "-1", "--format=%s", commit_sha)
    assert result.stdout.strip() == "Backup of plan: test-plan"


def test_create_backup_force_updates_on_subsequent_calls(git_repo: GitRepo) -> None:
    """Test that subsequent backups force-update the reference."""
    # Setup: Create initial plan and backup
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Original Body",
    )

    create_backup(git_repo.path, "test-plan")
    result = git_repo.run("show-ref", "refs/plan-backups/test-plan")
    first_commit = result.stdout.split()[0]

    # Modify plan and create another backup
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Modified Body",
    )

    create_backup(git_repo.path, "test-plan")
    result = git_repo.run("show-ref", "refs/plan-backups/test-plan")
    second_commit = result.stdout.split()[0]

    # Verify: Reference points to new commit
    assert first_commit != second_commit

    # Verify: New commit has modified content
    result = git_repo.run("show", f"{second_commit}:.lw_coder/tasks/test-plan.md")
    assert "# Modified Body" in result.stdout


def test_create_backup_raises_error_on_missing_file(git_repo: GitRepo) -> None:
    """Test that create_backup raises error when plan file doesn't exist."""
    with pytest.raises(PlanBackupError, match="Failed to read plan file"):
        create_backup(git_repo.path, "nonexistent-plan")


def test_cleanup_backup_deletes_ref(git_repo: GitRepo) -> None:
    """Test that cleanup_backup deletes the backup reference."""
    # Setup: Create backup
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "test-plan")

    # Verify backup exists
    result = git_repo.run("show-ref", "refs/plan-backups/test-plan")
    assert "refs/plan-backups/test-plan" in result.stdout

    # Execute: Cleanup backup
    cleanup_backup(git_repo.path, "test-plan")

    # Verify: Reference no longer exists
    result = subprocess.run(
        ["git", "show-ref", "refs/plan-backups/test-plan"],
        cwd=git_repo.path,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert result.returncode != 0, "Reference should not exist after cleanup"


def test_cleanup_backup_is_idempotent(git_repo: GitRepo) -> None:
    """Test that cleanup_backup is safe when ref doesn't exist."""
    # Execute: Try to cleanup non-existent backup (should not raise)
    cleanup_backup(git_repo.path, "nonexistent-plan")

    # Execute again to ensure it's truly idempotent
    cleanup_backup(git_repo.path, "nonexistent-plan")


def test_list_backups_returns_correct_data(git_repo: GitRepo) -> None:
    """Test that list_backups returns correct metadata."""
    # Setup: Create multiple backups
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create first plan with existing file
    plan1 = tasks_dir / "plan-one.md"
    write_plan(
        plan1,
        {
            "plan_id": "plan-one",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "plan-one")

    # Create second plan then delete file
    plan2 = tasks_dir / "plan-two.md"
    write_plan(
        plan2,
        {
            "plan_id": "plan-two",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "plan-two")
    plan2.unlink()

    # Execute: List backups
    backups = list_backups(git_repo.path)

    # Verify: Returns correct data
    assert len(backups) == 2

    # Sort by plan_id to ensure consistent ordering
    backups_dict = {plan_id: (timestamp, exists) for plan_id, timestamp, exists in backups}

    assert "plan-one" in backups_dict
    assert "plan-two" in backups_dict

    # Verify timestamps are integers
    assert isinstance(backups_dict["plan-one"][0], int)
    assert isinstance(backups_dict["plan-two"][0], int)

    # Verify existence status
    assert backups_dict["plan-one"][1] is True  # File exists
    assert backups_dict["plan-two"][1] is False  # File deleted


def test_list_backups_returns_empty_when_no_backups(git_repo: GitRepo) -> None:
    """Test that list_backups returns empty list when no backups exist."""
    backups = list_backups(git_repo.path)
    assert backups == []


def test_recover_backup_restores_file_content(git_repo: GitRepo) -> None:
    """Test that recover_backup restores plan file with correct content."""
    # Setup: Create backup then delete file
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    expected_body = "# Expected Body Content"
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body=expected_body,
    )
    original_content = plan_file.read_text(encoding="utf-8")
    create_backup(git_repo.path, "test-plan")
    plan_file.unlink()

    # Execute: Recover backup
    recovered_path = recover_backup(git_repo.path, "test-plan")

    # Verify: File restored with correct content
    assert recovered_path == plan_file
    assert plan_file.exists()
    assert plan_file.read_text(encoding="utf-8") == original_content


def test_recover_backup_fails_when_file_exists_without_force(git_repo: GitRepo) -> None:
    """Test that recover_backup raises error when file exists and force=False."""
    # Setup: Create backup with existing file
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "test-plan")

    # Execute & Verify: Raises BackupExistsError
    with pytest.raises(BackupExistsError, match="already exists"):
        recover_backup(git_repo.path, "test-plan", force=False)


def test_recover_backup_succeeds_with_force_flag(git_repo: GitRepo) -> None:
    """Test that recover_backup overwrites with force=True."""
    # Setup: Create backup with different content
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Original Content",
    )
    original_content = plan_file.read_text(encoding="utf-8")
    create_backup(git_repo.path, "test-plan")

    # Modify file
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Modified Content",
    )
    assert "# Modified Content" in plan_file.read_text(encoding="utf-8")

    # Execute: Recover with force
    recover_backup(git_repo.path, "test-plan", force=True)

    # Verify: Content restored to original
    assert plan_file.read_text(encoding="utf-8") == original_content


def test_recover_backup_raises_error_when_ref_doesnt_exist(git_repo: GitRepo) -> None:
    """Test that recover_backup raises BackupNotFoundError for missing refs."""
    with pytest.raises(BackupNotFoundError, match="No backup found"):
        recover_backup(git_repo.path, "nonexistent-plan")
