---
plan_id: overmocked-test-cleanup
status: done
evaluation_notes: []
git_sha: 41568a51991e291e8480f3360bc9529058559dfa
---

# Overmocked Test Cleanup

Clean up low-quality tests that rely on excessive mocking, test implementation details rather than behavior, or use fragile assertions. This improves test maintainability and provides more meaningful coverage.

## Objectives

1. Remove tests that "test mocks, not real orchestration" due to 4+ mocks per test
2. Replace mocked parallel execution tests with real integration tests
3. Refactor fragile `call_count` assertions to assert on observable behavior (paths passed)
4. Delete tests that verify mechanism (method calls) rather than outcome

## Requirements & Constraints

### Testing Guidelines (from CLAUDE.md)
- Avoid mocking DSPy and LLMs - use real API calls with DSPy caching
- Don't test interactive commands (finalize runs Claude Code interactively)
- Use parametrization for similar test cases
- Keep tests focused on behavior, not implementation

### Constraints
- Preserve orchestration logic tests in finalize_command (precondition validation, cleanup coordination)
- Maintain test coverage for error paths that don't require integration tests
- Follow existing integration test patterns (see `test_judge_executor_api.py`)

## Work Items

### 1. Clean up `tests/unit/test_finalize_command.py`

**DELETE** (1 test):
- `test_run_finalize_command_with_droid_tool` (lines 114-177) - Redundant; tests same orchestration as other tests with different executor parameter

**KEEP** (9 tests):
- `test_move_plan_to_worktree_success` - Tests real filesystem behavior
- `test_run_finalize_command_no_uncommitted_changes` - Precondition validation
- `test_run_finalize_command_invalid_plan_file` - Precondition validation
- `test_run_finalize_command_auth_failure` - Error handling
- `test_run_finalize_command_cleanup_on_success` - Cleanup coordination
- `test_run_finalize_command_no_cleanup_on_failure` - Cleanup coordination
- `test_run_finalize_command_no_cleanup_if_verification_fails` - Cleanup coordination
- `test_backup_cleanup_called_after_successful_finalize` - Backup integration
- `test_finalize_succeeds_with_idempotent_cleanup` - Backup integration

### 2. Clean up `tests/unit/test_judge_orchestrator.py`

**DELETE** (2 tests):
- `test_execute_judges_parallel_success` (lines 18-61) - Mocks execute_judge; will be covered by integration test
- `test_execute_judges_parallel_sorted_results` (lines 117-167) - Mocks execute_judge; will be covered by integration test

**KEEP** (3 tests):
- `test_execute_judges_parallel_no_judges` - Validates empty list error (edge case)
- `test_execute_judges_parallel_fail_fast` - Validates JudgeExecutionError wrapping
- `test_execute_judges_parallel_unexpected_error` - Validates RuntimeError wrapping

### 3. Add `tests/integration/test_judge_orchestrator_api.py`

Create new integration test file following the pattern from `test_judge_executor_api.py`:

```python
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
```

### 4. Refactor `tests/unit/test_file_watcher.py`

**KEEP AS-IS** (count IS the behavior being tested):
- `test_watcher_ignores_non_md_files` (lines 74-90) - `call_count == 0` verifies filtering
- `test_watcher_ignores_directories` (lines 92-106) - `call_count == 0` verifies filtering
- `test_watcher_ignores_empty_files` (lines 108-122) - `call_count == 0` verifies filtering
- `test_watcher_prevents_duplicate_triggers` (lines 190-210) - `call_count == 1` verifies dedup

**REFACTOR** (assert on paths via `call_args_list`):

#### `test_watcher_detects_md_file_creation` (lines 55-72)
```python
# Current:
assert callback.call_count == 1
called_path = callback.call_args[0][0]
assert called_path.name == "test-plan.md"

# Refactored:
assert callback.called
called_path = callback.call_args_list[0][0][0]
assert called_path.name == "test-plan.md"
assert called_path.parent == watch_dir
```

#### `test_watcher_handles_multiple_files` (lines 124-140)
```python
# Current:
assert callback.call_count == 2

# Refactored:
assert len(callback.call_args_list) == 2
called_paths = {call[0][0].name for call in callback.call_args_list}
assert called_paths == {"plan1.md", "plan2.md"}
```

#### `test_watcher_handles_callback_exception` (lines 168-188)
```python
# Current:
assert callback.call_count == 2

# Refactored:
assert len(callback.call_args_list) == 2
called_paths = {call[0][0].name for call in callback.call_args_list}
assert called_paths == {"plan1.md", "plan2.md"}
```

#### `test_watcher_file_stem_extraction` (lines 212-226)
```python
# Current:
assert callback.call_count == 1
called_path = callback.call_args[0][0]
assert called_path.stem == "my-test-plan"

# Refactored:
assert callback.called
called_path = callback.call_args_list[0][0][0]
assert called_path.stem == "my-test-plan"
assert called_path.suffix == ".md"
```

### 5. Clean up `tests/unit/test_hooks.py`

**DELETE** (2 tests):
- `test_cleanup_terminates_processes` (lines 411-429) - Tests mechanism (`.terminate()` called), not outcome
- `test_cleanup_kills_stubborn_processes` (lines 431-453) - Tests mechanism (`.terminate()` then `.kill()` called), not outcome

**KEEP**:
- `test_process_tracking` (lines 272-295) - Verifies processes are tracked for cleanup (white-box testing acceptable per prior review)
- `test_prune_completed_removes_finished` (lines 455-474) - Verifies pruning logic
- All other tests in the file

## Deliverables

1. **Updated**: `tests/unit/test_finalize_command.py` - 1 test deleted
2. **Updated**: `tests/unit/test_judge_orchestrator.py` - 2 tests deleted
3. **New**: `tests/integration/test_judge_orchestrator_api.py` - 1 integration test added
4. **Updated**: `tests/unit/test_file_watcher.py` - 4 tests refactored
5. **Updated**: `tests/unit/test_hooks.py` - 2 tests deleted

## Out of Scope

- Adding new test coverage beyond the judge orchestrator integration test
- Refactoring production code to make it more testable
- Changes to tests not mentioned in this plan
- Adding integration tests for finalize_command (runs interactively per CLAUDE.md)

## Unit Tests

**Validation after implementation:**
- Run `uv run pytest tests/unit/test_finalize_command.py` - should pass with 9 tests
- Run `uv run pytest tests/unit/test_judge_orchestrator.py` - should pass with 3 tests
- Run `uv run pytest tests/unit/test_file_watcher.py` - should pass with all existing tests
- Run `uv run pytest tests/unit/test_hooks.py` - should pass with 2 fewer tests
- Run `uv run pytest tests/unit/` - all unit tests should pass

## Integration Tests

**New integration test:**
- `tests/integration/test_judge_orchestrator_api.py::test_execute_judges_parallel_with_real_llm`

**Validation after implementation:**
- Run `uv run pytest tests/integration/test_judge_orchestrator_api.py` - requires OPENROUTER_API_KEY
- First run makes real API calls; subsequent runs use DSPy cache
