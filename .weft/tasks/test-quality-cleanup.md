---
plan_id: test-quality-cleanup
status: done
evaluation_notes: []
git_sha: 042d47bc8655311a5e0be5387d036028979b77eb
---

# Test Quality Cleanup

Consolidate scattered validation tests, remove redundant tests, and delete implementation-focused tests that duplicate existing behavior-based integration tests.

## Objectives

1. Reduce test maintenance burden by consolidating similar validation tests into parametrized tests
2. Remove redundant tests that duplicate coverage without adding value
3. Delete implementation-focused tests (rsync command structure) where behavior is already tested
4. Improve test naming to clarify intent

## Requirements & Constraints

### Testing Guidelines (from CLAUDE.md)
- Use parametrization for similar test cases with `@pytest.mark.parametrize`
- Use `ids` parameter to provide clear labels for each test case
- Avoid redundant tests that increase maintenance burden without adding value
- Keep parametrized tests focused on single concerns

### Constraints
- No changes to `tests/integration/test_abandon_integration.py` - explicit patching pattern is appropriate
- No changes to `tests/unit/test_hooks.py` - private `_processes` access is acceptable for lifecycle tests
- Preserve all unique test coverage; only remove true duplicates

## Work Items

### 1. Create `tests/unit/test_validation.py`

Create a new consolidated validation test file with:

**Module docstring** explaining consolidation rationale:
```python
"""CLI parameter validation tests.

These tests verify validation logic for all commands before reaching
the command handlers. Consolidating them here makes it easier to:
- Ensure consistent validation patterns across commands
- Update validation rules in one place
- Use parametrization for similar validation patterns

For command-specific behavior tests, see:
- tests/unit/test_train_command.py
- tests/unit/test_cli.py (CLI wiring and dispatch)
"""
```

**TestTrainCommandValidation class** - parametrized test covering:
- `batch_size` below minimum (0)
- `batch_size` above maximum (15)
- `max_subagents` below minimum (0)
- `max_subagents` above maximum (15)
- Invalid `variant` value
- Valid parameters (boundary cases: 1, 10)

**TestCodeCommandValidation class** - parametrized tests covering:
- `--tool droid` with `--model` (incompatible combination)
- Invalid `--tool` value
- Invalid `--model` value
- `plan_path` with `--text` (mutual exclusivity)
- Empty `--text` value
- Neither `plan_path` nor `--text` provided

### 2. Clean up `tests/unit/test_train_command.py`

**Remove:**
- `TestValidateParameters` class (lines 13-61) - moved to `test_validation.py`
- Duplicate validation tests in `TestRunTrainCommand` (lines 94-108):
  - `test_train_command_invalid_batch_size`
  - `test_train_command_invalid_max_subagents`
  - `test_train_command_invalid_variant`

**Add:**
- Cross-reference comment at top of file:
  ```python
  # Parameter validation tests: see tests/unit/test_validation.py
  ```

**Keep:**
- `test_train_command_no_training_data`
- `test_train_command_no_active_prompts`
- `test_train_command_repo_not_found`

### 3. Clean up `tests/unit/test_cli.py`

**Remove:**
- Validation tests (lines 27-135):
  - `test_code_command_validation_error_droid_with_model`
  - `test_code_command_validation_error_invalid_tool`
  - `test_code_command_invalid_model`
  - `test_code_command_text_mutual_exclusivity`
  - `test_code_command_text_empty_error`
  - `test_code_command_neither_path_nor_text`

**Add:**
- Cross-reference comment at top of file:
  ```python
  # Parameter validation tests: see tests/unit/test_validation.py
  ```

**Keep:**
- Quick-fix creation tests (`test_code_command_with_text_flag`, `test_code_command_text_multiline`)
- Import/dispatch safety tests (`test_subcommand_help_no_import_errors`, `test_all_subcommands_dispatch_without_import_errors`)

### 4. Delete `tests/unit/test_cache_sync.py`

Delete the entire file. Rationale:
- Tests verify rsync command structure (implementation detail) rather than sync behavior
- Behavior is already comprehensively tested in `tests/integration/test_dspy_cache.py`:
  - `test_cache_sync_workflow` - bidirectional sync
  - `test_sync_to_worktree_mirrors_with_delete` - `--delete` behavior
  - `test_sync_from_worktree_preserves_global` - preservation behavior

### 5. Rename test in `tests/integration/test_trace_summarizer_api.py`

**Rename:**
- `test_summary_caching_prevents_regeneration` → `test_summary_file_not_rewritten_when_trace_unchanged`

**Rationale:** The test verifies file-based caching by checking `st_mtime` equality. The new name clarifies this is testing file-level behavior, not abstract "caching works."

## Deliverables

1. New file: `tests/unit/test_validation.py` with consolidated parametrized validation tests
2. Updated file: `tests/unit/test_train_command.py` with validation tests removed
3. Updated file: `tests/unit/test_cli.py` with validation tests removed
4. Deleted file: `tests/unit/test_cache_sync.py`
5. Updated file: `tests/integration/test_trace_summarizer_api.py` with renamed test

## Out of Scope

- Changes to `tests/integration/test_abandon_integration.py` - explicit `find_repo_root` patching is appropriate for integration tests
- Changes to `tests/unit/test_hooks.py` - private `_processes` access is acceptable for lifecycle management tests
- Adding new test coverage - this is a cleanup/consolidation effort only
- Changes to production code

## Unit Tests

No new unit tests required. This plan consolidates existing unit tests.

**Validation after implementation:**
- Run `uv run pytest tests/unit/` to verify all unit tests pass
- Verify test count is reduced (fewer tests due to parametrization consolidation)
- Verify no coverage loss by checking parametrized test cases match original test scenarios

## Integration Tests

No new integration tests required. Existing integration tests in `tests/integration/test_dspy_cache.py` already cover cache sync behavior.

**Validation after implementation:**
- Run `uv run pytest tests/integration/test_dspy_cache.py` to confirm cache sync behavior tests still pass
- Run `uv run pytest tests/integration/test_trace_summarizer_api.py` to confirm renamed test passes
