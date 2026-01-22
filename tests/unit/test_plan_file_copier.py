"""Tests for plan file copier module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from weft.plan_file_copier import (
    PlanFileCopyError,
    copy_plan_files,
    get_existing_files,
)


class TestCopyPlanFilesBehavior:
    """Tests for copy_plan_files behavior."""

    def test_copy_result_tracks_files_found(self, tmp_path: Path) -> None:
        """Verify files_found count matches new files detected."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        # Track existing files (none)
        existing_files = get_existing_files(source_dir)

        # Create 3 new files
        (source_dir / "plan-a.md").write_text("content a")
        (source_dir / "plan-b.md").write_text("content b")
        (source_dir / "plan-c.md").write_text("content c")

        result = copy_plan_files(source_dir, dest_dir, existing_files)

        assert result.files_found == 3
        assert len(result.file_mapping) == 3

    def test_copy_result_tracks_failed_files(self, tmp_path: Path) -> None:
        """Verify files_failed populated when individual copies fail."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        # Track existing files (none)
        existing_files = get_existing_files(source_dir)

        # Create new files
        (source_dir / "plan-a.md").write_text("content a")
        (source_dir / "plan-b.md").write_text("content b")

        # Mock write_bytes to fail for a specific file (by name, not order)
        original_write_bytes = Path.write_bytes

        def mock_write_bytes(self, data):
            # Fail for plan-b.md specifically
            if self.name == "plan-b.md":
                raise OSError("Simulated write failure")
            return original_write_bytes(self, data)

        with patch.object(Path, "write_bytes", mock_write_bytes):
            result = copy_plan_files(source_dir, dest_dir, existing_files)

        assert result.files_found == 2
        # plan-a.md should have succeeded, plan-b.md should have failed
        assert len(result.file_mapping) == 1
        assert "plan-a.md" in result.file_mapping
        assert len(result.files_failed) == 1
        assert "plan-b.md" in result.files_failed

    def test_copy_result_empty_when_no_new_files(self, tmp_path: Path) -> None:
        """Verify files_found == 0 when no new files exist."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        # Create existing file before capturing existing files
        (source_dir / "old-plan.md").write_text("old content")
        existing_files = get_existing_files(source_dir)

        # No new files created
        result = copy_plan_files(source_dir, dest_dir, existing_files)

        assert result.files_found == 0
        assert result.file_mapping == {}
        assert result.files_failed == []

    def test_copy_plan_files_file_mapping_populated(self, tmp_path: Path) -> None:
        """Test that file_mapping is correctly populated in CopyResult."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        existing_files = get_existing_files(source_dir)
        (source_dir / "my-feature.md").write_text("# My Feature")

        result = copy_plan_files(source_dir, dest_dir, existing_files)

        assert result.file_mapping == {"my-feature.md": "my-feature.md"}
        assert result.files_found == 1
        assert result.files_failed == []

    def test_copy_plan_files_with_conflict_uses_copy_result(self, tmp_path: Path) -> None:
        """Test that CopyResult tracks files correctly even with naming conflicts."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        # Create existing file in destination
        (dest_dir / "my-feature.md").write_text("old content")

        existing_files = get_existing_files(source_dir)
        (source_dir / "my-feature.md").write_text("new content")

        result = copy_plan_files(source_dir, dest_dir, existing_files)

        assert result.file_mapping == {"my-feature.md": "my-feature (1).md"}
        assert result.files_found == 1
        assert result.files_failed == []

    def test_copy_plan_files_raises_plan_file_copy_error(self, tmp_path: Path) -> None:
        """Test that PlanFileCopyError is raised when dest doesn't exist."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "nonexistent"
        source_dir.mkdir()

        existing_files = get_existing_files(source_dir)
        (source_dir / "plan.md").write_text("content")

        with pytest.raises(PlanFileCopyError, match="Destination directory does not exist"):
            copy_plan_files(source_dir, dest_dir, existing_files)
