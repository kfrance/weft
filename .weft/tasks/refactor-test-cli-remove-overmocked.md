---
plan_id: refactor-test-cli-remove-overmocked
status: done
evaluation_notes: []
git_sha: 266965f6ad2d381a652d92aab05a41827ca7fe66
---

# Refactor test_cli.py: Remove Over-Mocked Tests

## Objectives

1. Remove over-mocked unit tests that only verify argparse behavior
2. Keep unit tests that validate real CLI business logic (validation, quick-fix creation)
3. Add integration tests that verify validation errors via subprocess invocation
4. Reduce test maintenance burden while improving test quality

## Requirements & Constraints

- Tests must follow project guidelines in CLAUDE.md (avoid over-mocking, test behavior not implementation)
- Integration tests cannot test interactive commands (`code`, `plan`) end-to-end per CLAUDE.md
- Integration tests should use subprocess calls to verify exit codes and error messages
- Unit tests should only mock what's necessary to prevent interactive sessions

## Work Items

### 1. Delete over-mocked unit tests from `tests/unit/test_cli.py`

Remove 21 tests that primarily test argparse or are redundant:

**Argparse-testing tests:**
- `test_code_command_explicit_tool`, `test_code_command_explicit_model`, `test_code_command_tool_and_model`
- `test_plan_command_tool_parameter`, `test_code_command_debug_flag`, `test_help_flag`
- `test_code_command_parameter_order`, `test_code_command_text_with_tool_flag`, `test_code_command_text_with_model_flag`

**Init command tests (redundant with test_init_command.py):**
- `test_init_command_success`, `test_init_command_with_force`, `test_init_command_with_yes`
- `test_init_command_with_force_and_yes`, `test_init_command_help_text`

**No-hooks flag tests (trivial pass-through):**
- `test_plan_command_no_hooks_flag`, `test_plan_command_no_hooks_default_false`
- `test_code_command_no_hooks_flag`, `test_code_command_no_hooks_default_false`
- `test_code_command_no_hooks_with_other_flags`, `test_no_hooks_help_text_plan`, `test_no_hooks_help_text_code`

### 2. Keep valuable unit tests in `tests/unit/test_cli.py`

Retain 10 tests that validate real CLI behavior:

**Validation logic tests:**
- `test_code_command_validation_error_droid_with_model` - droid + model incompatibility
- `test_code_command_validation_error_invalid_tool` - invalid tool rejection
- `test_code_command_invalid_model` - invalid model rejection
- `test_code_command_text_mutual_exclusivity` - plan_path + --text rejection
- `test_code_command_text_empty_error` - empty --text rejection
- `test_code_command_neither_path_nor_text` - missing argument error

**Quick-fix creation tests:**
- `test_code_command_with_text_flag` - plan file creation with --text
- `test_code_command_text_multiline` - multiline text preservation

**Import/dispatch safety tests:**
- `test_subcommand_help_no_import_errors` - catches lazy import bugs
- `test_all_subcommands_dispatch_without_import_errors` - catches import shadowing

### 3. Create integration tests in `tests/integration/test_cli_validation.py`

Create 6 integration tests that run the CLI as a subprocess and verify exit codes and error messages:

| Test | Behavior to Verify |
|------|-------------------|
| `test_cli_rejects_droid_with_model` | `--tool droid --model sonnet` returns exit code 1 with "cannot be used with --tool droid" in stderr |
| `test_cli_rejects_invalid_tool` | `--tool invalid-tool` returns exit code 1 with "Unknown tool" in stderr |
| `test_cli_rejects_invalid_model` | `--model gpt-4` returns exit code 1 with "Unknown model" in stderr |
| `test_cli_rejects_plan_path_and_text` | Both plan_path and `--text` returns exit code 1 with "mutually exclusive" in stderr |
| `test_init_fails_outside_git_repo` | `lw_coder init` outside git repo returns exit code 1 with git-related error |
| `test_init_force_yes_completes` | `lw_coder init --force --yes` succeeds non-interactively, creates `.lw_coder` directory |

### 4. Run tests and verify

- Run `uv run pytest tests/unit/test_cli.py` to verify unit tests pass
- Run `uv run pytest tests/integration/test_cli_validation.py` to verify integration tests pass

## Deliverables

1. Modified `tests/unit/test_cli.py` with 10 tests (down from 31)
2. New `tests/integration/test_cli_validation.py` with 6 tests
3. All tests passing

## Out of Scope

- Modifying the CLI implementation (`src/lw_coder/cli.py`)
- Adding tests for interactive commands (`code`, `plan` end-to-end)
- Modifying other test files (`test_param_validation.py`, `test_init_command.py`)
- Adding new CLI features or validation rules
