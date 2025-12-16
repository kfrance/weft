"""Integration tests for judge orchestrator with real DSPy LLM calls.

These tests make real LLM API calls to external services (OpenRouter).
They require OPENROUTER_API_KEY to be configured and consume API credits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.judge_executor import (
    JudgeExecutionError,
    get_cache_dir,
    get_openrouter_api_key,
)
from lw_coder.judge_loader import JudgeConfig
from lw_coder.judge_orchestrator import execute_judges_parallel


@pytest.mark.integration
def test_execute_judges_parallel_with_real_llm(tmp_path: Path) -> None:
    """Test parallel execution of 2 judges with real DSPy calls.

    Verifies:
    1. ThreadPoolExecutor actually runs judges concurrently
    2. Results are collected correctly via as_completed()
    3. Results are sorted by judge name
    """
    # Get API key
    try:
        api_key = get_openrouter_api_key()
    except JudgeExecutionError:
        pytest.fail(
            "OPENROUTER_API_KEY not found in ~/.lw_coder/.env. "
            "Add it to run this integration test."
        )

    # Create 2 judges in reverse alphabetical order to test sorting
    judge_b = JudgeConfig(
        name="judge-b",
        weight=0.4,
        model="x-ai/grok-4.1-fast",
        instructions="Evaluate code quality. Score between 0.0-1.0.",
        file_path=tmp_path / "judge-b.md",
    )

    judge_a = JudgeConfig(
        name="judge-a",
        weight=0.6,
        model="x-ai/grok-4.1-fast",
        instructions="Evaluate test coverage. Score between 0.0-1.0.",
        file_path=tmp_path / "judge-a.md",
    )

    judges = [judge_b, judge_a]  # Reversed order

    plan_content = "# Test Plan\nAdd calculator function"
    git_changes = "=== Git Diff ===\n+def add(a, b):\n+    return a + b"
    cache_dir = get_cache_dir()

    # Execute judges in parallel
    results = execute_judges_parallel(
        judges, plan_content, git_changes, api_key, cache_dir
    )

    # Verify all judges completed
    assert len(results) == 2

    # Verify results are sorted alphabetically by judge name
    assert results[0].judge_name == "judge-a"
    assert results[1].judge_name == "judge-b"

    # Verify each result has valid structure
    for result in results:
        assert 0.0 <= result.score <= 1.0
        assert isinstance(result.feedback, str)
        assert len(result.feedback) > 0
        assert result.weight in [0.4, 0.6]
