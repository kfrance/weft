"""Tests for plan command functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.plan_command import (
    PlanCommandError,
    _copy_droids_for_plan,
    _ensure_placeholder_git_sha,
    _extract_idea_text,
    _write_maintainability_agent,
)
from lw_coder.plan_file_copier import (
    PlanFileCopyError,
    copy_plan_files,
    find_new_files,
    generate_unique_filename,
    get_existing_files,
)
from lw_coder.plan_validator import PLACEHOLDER_SHA, extract_front_matter
from tests.conftest import write_plan
import lw_coder.plan_command


def test_extract_idea_text_from_text_input() -> None:
    """Test extracting idea text from direct text input."""
    text = "This is my plan idea"
    result = _extract_idea_text(None, text)
    assert result == text


def test_extract_idea_text_from_file(tmp_path: Path) -> None:
    """Test extracting idea text from a file."""
    plan_file = tmp_path / "idea.md"
    content = "# My Plan\n\nThis is the plan content."
    plan_file.write_text(content)

    result = _extract_idea_text(plan_file, None)
    assert result == content.strip()


def test_extract_idea_text_from_file_with_frontmatter(tmp_path: Path) -> None:
    """Test extracting idea text from a file with YAML frontmatter (should be ignored)."""
    plan_file = tmp_path / "idea.md"
    content = """---
plan_id: test-plan
git_sha: 1234567890abcdef1234567890abcdef12345678
status: draft
evaluation_notes:
  - Test note
---

# My Plan

This is the plan content without frontmatter."""
    plan_file.write_text(content)

    result = _extract_idea_text(plan_file, None)
    # Should extract only the body, ignoring frontmatter
    assert "# My Plan" in result
    assert "This is the plan content without frontmatter." in result
    assert "plan_id" not in result


def test_extract_idea_text_missing_file(tmp_path: Path) -> None:
    """Test extracting idea text from nonexistent file."""
    nonexistent = tmp_path / "nonexistent.md"
    with pytest.raises(PlanCommandError, match="Plan file not found"):
        _extract_idea_text(nonexistent, None)


def test_extract_idea_text_both_inputs() -> None:
    """Test that providing both file and text raises error."""
    with pytest.raises(PlanCommandError, match="Cannot specify both"):
        _extract_idea_text(Path("file.md"), "text input")


def test_extract_idea_text_no_inputs() -> None:
    """Test that providing neither file nor text raises error."""
    with pytest.raises(PlanCommandError, match="Must specify either"):
        _extract_idea_text(None, None)


def test_ensure_placeholder_git_sha(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    plan_path = tasks_dir / "plan.md"
    write_plan(
        plan_path,
        {
            "plan_id": "plan-placeholder",
            "git_sha": "abcdef" * 6 + "ab",
            "status": "draft",
            "evaluation_notes": [],
        },
    )

    _ensure_placeholder_git_sha(tasks_dir)

    front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == PLACEHOLDER_SHA
    assert front_matter["status"] == "draft"


def test_run_plan_command_with_droid_executor() -> None:
    """Test that run_plan_command can use droid executor."""
    from lw_coder.plan_command import run_plan_command
    from lw_coder.executors import ExecutorRegistry

    # Verify droid executor is registered
    executor = ExecutorRegistry.get_executor("droid")
    assert executor is not None


def test_run_plan_command_with_claude_code_executor() -> None:
    """Test that run_plan_command can use claude-code executor."""
    from lw_coder.plan_command import run_plan_command
    from lw_coder.executors import ExecutorRegistry

    # Verify claude-code executor is registered
    executor = ExecutorRegistry.get_executor("claude-code")
    assert executor is not None


def test_run_plan_command_with_unknown_executor() -> None:
    """Test that run_plan_command fails with unknown executor."""
    from lw_coder.plan_command import run_plan_command
    from unittest.mock import patch

    with patch("lw_coder.plan_command.find_repo_root"):
        with patch("lw_coder.plan_command._extract_idea_text", return_value="test"):
            result = run_plan_command(None, "test idea", "unknown-executor")
            # Should fail due to unknown executor
            assert result != 0


# Tests for plan_file_copier module


def test_get_existing_files_empty_directory(tmp_path: Path) -> None:
    """Test get_existing_files returns empty set for empty directory."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    existing = get_existing_files(tasks_dir)
    assert existing == set()


