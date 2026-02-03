"""Tests for prompt_loader migration functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from weft.prompt_loader import (
    PromptLoadingError,
    _migrate_legacy_tool_directory,
    _migrate_prompts_if_needed,
    load_current_prompts_for_training,
    load_prompts,
)


def create_prompts_at_location(base_dir: Path, location: str) -> None:
    """Create prompt files at the specified location.

    Args:
        base_dir: Repository root
        location: Either "optimized_prompts" (old) or "prompts/active" (new)
    """
    prompts_dir = base_dir / ".weft" / location / "claude-code" / "sonnet"
    prompts_dir.mkdir(parents=True)

    (prompts_dir / "main.md").write_text("Main prompt content")
    (prompts_dir / "code-review-auditor.md").write_text("Code review prompt")
    (prompts_dir / "plan-alignment-checker.md").write_text("Plan alignment prompt")


class TestPromptMigration:
    """Tests for prompt directory migration."""

    def test_load_prompts_from_new_location(self, tmp_path: Path) -> None:
        """Loads from prompts/active/ when available."""
        create_prompts_at_location(tmp_path, "prompts/active")

        result = load_prompts(tmp_path, tool="claude-code", model="sonnet")

        assert result["main_prompt"] == "Main prompt content"
        assert result["code_review_auditor"] == "Code review prompt"
        assert result["plan_alignment_checker"] == "Plan alignment prompt"

    def test_load_prompts_migrates_old_location(self, tmp_path: Path) -> None:
        """Migrates optimized_prompts/ to prompts/active/."""
        create_prompts_at_location(tmp_path, "optimized_prompts")

        result = load_prompts(tmp_path, tool="claude-code", model="sonnet")

        # Should still work
        assert result["main_prompt"] == "Main prompt content"

        # New location should now exist
        new_location = tmp_path / ".weft" / "prompts" / "active"
        assert new_location.exists()

    def test_load_prompts_deletes_old_after_migration(self, tmp_path: Path) -> None:
        """Old directory removed after migration."""
        create_prompts_at_location(tmp_path, "optimized_prompts")

        load_prompts(tmp_path, tool="claude-code", model="sonnet")

        old_location = tmp_path / ".weft" / "optimized_prompts"
        assert not old_location.exists()

    def test_load_prompts_no_double_migration(self, tmp_path: Path) -> None:
        """Doesn't migrate if already migrated."""
        # Create prompts at new location
        create_prompts_at_location(tmp_path, "prompts/active")

        # Also create at old location (shouldn't be touched)
        old_dir = tmp_path / ".weft" / "optimized_prompts" / "claude-code" / "sonnet"
        old_dir.mkdir(parents=True)
        (old_dir / "main.md").write_text("OLD content")
        (old_dir / "code-review-auditor.md").write_text("OLD content")
        (old_dir / "plan-alignment-checker.md").write_text("OLD content")

        result = load_prompts(tmp_path, tool="claude-code", model="sonnet")

        # Should load from new location, not old
        assert result["main_prompt"] == "Main prompt content"

        # Old location should still exist (wasn't migrated)
        old_location = tmp_path / ".weft" / "optimized_prompts"
        assert old_location.exists()

    def test_migrate_prompts_if_needed_no_old_location(self, tmp_path: Path) -> None:
        """Returns False when old location doesn't exist."""
        result = _migrate_prompts_if_needed(tmp_path)
        assert result is False

    def test_migrate_prompts_if_needed_new_exists(self, tmp_path: Path) -> None:
        """Returns False when new location already exists."""
        create_prompts_at_location(tmp_path, "prompts/active")
        create_prompts_at_location(tmp_path, "optimized_prompts")

        result = _migrate_prompts_if_needed(tmp_path)
        assert result is False


