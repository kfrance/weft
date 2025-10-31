"""Tests for completer functions."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import PropertyMock, patch

import pytest

from lw_coder.completion.cache import _global_cache
from lw_coder.completion.completers import (
    complete_models,
    complete_plan_files,
    complete_tools,
)


@pytest.fixture(autouse=True)
def invalidate_cache():
    """Invalidate global cache before each test."""
    _global_cache.invalidate()
    yield
    _global_cache.invalidate()


def test_complete_tools():
    """Test tool completion returns executor registry tools."""
    result = complete_tools("", Namespace())

    assert "claude-code" in result
    assert "droid" in result


def test_complete_tools_with_prefix():
    """Test tool completion filters by prefix."""
    result = complete_tools("dr", Namespace())

    assert "droid" in result
    assert "claude-code" not in result


def test_complete_tools_error_handling():
    """Test tool completion handles errors gracefully."""
    with patch("lw_coder.completion.completers.ExecutorRegistry.list_executors") as mock:
        mock.side_effect = Exception("Test error")
        result = complete_tools("", Namespace())

    assert result == []


def test_complete_models():
    """Test model completion returns valid models."""
    result = complete_models("", Namespace(tool="claude-code"))

    assert "sonnet" in result
    assert "opus" in result
    assert "haiku" in result


def test_complete_models_with_prefix():
    """Test model completion filters by prefix."""
    result = complete_models("s", Namespace(tool="claude-code"))

    assert "sonnet" in result
    assert "opus" not in result


def test_complete_models_suppressed_for_droid():
    """Test model completion is suppressed when tool is droid."""
    result = complete_models("", Namespace(tool="droid"))

    assert result == []


def test_complete_models_no_tool_attribute():
    """Test model completion when parsed_args has no tool attribute."""
    result = complete_models("", Namespace())

    # Should return models when tool is not set
    assert "sonnet" in result


def test_complete_models_error_handling():
    """Test model completion handles unexpected errors gracefully.

    This tests defensive error handling for edge cases where accessing VALID_MODELS
    might raise an exception (e.g., import failures, attribute errors). While unlikely
    in normal operation, completers must never break the shell, so all exceptions
    are caught and return empty lists.
    """
    # Patch VALID_MODELS to raise an error when accessed
    with patch("lw_coder.completion.completers.ClaudeCodeExecutor") as mock_executor:
        # Configure the mock to raise an exception when VALID_MODELS is accessed
        type(mock_executor).VALID_MODELS = PropertyMock(side_effect=Exception("Test error"))
        result = complete_models("", Namespace())

    # Should return empty list on error
    assert result == []


def test_complete_plan_files_empty_cache(tmp_path, monkeypatch):
    """Test plan file completion with empty cache."""
    # Create real git repo with no plans
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)

    result = complete_plan_files("", Namespace())

    assert result == []


def test_complete_plan_files_with_plans(tmp_path, monkeypatch):
    """Test plan file completion with active plans."""
    # Create real git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plans
    (tasks_dir / "fix-bug.md").write_text("---\nstatus: draft\n---\n# Fix Bug")
    (tasks_dir / "add-feature.md").write_text("---\nstatus: draft\n---\n# Add Feature")

    monkeypatch.chdir(tmp_path)

    result = complete_plan_files("", Namespace())

    assert "fix-bug" in result
    assert "add-feature" in result


def test_complete_plan_files_filters_by_prefix(tmp_path, monkeypatch):
    """Test plan file completion filters by prefix."""
    # Create real git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plans
    (tasks_dir / "fix-bug.md").write_text("---\nstatus: draft\n---\n# Fix Bug")
    (tasks_dir / "add-feature.md").write_text("---\nstatus: draft\n---\n# Add Feature")

    monkeypatch.chdir(tmp_path)

    result = complete_plan_files("fix", Namespace())

    assert "fix-bug" in result
    assert "add-feature" not in result


def test_complete_plan_files_with_path_prefix(tmp_path, monkeypatch):
    """Test plan file completion with path prefix."""
    # Create real git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plan
    (tasks_dir / "fix-bug.md").write_text("---\nstatus: draft\n---\n# Fix Bug")

    monkeypatch.chdir(tmp_path)

    result = complete_plan_files(".lw_coder/tasks/fix", Namespace())

    # Should include full path completions
    assert any(".lw_coder/tasks/fix-bug.md" in item for item in result)


def test_complete_plan_files_error_handling():
    """Test plan file completion handles errors gracefully."""
    with patch("lw_coder.completion.completers.get_active_plans") as mock:
        mock.side_effect = Exception("Test error")
        result = complete_plan_files("", Namespace())

    assert result == []


def test_complete_plan_files_excludes_done_plans(tmp_path, monkeypatch):
    """Test plan file completion excludes done plans."""
    # Create real git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create active and done plans
    (tasks_dir / "active.md").write_text("---\nstatus: draft\n---\n# Active")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    monkeypatch.chdir(tmp_path)

    result = complete_plan_files("", Namespace())

    assert "active" in result
    assert "done" not in result
