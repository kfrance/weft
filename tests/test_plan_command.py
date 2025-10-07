"""Tests for plan command functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.plan_command import (
    PlanCommandError,
    _extract_idea_text,
    _load_template,
)


def test_load_template_success() -> None:
    """Test loading a valid template."""
    template = _load_template("droid")
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
