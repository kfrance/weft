"""Tests for abandon command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from weft.abandon_command import (
    AbandonCommandError,
    CleanupResult,
    PlanArtifacts,
    _cleanup_branch,
    _cleanup_plan_file,
    _cleanup_worktree,
    _detect_plan_artifacts,
    _log_abandonment,
    _move_backup_to_abandoned_ref,
    _show_confirmation_prompt,
    run_abandon_command,
)
from weft.plan_backup import create_backup

from conftest import GitRepo, write_plan


def test_detect_plan_artifacts_all_present(git_repo: GitRepo) -> None:
    """Test artifact detection when all artifacts exist."""
    # Setup: Create plan file, backup, worktree, and branch
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "test-plan")

    # Create branch and worktree
    git_repo.run("branch", "test-plan", "HEAD")
    worktree_path = git_repo.path / ".weft" / "worktrees" / "test-plan"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    git_repo.run("worktree", "add", str(worktree_path), "test-plan")

    # Execute: Detect artifacts
    artifacts = _detect_plan_artifacts(git_repo.path, "test-plan")

    # Verify: All artifacts detected
    assert artifacts.worktree_exists is True
    assert artifacts.branch_exists is True
    assert artifacts.plan_file_exists is True
    assert artifacts.backup_ref_exists is True


def test_detect_plan_artifacts_none_present(git_repo: GitRepo) -> None:
    """Test artifact detection when no artifacts exist."""
    # Execute: Detect artifacts for non-existent plan
    artifacts = _detect_plan_artifacts(git_repo.path, "nonexistent-plan")

    # Verify: No artifacts detected
    assert artifacts.worktree_exists is False
    assert artifacts.branch_exists is False
    assert artifacts.plan_file_exists is False
    assert artifacts.backup_ref_exists is False


def test_detect_plan_artifacts_partial(git_repo: GitRepo) -> None:
    """Test artifact detection with some artifacts missing."""
    # Setup: Create only plan file and backup
    tasks_dir = git_repo.path / ".weft" / "tasks"
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

    # Execute: Detect artifacts
    artifacts = _detect_plan_artifacts(git_repo.path, "test-plan")

    # Verify: Only plan file and backup detected
    assert artifacts.worktree_exists is False
    assert artifacts.branch_exists is False
    assert artifacts.plan_file_exists is True
    assert artifacts.backup_ref_exists is True


def test_cleanup_worktree_success(git_repo: GitRepo) -> None:
    """Test successful worktree cleanup."""
    # Setup: Create branch and worktree
    git_repo.run("branch", "test-plan", "HEAD")
    worktree_path = git_repo.path / ".weft" / "worktrees" / "test-plan"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    git_repo.run("worktree", "add", str(worktree_path), "test-plan")
    assert worktree_path.exists()

    # Execute: Cleanup worktree
    result = _cleanup_worktree(git_repo.path, "test-plan")

    # Verify: Success
    assert result.success is True
    assert result.already_clean is False
    assert result.error_message is None
    assert not worktree_path.exists()


def test_cleanup_worktree_already_clean(git_repo: GitRepo) -> None:
    """Test worktree cleanup when worktree doesn't exist."""
    # Execute: Cleanup non-existent worktree
    result = _cleanup_worktree(git_repo.path, "nonexistent-plan")

    # Verify: Already clean
    assert result.success is True
    assert result.already_clean is True
    assert result.error_message is None


