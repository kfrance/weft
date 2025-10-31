---
plan_id: test-suite-optimization
status: done
evaluation_notes: []
git_sha: 18c18d2381822c3f3e86bd6f5e58595dc684a933
---

## Objectives

Optimize the test suite by removing 18 verified redundant tests through deletion and parametrization, improving maintainability while preserving 100% test coverage. Update documentation to prevent future test bloat.

## Requirements & Constraints

### Functional Requirements

- Remove or merge 18 tests across 9 test files
- Group 1: Remove 6 duplicate tests (simple deletions)
- Group 2: Parametrize 12 tests into 6 tests (consolidate similar tests)
- Add brief guidance (~10 lines) to `docs/BEST_PRACTICES.md` on avoiding redundant tests
- Run full test suite (`uv run pytest`) after each group to ensure no regressions

### Coverage Requirements

- Must maintain 100% of existing test coverage
- Must preserve all edge cases and error conditions currently tested
- Error message assertions must be preserved (integrate into parametrized tests where applicable)

### Implementation Constraints

- Use subagents to modify files in parallel within each group for efficiency
- Keep parametrization focused: one test concern per parametrized test function
- Do not mix unrelated test scenarios in a single parametrized test
- Preserve clear test names that document behavior
- All tests must pass after each group's changes

## Work Items

### Group 1: Simple Removals (6 tests removed)

Use parallel subagents to modify these files simultaneously.

#### 1.1 test_plan_command.py
- Remove `test_run_plan_command_with_droid_executor` (duplicate of test_executors.py)
- Remove `test_run_plan_command_with_claude_code_executor` (duplicate of test_executors.py)

#### 1.2 test_cli.py
- Remove `test_code_command_droid_with_model_error` (duplicates `test_code_command_validation_error_droid_with_model`)
- Remove `test_code_command_invalid_tool_error` (duplicates `test_code_command_validation_error_invalid_tool`)

#### 1.3 test_param_validation.py
- Remove `test_validate_all_valid_claude_code_model_combinations` (overlaps with individual model tests)
- Remove `test_validate_droid_rejects_all_models` (overlaps with single model rejection test)

#### 1.4 Validate Group 1
- Run `uv run pytest` to ensure all tests pass
- Verify test count decreased by 6

### Group 2: Parametrization (12 tests → 6 tests)

Use parallel subagents to modify these files simultaneously.

#### 2.1 test_executors.py
Merge these 3 tests into 1 parametrized test with 3 cases (sonnet, haiku, opus):
- `test_build_command`
- `test_build_command_with_haiku_model`
- `test_build_command_with_opus_model`

#### 2.2 test_home_env.py
Merge 2 tests into 1 parametrized test (missing_file, missing_directory):
- `test_load_home_env_missing_file`
- `test_load_home_env_missing_lw_coder_dir`

Remove this test and integrate error message assertion into the parametrized test above:
- `test_load_home_env_error_message_includes_path`

#### 2.3 test_prompt_loader.py
Merge these 3 tests into 1 parametrized test (parametrize missing_file and other_files):
- `test_load_prompts_missing_main_file`
- `test_load_prompts_missing_code_review_file`
- `test_load_prompts_missing_alignment_file`

#### 2.4 test_plan_command.py
Create 3 separate parametrized tests (one per concern) to maintain clarity:

**2.4a** - Merge into parametrized test for get_existing_files edge cases:
- `test_get_existing_files_empty_directory`
- `test_get_existing_files_nonexistent_directory`

**2.4b** - Merge into parametrized test for permission error handling:
- `test_copy_droids_for_plan_permission_error`
- `test_write_maintainability_agent_permission_error`

**2.4c** - Merge into parametrized test for missing source file handling:
- `test_copy_droids_for_plan_missing_source`
- `test_write_maintainability_agent_missing_source`

#### 2.5 test_code_command.py
- Remove `test_code_command_with_claude_code_default_model` (redundant with `test_code_command_default_tool_and_model`)

#### 2.6 test_worktree_utils.py
- Remove `test_get_worktree_path` (covered by `test_get_worktree_path_valid_plan_ids`)

#### 2.7 test_integration.py (completion subdirectory)
- Remove `test_all_subcommands_have_completers` (overlaps with individual completer tests)

#### 2.8 Validate Group 2
- Run `uv run pytest` to ensure all tests pass
- Verify test count decreased by 6 more (12 original → 6 parametrized)
- Verify parametrized test output is clear when failures occur

### 3. Update Documentation

#### 3.1 docs/BEST_PRACTICES.md
Add a new section (approximately 10 lines) covering:
- Avoid redundant tests (check for duplicates before adding new tests)
- When to use parametrization (same behavior/code path with different inputs)
- Keep parametrized tests focused on a single concern
- Ensure test function names clearly document behavior

### 4. Final Validation

- Execute `uv run pytest` to verify all tests pass
- Verify total test count: ~332 tests → ~314 tests (18 test reduction)
- Spot-check that parametrized test names in pytest output are clear
- Confirm running individual parametrized cases works: `pytest -k "test_name[parameter]"`

## Deliverables

1. Modified test files (9 files):
   - `tests/test_executors.py`
   - `tests/test_home_env.py`
   - `tests/test_prompt_loader.py`
   - `tests/test_plan_command.py`
   - `tests/test_code_command.py`
   - `tests/test_cli.py`
   - `tests/test_worktree_utils.py`
   - `tests/test_param_validation.py`
   - `tests/completion/test_integration.py`

2. Updated `docs/BEST_PRACTICES.md` with guidance on avoiding redundant tests

3. Validation: All tests pass, 18 fewer tests, coverage maintained

## Out of Scope

- Baseline metrics collection (test timing, coverage reports)
- Git tagging for rollback capability
- Extensive parametrization guidelines (keeping brief only)
- Refactoring test fixtures or conftest.py
- Modifying any source code outside of tests and documentation
- Performance optimization beyond reducing test count
- Adding new tests or test coverage
- Restructuring test file organization
