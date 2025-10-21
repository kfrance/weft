"""Tests for plan command functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.plan_command import (
    PlanCommandError,
    _ensure_placeholder_git_sha,
    _extract_idea_text,
    _load_template,
)
from lw_coder.plan_validator import PLACEHOLDER_SHA, _extract_front_matter
from tests.conftest import write_plan
import lw_coder.plan_command


def test_load_template_success() -> None:
    """Test loading a valid template."""
    template = _load_template("droid")
    assert "{IDEA_TEXT}" in template
    assert "Your task:" in template


def test_load_template_claude_code() -> None:
    """Test loading Claude Code CLI template."""
    template = _load_template("claude-code")
    assert "{IDEA_TEXT}" in template
    assert "Your task:" in template


def test_load_template_nonexistent_tool() -> None:
    """Test loading template for nonexistent tool."""
    with pytest.raises(PlanCommandError, match="Prompt template not found"):
        _load_template("nonexistent_tool")


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


def test_load_template_delegates_to_droid_session(monkeypatch) -> None:
    """Test that _load_template uses get_lw_coder_src_dir from droid_session."""
    # Track if get_lw_coder_src_dir was called
    calls = []

    def mock_get_lw_coder_src_dir():
        calls.append(1)
        # Return the actual source directory so template loading works
        return Path(__file__).resolve().parent.parent / "src" / "lw_coder"

    # Patch it in the plan_command module where it's imported
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", mock_get_lw_coder_src_dir
    )

    # Call _load_template which should use the mocked function
    template = _load_template("droid")

    # Verify the mock was called
    assert len(calls) == 1
    # Verify template was loaded successfully
    assert "{IDEA_TEXT}" in template


def test_load_template_runtime_error_becomes_plan_command_error(monkeypatch) -> None:
    """Test that RuntimeError from get_lw_coder_src_dir becomes PlanCommandError."""
    def mock_get_lw_coder_src_dir():
        raise RuntimeError("Source directory not found")

    # Patch it in the plan_command module where it's imported
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", mock_get_lw_coder_src_dir
    )

    with pytest.raises(PlanCommandError, match="Source directory not found"):
        _load_template("droid")


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

    front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
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

    with patch("lw_coder.plan_command._find_repo_root"):
        with patch("lw_coder.plan_command._extract_idea_text", return_value="test"):
            result = run_plan_command(None, "test idea", "unknown-executor")
            # Should fail due to unknown executor
            assert result != 0
