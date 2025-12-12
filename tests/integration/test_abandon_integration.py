"""Integration tests for abandon command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lw_coder.abandon_command import run_abandon_command
from lw_coder.plan_backup import (
    backup_exists_in_namespace,
    create_backup,
    list_abandoned_plans,
    list_backups,
)
from lw_coder.recover_command import run_recover_command

from conftest import GitRepo, write_plan


def test_end_to_end_abandon_workflow(git_repo: GitRepo) -> None:
    """Test complete abandon workflow with real git repository."""
    # Setup: Create plan file, backup, worktree, and branch
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "integration-test.md"
    commit_sha = git_repo.latest_commit()
    write_plan(
        plan_file,
        {
            "plan_id": "integration-test",
            "status": "draft",
            "git_sha": commit_sha,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "integration-test")

    # Create branch and worktree
    git_repo.run("branch", "integration-test", commit_sha)
    worktree_path = git_repo.path / ".lw_coder" / "worktrees" / "integration-test"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    git_repo.run("worktree", "add", str(worktree_path), "integration-test")

    # Verify initial state
    assert plan_file.exists()
    assert worktree_path.exists()
    assert backup_exists_in_namespace(git_repo.path, "integration-test", "plan-backups")

    # Execute: Abandon the plan
    with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_abandon_command(
            plan_file,
            reason="Integration test abandonment",
            skip_confirmation=True,
        )

    # Verify: Success
    assert exit_code == 0

    # Verify: All artifacts cleaned up
    assert not plan_file.exists()
    assert not worktree_path.exists()

    # Verify: Branch deleted
    branch_check = subprocess.run(
        ["git", "branch", "--list", "integration-test"],
        cwd=git_repo.path,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert "integration-test" not in branch_check.stdout

    # Verify: Backup moved to abandoned namespace
    assert not backup_exists_in_namespace(git_repo.path, "integration-test", "plan-backups")
    assert backup_exists_in_namespace(git_repo.path, "integration-test", "plan-abandoned")

    # Verify: Reason logged
    log_file = git_repo.path / ".lw_coder" / "abandoned-plans.log"
    assert log_file.exists()
    log_content = log_file.read_text(encoding="utf-8")
    assert "integration-test" in log_content
    assert "Integration test abandonment" in log_content


def test_recover_abandoned_plan_workflow(git_repo: GitRepo) -> None:
    """Test recovering an abandoned plan and verifying ref moves back."""
    # Setup: Create plan file and backup
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "recoverable-plan.md"
    write_plan(
        plan_file,
        {
            "plan_id": "recoverable-plan",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Recoverable Plan Body",
    )
    create_backup(git_repo.path, "recoverable-plan")

    # Abandon the plan
    with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
        run_abandon_command(plan_file, reason="Will recover later", skip_confirmation=True)

    # Verify: Plan is in abandoned namespace
    assert not plan_file.exists()
    assert not backup_exists_in_namespace(git_repo.path, "recoverable-plan", "plan-backups")
    assert backup_exists_in_namespace(git_repo.path, "recoverable-plan", "plan-abandoned")

    # Execute: Recover the abandoned plan
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id="recoverable-plan",
            force=False,
            show_abandoned=True,
            show_all=False,
        )

    # Verify: Success
    assert exit_code == 0

    # Verify: Plan file restored
    assert plan_file.exists()
    assert "# Recoverable Plan Body" in plan_file.read_text(encoding="utf-8")

    # Verify: Ref moved back to plan-backups
    assert backup_exists_in_namespace(git_repo.path, "recoverable-plan", "plan-backups")
    assert not backup_exists_in_namespace(git_repo.path, "recoverable-plan", "plan-abandoned")


def test_multiple_abandon_recover_cycles(git_repo: GitRepo) -> None:
    """Test multiple abandon/recover cycles on the same plan."""
    # Setup: Create plan file and backup
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "cycle-test.md"
    write_plan(
        plan_file,
        {
            "plan_id": "cycle-test",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "cycle-test")

    # Cycle 1: Abandon
    with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_abandon_command(plan_file, reason="Cycle 1", skip_confirmation=True)
    assert exit_code == 0
    assert backup_exists_in_namespace(git_repo.path, "cycle-test", "plan-abandoned")

    # Cycle 1: Recover
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command("cycle-test", force=False, show_abandoned=True)
    assert exit_code == 0
    assert backup_exists_in_namespace(git_repo.path, "cycle-test", "plan-backups")

    # Cycle 2: Abandon again
    with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_abandon_command(plan_file, reason="Cycle 2", skip_confirmation=True)
    assert exit_code == 0
    assert backup_exists_in_namespace(git_repo.path, "cycle-test", "plan-abandoned")

    # Verify log has both entries
    log_file = git_repo.path / ".lw_coder" / "abandoned-plans.log"
    log_content = log_file.read_text(encoding="utf-8")
    assert "Cycle 1" in log_content
    assert "Cycle 2" in log_content


def test_list_abandoned_plans_flag(git_repo: GitRepo, capsys) -> None:
    """Test --abandoned flag shows only abandoned plans."""
    # Setup: Create active backup and abandoned backup
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create and abandon first plan
    plan1 = tasks_dir / "abandoned-one.md"
    write_plan(
        plan1,
        {
            "plan_id": "abandoned-one",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "abandoned-one")
    with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
        run_abandon_command(plan1, skip_confirmation=True)

    # Create active backup for second plan
    plan2 = tasks_dir / "active-one.md"
    write_plan(
        plan2,
        {
            "plan_id": "active-one",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "active-one")

    # Execute: List with --abandoned flag
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id=None,
            force=False,
            show_abandoned=True,
            show_all=False,
        )

    # Verify: Success
    assert exit_code == 0

    # Verify: Shows only abandoned plans
    captured = capsys.readouterr()
    assert "abandoned-one" in captured.out
    assert "active-one" not in captured.out
    assert "abandoned plan(s)" in captured.out


def test_list_all_plans_flag(git_repo: GitRepo, capsys) -> None:
    """Test --all flag shows both active and abandoned plans."""
    # Setup: Create active backup and abandoned backup
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create and abandon first plan
    plan1 = tasks_dir / "abandoned-two.md"
    write_plan(
        plan1,
        {
            "plan_id": "abandoned-two",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "abandoned-two")
    with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
        run_abandon_command(plan1, skip_confirmation=True)

    # Create active backup for second plan
    plan2 = tasks_dir / "active-two.md"
    write_plan(
        plan2,
        {
            "plan_id": "active-two",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "active-two")

    # Execute: List with --all flag
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id=None,
            force=False,
            show_abandoned=False,
            show_all=True,
        )

    # Verify: Success
    assert exit_code == 0

    # Verify: Shows both plans
    captured = capsys.readouterr()
    assert "abandoned-two" in captured.out
    assert "active-two" in captured.out
    assert "active" in captured.out.lower()
    assert "abandoned" in captured.out.lower()


def test_git_refs_integrity_after_operations(git_repo: GitRepo) -> None:
    """Test git refs remain valid after abandon/recover operations."""
    # Setup: Create plan file and backup
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "ref-test.md"
    write_plan(
        plan_file,
        {
            "plan_id": "ref-test",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Ref Test Body",
    )
    create_backup(git_repo.path, "ref-test")

    # Get original ref SHA
    original_ref = subprocess.run(
        ["git", "show-ref", "--hash", "refs/plan-backups/ref-test"],
        cwd=git_repo.path,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    original_sha = original_ref.stdout.strip()

    # Abandon
    with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
        run_abandon_command(plan_file, skip_confirmation=True)

    # Verify abandoned ref has same SHA
    abandoned_ref = subprocess.run(
        ["git", "show-ref", "--hash", "refs/plan-abandoned/ref-test"],
        cwd=git_repo.path,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert abandoned_ref.stdout.strip() == original_sha

    # Recover
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        run_recover_command("ref-test", force=False, show_abandoned=True)

    # Verify restored ref has same SHA
    restored_ref = subprocess.run(
        ["git", "show-ref", "--hash", "refs/plan-backups/ref-test"],
        cwd=git_repo.path,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert restored_ref.stdout.strip() == original_sha


def test_log_file_format_and_content(git_repo: GitRepo) -> None:
    """Test abandoned plans log file format."""
    # Setup: Create and abandon multiple plans
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    for i, (plan_id, reason) in enumerate([
        ("log-test-one", "First reason"),
        ("log-test-two", "Second reason\nwith multiple lines"),
    ]):
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
        with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
            run_abandon_command(plan_file, reason=reason, skip_confirmation=True)

    # Verify log file format
    log_file = git_repo.path / ".lw_coder" / "abandoned-plans.log"
    assert log_file.exists()

    content = log_file.read_text(encoding="utf-8")

    # Verify format: ## <plan_id> - <timestamp>
    assert "## log-test-one" in content
    assert "## log-test-two" in content
    assert "First reason" in content
    assert "Second reason" in content
    assert "with multiple lines" in content

    # Verify timestamps are included (format: YYYY-MM-DD HH:MM:SS)
    import re
    timestamp_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
    assert re.search(timestamp_pattern, content)


def test_list_abandoned_shows_reason(git_repo: GitRepo, capsys) -> None:
    """Test that listing abandoned plans shows the abandonment reason."""
    # Setup: Create plan file and backup
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "reason-test.md"
    write_plan(
        plan_file,
        {
            "plan_id": "reason-test",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "reason-test")

    # Abandon with a specific reason
    with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
        run_abandon_command(
            plan_file,
            reason="The reason for abandoning this plan",
            skip_confirmation=True,
        )

    # Execute: List abandoned plans
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id=None,
            force=False,
            show_abandoned=True,
            show_all=False,
        )

    # Verify: Success and reason is shown
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "reason-test" in captured.out
    assert "Reason:" in captured.out
    assert "The reason for abandoning this plan" in captured.out


def test_plan_backup_create_and_list(git_repo: GitRepo) -> None:
    """Test plan_backup module create_backup and list_backups functions directly."""
    from lw_coder.plan_backup import create_backup, list_backups

    # Setup: Create plan files
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    for plan_id in ["backup-test-a", "backup-test-b"]:
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

    # Execute: List backups
    backups = list_backups(git_repo.path)

    # Verify: Both backups exist
    plan_ids = [plan_id for plan_id, _, _ in backups]
    assert "backup-test-a" in plan_ids
    assert "backup-test-b" in plan_ids

    # Verify: Timestamps are valid (non-zero)
    for _, timestamp, _ in backups:
        assert timestamp > 0

    # Verify: File exists flag is correct
    for plan_id, _, file_exists in backups:
        if plan_id in ["backup-test-a", "backup-test-b"]:
            assert file_exists is True


def test_plan_backup_recover(git_repo: GitRepo) -> None:
    """Test plan_backup module recover_backup function directly."""
    from lw_coder.plan_backup import create_backup, recover_backup

    # Setup: Create and backup a plan
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "recover-test.md"
    write_plan(
        plan_file,
        {
            "plan_id": "recover-test",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Original Content",
    )
    create_backup(git_repo.path, "recover-test")

    # Modify the plan file
    write_plan(
        plan_file,
        {
            "plan_id": "recover-test",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
        body="# Modified Content",
    )
    assert "# Modified Content" in plan_file.read_text(encoding="utf-8")

    # Execute: Recover backup with force
    recovered_path = recover_backup(git_repo.path, "recover-test", force=True)

    # Verify: Original content restored
    assert recovered_path == plan_file
    assert "# Original Content" in plan_file.read_text(encoding="utf-8")
    assert "# Modified Content" not in plan_file.read_text(encoding="utf-8")


def test_recover_command_error_cases(git_repo: GitRepo, capsys) -> None:
    """Test recover_command error handling for edge cases."""
    # Setup: Create an abandoned plan (no active backup)
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "error-test.md"
    write_plan(
        plan_file,
        {
            "plan_id": "error-test",
            "status": "draft",
            "git_sha": "0" * 40,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "error-test")
    with patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path):
        run_abandon_command(plan_file, skip_confirmation=True)

    # Execute: Try to recover from active backups (should fail with helpful message)
    with patch("lw_coder.recover_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_recover_command(
            plan_id="error-test",
            force=False,
            show_abandoned=False,  # Looking in active, but it's in abandoned
            show_all=False,
        )

    # Verify: Failure with helpful message about abandoned location
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "exists in abandoned plans" in captured.out
    assert "--abandoned" in captured.out
