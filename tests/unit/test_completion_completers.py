"""Tests for completer functions."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import PropertyMock, patch

import pytest

from weft.completion.cache import _global_cache
from weft.completion.completers import (
    complete_eval_plans,
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
    with patch("weft.completion.completers.ExecutorRegistry.list_executors") as mock:
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
    with patch("weft.completion.completers.ClaudeCodeExecutor") as mock_executor:
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
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)

    result = complete_plan_files("", Namespace())

    assert result == []


def test_complete_plan_files_with_plans(tmp_path, monkeypatch):
    """Test plan file completion with active plans."""
    # Create real git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
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
    tasks_dir = tmp_path / ".weft" / "tasks"
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
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plan
    (tasks_dir / "fix-bug.md").write_text("---\nstatus: draft\n---\n# Fix Bug")

    monkeypatch.chdir(tmp_path)

    result = complete_plan_files(".weft/tasks/fix", Namespace())

    # Should include full path completions
    assert any(".weft/tasks/fix-bug.md" in item for item in result)


def test_complete_plan_files_error_handling():
    """Test plan file completion handles errors gracefully."""
    with patch("weft.completion.completers.get_active_plans") as mock:
        mock.side_effect = Exception("Test error")
        result = complete_plan_files("", Namespace())

    assert result == []


def test_complete_plan_files_excludes_done_plans(tmp_path, monkeypatch):
    """Test plan file completion excludes done plans."""
    # Create real git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create active and done plans
    (tasks_dir / "active.md").write_text("---\nstatus: draft\n---\n# Active")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    monkeypatch.chdir(tmp_path)

    result = complete_plan_files("", Namespace())

    assert "active" in result
    assert "done" not in result


def test_complete_plan_files_includes_implemented_plans(tmp_path, monkeypatch):
    """Test plan file completion includes implemented plans."""
    # Create real git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plans with different statuses
    (tasks_dir / "draft.md").write_text("---\nstatus: draft\n---\n# Draft")
    (tasks_dir / "implemented.md").write_text("---\nstatus: implemented\n---\n# Implemented")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    monkeypatch.chdir(tmp_path)

    result = complete_plan_files("", Namespace())

    # Should include draft and implemented but not done
    assert "draft" in result
    assert "implemented" in result
    assert "done" not in result


# Tests for complete_eval_plans


def test_complete_eval_plans_returns_all_plans(tmp_path, monkeypatch):
    """Test complete_eval_plans returns all plans (finished and unfinished)."""
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create active and done plans
    (tasks_dir / "active.md").write_text("---\nstatus: draft\n---\n# Active")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    monkeypatch.chdir(tmp_path)

    result = complete_eval_plans("", Namespace())

    assert "active" in result
    assert "done" in result


def test_complete_eval_plans_two_tier_ordering_unfinished_first(tmp_path, monkeypatch):
    """Test two-tier ordering: unfinished plans first (alphabetically sorted)."""
    import subprocess
    import time
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create unfinished plans
    (tasks_dir / "zebra.md").write_text("---\nstatus: draft\n---\n# Zebra")
    (tasks_dir / "alpha.md").write_text("---\nstatus: coding\n---\n# Alpha")

    # Create finished plans with different mtimes
    done1 = tasks_dir / "done-old.md"
    done1.write_text("---\nstatus: done\n---\n# Done Old")

    monkeypatch.chdir(tmp_path)

    result = complete_eval_plans("", Namespace())

    # Unfinished plans should come before done plans
    alpha_idx = result.index("alpha")
    zebra_idx = result.index("zebra")
    done_old_idx = result.index("done-old")

    # Unfinished should be alphabetically sorted and come before done
    assert alpha_idx < zebra_idx
    assert alpha_idx < done_old_idx
    assert zebra_idx < done_old_idx


def test_complete_eval_plans_finished_sorted_by_mtime(tmp_path, monkeypatch):
    """Test two-tier ordering: finished plans sorted by mtime (most recent first)."""
    import os
    import subprocess
    import time
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create finished plans with different mtimes
    done_old = tasks_dir / "done-old.md"
    done_old.write_text("---\nstatus: done\n---\n# Done Old")
    # Set an older mtime
    old_time = time.time() - 1000
    os.utime(done_old, (old_time, old_time))

    # Small delay to ensure different mtimes
    time.sleep(0.01)

    done_new = tasks_dir / "done-new.md"
    done_new.write_text("---\nstatus: done\n---\n# Done New")
    # done_new keeps current mtime (newer)

    monkeypatch.chdir(tmp_path)

    result = complete_eval_plans("", Namespace())

    done_old_idx = result.index("done-old")
    done_new_idx = result.index("done-new")

    # Most recent (done-new) should come before older (done-old)
    assert done_new_idx < done_old_idx


def test_complete_eval_plans_prefix_filtering(tmp_path, monkeypatch):
    """Test prefix filtering works correctly."""
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    (tasks_dir / "fix-bug.md").write_text("---\nstatus: draft\n---\n# Fix Bug")
    (tasks_dir / "fix-feature.md").write_text("---\nstatus: done\n---\n# Fix Feature")
    (tasks_dir / "add-feature.md").write_text("---\nstatus: draft\n---\n# Add Feature")

    monkeypatch.chdir(tmp_path)

    result = complete_eval_plans("fix", Namespace())

    assert "fix-bug" in result
    assert "fix-feature" in result
    assert "add-feature" not in result


def test_complete_eval_plans_identical_mtime_stable_sort(tmp_path, monkeypatch):
    """Test edge case: plans with identical mtime (stable sort by plan_id)."""
    import os
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create done plans with exact same mtime
    same_time = 1000000.0
    for name in ["zebra-done", "alpha-done", "beta-done"]:
        plan_file = tasks_dir / f"{name}.md"
        plan_file.write_text("---\nstatus: done\n---\n# Plan")
        os.utime(plan_file, (same_time, same_time))

    monkeypatch.chdir(tmp_path)

    result = complete_eval_plans("", Namespace())

    # With identical mtime, should fall back to alphabetical order
    alpha_idx = result.index("alpha-done")
    beta_idx = result.index("beta-done")
    zebra_idx = result.index("zebra-done")

    assert alpha_idx < beta_idx
    assert beta_idx < zebra_idx


def test_complete_eval_plans_empty_prefix_returns_all(tmp_path, monkeypatch):
    """Test edge case: empty prefix returns all plans."""
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    (tasks_dir / "plan1.md").write_text("---\nstatus: draft\n---\n# Plan 1")
    (tasks_dir / "plan2.md").write_text("---\nstatus: done\n---\n# Plan 2")
    (tasks_dir / "plan3.md").write_text("---\nstatus: coding\n---\n# Plan 3")

    monkeypatch.chdir(tmp_path)

    result = complete_eval_plans("", Namespace())

    assert len(result) == 3


def test_complete_eval_plans_all_done(tmp_path, monkeypatch):
    """Test edge case: all plans done."""
    import os
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # All plans are done with different mtimes
    old_time = 1000.0
    new_time = 2000.0
    done1 = tasks_dir / "done1.md"
    done1.write_text("---\nstatus: done\n---\n# Done 1")
    os.utime(done1, (old_time, old_time))

    done2 = tasks_dir / "done2.md"
    done2.write_text("---\nstatus: done\n---\n# Done 2")
    os.utime(done2, (new_time, new_time))

    monkeypatch.chdir(tmp_path)

    result = complete_eval_plans("", Namespace())

    assert len(result) == 2
    # done2 is newer, should come first
    assert result.index("done2") < result.index("done1")


def test_complete_eval_plans_no_done(tmp_path, monkeypatch):
    """Test edge case: no plans done."""
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    (tasks_dir / "zebra.md").write_text("---\nstatus: draft\n---\n# Zebra")
    (tasks_dir / "alpha.md").write_text("---\nstatus: coding\n---\n# Alpha")

    monkeypatch.chdir(tmp_path)

    result = complete_eval_plans("", Namespace())

    assert len(result) == 2
    # Alphabetically sorted
    assert result == ["alpha", "zebra"]


def test_complete_eval_plans_error_handling():
    """Test eval plan completion handles errors gracefully."""
    with patch("weft.completion.completers.get_all_plans") as mock:
        mock.side_effect = Exception("Test error")
        result = complete_eval_plans("", Namespace())

    assert result == []
