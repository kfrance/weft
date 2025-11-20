"""Tests for quick fix functionality."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from lw_coder.plan_validator import load_plan_metadata
from lw_coder.quick_fix import QuickFixError, create_quick_fix_plan, generate_quick_fix_id

from conftest import GitRepo


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
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
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
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)

        with pytest.raises(QuickFixError, match="Text cannot be empty"):
            create_quick_fix_plan("")

    def test_whitespace_only_text(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that whitespace-only text is rejected."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)

        with pytest.raises(QuickFixError, match="Text cannot be empty"):
            create_quick_fix_plan("   \n  \t  ")

    def test_multiline_text_preserved(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that multi-line text input is preserved exactly."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)

        text = "Fix login\n\nUpdate button styles\nAdd hover effect"
        plan_path = create_quick_fix_plan(text)

        content = plan_path.read_text(encoding="utf-8")
        assert text in content

    def test_creates_tasks_directory(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that tasks directory is created if it doesn't exist."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
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
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)

        # Mock write_text to raise an OSError
        with patch("pathlib.Path.write_text", side_effect=OSError("Disk full")):
            with pytest.raises(QuickFixError, match="Failed to write plan file"):
                create_quick_fix_plan("Test fix")

    def test_non_string_text(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that non-string text is rejected."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)

        with pytest.raises(QuickFixError, match="Text must be a string"):
            create_quick_fix_plan(123)  # type: ignore

    def test_sequential_creation(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that multiple quick fixes get sequential IDs."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
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
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
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
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)

        plan_path = create_quick_fix_plan("Test fix")

        metadata = load_plan_metadata(plan_path)

        # Should match pattern ^[a-zA-Z0-9._-]{3,100}$
        pattern = re.compile(r"^[a-zA-Z0-9._-]{3,100}$")
        assert pattern.match(metadata.plan_id)

    def test_plan_id_uniqueness(self, git_repo: GitRepo, monkeypatch) -> None:
        """Test that each generated plan has a unique plan_id."""
        monkeypatch.chdir(git_repo.path)
        tasks_dir = git_repo.path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)

        plan1 = create_quick_fix_plan("First fix")
        plan2 = create_quick_fix_plan("Second fix")

        metadata1 = load_plan_metadata(plan1)
        metadata2 = load_plan_metadata(plan2)

        assert metadata1.plan_id != metadata2.plan_id
