"""Tests for quick fix functionality."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from weft.plan_validator import load_plan_metadata
from weft.quick_fix import (
    QuickFixError,
    create_quick_fix_plan,
    extract_quick_fix_counter,
    generate_quick_fix_id,
)
from weft.worktree_utils import WorktreeError, list_branches_matching_pattern

from tests.helpers import GitRepo


class TestGenerateQuickFixId:
    """Tests for generate_quick_fix_id function."""

    def test_no_existing_files(self, tmp_path: Path) -> None:
        """Test ID generation with no existing files returns 001."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        plan_id = generate_quick_fix_id(tasks_dir)

        now = datetime.now()
        expected = f"quick-fix-{now.year:04d}.{now.month:02d}-001"
        assert plan_id == expected

    def test_with_existing_files(self, tmp_path: Path) -> None:
        """Test ID generation increments highest existing counter."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        now = datetime.now()
        year = now.year
        month = now.month

        # Create existing files
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-001.md").touch()
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-002.md").touch()
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-005.md").touch()

        plan_id = generate_quick_fix_id(tasks_dir)

        expected = f"quick-fix-{year:04d}.{month:02d}-006"
        assert plan_id == expected

    def test_gaps_in_sequence(self, tmp_path: Path) -> None:
        """Test ID generation with gaps in sequence returns next after highest."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        now = datetime.now()
        year = now.year
        month = now.month

        # Create files with gaps: 001, 003
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-001.md").touch()
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-003.md").touch()

        plan_id = generate_quick_fix_id(tasks_dir)

        expected = f"quick-fix-{year:04d}.{month:02d}-004"
        assert plan_id == expected

    def test_different_months_separate_counters(self, tmp_path: Path) -> None:
        """Test that counters are separate for different months."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        now = datetime.now()
        year = now.year
        month = now.month

        # Create files from previous month
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        (tasks_dir / f"quick-fix-{prev_year:04d}.{prev_month:02d}-050.md").touch()

        # Create one file from current month
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-001.md").touch()

        plan_id = generate_quick_fix_id(tasks_dir)

        # Should be 002 for current month, not 051
        expected = f"quick-fix-{year:04d}.{month:02d}-002"
        assert plan_id == expected

    def test_overflow_fallback_to_timestamp(self, tmp_path: Path) -> None:
        """Test overflow scenario falls back to timestamp format."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        now = datetime.now()
        year = now.year
        month = now.month

        # Create file with counter 999
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-999.md").touch()

        plan_id = generate_quick_fix_id(tasks_dir)

        # Should use timestamp format: quick-fix-YYYY.MM.DD-HHMMSS
        pattern = rf"quick-fix-{year:04d}\.{month:02d}\.\d{{2}}-\d{{6}}"
        assert re.match(pattern, plan_id)

    def test_ignores_invalid_format(self, tmp_path: Path) -> None:
        """Test that files with invalid counter format are ignored."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        now = datetime.now()
        year = now.year
        month = now.month

        # Create valid file
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-001.md").touch()

        # Create invalid files that should be ignored
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-abc.md").touch()
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-99.md").touch()  # Only 2 digits
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-1234.md").touch()  # 4 digits

        plan_id = generate_quick_fix_id(tasks_dir)

        # Should return 002, ignoring invalid files
        expected = f"quick-fix-{year:04d}.{month:02d}-002"
        assert plan_id == expected


class TestCreateQuickFixPlan:
    """Tests for create_quick_fix_plan function."""

    def test_valid_text(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test plan creation with valid text."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        plan_path = create_quick_fix_plan("Fix the login button styling")

        assert plan_path.exists()
        assert plan_path.parent == tasks_dir
        assert plan_path.name.startswith("quick-fix-")
        assert plan_path.suffix == ".md"

        # Verify content
        content = plan_path.read_text(encoding="utf-8")
        assert "Fix the login button styling" in content
        assert "status: draft" in content
        assert "0000000000000000000000000000000000000000" in content

    def test_empty_text(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that empty text is rejected."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        with pytest.raises(QuickFixError, match="Text cannot be empty"):
            create_quick_fix_plan("")

    def test_whitespace_only_text(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that whitespace-only text is rejected."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        with pytest.raises(QuickFixError, match="Text cannot be empty"):
            create_quick_fix_plan("   \n  \t  ")

    def test_multiline_text_preserved(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that multi-line text input is preserved exactly."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        text = "Fix login\n\nUpdate button styles\nAdd hover effect"
        plan_path = create_quick_fix_plan(text)

        content = plan_path.read_text(encoding="utf-8")
        assert text in content

    def test_creates_tasks_directory(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that tasks directory is created if it doesn't exist."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        assert not tasks_dir.exists()

        plan_path = create_quick_fix_plan("Test fix")

        assert tasks_dir.exists()
        assert plan_path.parent == tasks_dir

    def test_not_in_git_repo(self, tmp_path: Path, monkeypatch) -> None:
        """Test that error is raised when not in a git repository."""
        # Change to a non-git directory
        non_git_dir = tmp_path / "not-a-repo"
        non_git_dir.mkdir()
        monkeypatch.chdir(non_git_dir)

        with pytest.raises(QuickFixError, match="Failed to find repository root"):
            create_quick_fix_plan("Test fix")

    def test_filesystem_error_handling(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test handling of filesystem errors during plan creation."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        # Mock write_text to raise an OSError
        with patch("pathlib.Path.write_text", side_effect=OSError("Disk full")):
            with pytest.raises(QuickFixError, match="Failed to write plan file"):
                create_quick_fix_plan("Test fix")

    def test_non_string_text(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that non-string text is rejected."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        with pytest.raises(QuickFixError, match="Text must be a string"):
            create_quick_fix_plan(123)  # type: ignore

    def test_sequential_creation(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that multiple quick fixes get sequential IDs."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        plan1 = create_quick_fix_plan("First fix")
        plan2 = create_quick_fix_plan("Second fix")
        plan3 = create_quick_fix_plan("Third fix")

        # Extract counter from filenames
        now = datetime.now()
        pattern = rf"quick-fix-{now.year:04d}\.{now.month:02d}-(\d{{3}})\.md"

        match1 = re.match(pattern, plan1.name)
        match2 = re.match(pattern, plan2.name)
        match3 = re.match(pattern, plan3.name)

        assert match1 and match2 and match3

        counter1 = int(match1.group(1))
        counter2 = int(match2.group(1))
        counter3 = int(match3.group(1))

        assert counter2 == counter1 + 1
        assert counter3 == counter2 + 1


class TestPlanValidationIntegration:
    """Integration tests for plan validation."""

    def test_generated_plan_passes_validation(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that a generated plan file passes load_plan_metadata validation."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        plan_path = create_quick_fix_plan("Test fix for validation")

        # This should not raise any exceptions
        metadata = load_plan_metadata(plan_path)

        assert metadata.plan_id.startswith("quick-fix-")
        assert metadata.status == "draft"
        assert metadata.git_sha == "0000000000000000000000000000000000000000"
        assert metadata.plan_text.strip() == "Test fix for validation"
        assert metadata.evaluation_notes == []

    def test_plan_id_matches_pattern(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that generated plan_id matches validation pattern."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        plan_path = create_quick_fix_plan("Test fix")

        metadata = load_plan_metadata(plan_path)

        # Should match pattern ^[a-zA-Z0-9._-]{3,100}$
        pattern = re.compile(r"^[a-zA-Z0-9._-]{3,100}$")
        assert pattern.match(metadata.plan_id)

    def test_plan_id_uniqueness(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that each generated plan has a unique plan_id."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        plan1 = create_quick_fix_plan("First fix")
        plan2 = create_quick_fix_plan("Second fix")

        metadata1 = load_plan_metadata(plan1)
        metadata2 = load_plan_metadata(plan2)

        assert metadata1.plan_id != metadata2.plan_id


class TestExtractQuickFixCounter:
    """Tests for extract_quick_fix_counter helper function."""

    def test_extract_counter_from_filename(self) -> None:
        """Test extracting counter from a valid filename."""
        counter = extract_quick_fix_counter("quick-fix-2026.02-005.md", 2026, 2)
        assert counter == 5

    def test_extract_counter_from_branch(self) -> None:
        """Test extracting counter from a valid branch name."""
        counter = extract_quick_fix_counter("quick-fix-2026.02-005", 2026, 2)
        assert counter == 5

    def test_extract_counter_from_high_number(self) -> None:
        """Test extracting counter with high number (999)."""
        counter = extract_quick_fix_counter("quick-fix-2026.12-999.md", 2026, 12)
        assert counter == 999

    def test_extract_counter_invalid_format_no_dash(self) -> None:
        """Test that invalid format without dash returns None."""
        counter = extract_quick_fix_counter("quick-fix-2026.02.001.md", 2026, 2)
        assert counter is None

    def test_extract_counter_invalid_format_wrong_digits(self) -> None:
        """Test that counter with wrong number of digits returns None."""
        # Too few digits
        counter = extract_quick_fix_counter("quick-fix-2026.02-01.md", 2026, 2)
        assert counter is None
        # Too many digits
        counter = extract_quick_fix_counter("quick-fix-2026.02-0001.md", 2026, 2)
        assert counter is None

    def test_extract_counter_wrong_month(self) -> None:
        """Test that different month returns None."""
        counter = extract_quick_fix_counter("quick-fix-2026.02-005.md", 2026, 3)
        assert counter is None

    def test_extract_counter_wrong_year(self) -> None:
        """Test that different year returns None."""
        counter = extract_quick_fix_counter("quick-fix-2026.02-005.md", 2025, 2)
        assert counter is None

    def test_extract_counter_timestamp_format(self) -> None:
        """Test that timestamp format returns None (not counter format)."""
        counter = extract_quick_fix_counter("quick-fix-2026.02.15-143052", 2026, 2)
        assert counter is None

    def test_extract_counter_non_quick_fix(self) -> None:
        """Test that non-quick-fix names return None."""
        counter = extract_quick_fix_counter("feature-branch-001", 2026, 2)
        assert counter is None

    def test_extract_counter_leading_zeros(self) -> None:
        """Test extracting counter preserves leading zeros in value."""
        counter = extract_quick_fix_counter("quick-fix-2026.02-001.md", 2026, 2)
        assert counter == 1


class TestListBranchesMatchingPattern:
    """Tests for list_branches_matching_pattern function."""

    def test_list_local_branches(self, git_repo: GitRepo) -> None:
        """Test listing local branches matching pattern."""
        # Create some branches
        git_repo.run("branch", "quick-fix-2026.02-001")
        git_repo.run("branch", "quick-fix-2026.02-003")
        git_repo.run("branch", "feature-unrelated")

        branches = list_branches_matching_pattern(
            git_repo.path, "quick-fix-2026.02-*"
        )

        assert "quick-fix-2026.02-001" in branches
        assert "quick-fix-2026.02-003" in branches
        assert "feature-unrelated" not in branches

    def test_list_no_matching_branches(self, git_repo: GitRepo) -> None:
        """Test listing when no branches match returns empty list."""
        branches = list_branches_matching_pattern(
            git_repo.path, "quick-fix-2099.01-*"
        )
        assert branches == []

    def test_list_remote_branches(self, git_repo: GitRepo, tmp_path: Path) -> None:
        """Test listing remote tracking branches."""
        # Create a "remote" repository
        remote_path = tmp_path / "remote"
        remote_path.mkdir()
        import subprocess
        subprocess.run(["git", "init", "--bare"], cwd=remote_path, check=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Add remote to test repo
        git_repo.run("remote", "add", "origin", str(remote_path))

        # Create a branch and push it
        git_repo.run("branch", "quick-fix-2026.02-002")
        git_repo.run("push", "origin", "quick-fix-2026.02-002")

        # Delete local branch to isolate remote tracking branch test
        git_repo.run("branch", "-D", "quick-fix-2026.02-002")

        # Fetch to ensure remote tracking refs are present
        git_repo.run("fetch", "origin")

        branches = list_branches_matching_pattern(
            git_repo.path, "quick-fix-2026.02-*"
        )

        # Should include the remote tracking branch (only remote exists now)
        assert "quick-fix-2026.02-002" in branches

    def test_list_branches_invalid_repo(self, tmp_path: Path) -> None:
        """Test that invalid repo raises WorktreeError."""
        non_git_dir = tmp_path / "not-a-repo"
        non_git_dir.mkdir()

        with pytest.raises(WorktreeError):
            list_branches_matching_pattern(non_git_dir, "quick-fix-*")


class TestGenerateQuickFixIdBranchCollision:
    """Tests for branch collision detection in generate_quick_fix_id."""

    def test_existing_branch_no_task_file(self, git_repo: GitRepo) -> None:
        """Test that existing branch without task file is detected."""
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        now = datetime.now()
        year = now.year
        month = now.month

        # Create branch for counter 003 but no task file
        git_repo.run("branch", f"quick-fix-{year:04d}.{month:02d}-003")

        plan_id = generate_quick_fix_id(tasks_dir, repo_root=git_repo.path)

        # Should return 004, skipping the counter used by the branch
        expected = f"quick-fix-{year:04d}.{month:02d}-004"
        assert plan_id == expected

    def test_branch_and_file_both_exist(self, git_repo: GitRepo) -> None:
        """Test that max of file and branch counters is used."""
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        now = datetime.now()
        year = now.year
        month = now.month

        # Create task files for 001, 002
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-001.md").touch()
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-002.md").touch()

        # Create branch for 005 (higher than files)
        git_repo.run("branch", f"quick-fix-{year:04d}.{month:02d}-005")

        plan_id = generate_quick_fix_id(tasks_dir, repo_root=git_repo.path)

        # Should return 006 (max of branch and file counters + 1)
        expected = f"quick-fix-{year:04d}.{month:02d}-006"
        assert plan_id == expected

    def test_same_counter_in_file_and_branch(self, git_repo: GitRepo) -> None:
        """Test that duplicate counter in file and branch doesn't cause issues."""
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        now = datetime.now()
        year = now.year
        month = now.month

        # Create both file and branch for counter 003
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-003.md").touch()
        git_repo.run("branch", f"quick-fix-{year:04d}.{month:02d}-003")

        plan_id = generate_quick_fix_id(tasks_dir, repo_root=git_repo.path)

        # Should return 004
        expected = f"quick-fix-{year:04d}.{month:02d}-004"
        assert plan_id == expected

    def test_remote_branch_detected(self, git_repo: GitRepo, tmp_path: Path) -> None:
        """Test that remote tracking branches are detected."""
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        now = datetime.now()
        year = now.year
        month = now.month

        # Create a "remote" repository
        remote_path = tmp_path / "remote"
        remote_path.mkdir()
        import subprocess
        subprocess.run(["git", "init", "--bare"], cwd=remote_path, check=True,
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Add remote
        git_repo.run("remote", "add", "origin", str(remote_path))

        # Create a branch, push it, and delete local copy
        git_repo.run("branch", f"quick-fix-{year:04d}.{month:02d}-002")
        git_repo.run("push", "origin", f"quick-fix-{year:04d}.{month:02d}-002")
        git_repo.run("branch", "-D", f"quick-fix-{year:04d}.{month:02d}-002")

        # Fetch to ensure remote tracking refs are present
        git_repo.run("fetch", "origin")

        plan_id = generate_quick_fix_id(tasks_dir, repo_root=git_repo.path)

        # Should return 003, detecting the remote tracking branch
        expected = f"quick-fix-{year:04d}.{month:02d}-003"
        assert plan_id == expected

    def test_git_failure_falls_back_to_files(self, tmp_path: Path, caplog) -> None:
        """Test that git failure falls back to file-only checking with warning."""
        import logging

        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        now = datetime.now()
        year = now.year
        month = now.month

        # Create a task file
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-001.md").touch()

        # Use a non-git directory as repo_root (will cause git command to fail)
        non_git_dir = tmp_path / "not-a-repo"
        non_git_dir.mkdir()

        # Should still work, falling back to file-only checking
        with caplog.at_level(logging.WARNING):
            plan_id = generate_quick_fix_id(tasks_dir, repo_root=non_git_dir)

        # Should return 002 based on file only
        expected = f"quick-fix-{year:04d}.{month:02d}-002"
        assert plan_id == expected

        # Verify warning was logged about falling back to file-only checking
        assert any(
            "falling back to file-only checking" in record.message
            for record in caplog.records
        )

    def test_repo_without_remotes(self, git_repo: GitRepo) -> None:
        """Test that repo without remotes still checks local branches."""
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        now = datetime.now()
        year = now.year
        month = now.month

        # Create local branch (no remotes configured in git_repo fixture)
        git_repo.run("branch", f"quick-fix-{year:04d}.{month:02d}-002")

        plan_id = generate_quick_fix_id(tasks_dir, repo_root=git_repo.path)

        # Should detect local branch
        expected = f"quick-fix-{year:04d}.{month:02d}-003"
        assert plan_id == expected

    def test_timestamp_branches_ignored(self, git_repo: GitRepo) -> None:
        """Test that timestamp-format branches are ignored by counter logic."""
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        now = datetime.now()
        year = now.year
        month = now.month

        # Create a timestamp-format branch (overflow format)
        git_repo.run("branch", f"quick-fix-{year:04d}.{month:02d}.15-143052")

        # Create a normal counter branch
        git_repo.run("branch", f"quick-fix-{year:04d}.{month:02d}-001")

        plan_id = generate_quick_fix_id(tasks_dir, repo_root=git_repo.path)

        # Should return 002, ignoring the timestamp branch
        expected = f"quick-fix-{year:04d}.{month:02d}-002"
        assert plan_id == expected

    def test_repo_root_none_skips_branch_check(self, git_repo: GitRepo) -> None:
        """Test that repo_root=None skips branch checking (backward compat)."""
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        now = datetime.now()
        year = now.year
        month = now.month

        # Create a branch for counter 005
        git_repo.run("branch", f"quick-fix-{year:04d}.{month:02d}-005")

        # Create task file for counter 001
        (tasks_dir / f"quick-fix-{year:04d}.{month:02d}-001.md").touch()

        # Call without repo_root - should only check files
        plan_id = generate_quick_fix_id(tasks_dir, repo_root=None)

        # Should return 002 based on files only, ignoring the branch
        expected = f"quick-fix-{year:04d}.{month:02d}-002"
        assert plan_id == expected