class TestLoadCurrentPromptsForTraining:
    """Tests for load_current_prompts_for_training function."""

    def test_load_current_prompts_for_training(self, tmp_path: Path) -> None:
        """Returns CurrentPrompts object with subagents."""
        create_prompts_at_location(tmp_path, "prompts/active")

        result = load_current_prompts_for_training(tmp_path, tool="claude-code", model="sonnet")

        assert result.main_prompt == "Main prompt content"
        assert len(result.subagents) == 2

        # Check subagent names
        subagent_names = [s.name for s in result.subagents]
        assert "code-review-auditor" in subagent_names
        assert "plan-alignment-checker" in subagent_names

    def test_load_current_prompts_for_training_missing_dir(self, tmp_path: Path) -> None:
        """Raises error when prompts directory not found."""
        with pytest.raises(PromptLoadingError) as exc_info:
            load_current_prompts_for_training(tmp_path)

        assert "Prompts directory not found" in str(exc_info.value)

    def test_load_current_prompts_for_training_missing_main(self, tmp_path: Path) -> None:
        """Raises error when main.md not found."""
        prompts_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code" / "sonnet"
        prompts_dir.mkdir(parents=True)
        # Create subagent but not main.md
        (prompts_dir / "code-review-auditor.md").write_text("Review prompt")

        with pytest.raises(PromptLoadingError) as exc_info:
            load_current_prompts_for_training(tmp_path)

        assert "Main prompt not found" in str(exc_info.value)

    def test_load_current_prompts_for_training_no_subagents(self, tmp_path: Path) -> None:
        """Returns empty subagents when only main.md exists."""
        prompts_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code" / "sonnet"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "main.md").write_text("Main prompt only")

        result = load_current_prompts_for_training(tmp_path)

        assert result.main_prompt == "Main prompt only"
        assert result.subagents == []

    def test_load_current_prompts_for_training_with_migration(self, tmp_path: Path) -> None:
        """Handles migration from old location."""
        create_prompts_at_location(tmp_path, "optimized_prompts")

        result = load_current_prompts_for_training(tmp_path)

        assert result.main_prompt == "Main prompt content"
        assert len(result.subagents) == 2


class TestLegacyToolDirectoryMigration:
    """Tests for _migrate_legacy_tool_directory function."""

    def _create_legacy_prompts(self, tmp_path: Path) -> None:
        """Create prompts at legacy claude-code-cli location."""
        legacy_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli" / "sonnet"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "main.md").write_text("Legacy main prompt")
        (legacy_dir / "code-review-auditor.md").write_text("Legacy code review")
        (legacy_dir / "plan-alignment-checker.md").write_text("Legacy plan alignment")

    def test_migrate_legacy_tool_directory_renames_dir(self, tmp_path: Path) -> None:
        """Legacy claude-code-cli directory is renamed to claude-code."""
        self._create_legacy_prompts(tmp_path)

        result = _migrate_legacy_tool_directory(tmp_path)

        assert result is True
        # Legacy directory should no longer exist
        legacy_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli"
        assert not legacy_dir.exists()
        # New directory should exist with contents
        new_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code" / "sonnet"
        assert new_dir.exists()
        assert (new_dir / "main.md").read_text() == "Legacy main prompt"

    def test_migrate_legacy_tool_directory_no_legacy(self, tmp_path: Path) -> None:
        """Returns False when legacy directory doesn't exist."""
        result = _migrate_legacy_tool_directory(tmp_path)
        assert result is False

    def test_migrate_legacy_tool_directory_both_exist_no_overwrite(self, tmp_path: Path) -> None:
        """Doesn't overwrite when both directories exist."""
        # Create legacy prompts
        self._create_legacy_prompts(tmp_path)

        # Also create new location with different content
        new_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code" / "sonnet"
        new_dir.mkdir(parents=True)
        (new_dir / "main.md").write_text("New main prompt")

        result = _migrate_legacy_tool_directory(tmp_path)

        assert result is False
        # Legacy should still exist (not deleted)
        legacy_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli"
        assert legacy_dir.exists()
        # New content should be unchanged
        assert (new_dir / "main.md").read_text() == "New main prompt"

    def test_load_prompts_migrates_legacy_tool_dir(self, tmp_path: Path) -> None:
        """load_prompts automatically migrates legacy tool directory."""
        self._create_legacy_prompts(tmp_path)

        result = load_prompts(tmp_path, tool="claude-code", model="sonnet")

        assert result["main_prompt"] == "Legacy main prompt"
        # Legacy directory should be migrated
        legacy_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli"
        assert not legacy_dir.exists()
        new_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code"
        assert new_dir.exists()

    def test_load_finalize_prompt_migrates_legacy_tool_dir(self, tmp_path: Path) -> None:
        """load_finalize_prompt automatically migrates legacy tool directory."""
        from weft.prompt_loader import load_finalize_prompt

        # Create legacy finalize prompt at claude-code-cli location
        legacy_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "finalize.md").write_text("Legacy finalize prompt for {PLAN_ID}")

        result = load_finalize_prompt(tmp_path, "claude-code")

        assert result == "Legacy finalize prompt for {PLAN_ID}"
        # Legacy directory should be migrated
        assert not legacy_dir.exists()
        new_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code"
        assert new_dir.exists()
        assert (new_dir / "finalize.md").read_text() == "Legacy finalize prompt for {PLAN_ID}"
