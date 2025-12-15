---
plan_id: cleanup-test-code-command
status: done
evaluation_notes: []
git_sha: 8511131fdd2ed5b33d97d533839a6ab47fe7c04e
---

# Cleanup test_code_command.py - Remove Over-Mocked Tests

## Objectives

Remove over-mocked unit tests from `tests/unit/test_code_command.py` that test implementation details rather than behavior. Keep only tests that provide real value: pure function tests and critical error path tests with minimal mocking.

## Requirements & Constraints

- Per CLAUDE.md: "Don't test interactive commands" - `lw_coder code` launches interactive sessions
- Integration smoke test in `tests/integration/test_command_smoke.py` already covers the happy path
- Keep tests that verify critical safety features (SHA mismatch validation)
- Minimize mocking - prefer real git operations via `git_repo` fixture

## Work Items

### 1. Delete over-mocked tests

Delete the following tests (15 tests):
- `test_code_command_replaces_placeholder_git_sha` (lines 134-206)
- `test_code_command_status_implemented_on_success` (lines 208-274)
- `test_code_command_status_stays_coding_on_failure` (lines 276-342)
- `test_code_command_error_on_initial_update_failure` (lines 375-400)
- `test_code_command_warning_on_final_update_failure` (lines 402-480)
- `test_code_command_interrupted_by_user` (lines 482-545)
- `test_code_command_validation_failure_rolls_back_initial_update` (lines 547-567)
- `test_code_command_worktree_uses_updated_sha` (lines 569-632)
- `test_code_command_real_sha_matches_head_no_error` (lines 634-700)
- `test_code_command_agents_cleanup` (lines 702-771)
- `test_code_command_with_droid_tool` (lines 773-837)
- `test_code_command_with_claude_code_tool_explicit_model` (lines 839-914)
- `test_code_command_default_tool_and_model` (lines 916-988)
- `test_code_command_sdk_session_failure` (lines 990-1049)

### 2. Refactor test_run_code_command_worktree_failure

Reduce mocking from 5 dependencies to 1. Use `git_repo` fixture for real git operations:

```python
def test_run_code_command_worktree_failure(monkeypatch, caplog, git_repo):
    """Test run_code_command with worktree preparation failure."""
    plan_path = git_repo.path / "test-plan.md"
    write_plan(plan_path, {
        "git_sha": git_repo.latest_commit(),
        "plan_id": "test-plan-fail",
        "status": "draft",
    })

    # Only mock the failing component
    def mock_ensure_worktree(metadata):
        raise WorktreeError("Failed to create worktree")

    monkeypatch.setattr(code_command, "ensure_worktree", mock_ensure_worktree)

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "Worktree preparation failed" in caplog.text
```

### 3. Clean up imports and helper code

- Remove unused imports: `MagicMock`, `patch`, `SimpleNamespace`
- Remove fallback `write_plan` and `GitRepo` class definitions (lines 18-39) - use fixtures from conftest.py
- Remove unused imports: `ExecutorRegistry`, `PLACEHOLDER_SHA`, `PlanMetadata`, `extract_front_matter`

### 4. Verify tests pass

Run the remaining tests to ensure they work correctly:
```bash
uv run pytest tests/unit/test_code_command.py -v
```

## Deliverables

- Reduced `tests/unit/test_code_command.py` from ~1050 lines to ~100 lines
- 6 focused tests instead of 18+ brittle tests:
  1. `test_filter_env_vars_with_patterns`
  2. `test_filter_env_vars_with_star`
  3. `test_filter_env_vars_no_matches`
  4. `test_run_code_command_validation_failure`
  5. `test_run_code_command_worktree_failure` (refactored)
  6. `test_code_command_error_when_sha_mismatch`

## Unit Tests

The remaining 6 tests ARE the unit tests. No new unit tests needed.

## Integration Tests

No changes to integration tests. The existing smoke test in `tests/integration/test_command_smoke.py` provides coverage for the happy path.

## Out of Scope

- Changes to `code_command.py` implementation
- Changes to integration tests
- Adding new tests beyond what's being kept
- Refactoring other test files
