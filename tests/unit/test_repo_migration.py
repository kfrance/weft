"""Tests for repository directory migration (.lw_coder -> .weft)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from weft.repo_utils import migrate_repo_dir_if_needed


class TestRepoMigration:
    """Tests for .lw_coder to .weft directory migration."""

    def test_migrate_repo_dir_legacy_to_new(self, tmp_path: Path) -> None:
        """Migrates .lw_coder/ to .weft/ when only legacy directory exists."""
        # Setup: Create .lw_coder/ with sample files
        old_dir = tmp_path / ".lw_coder"
        old_dir.mkdir()
        (old_dir / "tasks").mkdir()
        (old_dir / "tasks" / "plan1.md").write_text("Plan content")
        (old_dir / "worktrees").mkdir()

        # Action: Run migration
        result = migrate_repo_dir_if_needed(tmp_path)

        # Assert: Migration occurred
        assert result is True
        assert not old_dir.exists()
        new_dir = tmp_path / ".weft"
        assert new_dir.exists()
        assert (new_dir / "tasks" / "plan1.md").read_text() == "Plan content"
        assert (new_dir / "worktrees").exists()

    def test_migrate_repo_dir_already_migrated(self, tmp_path: Path) -> None:
        """No migration when .weft/ already exists (no .lw_coder/)."""
        # Setup: Create .weft/ directory (no .lw_coder/)
        new_dir = tmp_path / ".weft"
        new_dir.mkdir()
        (new_dir / "tasks").mkdir()
        (new_dir / "tasks" / "plan1.md").write_text("Existing content")

        # Action: Run migration
        result = migrate_repo_dir_if_needed(tmp_path)

        # Assert: No migration
        assert result is False
        assert new_dir.exists()
        assert (new_dir / "tasks" / "plan1.md").read_text() == "Existing content"

    def test_migrate_repo_dir_fresh_install(self, tmp_path: Path) -> None:
        """No migration for fresh install (no .lw_coder/, no .weft/)."""
        # Setup: Empty directory

        # Action: Run migration
        result = migrate_repo_dir_if_needed(tmp_path)

        # Assert: No migration, no directories created
        assert result is False
        assert not (tmp_path / ".lw_coder").exists()
        assert not (tmp_path / ".weft").exists()

    def test_migrate_repo_dir_both_exist_prefers_new(self, tmp_path: Path) -> None:
        """Prefers .weft/ when both .lw_coder/ and .weft/ exist."""
        # Setup: Create both directories with different content
        old_dir = tmp_path / ".lw_coder"
        old_dir.mkdir()
        (old_dir / "tasks").mkdir()
        (old_dir / "tasks" / "old.md").write_text("OLD content")

        new_dir = tmp_path / ".weft"
        new_dir.mkdir()
        (new_dir / "tasks").mkdir()
        (new_dir / "tasks" / "new.md").write_text("NEW content")

        # Action: Run migration
        result = migrate_repo_dir_if_needed(tmp_path)

        # Assert: No migration, .weft/ preserved, .lw_coder/ still exists
        assert result is False
        assert new_dir.exists()
        assert (new_dir / "tasks" / "new.md").read_text() == "NEW content"
        assert old_dir.exists()  # Left alone
        assert (old_dir / "tasks" / "old.md").read_text() == "OLD content"

    def test_migrate_repo_dir_preserves_content(self, tmp_path: Path) -> None:
        """Preserves all nested content during migration."""
        # Setup: Create .lw_coder/ with nested structure
        old_dir = tmp_path / ".lw_coder"
        (old_dir / "tasks").mkdir(parents=True)
        (old_dir / "tasks" / "plan1.md").write_text("Plan 1")
        (old_dir / "prompts" / "active").mkdir(parents=True)
        (old_dir / "prompts" / "active" / "main.md").write_text("Main prompt")
        (old_dir / "training_data" / "session1").mkdir(parents=True)
        (old_dir / "training_data" / "session1" / "trace.md").write_text("Trace")

        # Action: Run migration
        result = migrate_repo_dir_if_needed(tmp_path)

        # Assert: All content preserved in new location
        assert result is True
        new_dir = tmp_path / ".weft"
        assert (new_dir / "tasks" / "plan1.md").read_text() == "Plan 1"
        assert (new_dir / "prompts" / "active" / "main.md").read_text() == "Main prompt"
        assert (new_dir / "training_data" / "session1" / "trace.md").read_text() == "Trace"

    def test_migrate_repo_dir_logs_migration(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Logs migration action at INFO level."""
        caplog.set_level(logging.INFO)

        # Setup: Create .lw_coder/ directory
        old_dir = tmp_path / ".lw_coder"
        old_dir.mkdir()

        # Action: Run migration with log capture
        migrate_repo_dir_if_needed(tmp_path)

        # Assert: Log messages present
        assert "Migrating .lw_coder/ to .weft/" in caplog.text
        assert "Migration complete" in caplog.text