def test_get_existing_files_with_files(tmp_path: Path) -> None:
    """Test get_existing_files returns correct filenames."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    # Create some files
    (tasks_dir / "plan-a.md").write_text("content")
    (tasks_dir / "plan-b.md").write_text("content")
    (tasks_dir / "README.txt").write_text("content")

    existing = get_existing_files(tasks_dir)
    assert existing == {"plan-a.md", "plan-b.md", "README.txt"}


def test_get_existing_files_nonexistent_directory(tmp_path: Path) -> None:
    """Test get_existing_files returns empty set for nonexistent directory."""
    tasks_dir = tmp_path / "nonexistent"

    existing = get_existing_files(tasks_dir)
    assert existing == set()


def test_find_new_files_identifies_new_files(tmp_path: Path) -> None:
    """Test find_new_files correctly identifies only new files."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    # Create initial files
    (tasks_dir / "old-plan.md").write_text("old")
    existing_files = get_existing_files(tasks_dir)

    # Create new files
    (tasks_dir / "new-plan-1.md").write_text("new 1")
    (tasks_dir / "new-plan-2.md").write_text("new 2")

    new_files = find_new_files(tasks_dir, existing_files)
    new_file_names = {f.name for f in new_files}

    assert new_file_names == {"new-plan-1.md", "new-plan-2.md"}
    assert "old-plan.md" not in new_file_names


def test_find_new_files_empty_directory(tmp_path: Path) -> None:
    """Test find_new_files returns empty list for empty directory."""
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    existing = get_existing_files(tasks_dir)
    new_files = find_new_files(tasks_dir, existing)

    assert new_files == []


def test_generate_unique_filename_no_conflict(tmp_path: Path) -> None:
    """Test generate_unique_filename returns original name when no conflict."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    filename = generate_unique_filename(target_dir, "my-plan.md")
    assert filename == "my-plan.md"


def test_generate_unique_filename_single_conflict(tmp_path: Path) -> None:
    """Test generate_unique_filename with one existing file."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Create existing file
    (target_dir / "my-plan.md").write_text("existing")

    filename = generate_unique_filename(target_dir, "my-plan.md")
    assert filename == "my-plan (1).md"


def test_generate_unique_filename_multiple_conflicts(tmp_path: Path) -> None:
    """Test generate_unique_filename with multiple conflicts."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Create existing files
    (target_dir / "my-plan.md").write_text("existing")
    (target_dir / "my-plan (1).md").write_text("existing")
    (target_dir / "my-plan (2).md").write_text("existing")

    filename = generate_unique_filename(target_dir, "my-plan.md")
    assert filename == "my-plan (3).md"


def test_generate_unique_filename_gaps_in_numbering(tmp_path: Path) -> None:
    """Test generate_unique_filename with gaps in numbering sequence."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Create files with gaps (1, 3, 5)
    (target_dir / "my-plan.md").write_text("existing")
    (target_dir / "my-plan (1).md").write_text("existing")
    (target_dir / "my-plan (3).md").write_text("existing")
    (target_dir / "my-plan (5).md").write_text("existing")

    # Should use next number after highest (6), not fill gaps
    filename = generate_unique_filename(target_dir, "my-plan.md")
    assert filename == "my-plan (6).md"


