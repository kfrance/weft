"""Tests for prompt_loader migration functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from weft.prompt_loader import (
    PromptLoadingError,
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
    prompts_dir = base_dir / ".weft" / location / "claude-code-cli" / "sonnet"
    prompts_dir.mkdir(parents=True)

    (prompts_dir / "main.md").write_text("Main prompt content")
    (prompts_dir / "code-review-auditor.md").write_text("Code review prompt")
    (prompts_dir / "plan-alignment-checker.md").write_text("Plan alignment prompt")


class TestPromptMigration:
    """Tests for prompt directory migration."""

    def test_load_prompts_from_new_location(self, tmp_path: Path) -> None:
        """Loads from prompts/active/ when available."""
        create_prompts_at_location(tmp_path, "prompts/active")

        result = load_prompts(tmp_path, tool="claude-code-cli", model="sonnet")

        assert result["main_prompt"] == "Main prompt content"
        assert result["code_review_auditor"] == "Code review prompt"
        assert result["plan_alignment_checker"] == "Plan alignment prompt"

    def test_load_prompts_migrates_old_location(self, tmp_path: Path) -> None:
        """Migrates optimized_prompts/ to prompts/active/."""
        create_prompts_at_location(tmp_path, "optimized_prompts")

        result = load_prompts(tmp_path, tool="claude-code-cli", model="sonnet")

        # Should still work
        assert result["main_prompt"] == "Main prompt content"

        # New location should now exist
        new_location = tmp_path / ".weft" / "prompts" / "active"
        assert new_location.exists()

    def test_load_prompts_deletes_old_after_migration(self, tmp_path: Path) -> None:
        """Old directory removed after migration."""
        create_prompts_at_location(tmp_path, "optimized_prompts")

        load_prompts(tmp_path, tool="claude-code-cli", model="sonnet")

        old_location = tmp_path / ".weft" / "optimized_prompts"
        assert not old_location.exists()

    def test_load_prompts_no_double_migration(self, tmp_path: Path) -> None:
        """Doesn't migrate if already migrated."""
        # Create prompts at new location
        create_prompts_at_location(tmp_path, "prompts/active")

        # Also create at old location (shouldn't be touched)
        old_dir = tmp_path / ".weft" / "optimized_prompts" / "claude-code-cli" / "sonnet"
        old_dir.mkdir(parents=True)
        (old_dir / "main.md").write_text("OLD content")
        (old_dir / "code-review-auditor.md").write_text("OLD content")
        (old_dir / "plan-alignment-checker.md").write_text("OLD content")

        result = load_prompts(tmp_path, tool="claude-code-cli", model="sonnet")

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

        result = load_current_prompts_for_training(tmp_path, tool="claude-code-cli", model="sonnet")

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
        prompts_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli" / "sonnet"
        prompts_dir.mkdir(parents=True)
        # Create subagent but not main.md
        (prompts_dir / "code-review-auditor.md").write_text("Review prompt")

        with pytest.raises(PromptLoadingError) as exc_info:
            load_current_prompts_for_training(tmp_path)

        assert "Main prompt not found" in str(exc_info.value)

    def test_load_current_prompts_for_training_no_subagents(self, tmp_path: Path) -> None:
        """Returns empty subagents when only main.md exists."""
        prompts_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli" / "sonnet"
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
