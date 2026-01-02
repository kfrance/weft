"""Tests for plan command functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weft.plan_command import (
    PLAN_SUBAGENT_CONFIGS,
    PlanCommandError,
    _ensure_placeholder_git_sha,
    _extract_idea_text,
    _write_plan_subagents,
)
from weft.plan_file_copier import (
    PlanFileCopyError,
    copy_plan_files,
    find_new_files,
    generate_unique_filename,
    get_existing_files,
)
from weft.plan_validator import PLACEHOLDER_SHA, extract_front_matter
from tests.helpers import write_plan
import weft.plan_command


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


def test_run_plan_command_with_unknown_executor() -> None:
    """Test that run_plan_command fails with unknown executor."""
    from weft.plan_command import run_plan_command
    from unittest.mock import patch

    with patch("weft.plan_command.find_repo_root"):
        with patch("weft.plan_command._extract_idea_text", return_value="test"):
            result = run_plan_command(None, "test idea", "unknown-executor")
            # Should fail due to unknown executor
            assert result != 0


# Tests for plan_file_copier module


@pytest.mark.parametrize(
    "directory_exists,expected_result",
    [
        (True, set()),  # Empty directory
        (False, set()),  # Nonexistent directory
    ],
    ids=["empty_directory", "nonexistent_directory"]
)
def test_get_existing_files_edge_cases(tmp_path: Path, directory_exists: bool, expected_result: set) -> None:
    """Test get_existing_files with empty or nonexistent directory."""
    tasks_dir = tmp_path / "tasks"

    if directory_exists:
        tasks_dir.mkdir()

    existing = get_existing_files(tasks_dir)
    assert existing == expected_result


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


# Tests for plan subagent setup functions


def test_write_plan_subagents_droid(tmp_path: Path, monkeypatch) -> None:
    """Test _write_plan_subagents for Droid creates correct directory structure and files."""
    # Create fake source directory with prompt files
    fake_src_dir = tmp_path / "fake_src"
    prompts_dir = fake_src_dir / "prompts" / "plan-subagents"
    prompts_dir.mkdir(parents=True)

    # Create prompt files (plain markdown, no YAML)
    maintainability_prompt = prompts_dir / "maintainability-reviewer.md"
    maintainability_prompt.write_text("Maintainability review guidance")

    test_reviewer_prompt = prompts_dir / "test-reviewer.md"
    test_reviewer_prompt.write_text("Test review guidance")

    test_discovery_prompt = prompts_dir / "test-discovery.md"
    test_discovery_prompt.write_text("Test discovery guidance")

    # Mock get_weft_src_dir
    monkeypatch.setattr(
        weft.plan_command, "get_weft_src_dir", lambda: fake_src_dir
    )

    # Create worktree path
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Call the function for Droid
    _write_plan_subagents(worktree_path, "droid", "sonnet")

    # Verify directory structure was created
    dest_droids_dir = worktree_path / ".factory" / "droids"
    assert dest_droids_dir.exists()
    assert dest_droids_dir.is_dir()

    # Verify maintainability-reviewer file
    dest_maintainability = dest_droids_dir / "maintainability-reviewer.md"
    assert dest_maintainability.exists()
    content = dest_maintainability.read_text()
    assert "model: gpt-5-codex" in content
    assert "tools: read-only" in content
    assert "Maintainability review guidance" in content

    # Verify test-reviewer file
    dest_test_reviewer = dest_droids_dir / "test-reviewer.md"
    assert dest_test_reviewer.exists()
    content = dest_test_reviewer.read_text()
    assert "model: gpt-5-codex" in content
    assert "tools: read-only" in content
    assert "Test review guidance" in content

    # Verify test-discovery file
    dest_test_discovery = dest_droids_dir / "test-discovery.md"
    assert dest_test_discovery.exists()
    content = dest_test_discovery.read_text()
    assert "model: gpt-5-codex" in content
    assert "tools: read-only" in content
    assert "Test discovery guidance" in content


def test_write_plan_subagents_claude_code(tmp_path: Path, monkeypatch) -> None:
    """Test _write_plan_subagents for Claude Code creates correct directory structure and files."""
    # Create fake source directory with prompt files
    fake_src_dir = tmp_path / "fake_src"
    prompts_dir = fake_src_dir / "prompts" / "plan-subagents"
    prompts_dir.mkdir(parents=True)

    # Create prompt files (plain markdown, no YAML)
    maintainability_prompt = prompts_dir / "maintainability-reviewer.md"
    maintainability_prompt.write_text("Maintainability review guidance")

    test_reviewer_prompt = prompts_dir / "test-reviewer.md"
    test_reviewer_prompt.write_text("Test review guidance")

    test_discovery_prompt = prompts_dir / "test-discovery.md"
    test_discovery_prompt.write_text("Test discovery guidance")

    # Mock get_weft_src_dir
    monkeypatch.setattr(
        weft.plan_command, "get_weft_src_dir", lambda: fake_src_dir
    )

    # Create worktree path
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Call the function for Claude Code
    _write_plan_subagents(worktree_path, "claude-code", "sonnet")

    # Verify directory structure was created
    dest_agents_dir = worktree_path / ".claude" / "agents"
    assert dest_agents_dir.exists()
    assert dest_agents_dir.is_dir()

    # Verify maintainability-reviewer file
    dest_maintainability = dest_agents_dir / "maintainability-reviewer.md"
    assert dest_maintainability.exists()
    content = dest_maintainability.read_text()
    assert "model: sonnet" in content
    assert "tools:" not in content  # Should omit tools field for Claude Code
    assert "Maintainability review guidance" in content

    # Verify test-reviewer file
    dest_test_reviewer = dest_agents_dir / "test-reviewer.md"
    assert dest_test_reviewer.exists()
    content = dest_test_reviewer.read_text()
    assert "model: sonnet" in content
    assert "tools:" not in content  # Should omit tools field for Claude Code
    assert "Test review guidance" in content

    # Verify test-discovery file
    dest_test_discovery = dest_agents_dir / "test-discovery.md"
    assert dest_test_discovery.exists()
    content = dest_test_discovery.read_text()
    assert "model: sonnet" in content
    assert "tools:" not in content  # Should omit tools field for Claude Code
    assert "Test discovery guidance" in content


@pytest.mark.parametrize(
    "model",
    ["sonnet", "opus", "haiku"],
    ids=["sonnet", "opus", "haiku"]
)
def test_write_plan_subagents_different_models(tmp_path: Path, monkeypatch, model: str) -> None:
    """Test _write_plan_subagents with different models for Claude Code."""
    # Create fake source directory with prompt files
    fake_src_dir = tmp_path / "fake_src"
    prompts_dir = fake_src_dir / "prompts" / "plan-subagents"
    prompts_dir.mkdir(parents=True)

    maintainability_prompt = prompts_dir / "maintainability-reviewer.md"
    maintainability_prompt.write_text("Test content")

    test_reviewer_prompt = prompts_dir / "test-reviewer.md"
    test_reviewer_prompt.write_text("Test content")

    test_discovery_prompt = prompts_dir / "test-discovery.md"
    test_discovery_prompt.write_text("Test content")

    # Mock get_weft_src_dir
    monkeypatch.setattr(
        weft.plan_command, "get_weft_src_dir", lambda: fake_src_dir
    )

    # Create worktree path
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Call the function for Claude Code with specified model
    _write_plan_subagents(worktree_path, "claude-code", model)

    # Verify model is correctly set in all files
    dest_agents_dir = worktree_path / ".claude" / "agents"

    maintainability_content = (dest_agents_dir / "maintainability-reviewer.md").read_text()
    assert f"model: {model}" in maintainability_content

    test_reviewer_content = (dest_agents_dir / "test-reviewer.md").read_text()
    assert f"model: {model}" in test_reviewer_content

    test_discovery_content = (dest_agents_dir / "test-discovery.md").read_text()
    assert f"model: {model}" in test_discovery_content

    # Verify Droid always uses gpt-5-codex regardless of model parameter
    worktree_path_droid = tmp_path / "worktree_droid"
    worktree_path_droid.mkdir()

    _write_plan_subagents(worktree_path_droid, "droid", model)

    dest_droids_dir = worktree_path_droid / ".factory" / "droids"
    maintainability_content = (dest_droids_dir / "maintainability-reviewer.md").read_text()
    assert "model: gpt-5-codex" in maintainability_content

    test_reviewer_content = (dest_droids_dir / "test-reviewer.md").read_text()
    assert "model: gpt-5-codex" in test_reviewer_content

    test_discovery_content = (dest_droids_dir / "test-discovery.md").read_text()
    assert "model: gpt-5-codex" in test_discovery_content


def test_write_plan_subagents_unknown_tool(tmp_path: Path, monkeypatch) -> None:
    """Test _write_plan_subagents raises error for unknown tool."""
    fake_src_dir = tmp_path / "fake_src"
    fake_src_dir.mkdir()
    monkeypatch.setattr(
        weft.plan_command, "get_weft_src_dir", lambda: fake_src_dir
    )

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    with pytest.raises(PlanCommandError, match="Unknown tool"):
        _write_plan_subagents(worktree_path, "invalid-tool", "sonnet")


@pytest.mark.parametrize(
    "error_type,expected_match",
    [
        ("missing_source", "Subagent prompt not found"),
        ("permission_error", "Failed to write subagent"),
        ("read_error", "Failed to read subagent prompt"),
    ],
    ids=["missing_source", "permission_error", "read_error"]
)
def test_write_plan_subagents_errors(tmp_path: Path, monkeypatch, error_type: str, expected_match: str) -> None:
    """Test _write_plan_subagents error handling for missing source, permission, and read errors."""
    # Create fake source directory
    fake_src_dir = tmp_path / "fake_src"
    prompts_dir = fake_src_dir / "prompts" / "plan-subagents"
    prompts_dir.mkdir(parents=True)

    if error_type == "permission_error":
        # Create source files for permission error test
        maintainability_prompt = prompts_dir / "maintainability-reviewer.md"
        maintainability_prompt.write_text("Test content")

        test_reviewer_prompt = prompts_dir / "test-reviewer.md"
        test_reviewer_prompt.write_text("Test content")

        test_discovery_prompt = prompts_dir / "test-discovery.md"
        test_discovery_prompt.write_text("Test content")

        # Mock Path.write_text to raise permission error
        from pathlib import Path as PathLib
        original_write_text = PathLib.write_text

        def mock_write_text(self, *args, **kwargs):
            # Only raise error for destination files, not source setup
            if ".claude" in str(self) or ".factory" in str(self):
                raise OSError("Permission denied")
            return original_write_text(self, *args, **kwargs)

        monkeypatch.setattr(PathLib, "write_text", mock_write_text)

    elif error_type == "read_error":
        # Create source files for read error test
        maintainability_prompt = prompts_dir / "maintainability-reviewer.md"
        maintainability_prompt.write_text("Test content")

        test_reviewer_prompt = prompts_dir / "test-reviewer.md"
        test_reviewer_prompt.write_text("Test content")

        test_discovery_prompt = prompts_dir / "test-discovery.md"
        test_discovery_prompt.write_text("Test content")

        # Mock Path.read_text to raise read error
        from pathlib import Path as PathLib
        original_read_text = PathLib.read_text

        def mock_read_text(self, *args, **kwargs):
            # Only raise error for prompt files
            if "plan-subagents" in str(self):
                raise OSError("Permission denied reading file")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(PathLib, "read_text", mock_read_text)

    # Mock get_weft_src_dir
    monkeypatch.setattr(
        weft.plan_command, "get_weft_src_dir", lambda: fake_src_dir
    )

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Should raise appropriate error
    with pytest.raises(PlanCommandError, match=expected_match):
        _write_plan_subagents(worktree_path, "claude-code", "sonnet")

# Integration tests for backup functionality


def test_backup_created_after_plan_file_copied(tmp_path: Path, monkeypatch) -> None:
    """Test that create_backup is called after plan files are copied."""
    from unittest.mock import Mock, MagicMock
    from weft.plan_command import run_plan_command

    # Track calls to create_backup
    mock_create_backup = Mock()
    monkeypatch.setattr("weft.plan_command.create_backup", mock_create_backup)

    # Mock all external dependencies
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    tasks_dir = repo_root / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    monkeypatch.setattr("weft.plan_command.find_repo_root", Mock(return_value=repo_root))

    # Mock temp worktree
    temp_worktree = tmp_path / "worktree"
    temp_worktree.mkdir()
    worktree_tasks_dir = temp_worktree / ".weft" / "tasks"
    worktree_tasks_dir.mkdir(parents=True)

    # Create a plan file in worktree
    (worktree_tasks_dir / "test-plan.md").write_text("---\nplan_id: test-plan\nstatus: draft\n---\n# Test")

    monkeypatch.setattr("weft.plan_command.create_temp_worktree", Mock(return_value=temp_worktree))
    monkeypatch.setattr("weft.plan_command.remove_temp_worktree", Mock())
    monkeypatch.setattr("weft.plan_command.get_weft_src_dir", Mock(return_value=tmp_path / "src"))

    # Mock subagent setup
    monkeypatch.setattr("weft.plan_command._write_plan_subagents", Mock())

    # Mock trace capture functions (now using session_manager)
    monkeypatch.setattr("weft.plan_command.prune_old_sessions", Mock())
    monkeypatch.setattr("weft.plan_command.create_session_directory", Mock(return_value=tmp_path / "traces"))
    monkeypatch.setattr("weft.plan_command.capture_session_trace", Mock(return_value=None))

    # Mock copy_plan_files to return a file mapping indicating a plan was copied
    def mock_copy_plan_files(source_dir, dest_dir, existing_files):
        # Simulate copying a plan file
        plan_file = dest_dir / "test-plan.md"
        plan_file.write_text("---\nplan_id: test-plan\nstatus: draft\n---\n# Test")
        return {"test-plan.md": "test-plan.md"}

    monkeypatch.setattr("weft.plan_command.copy_plan_files", mock_copy_plan_files)

    # Mock executor
    mock_executor = MagicMock()
    mock_executor.check_auth = Mock()
    mock_executor.build_command = Mock(return_value="echo test")
    mock_executor.get_env_vars = Mock(return_value={})
    from weft.executors import ExecutorRegistry
    monkeypatch.setattr(ExecutorRegistry, "get_executor", Mock(return_value=mock_executor))

    # Mock host runner
    monkeypatch.setattr("weft.plan_command.host_runner_config", Mock(return_value={}))
    monkeypatch.setattr("weft.plan_command.build_host_command", Mock(return_value=(["echo"], {})))
    monkeypatch.setattr("weft.plan_command.load_prompt_template", Mock(return_value="test template"))

    # Mock subprocess to succeed
    mock_result = MagicMock(returncode=0)
    monkeypatch.setattr("weft.plan_command.subprocess.run", Mock(return_value=mock_result))

    # Run the command
    exit_code = run_plan_command(plan_path=None, text_input="test idea", tool="claude-code")

    # Verify backup was created
    assert exit_code == 0
    assert mock_create_backup.called
    # Verify it was called with repo_root and a plan_id
    call_args = mock_create_backup.call_args
    assert call_args[0][0] == repo_root
    assert isinstance(call_args[0][1], str)  # plan_id


def test_plan_command_succeeds_despite_backup_failure(tmp_path: Path, monkeypatch, caplog) -> None:
    """Test that plan command succeeds even when backup creation fails (non-fatal)."""
    from unittest.mock import Mock, MagicMock
    from weft.plan_command import run_plan_command
    from weft.plan_backup import PlanBackupError

    # Mock create_backup to raise error
    def mock_create_backup_failing(repo_root, plan_id):
        raise PlanBackupError(f"Test backup failure for {plan_id}")

    monkeypatch.setattr("weft.plan_command.create_backup", mock_create_backup_failing)

    # Mock all external dependencies
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    tasks_dir = repo_root / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    monkeypatch.setattr("weft.plan_command.find_repo_root", Mock(return_value=repo_root))

    # Mock temp worktree
    temp_worktree = tmp_path / "worktree"
    temp_worktree.mkdir()
    worktree_tasks_dir = temp_worktree / ".weft" / "tasks"
    worktree_tasks_dir.mkdir(parents=True)

    # Create a plan file in worktree
    (worktree_tasks_dir / "test-plan.md").write_text("---\nplan_id: test-plan\nstatus: draft\n---\n# Test")

    monkeypatch.setattr("weft.plan_command.create_temp_worktree", Mock(return_value=temp_worktree))
    monkeypatch.setattr("weft.plan_command.remove_temp_worktree", Mock())
    monkeypatch.setattr("weft.plan_command.get_weft_src_dir", Mock(return_value=tmp_path / "src"))

    # Mock subagent setup
    monkeypatch.setattr("weft.plan_command._write_plan_subagents", Mock())

    # Mock trace capture functions (now using session_manager)
    monkeypatch.setattr("weft.plan_command.prune_old_sessions", Mock())
    monkeypatch.setattr("weft.plan_command.create_session_directory", Mock(return_value=tmp_path / "traces"))
    monkeypatch.setattr("weft.plan_command.capture_session_trace", Mock(return_value=None))

    # Mock copy_plan_files to return a file mapping indicating a plan was copied
    def mock_copy_plan_files(source_dir, dest_dir, existing_files):
        # Simulate copying a plan file
        plan_file = dest_dir / "test-plan.md"
        plan_file.write_text("---\nplan_id: test-plan\nstatus: draft\n---\n# Test")
        return {"test-plan.md": "test-plan.md"}

    monkeypatch.setattr("weft.plan_command.copy_plan_files", mock_copy_plan_files)

    # Mock executor
    mock_executor = MagicMock()
    mock_executor.check_auth = Mock()
    mock_executor.build_command = Mock(return_value="echo test")
    mock_executor.get_env_vars = Mock(return_value={})
    from weft.executors import ExecutorRegistry
    monkeypatch.setattr(ExecutorRegistry, "get_executor", Mock(return_value=mock_executor))

    # Mock host runner
    monkeypatch.setattr("weft.plan_command.host_runner_config", Mock(return_value={}))
    monkeypatch.setattr("weft.plan_command.build_host_command", Mock(return_value=(["echo"], {})))
    monkeypatch.setattr("weft.plan_command.load_prompt_template", Mock(return_value="test template"))

    # Mock subprocess to succeed
    mock_result = MagicMock(returncode=0)
    monkeypatch.setattr("weft.plan_command.subprocess.run", Mock(return_value=mock_result))

    # Run the command - should succeed despite backup error
    exit_code = run_plan_command(plan_path=None, text_input="test idea", tool="claude-code")

    # Verify command succeeded (backup failure is non-fatal)
    assert exit_code == 0

    # Verify warning was logged about backup failure
    assert "backup(s) failed" in caplog.text
    assert "test-plan" in caplog.text


# Tests for PLAN_SUBAGENT_CONFIGS module-level constant


def test_plan_subagent_configs_is_module_constant() -> None:
    """Test that PLAN_SUBAGENT_CONFIGS is accessible at module level."""
    # Verify it's a dict
    assert isinstance(PLAN_SUBAGENT_CONFIGS, dict)

    # Verify expected keys exist
    expected_keys = {"maintainability-reviewer", "test-discovery", "test-reviewer"}
    assert set(PLAN_SUBAGENT_CONFIGS.keys()) == expected_keys

    # Verify all values are non-empty strings (descriptions)
    for key, value in PLAN_SUBAGENT_CONFIGS.items():
        assert isinstance(value, str), f"Value for {key} should be a string"
        assert len(value) > 0, f"Description for {key} should not be empty"


def test_write_plan_subagents_creates_all_configured(tmp_path: Path, monkeypatch) -> None:
    """Test that _write_plan_subagents creates files for all configured subagents."""
    # Create fake source directory with prompt files for all configured subagents
    fake_src_dir = tmp_path / "fake_src"
    prompts_dir = fake_src_dir / "prompts" / "plan-subagents"
    prompts_dir.mkdir(parents=True)

    # Create a prompt file for each configured subagent
    for subagent_name in PLAN_SUBAGENT_CONFIGS:
        prompt_file = prompts_dir / f"{subagent_name}.md"
        prompt_file.write_text(f"Prompt for {subagent_name}")

    # Mock get_weft_src_dir
    monkeypatch.setattr(
        weft.plan_command, "get_weft_src_dir", lambda: fake_src_dir
    )

    # Create worktree path
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Call the function for Claude Code
    _write_plan_subagents(worktree_path, "claude-code", "sonnet")

    # Verify the number of created files matches the number of configured subagents
    dest_agents_dir = worktree_path / ".claude" / "agents"
    created_files = list(dest_agents_dir.glob("*.md"))
    assert len(created_files) == len(PLAN_SUBAGENT_CONFIGS)

    # Verify each configured subagent has a file
    created_names = {f.stem for f in created_files}
    assert created_names == set(PLAN_SUBAGENT_CONFIGS.keys())


def test_plan_template_has_idea_placeholder() -> None:
    """Test that restored plan templates contain {IDEA_TEXT} placeholder."""
    from weft.repo_utils import load_prompt_template

    # Test both tool variants
    for tool in ["claude-code", "droid"]:
        template = load_prompt_template(tool, "plan")
        assert "{IDEA_TEXT}" in template, f"{tool}/plan.md should contain {{IDEA_TEXT}} placeholder"
