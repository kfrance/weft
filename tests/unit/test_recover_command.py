"""Tests for recover-plan command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from weft.plan_backup import create_backup, move_backup_to_abandoned
from weft.recover_command import run_recover_command, parse_abandoned_log

from conftest import GitRepo, write_plan


def test_list_backups_displays_correct_format(git_repo: GitRepo, capsys) -> None:
    """Test that listing backups displays correct format."""
    # Setup: Create backups
    tasks_dir = git_repo.path / ".weft" / "tasks"
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
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
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
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id=None, force=False)

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: Output message
    captured = capsys.readouterr()
    assert "No backed-up plans found" in captured.out


def test_recovery_with_valid_plan_id(git_repo: GitRepo, capsys) -> None:
    """Test recovery with valid plan_id."""
    # Setup: Create backup then delete file
    tasks_dir = git_repo.path / ".weft" / "tasks"
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
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
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
    tasks_dir = git_repo.path / ".weft" / "tasks"
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
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id="my-feature (missing)", force=False)

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: File restored (suffix was stripped)
    assert plan_file.exists()


def test_recovery_force_flag_behavior(git_repo: GitRepo) -> None:
    """Test --force flag overwrites existing file."""
    # Setup: Create backup with original content
    tasks_dir = git_repo.path / ".weft" / "tasks"
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
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id="my-feature", force=True)

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: File overwritten
    assert plan_file.read_text(encoding="utf-8") == original_content


def test_recovery_error_for_missing_backup(git_repo: GitRepo, caplog) -> None:
    """Test error handling when backup doesn't exist."""
    # Execute: Try to recover non-existent backup
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id="nonexistent", force=False)

    # Verify: Exit code 1
    assert exit_code == 1

    # Verify: Error message in logs
    assert "No backup found" in caplog.text


def test_recovery_error_when_file_exists_without_force(git_repo: GitRepo, caplog) -> None:
    """Test error when file exists and --force not provided."""
    # Setup: Create backup with existing file
    tasks_dir = git_repo.path / ".weft" / "tasks"
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
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(plan_id="my-feature", force=False)

    # Verify: Exit code 1
    assert exit_code == 1

    # Verify: Error message suggests --force (check logs)
    assert "already exists" in caplog.text
    assert "--force" in caplog.text


# Tests for --abandoned and --all flags


