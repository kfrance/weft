"""Tests for code_command module.

Focused tests for the code_command module. Per CLAUDE.md, we don't test
interactive commands extensively - integration smoke tests cover the happy path.
These tests focus on:
- Pure function tests (_filter_env_vars)
- Critical error path tests with minimal mocking
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

import lw_coder.code_command as code_command
from lw_coder.code_command import _filter_env_vars, run_code_command
from lw_coder.plan_validator import PlanValidationError
from lw_coder.worktree_utils import WorktreeError
from conftest import write_plan


def test_run_code_command_validation_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with plan validation failure."""
    # Setup
    plan_path = tmp_path / "plan.md"

    # Mock load_plan_metadata to raise PlanValidationError
    def mock_load_plan_metadata(path):
        raise PlanValidationError("Invalid git_sha")

    # Apply monkeypatch
    monkeypatch.setattr(code_command, "load_plan_metadata", mock_load_plan_metadata)

    # Execute
    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    # Assert
    assert exit_code == 1
    assert "Plan validation failed" in caplog.text
    assert "Invalid git_sha" in caplog.text


def test_run_code_command_worktree_failure(monkeypatch, caplog, git_repo) -> None:
    """Test run_code_command with worktree preparation failure.

    Uses git_repo fixture for real git operations. Mocks load_prompts (required
    for claude-code tool to proceed) and ensure_worktree (the failing component).
    """
    plan_path = git_repo.path / "test-plan.md"
    write_plan(plan_path, {
        "git_sha": git_repo.latest_commit(),
        "plan_id": "test-plan-fail",
        "status": "draft",
    })

    # Mock load_prompts so we can reach the worktree preparation step
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

    # Mock the failing component
    def mock_ensure_worktree(metadata):
        raise WorktreeError("Failed to create worktree")

    monkeypatch.setattr(code_command, "ensure_worktree", mock_ensure_worktree)

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "Worktree preparation failed" in caplog.text
    assert "Failed to create worktree" in caplog.text


def test_filter_env_vars_with_patterns(monkeypatch) -> None:
    """Test _filter_env_vars with wildcard patterns."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "key123")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://api.openrouter.ai")
    monkeypatch.setenv("OTHER_VAR", "value")

    result = _filter_env_vars(["OPENROUTER_*"])

    assert "OPENROUTER_API_KEY" in result
    assert "OPENROUTER_BASE_URL" in result
    assert "OTHER_VAR" not in result


def test_filter_env_vars_with_star(monkeypatch) -> None:
    """Test _filter_env_vars with * pattern (all vars)."""
    monkeypatch.setenv("VAR1", "value1")
    monkeypatch.setenv("VAR2", "value2")

    result = _filter_env_vars(["*"])

    assert "VAR1" in result
    assert "VAR2" in result
    assert len(result) > 2  # Should include all env vars


def test_filter_env_vars_no_matches(monkeypatch) -> None:
    """Test _filter_env_vars when no vars match."""
    result = _filter_env_vars(["NONEXISTENT_*"])

    assert result == {}


def test_code_command_error_when_sha_mismatch(git_repo, caplog) -> None:
    """Test run_code_command errors when plan SHA doesn't match HEAD.

    This is a critical safety feature that prevents coding against stale code.
    Uses git_repo fixture for real git operations - minimal mocking.
    """
    initial_sha = git_repo.latest_commit()
    extra_file = git_repo.path / "extra.txt"
    extra_file.write_text("extra", encoding="utf-8")
    git_repo.run("add", "extra.txt")
    git_repo.run("commit", "-m", "extra commit")
    head_sha = git_repo.latest_commit()
    assert head_sha != initial_sha

    plan_path = git_repo.path / "plan-mismatch.md"
    write_plan(
        plan_path,
        {
            "git_sha": initial_sha,
            "plan_id": "plan-mismatch",
            "status": "coding",
        },
    )

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "does not match repository HEAD" in caplog.text
    assert "uncommitted changes" in caplog.text or "rebasing" in caplog.text
