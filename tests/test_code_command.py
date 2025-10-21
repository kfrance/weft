"""Tests for code_command module."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.code_command import _filter_env_vars, run_code_command
from lw_coder.plan_validator import PlanMetadata, PlanValidationError
from lw_coder.worktree_utils import WorktreeError

try:
    from tests.conftest import write_plan, GitRepo
except ImportError:
    # Fallback if conftest is not available
    def write_plan(path, *args, **kwargs):
        """Write a test plan file."""
        plan_text = kwargs.get("body", "# Test Plan")
        git_sha = kwargs.get("git_sha", "a" * 40)
        plan_id = kwargs.get("plan_id", "test-plan")
        status = kwargs.get("status", "draft")

        content = f"""---
plan_id: {plan_id}
git_sha: {git_sha}
status: {status}
evaluation_notes: []
---

{plan_text}
"""
        path.write_text(content)

    class GitRepo:
        """Simple GitRepo mock."""
        pass


def test_run_code_command_validation_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with plan validation failure."""
    # Setup
    plan_path = tmp_path / "plan.md"

    # Mock load_plan_metadata to raise PlanValidationError
    def mock_load_plan_metadata(path):
        raise PlanValidationError("Invalid git_sha")

    # Apply monkeypatch
    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", mock_load_plan_metadata
    )

    # Execute
    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    # Assert
    assert exit_code == 1
    assert "Plan validation failed" in caplog.text
    assert "Invalid git_sha" in caplog.text


def test_run_code_command_worktree_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with worktree preparation failure."""
    plan_path = tmp_path / "plan.md"
    run_dir = tmp_path / ".lw_coder" / "runs" / "test-plan" / "20250101_120000"

    mock_metadata = PlanMetadata(
        plan_text="# Test Plan",
        git_sha="b" * 40,
        evaluation_notes=["Test note"],
        plan_path=plan_path,
        repo_root=tmp_path,
        plan_id="test-plan-fail",
        status="draft",
    )

    from lw_coder.dspy.prompt_orchestrator import PromptArtifacts
    mock_artifacts = PromptArtifacts(
        main_prompt_path=run_dir / "prompts" / "main.md",
        review_prompt_path=run_dir / "droids" / "code-review-auditor.md",
        alignment_prompt_path=run_dir / "droids" / "plan-alignment-checker.md",
    )

    def mock_ensure_worktree(metadata):
        raise WorktreeError("Failed to create worktree")

    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", lambda path: mock_metadata
    )
    monkeypatch.setattr(
        lw_coder.code_command, "create_run_directory", lambda repo_root, plan_id: run_dir
    )
    monkeypatch.setattr(
        lw_coder.code_command, "copy_coding_droids", lambda run_dir: run_dir / "droids"
    )
    monkeypatch.setattr(
        lw_coder.code_command, "generate_code_prompts", lambda metadata, run_dir: mock_artifacts
    )
    monkeypatch.setattr(
        lw_coder.code_command, "prune_old_runs", lambda repo_root, active_run_dir: 0
    )
    monkeypatch.setattr(
        lw_coder.code_command, "ensure_worktree", mock_ensure_worktree
    )

    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "Plan validation succeeded" in caplog.text
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
