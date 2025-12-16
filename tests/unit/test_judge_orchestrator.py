"""Tests for judge orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lw_coder.judge_executor import JudgeExecutionError, JudgeResult
from lw_coder.judge_loader import JudgeConfig
from lw_coder.judge_orchestrator import (
    JudgeOrchestrationError,
    execute_judges_parallel,
)


def test_execute_judges_parallel_fail_fast(tmp_path: Path) -> None:
    """Test that orchestrator fails fast on first judge error."""
    judge1 = JudgeConfig(
        name="judge-1",
        weight=0.5,
        model="x-ai/grok-4.1-fast",
        instructions="Judge 1 instructions",
        file_path=tmp_path / "judge-1.md",
    )

    judge2 = JudgeConfig(
        name="judge-2",
        weight=0.5,
        model="x-ai/grok-4.1-fast",
        instructions="Judge 2 instructions",
        file_path=tmp_path / "judge-2.md",
    )

    judges = [judge1, judge2]
    plan_content = "# Test Plan"
    git_changes = "=== Changes ==="
    api_key = "test_key"
    cache_dir = tmp_path / "cache"

    # Mock execute_judge to fail on first judge
    def mock_execute_judge(judge, plan, changes, key, cache):
        if judge.name == "judge-1":
            raise JudgeExecutionError(f"Failed to execute {judge.name}")
        return JudgeResult(
            judge_name=judge.name,
            score=0.8,
            feedback=f"Feedback from {judge.name}",
            weight=judge.weight,
        )

    with patch("lw_coder.judge_orchestrator.execute_judge", side_effect=mock_execute_judge):
        with pytest.raises(JudgeOrchestrationError, match="Judge 'judge-1' failed"):
            execute_judges_parallel(
                judges, plan_content, git_changes, api_key, cache_dir
            )


def test_execute_judges_parallel_no_judges(tmp_path: Path) -> None:
    """Test orchestrator with empty judge list."""
    plan_content = "# Test Plan"
    git_changes = "=== Changes ==="
    api_key = "test_key"
    cache_dir = tmp_path / "cache"

    with pytest.raises(JudgeOrchestrationError, match="No judges to execute"):
        execute_judges_parallel([], plan_content, git_changes, api_key, cache_dir)


def test_execute_judges_parallel_unexpected_error(tmp_path: Path) -> None:
    """Test orchestrator handles unexpected errors."""
    judge1 = JudgeConfig(
        name="judge-1",
        weight=0.5,
        model="x-ai/grok-4.1-fast",
        instructions="Judge 1 instructions",
        file_path=tmp_path / "judge-1.md",
    )

    judges = [judge1]
    plan_content = "# Test Plan"
    git_changes = "=== Changes ==="
    api_key = "test_key"
    cache_dir = tmp_path / "cache"

    # Mock execute_judge to raise unexpected exception
    def mock_execute_judge(judge, plan, changes, key, cache):
        raise RuntimeError("Unexpected error")

    with patch("lw_coder.judge_orchestrator.execute_judge", side_effect=mock_execute_judge):
        with pytest.raises(JudgeOrchestrationError, match="Unexpected error"):
            execute_judges_parallel(
                judges, plan_content, git_changes, api_key, cache_dir
            )