def test_cleanup_branch_success(git_repo: GitRepo) -> None:
    """Test successful branch cleanup."""
    # Setup: Create branch
    git_repo.run("branch", "test-plan", "HEAD")

    # Verify branch exists
    result = subprocess.run(
        ["git", "branch", "--list", "test-plan"],
        cwd=git_repo.path,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert "test-plan" in result.stdout

    # Execute: Cleanup branch
    result = _cleanup_branch(git_repo.path, "test-plan")

    # Verify: Success
    assert result.success is True
    assert result.already_clean is False
    assert result.error_message is None


def test_cleanup_branch_already_clean(git_repo: GitRepo) -> None:
    """Test branch cleanup when branch doesn't exist."""
    # Execute: Cleanup non-existent branch
    result = _cleanup_branch(git_repo.path, "nonexistent-plan")

    # Verify: Already clean
    assert result.success is True
    assert result.already_clean is True
    assert result.error_message is None


def test_cleanup_plan_file_success(git_repo: GitRepo) -> None:
    """Test successful plan file cleanup."""
    # Setup: Create plan file
    tasks_dir = git_repo.path / ".weft" / "tasks"
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
    assert plan_file.exists()

    # Execute: Cleanup plan file
    result = _cleanup_plan_file(git_repo.path, "test-plan")

    # Verify: Success
    assert result.success is True
    assert result.already_clean is False
    assert result.error_message is None
    assert not plan_file.exists()


def test_cleanup_plan_file_already_clean(git_repo: GitRepo) -> None:
    """Test plan file cleanup when file doesn't exist."""
    # Execute: Cleanup non-existent plan file
    result = _cleanup_plan_file(git_repo.path, "nonexistent-plan")

    # Verify: Already clean
    assert result.success is True
    assert result.already_clean is True
    assert result.error_message is None


def test_move_backup_to_abandoned_success(git_repo: GitRepo) -> None:
    """Test successful backup move to abandoned namespace."""
    # Setup: Create plan file and backup
    tasks_dir = git_repo.path / ".weft" / "tasks"
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

    # Verify backup exists in plan-backups
    result = subprocess.run(
        ["git", "show-ref", "refs/plan-backups/test-plan"],
        cwd=git_repo.path,
        check=False,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert result.returncode == 0

    # Execute: Move to abandoned
    result = _move_backup_to_abandoned_ref(git_repo.path, "test-plan")

    # Verify: Success
    assert result.success is True
    assert result.already_clean is False
    assert result.error_message is None

    # Verify backup moved to abandoned namespace
    check_backup = subprocess.run(
        ["git", "show-ref", "refs/plan-backups/test-plan"],
        cwd=git_repo.path,
        check=False,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert check_backup.returncode != 0  # Should not exist

    check_abandoned = subprocess.run(
        ["git", "show-ref", "refs/plan-abandoned/test-plan"],
        cwd=git_repo.path,
        check=False,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert check_abandoned.returncode == 0  # Should exist


def test_move_backup_to_abandoned_no_backup(git_repo: GitRepo) -> None:
    """Test move when no backup exists."""
    # Execute: Move non-existent backup
    result = _move_backup_to_abandoned_ref(git_repo.path, "nonexistent-plan")

    # Verify: Already clean (no backup to move)
    assert result.success is True
    assert result.already_clean is True
    assert result.error_message is None


def test_log_abandonment_creates_file(git_repo: GitRepo) -> None:
    """Test that abandonment logging creates log file."""
    # Execute: Log abandonment
    _log_abandonment(git_repo.path, "test-plan", "Test reason for abandonment")

    # Verify: Log file created
    log_file = git_repo.path / ".weft" / "abandoned-plans.log"
    assert log_file.exists()

    content = log_file.read_text(encoding="utf-8")
    assert "## test-plan" in content
    assert "Test reason for abandonment" in content


def test_log_abandonment_appends(git_repo: GitRepo) -> None:
    """Test that abandonment logging appends to existing file."""
    # Setup: Create initial log entry
    _log_abandonment(git_repo.path, "first-plan", "First reason")

    # Execute: Add another entry
    _log_abandonment(git_repo.path, "second-plan", "Second reason")

    # Verify: Both entries present
    log_file = git_repo.path / ".weft" / "abandoned-plans.log"
    content = log_file.read_text(encoding="utf-8")
    assert "## first-plan" in content
    assert "First reason" in content
    assert "## second-plan" in content
    assert "Second reason" in content


def test_run_abandon_command_with_all_artifacts(git_repo: GitRepo, monkeypatch) -> None:
    """Test abandon command with all artifacts present."""
    # Setup: Create plan file, backup, worktree, and branch
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    commit_sha = git_repo.latest_commit()
    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "status": "draft",
            "git_sha": commit_sha,
            "evaluation_notes": [],
        },
    )
    create_backup(git_repo.path, "test-plan")

    # Create branch and worktree
    git_repo.run("branch", "test-plan", commit_sha)
    worktree_path = git_repo.path / ".weft" / "worktrees" / "test-plan"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    git_repo.run("worktree", "add", str(worktree_path), "test-plan")

    # Execute: Run abandon command with --yes
    with patch("weft.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_abandon_command(plan_file, reason="Test abandonment", skip_confirmation=True)

    # Verify: Success
    assert exit_code == 0

    # Verify: All artifacts cleaned up
    assert not worktree_path.exists()
    assert not plan_file.exists()

    # Verify: Backup moved to abandoned
    check_abandoned = subprocess.run(
        ["git", "show-ref", "refs/plan-abandoned/test-plan"],
        cwd=git_repo.path,
        check=False,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert check_abandoned.returncode == 0

    # Verify: Reason logged
    log_file = git_repo.path / ".weft" / "abandoned-plans.log"
    assert log_file.exists()
    assert "Test abandonment" in log_file.read_text(encoding="utf-8")


def test_run_abandon_command_no_artifacts(git_repo: GitRepo, capsys) -> None:
    """Test abandon command when no artifacts exist."""
    # Execute: Run abandon command for non-existent plan
    with patch("weft.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_abandon_command("nonexistent-plan", skip_confirmation=True)

    # Verify: Success (nothing to clean up)
    assert exit_code == 0

    # Verify: Message about nothing to clean up
    captured = capsys.readouterr()
    assert "Nothing to clean up" in captured.out


def test_run_abandon_command_cancelled_by_user(git_repo: GitRepo, monkeypatch, capsys) -> None:
    """Test abandon command cancellation via user input."""
    # Setup: Create plan file
    tasks_dir = git_repo.path / ".weft" / "tasks"
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

    # Mock user input to decline
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    # Execute: Run abandon command without --yes
    with patch("weft.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_abandon_command(plan_file, skip_confirmation=False)

    # Verify: Cancelled
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "cancelled" in captured.out.lower()

    # Verify: Plan file still exists
    assert plan_file.exists()


def test_run_abandon_command_confirmed_by_user(git_repo: GitRepo, monkeypatch) -> None:
    """Test abandon command confirmation via user input."""
    # Setup: Create plan file
    tasks_dir = git_repo.path / ".weft" / "tasks"
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

    # Track prompts
    prompts_shown = []

    def mock_input(prompt):
        prompts_shown.append(prompt)
        return "y"

    monkeypatch.setattr("builtins.input", mock_input)

    # Execute: Run abandon command without --yes
    with patch("weft.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_abandon_command(plan_file, skip_confirmation=False)

    # Verify: Success
    assert exit_code == 0

    # Verify: Prompt was shown
    assert len(prompts_shown) == 1
    assert "Continue?" in prompts_shown[0]

    # Verify: Plan file deleted
    assert not plan_file.exists()


def test_run_abandon_command_without_reason_no_log(git_repo: GitRepo) -> None:
    """Test that no log entry is created when --reason not provided."""
    # Setup: Create plan file
    tasks_dir = git_repo.path / ".weft" / "tasks"
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

    # Execute: Run abandon command without --reason
    with patch("weft.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_abandon_command(plan_file, reason=None, skip_confirmation=True)

    # Verify: Success
    assert exit_code == 0

    # Verify: No log file created
    log_file = git_repo.path / ".weft" / "abandoned-plans.log"
    assert not log_file.exists()


def test_run_abandon_command_by_plan_id(git_repo: GitRepo) -> None:
    """Test abandon command using plan ID instead of path."""
    # Setup: Create plan file
    tasks_dir = git_repo.path / ".weft" / "tasks"
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

    # Execute: Run abandon command using plan ID
    with patch("weft.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_abandon_command("test-plan", skip_confirmation=True)

    # Verify: Success
    assert exit_code == 0

    # Verify: Plan file deleted
    assert not plan_file.exists()


def test_show_confirmation_prompt_all_artifacts(monkeypatch, capsys) -> None:
    """Test confirmation prompt shows all artifact warnings."""
    # Setup: Create artifacts with details
    artifacts = PlanArtifacts(
        worktree_exists=True,
        worktree_has_changes=True,
        branch_exists=True,
        branch_unmerged_commits=3,
        plan_file_exists=True,
        backup_ref_exists=True,
    )

    # Mock user input
    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    # Execute: Show prompt
    result = _show_confirmation_prompt("test-plan", artifacts)

    # Verify: User confirmed
    assert result is True

    # Verify: All warnings shown
    captured = capsys.readouterr()
    assert "Worktree will be force-deleted (has uncommitted changes)" in captured.out
    assert "Branch will be force-deleted (has 3 unmerged commits)" in captured.out
    assert "Plan file will be deleted" in captured.out
    assert "Backup moved to refs/plan-abandoned/test-plan" in captured.out


def test_show_confirmation_prompt_no_artifacts(monkeypatch, capsys) -> None:
    """Test confirmation prompt with no artifacts."""
    # Setup: No artifacts
    artifacts = PlanArtifacts(
        worktree_exists=False,
        worktree_has_changes=False,
        branch_exists=False,
        branch_unmerged_commits=0,
        plan_file_exists=False,
        backup_ref_exists=False,
    )

    # Execute: Show prompt (should return True without asking)
    result = _show_confirmation_prompt("test-plan", artifacts)

    # Verify: Returns True (nothing to clean up)
    assert result is True

    captured = capsys.readouterr()
    assert "no artifacts found" in captured.out.lower()


def test_run_abandon_command_idempotent(git_repo: GitRepo) -> None:
    """Test that abandon command can be run multiple times safely."""
    # Setup: Create plan file
    tasks_dir = git_repo.path / ".weft" / "tasks"
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

    # Execute: Run abandon command first time
    with patch("weft.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code1 = run_abandon_command("test-plan", skip_confirmation=True)

    # Verify: First run successful
    assert exit_code1 == 0

    # Execute: Run abandon command second time
    with patch("weft.abandon_command.find_repo_root", return_value=git_repo.path):
        exit_code2 = run_abandon_command("test-plan", skip_confirmation=True)

    # Verify: Second run also successful (idempotent)
    assert exit_code2 == 0


def test_cleanup_worktree_with_uncommitted_changes(git_repo: GitRepo) -> None:
    """Test worktree cleanup succeeds even with uncommitted changes."""
    # Setup: Create branch and worktree
    git_repo.run("branch", "test-plan", "HEAD")
    worktree_path = git_repo.path / ".weft" / "worktrees" / "test-plan"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    git_repo.run("worktree", "add", str(worktree_path), "test-plan")

    # Add uncommitted changes
    (worktree_path / "uncommitted.txt").write_text("uncommitted content", encoding="utf-8")

    # Execute: Cleanup worktree (force)
    result = _cleanup_worktree(git_repo.path, "test-plan")

    # Verify: Success even with uncommitted changes
    assert result.success is True
    assert result.already_clean is False
    assert not worktree_path.exists()


def test_cleanup_branch_force_deletes_unmerged(git_repo: GitRepo) -> None:
    """Test branch cleanup force-deletes unmerged branches."""
    # Get current branch name (could be 'main' or 'master' depending on git config)
    current_branch = git_repo.run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    # Setup: Create branch with unmerged commits
    git_repo.run("branch", "test-plan", "HEAD")
    git_repo.run("checkout", "test-plan")
    (git_repo.path / "unmerged.txt").write_text("unmerged content", encoding="utf-8")
    git_repo.run("add", "unmerged.txt")
    git_repo.run("commit", "-m", "unmerged commit")
    git_repo.run("checkout", current_branch)

    # Execute: Cleanup branch
    result = _cleanup_branch(git_repo.path, "test-plan")

    # Verify: Success (force deleted)
    assert result.success is True
    assert result.already_clean is False

    # Verify: Branch no longer exists
    check = subprocess.run(
        ["git", "branch", "--list", "test-plan"],
        cwd=git_repo.path,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert "test-plan" not in check.stdout