def test_generate_unique_filename_no_extension(tmp_path: Path) -> None:
    """Test generate_unique_filename works with files without extension."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    (target_dir / "README").write_text("existing")

    filename = generate_unique_filename(target_dir, "README")
    assert filename == "README (1)"


def test_copy_plan_files_single_file(tmp_path: Path) -> None:
    """Test copying a single new plan file."""
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "dest"
    source_dir.mkdir()
    dest_dir.mkdir()

    # Track existing files (none)
    existing_files = get_existing_files(source_dir)

    # Create new file
    (source_dir / "my-feature.md").write_text("# My Feature")

    # Copy files
    mapping = copy_plan_files(source_dir, dest_dir, existing_files)

    assert mapping == {"my-feature.md": "my-feature.md"}
    assert (dest_dir / "my-feature.md").exists()
    assert (dest_dir / "my-feature.md").read_text() == "# My Feature"


def test_copy_plan_files_with_conflict(tmp_path: Path) -> None:
    """Test copying with naming conflict."""
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "dest"
    source_dir.mkdir()
    dest_dir.mkdir()

    # Create existing file in destination
    (dest_dir / "my-feature.md").write_text("old content")

    # Track existing files (none in source)
    existing_files = get_existing_files(source_dir)

    # Create new file in source with conflicting name
    (source_dir / "my-feature.md").write_text("new content")

    # Copy files
    mapping = copy_plan_files(source_dir, dest_dir, existing_files)

    assert mapping == {"my-feature.md": "my-feature (1).md"}
    assert (dest_dir / "my-feature.md").read_text() == "old content"
    assert (dest_dir / "my-feature (1).md").read_text() == "new content"


def test_copy_plan_files_multiple_new_files(tmp_path: Path) -> None:
    """Test copying multiple new files."""
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "dest"
    source_dir.mkdir()
    dest_dir.mkdir()

    # Create one existing file in destination
    (dest_dir / "feature-a.md").write_text("existing")

    # Track existing files in source (none)
    existing_files = get_existing_files(source_dir)

    # Create new files in source
    (source_dir / "feature-a.md").write_text("new a")
    (source_dir / "feature-b.md").write_text("new b")

    # Copy files
    mapping = copy_plan_files(source_dir, dest_dir, existing_files)

    assert mapping == {
        "feature-a.md": "feature-a (1).md",
        "feature-b.md": "feature-b.md"
    }
    assert (dest_dir / "feature-a.md").read_text() == "existing"
    assert (dest_dir / "feature-a (1).md").read_text() == "new a"
    assert (dest_dir / "feature-b.md").read_text() == "new b"


def test_copy_plan_files_only_copies_new_files(tmp_path: Path) -> None:
    """Test that only newly created files are copied, not pre-existing ones."""
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "dest"
    source_dir.mkdir()
    dest_dir.mkdir()

    # Create existing file in source
    (source_dir / "old-plan.md").write_text("old")
    existing_files = get_existing_files(source_dir)

    # Modify existing file and create new file
    (source_dir / "old-plan.md").write_text("modified old")
    (source_dir / "new-plan.md").write_text("new")

    # Copy files
    mapping = copy_plan_files(source_dir, dest_dir, existing_files)

    # Only new-plan.md should be copied
    assert mapping == {"new-plan.md": "new-plan.md"}
    assert not (dest_dir / "old-plan.md").exists()
    assert (dest_dir / "new-plan.md").exists()


def test_copy_plan_files_nonexistent_destination(tmp_path: Path) -> None:
    """Test that copy_plan_files raises error if destination doesn't exist."""
    source_dir = tmp_path / "source"
    dest_dir = tmp_path / "nonexistent"
    source_dir.mkdir()

    existing_files = get_existing_files(source_dir)
    (source_dir / "plan.md").write_text("content")

    with pytest.raises(PlanFileCopyError, match="Destination directory does not exist"):
        copy_plan_files(source_dir, dest_dir, existing_files)


def test_copy_plan_files_destination_is_file(tmp_path: Path) -> None:
    """Test that copy_plan_files raises error if destination is a file."""
    source_dir = tmp_path / "source"
    dest_file = tmp_path / "dest_file"
    source_dir.mkdir()
    dest_file.write_text("not a directory")

    existing_files = get_existing_files(source_dir)
    (source_dir / "plan.md").write_text("content")

    with pytest.raises(PlanFileCopyError, match="not a directory"):
        copy_plan_files(source_dir, dest_file, existing_files)


# Tests for agent/droid setup functions


def test_copy_droids_for_plan_success(tmp_path: Path, monkeypatch) -> None:
    """Test _copy_droids_for_plan creates correct directory structure and copies file."""
    # Create a fake source droid file
    fake_src_dir = tmp_path / "fake_src"
    droids_dir = fake_src_dir / "droids"
    droids_dir.mkdir(parents=True)
    source_droid = droids_dir / "maintainability-reviewer.md"
    source_droid.write_text("---\nname: maintainability-reviewer\n---\nTest content")

    # Mock get_lw_coder_src_dir to return our fake directory
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", lambda: fake_src_dir
    )

    # Create worktree path
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Call the function
    _copy_droids_for_plan(worktree_path)

    # Verify directory structure was created
    dest_droids_dir = worktree_path / ".factory" / "droids"
    assert dest_droids_dir.exists()
    assert dest_droids_dir.is_dir()

    # Verify file was copied
    dest_droid = dest_droids_dir / "maintainability-reviewer.md"
    assert dest_droid.exists()
    assert dest_droid.read_text() == "---\nname: maintainability-reviewer\n---\nTest content"


