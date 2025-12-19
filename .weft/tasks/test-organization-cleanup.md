---
plan_id: test-organization-cleanup
status: done
evaluation_notes: []
git_sha: 193e27460d315f6820667dfcca60fc8fb22974bf
---

# Test Organization Cleanup

## Objectives

Simplify the test organization by switching from marker-based filtering to directory-based test discovery, fix misplaced tests, and improve documentation for AI assistants.

## Requirements & Constraints

- Tests must still be separated into unit tests (no external API calls) and integration tests (real API calls)
- Default `pytest` command should run only unit tests (fast feedback)
- Running integration tests should be intuitive (`pytest tests/integration/`)
- Documentation must be clear enough that AI assistants don't make repeated mistakes
- Changes must not break existing CI/CD workflows (if any)

## Work Items

### 1. Update pytest configuration in pyproject.toml
**File:** `pyproject.toml`

- Remove `addopts = "-m 'not integration'"`
- Add `testpaths = ["tests/unit"]` to default to unit tests
- Keep other pytest configuration unchanged

### 2. Remove @pytest.mark.integration decorators from all integration tests
**Files in `tests/integration/`:**
- `test_abandon_integration.py`
- `test_dspy_cache.py`
- `test_hooks_integration.py`
- `test_judge_executor_api.py`
- `test_sdk.py`
- `test_sdk_network.py`
- `test_sdk_subagents.py`

Remove `@pytest.mark.integration` decorator from all test functions and classes. The directory location now determines test type.

### 3. Remove test_marker_consistency.py
**File:** `tests/unit/test_marker_consistency.py`

Delete this file entirely - marker enforcement is no longer needed with directory-based approach.

### 4. Move test_execute_judge_invalid_api_key to integration tests
**From:** `tests/unit/test_judge_executor.py`
**To:** `tests/integration/test_judge_executor_api.py`

Move the `test_execute_judge_invalid_api_key` function to the integration test file. This test makes a real API call to OpenRouter (with invalid credentials) to verify error handling.

### 5. Remove test_get_openrouter_api_key_not_found
**File:** `tests/unit/test_judge_executor.py`

Remove this low-value test. It only verifies that an error is raised when an environment variable is missing.

### 6. Rename test_completion_integration.py to test_argcomplete.py
**From:** `tests/unit/test_completion_integration.py`
**To:** `tests/unit/test_argcomplete.py`

Use `git mv` to preserve history. The name "integration" is misleading - this file tests argparse/argcomplete component integration, not external API integration.

### 7. Update CLAUDE.md
**File:** `CLAUDE.md`

Update the Test Organization section:
- Remove marker requirement documentation and code examples
- Remove reference to `test_marker_consistency.py`
- Simplify test commands to directory-based approach
- Add guidance to only run integration tests relevant to changed code

New test commands section:
```
- `pytest` - Runs unit tests only (default via testpaths)
- `pytest tests/integration/` - Runs integration tests
- `pytest tests/` - Runs all tests (unit + integration)
```

Add guidance:
> **When to run integration tests**: Only run integration tests relevant to the code you changed. For example, if you modified `judge_executor.py`, run `pytest tests/integration/test_judge_executor_api.py` rather than all integration tests.

### 8. Update tests/README.md
**File:** `tests/README.md`

Update to reflect directory-based approach:
- Remove marker requirement documentation
- Simplify "Adding New Tests" section (no marker needed for integration tests)
- Update "Running Tests" commands
- Remove marker code examples

## Deliverables

1. Updated `pyproject.toml` with `testpaths` configuration
2. All `@pytest.mark.integration` decorators removed from integration tests
3. `test_marker_consistency.py` deleted
4. `test_execute_judge_invalid_api_key` moved to integration tests
5. `test_get_openrouter_api_key_not_found` removed
6. `test_completion_integration.py` renamed to `test_argcomplete.py`
7. Updated `CLAUDE.md` with simplified commands and integration test guidance
8. Updated `tests/README.md` reflecting directory-based approach

## Unit Tests

No new unit tests required. Existing unit tests should continue to pass after:
- Removing `test_marker_consistency.py`
- Removing `test_get_openrouter_api_key_not_found`
- Renaming `test_completion_integration.py`

Verify with: `pytest`

## Integration Tests

No new integration tests required. Existing integration tests should continue to pass after:
- Removing `@pytest.mark.integration` markers
- Adding `test_execute_judge_invalid_api_key` to `test_judge_executor_api.py`

Verify with: `pytest tests/integration/`

## Out of Scope

- Changes to CI/CD configuration (if exists) - may need separate update
- Adding new test coverage beyond what's being moved/reorganized
- Refactoring test implementations beyond marker removal
- Changes to conftest.py files (unless marker-related imports need removal)
