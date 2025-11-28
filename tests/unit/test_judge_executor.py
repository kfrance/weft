"""Unit tests for judge executor module.

These tests verify internal logic using mocks and controlled inputs.
They do not make any external API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.judge_executor import (
    JudgeExecutionError,
    execute_judge,
    get_cache_dir,
    get_openrouter_api_key,
)
from lw_coder.judge_loader import JudgeConfig


def test_execute_judge_invalid_api_key(tmp_path: Path) -> None:
    """Test judge execution with invalid API key."""
    judge = JudgeConfig(
        name="test-judge",
        weight=0.5,
        model="x-ai/grok-4.1-fast",
        instructions="Test instructions",
        file_path=tmp_path / "test-judge.md",
    )

    plan_content = "# Test Plan"
    git_changes = "=== Git Status ===\n(no changes)"
    cache_dir = tmp_path / "cache"

    # Use clearly invalid API key
    with pytest.raises(JudgeExecutionError, match="Failed to execute judge"):
        execute_judge(judge, plan_content, git_changes, "invalid_key", cache_dir)


def test_get_openrouter_api_key_not_found(monkeypatch) -> None:
    """Test getting API key when OPENROUTER_API_KEY is not set."""
    # Remove the environment variable if it exists
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # Also need to handle the case where load_home_env() sets it
    # We'll monkeypatch load_home_env to not set the key
    from lw_coder import judge_executor

    def mock_load_home_env():
        # Don't load anything
        pass

    monkeypatch.setattr(judge_executor, "load_home_env", mock_load_home_env)

    with pytest.raises(
        JudgeExecutionError, match="OPENROUTER_API_KEY not found in environment"
    ):
        get_openrouter_api_key()


def test_get_cache_dir() -> None:
    """Test cache directory path generation."""
    cache_dir = get_cache_dir()

    assert cache_dir == Path.home() / ".lw_coder" / "dspy_cache"
    assert isinstance(cache_dir, Path)
