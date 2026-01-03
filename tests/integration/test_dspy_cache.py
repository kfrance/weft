"""Integration tests for DSPy cache functionality.

These tests verify that DSPy caching works correctly:
1. Cache files are actually written to disk
2. Cache is used on subsequent identical calls

Note: These tests require OPENROUTER_API_KEY to be available.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from weft.judge_executor import (
    JudgeExecutionError,
    configure_dspy_cache,
    execute_judge,
    get_openrouter_api_key,
)
from weft.judge_loader import JudgeConfig


def test_dspy_cache_creates_files(tmp_path: Path) -> None:
    """Verify DSPy cache actually writes files to disk.

    This test:
    1. Creates an empty cache directory
    2. Configures DSPy to use that cache
    3. Executes a judge with real DSPy/LLM call
    4. Verifies cache files were created
    """
    # Get API key (will fail with clear message if not available)
    try:
        api_key = get_openrouter_api_key()
    except JudgeExecutionError:
        pytest.fail(
            "OPENROUTER_API_KEY not found in ~/.weft/.env. "
            "Add it to run this integration test."
        )

    cache_dir = tmp_path / "test_cache"
    cache_dir.mkdir()

    # Verify cache is empty
    assert list(cache_dir.iterdir()) == []

    # Configure DSPy to use our test cache
    configure_dspy_cache(cache_dir)

    # Create a simple test judge
    judge = JudgeConfig(
        name="cache-test-judge",
        weight=0.5,
        model="x-ai/grok-4.1-fast",
        instructions=(
            "You are evaluating code changes. "
            "Provide a score between 0.0 and 1.0. "
            "Give brief feedback."
        ),
        file_path=tmp_path / "cache-test-judge.md",
    )

    plan_content = "# Test Plan\nSimple test for cache verification."
    git_changes = "=== Git Status ===\nNo changes"

    # Execute judge (will hit API)
    result1 = execute_judge(judge, plan_content, git_changes, api_key, cache_dir)

    # Verify we got a valid result
    assert result1.judge_name == "cache-test-judge"
    assert 0.0 <= result1.score <= 1.0
    assert isinstance(result1.feedback, str)

    # Verify cache files were created
    cache_files = list(cache_dir.rglob("*"))
    # Filter to only files (not directories)
    cache_files = [f for f in cache_files if f.is_file()]
    assert len(cache_files) > 0, "Cache should contain files after execution"
