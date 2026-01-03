---
plan_id: weft-judge-command
status: done
evaluation_notes: []
git_sha: 735103c892e14044794f98cddf4cb92a87bba439
---

# weft judge Command

## Objectives

Implement a standalone `weft judge` command that runs LLM judges against git changes in a worktree, independent of the full eval pipeline. This provides lightweight feedback during the coding phase without running tests, collecting human feedback, or generating training data.

**Primary use case**: Get judge feedback on code quality and plan compliance while iterating on changes, before running `weft eval`.

## Requirements & Constraints

### Functional Requirements

1. **Worktree context required**: Command must be run from within a weft worktree (created by `weft code`)
2. **Plan input required**: Accepts plan ID as positional argument (tab completable via existing `complete_plan_files`)
3. **Run all judges**: Discovers and executes all judges from `.weft/judges/` directory
4. **Parallel execution**: Uses existing `execute_judges_parallel()` for concurrent judge execution
5. **Output to stdout**: Displays summary with scores, weights, and full feedback for each judge
6. **Optional file output**: `--output <dir>` flag saves results as markdown file to specified directory

### Non-Functional Requirements

1. **Reuse existing modules**: No modifications to judge_loader, judge_executor, judge_orchestrator, git_context, or plan_resolver
2. **Consistent CLI patterns**: Follow existing command patterns (positional plan_id, tab completion, exit codes)
3. **No session directory writes**: Does NOT save to `.weft/sessions/<plan_id>/eval/` to avoid conflicts with `weft eval` idempotency

### Out of Scope

- Commit range support (`--range` flag)
- Running outside worktrees
- Judge filtering (`--judges` flag)
- JSON output format
- Saving to session directories
- DSPy cache synchronization (pending separate task for cache handling)

## Work Items

### 1. Create `judge_command.py` module

**File**: `src/weft/judge_command.py`

Implement `run_judge_command(plan_id: str, output_dir: str | None = None) -> int`:

- Validate running in worktree context (use `validate_worktree_exists`)
- Resolve plan file using `PlanResolver`
- Gather git context using `gather_git_context()`
- Discover judges using `discover_judges()`
- Execute judges using `execute_judges_parallel()`
- Format and display results to stdout
- If `--output` provided, save markdown file to specified directory
- Return 0 on success, 1 on error

**Output format** (stdout):
```
Judge Results:

code-reuse (score: 0.85, weight: 0.4)
  The implementation properly reuses the existing validation
  utilities rather than reimplementing them...

plan-compliance (score: 0.92, weight: 0.6)
  The changes align well with the plan requirements...

Weighted average: 0.89
```

### 2. Add CLI subcommand

**File**: `src/weft/cli.py`

Add `judge` subparser:
- Positional `plan_id` argument with `complete_plan_files` completer
- Optional `--output` argument for directory path
- Dispatch to `run_judge_command()`

### 3. Unit Tests

**File**: `tests/unit/test_judge_command.py`

**Formatting and calculation** (test with constructed `JudgeResult` objects):
- `format_stdout()`: verify output matches spec format (scores, weights, feedback, weighted average)
- `format_markdown()`: verify markdown file content structure
- Weighted average: single judge, multiple judges with different weights

**Error handling** (mock dependencies to raise exceptions, verify exit code 1):
- Not in worktree → exit code 1
- Plan not found (`FileNotFoundError`) → exit code 1
- No judges found (`JudgeLoaderError`) → exit code 1
- Judge execution failure (`JudgeOrchestrationError`) → exit code 1
- API key not found (`JudgeExecutionError`) → exit code 1
- Git context error (`GitContextError`) → exit code 1

**Testing approach**:
- Use `capsys` to capture stdout for formatting tests
- Mock dependencies only to trigger specific exception types
- Follow patterns from `test_eval_command.py`

### 4. CLI Integration Test

**File**: `tests/unit/test_cli.py`

- Add `"judge"` to `test_all_subcommands_dispatch_without_import_errors()` parametrized test
- Add `"judge"` to `test_all_subcommands_help()` parametrized test

### 5. Integration Tests (Manual Verification)

The following existing integration tests exercise the judge execution path. Due to pending DSPy cache changes, these may have issues and should be verified manually rather than as automated requirements:

**File**: `tests/integration/test_judge_executor_api.py`
- `test_execute_judge_with_real_llm()` - validates DSPy LLM calls work
- `test_execute_judge_invalid_api_key()` - validates API error handling

**File**: `tests/integration/test_judge_orchestrator_api.py`
- `test_execute_judges_parallel_with_real_llm()` - validates parallel execution

### 6. Documentation

**File**: `README.md`

Add workflow documentation clarifying:
- When to use `weft judge` vs `weft eval`
- Example workflow: `weft code` → `weft judge` → iterate → `weft judge` → `weft eval`
- What the output means (scores, weights, weighted average)

**CLI help text** (in `cli.py`):
- Help string should clarify: "Run judges for quick feedback while coding. Use `weft eval` for full evaluation with tests and training data."

## Deliverables

1. `src/weft/judge_command.py` - New module implementing the command
2. Updated `src/weft/cli.py` - Judge subcommand registration with descriptive help text
3. `tests/unit/test_judge_command.py` - Unit test coverage
4. Updated `tests/unit/test_cli.py` - CLI dispatch tests include judge command
5. Updated `README.md` - Workflow documentation for judge vs eval

## Out of Scope

- Modifications to existing judge modules (loader, executor, orchestrator)
- Modifications to `git_context.py`
- Support for non-worktree contexts
- Commit range diffs
- Judge filtering
- Session directory integration
- JSON output format
- DSPy cache synchronization (pending separate task)