def test_list_abandoned_plans_flag(git_repo: GitRepo, capsys) -> None:
    """Test --abandoned flag shows only abandoned plans."""
    # Setup: Create active backup and abandoned backup
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create and abandon first plan
    plan1 = tasks_dir / "abandoned-plan.md"
    write_plan(
        plan1,
        {
            "plan_id": "abandoned-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "abandoned-plan")
    move_backup_to_abandoned(git_repo.path, "abandoned-plan")
    plan1.unlink()

    # Create active backup for second plan
    plan2 = tasks_dir / "active-plan.md"
    write_plan(
        plan2,
        {
            "plan_id": "active-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "active-plan")

    # Execute: List with --abandoned flag
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id=None, force=False, show_abandoned=True, show_all=False
        )

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: Shows only abandoned plans
    captured = capsys.readouterr()
    assert "abandoned-plan" in captured.out
    assert "active-plan" not in captured.out


def test_list_all_plans_flag(git_repo: GitRepo, capsys) -> None:
    """Test --all flag shows both active and abandoned plans."""
    # Setup: Create active backup and abandoned backup
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create and abandon first plan
    plan1 = tasks_dir / "abandoned-plan.md"
    write_plan(
        plan1,
        {
            "plan_id": "abandoned-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "abandoned-plan")
    move_backup_to_abandoned(git_repo.path, "abandoned-plan")

    # Create active backup for second plan
    plan2 = tasks_dir / "active-plan.md"
    write_plan(
        plan2,
        {
            "plan_id": "active-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "active-plan")

    # Execute: List with --all flag
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id=None, force=False, show_abandoned=False, show_all=True
        )

    # Verify: Exit code 0
    assert exit_code == 0

    # Verify: Shows both plans
    captured = capsys.readouterr()
    assert "abandoned-plan" in captured.out
    assert "active-plan" in captured.out
    assert "Type" in captured.out  # --all shows Type column


def test_recover_from_abandoned_namespace(git_repo: GitRepo, capsys) -> None:
    """Test recovering a plan from the abandoned namespace."""
    # Setup: Create and abandon a plan
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "abandoned-feature.md"
    write_plan(
        plan_file,
        {
            "plan_id": "abandoned-feature",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Abandoned Feature Body",
    )
    create_backup(git_repo.path, "abandoned-feature")
    move_backup_to_abandoned(git_repo.path, "abandoned-feature")
    plan_file.unlink()

    # Execute: Recover from abandoned
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id="abandoned-feature", force=False, show_abandoned=True, show_all=False
        )

    # Verify: Success
    assert exit_code == 0

    # Verify: File restored
    assert plan_file.exists()
    assert "# Abandoned Feature Body" in plan_file.read_text(encoding="utf-8")

    # Verify: Success message
    captured = capsys.readouterr()
    assert "Successfully recovered plan" in captured.out


def test_recover_from_active_when_in_abandoned_shows_hint(git_repo: GitRepo, capsys) -> None:
    """Test that recovering from active namespace shows hint when plan is in abandoned."""
    # Setup: Create and abandon a plan
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "in-abandoned.md"
    write_plan(
        plan_file,
        {
            "plan_id": "in-abandoned",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "in-abandoned")
    move_backup_to_abandoned(git_repo.path, "in-abandoned")
    plan_file.unlink()

    # Execute: Try to recover from active namespace (should fail with hint)
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id="in-abandoned", force=False, show_abandoned=False, show_all=False
        )

    # Verify: Failure
    assert exit_code == 1

    # Verify: Shows hint about --abandoned flag
    captured = capsys.readouterr()
    assert "--abandoned" in captured.out
    assert "in-abandoned" in captured.out


def test_list_empty_abandoned_shows_message(git_repo: GitRepo, capsys) -> None:
    """Test that listing abandoned with none shows appropriate message."""
    # Execute: List abandoned with no abandoned plans
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id=None, force=False, show_abandoned=True, show_all=False
        )

    # Verify: Success
    assert exit_code == 0

    # Verify: Message about no abandoned plans
    captured = capsys.readouterr()
    assert "No abandoned plans found" in captured.out


def test_recovery_strips_abandoned_suffix(git_repo: GitRepo) -> None:
    """Test that recovery strips (abandoned) suffix from tab completion input."""
    # Setup: Create and abandon a plan
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "suffix-test.md"
    write_plan(
        plan_file,
        {
            "plan_id": "suffix-test",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "suffix-test")
    move_backup_to_abandoned(git_repo.path, "suffix-test")
    plan_file.unlink()

    # Execute: Recover with (abandoned) suffix
    with patch("weft.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id="suffix-test (abandoned)", force=False, show_abandoned=True
        )

    # Verify: Success
    assert exit_code == 0

    # Verify: File restored
    assert plan_file.exists()


def test_parse_abandoned_log_finds_reason(git_repo: GitRepo) -> None:
    """Test that parse_abandoned_log finds the reason for a plan."""
    # Setup: Create log file
    log_file = git_repo.path / ".weft" / "abandoned-plans.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(
        "## first-plan - 2025-01-01 12:00:00 -0800\nFirst reason\n\n"
        "## second-plan - 2025-01-02 12:00:00 -0800\nSecond reason\nwith multiple lines\n\n",
        encoding="utf-8",
    )

    # Execute: Parse log for first-plan
    reason = parse_abandoned_log(git_repo.path, "first-plan")
    assert reason == "First reason"

    # Execute: Parse log for second-plan
    reason = parse_abandoned_log(git_repo.path, "second-plan")
    assert "Second reason" in reason
    assert "with multiple lines" in reason


def test_parse_abandoned_log_returns_none_when_not_found(git_repo: GitRepo) -> None:
    """Test that parse_abandoned_log returns None when plan not in log."""
    # Setup: Create log file without the plan we're looking for
    log_file = git_repo.path / ".weft" / "abandoned-plans.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(
        "## other-plan - 2025-01-01 12:00:00 -0800\nSome reason\n\n",
        encoding="utf-8",
    )

    # Execute: Parse log for non-existent plan
    reason = parse_abandoned_log(git_repo.path, "not-in-log")

    # Verify: Returns None
    assert reason is None


def test_parse_abandoned_log_returns_none_when_no_file(git_repo: GitRepo) -> None:
    """Test that parse_abandoned_log returns None when log file doesn't exist."""
    # Execute: Parse log when file doesn't exist
    reason = parse_abandoned_log(git_repo.path, "any-plan")

    # Verify: Returns None
    assert reason is None