def test_copy_droids_for_plan_missing_source(tmp_path: Path, monkeypatch) -> None:
    """Test _copy_droids_for_plan raises error when source droid doesn't exist."""
    # Create a fake source directory WITHOUT the droid file
    fake_src_dir = tmp_path / "fake_src"
    droids_dir = fake_src_dir / "droids"
    droids_dir.mkdir(parents=True)

    # Mock get_lw_coder_src_dir
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", lambda: fake_src_dir
    )

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Should raise error about missing source file
    with pytest.raises(PlanCommandError, match="Maintainability reviewer droid not found"):
        _copy_droids_for_plan(worktree_path)


def test_copy_droids_for_plan_permission_error(tmp_path: Path, monkeypatch) -> None:
    """Test _copy_droids_for_plan handles permission errors gracefully."""
    # Create a fake source droid file
    fake_src_dir = tmp_path / "fake_src"
    droids_dir = fake_src_dir / "droids"
    droids_dir.mkdir(parents=True)
    source_droid = droids_dir / "maintainability-reviewer.md"
    source_droid.write_text("Test content")

    # Mock get_lw_coder_src_dir
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", lambda: fake_src_dir
    )

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Mock shutil.copy2 to raise permission error
    import shutil
    original_copy2 = shutil.copy2

    def mock_copy2(src, dst):
        raise OSError("Permission denied")

    monkeypatch.setattr("shutil.copy2", mock_copy2)

    # Should raise error about failed copy
    with pytest.raises(PlanCommandError, match="Failed to copy droid"):
        _copy_droids_for_plan(worktree_path)


def test_write_maintainability_agent_success(tmp_path: Path, monkeypatch) -> None:
    """Test _write_maintainability_agent creates correct directory structure and writes file."""
    # Create a fake source agent file
    fake_src_dir = tmp_path / "fake_src"
    droids_dir = fake_src_dir / "droids"
    droids_dir.mkdir(parents=True)
    source_agent = droids_dir / "maintainability-reviewer.md"
    source_agent.write_text("---\nname: maintainability-reviewer\n---\nAgent content")

    # Mock get_lw_coder_src_dir
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", lambda: fake_src_dir
    )

    # Create worktree path
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Call the function
    _write_maintainability_agent(worktree_path)

    # Verify directory structure was created
    dest_agents_dir = worktree_path / ".claude" / "agents"
    assert dest_agents_dir.exists()
    assert dest_agents_dir.is_dir()

    # Verify file was written
    dest_agent = dest_agents_dir / "maintainability-reviewer.md"
    assert dest_agent.exists()
    assert dest_agent.read_text() == "---\nname: maintainability-reviewer\n---\nAgent content"


def test_write_maintainability_agent_missing_source(tmp_path: Path, monkeypatch) -> None:
    """Test _write_maintainability_agent raises error when source agent doesn't exist."""
    # Create a fake source directory WITHOUT the agent file
    fake_src_dir = tmp_path / "fake_src"
    droids_dir = fake_src_dir / "droids"
    droids_dir.mkdir(parents=True)

    # Mock get_lw_coder_src_dir
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", lambda: fake_src_dir
    )

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Should raise error about missing source file
    with pytest.raises(PlanCommandError, match="Maintainability reviewer agent not found"):
        _write_maintainability_agent(worktree_path)


def test_write_maintainability_agent_permission_error(tmp_path: Path, monkeypatch) -> None:
    """Test _write_maintainability_agent handles permission errors gracefully."""
    # Create a fake source agent file
    fake_src_dir = tmp_path / "fake_src"
    droids_dir = fake_src_dir / "droids"
    droids_dir.mkdir(parents=True)
    source_agent = droids_dir / "maintainability-reviewer.md"
    source_agent.write_text("Agent content")

    # Mock get_lw_coder_src_dir
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", lambda: fake_src_dir
    )

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Mock shutil.copy2 to raise permission error
    import shutil

    def mock_copy2(src, dst):
        raise OSError("Permission denied")

    monkeypatch.setattr("shutil.copy2", mock_copy2)

    # Should raise error about failed write
    with pytest.raises(PlanCommandError, match="Failed to write agent"):
        _write_maintainability_agent(worktree_path)
