---
plan_id: implement-eval-complete-hook
status: done
evaluation_notes: []
git_sha: efa2c3b6a97ab062b5a1e721bbba1fa892a0a0dc
---

# Implement eval_complete Hook

## Objectives

Add the `eval_complete` hook trigger to `eval_command.py` so that users can automate actions after training data is created. The hook is already registered in `hooks.py` and documented in `docs/HOOKS.md`, but the actual `trigger_hook()` call is missing from the eval command.

## Requirements & Constraints

### Functional Requirements
1. The `eval_complete` hook must trigger only after training data is successfully created
2. The hook must receive all documented context variables:
   - `training_data_dir` - Path to training data output directory
   - `worktree_path` - Path to the worktree
   - `plan_path` - Path to the plan file
   - `plan_id` - The plan ID
   - `repo_root` - Path to the repository root
3. The `--no-hooks` flag must prevent hook execution (consistency with plan/code commands)
4. Hook failures must not fail the eval command (non-blocking, per existing hook design)

### Constraints
- Must follow existing hook patterns from `code_command.py`
- Must not trigger hook when training data creation is skipped (e.g., missing feedback)
- No changes to the hook system itself (`hooks.py`)

## Work Items

### 1. Add trigger_hook import to eval_command.py
Add the import statement at the top of `src/weft/eval_command.py`:
```python
from .hooks import trigger_hook
```

### 2. Add --no-hooks flag to eval CLI parser
In `src/weft/cli.py`, add the `--no-hooks` argument to the eval subparser (following the pattern from plan/code commands):
```python
eval_parser.add_argument(
    "--no-hooks",
    dest="no_hooks",
    action="store_true",
    help="Disable execution of configured hooks",
)
```

### 3. Add no_hooks parameter to run_eval_command()
Update the function signature in `src/weft/eval_command.py`:
```python
def run_eval_command(
    plan_id: str,
    model: str = "sonnet",
    force: bool = False,
    no_hooks: bool = False,
) -> int:
```

### 4. Add trigger_hook call after training data creation
Insert the hook trigger after the `logger.info("Training data created at: %s", training_data_dir)` line (around line 452), inside the success path of `create_training_data()`:
```python
if not no_hooks:
    trigger_hook(
        "eval_complete",
        {
            "training_data_dir": training_data_dir,
            "worktree_path": worktree_path,
            "plan_path": plan_path,
            "plan_id": actual_plan_id,
            "repo_root": repo_root,
        },
    )
```

### 5. Pass no_hooks argument from CLI to run_eval_command
Update the CLI handler to pass the flag through to `run_eval_command()`.

## Deliverables

1. Modified `src/weft/eval_command.py` with:
   - Import for `trigger_hook`
   - `no_hooks` parameter in function signature
   - `trigger_hook()` call after training data creation
2. Modified `src/weft/cli.py` with:
   - `--no-hooks` argument for eval subparser
   - Passing `no_hooks` to `run_eval_command()`
3. Unit tests in `tests/unit/test_eval_command.py`

## Out of Scope

- Changes to the hook system itself (`src/weft/hooks.py`) - already complete
- Documentation updates (`docs/HOOKS.md`) - already documents `eval_complete`
- New hook types or additional variables
- Integration tests for hook execution mechanics - already covered by existing tests
- Changes to hook configuration format or validation

## Unit Tests

Tests should be added to `tests/unit/test_eval_command.py`, following patterns from `tests/unit/test_code_command.py`.

### Test 1: test_eval_command_triggers_hook_after_training_data_created

**Purpose:** Verify the `eval_complete` hook is triggered with correct context after training data is successfully created.

**Approach:**
- Use the existing `_setup_eval_environment()` helper pattern
- Mock all eval dependencies (judges, tests, feedback collection, training data export)
- Mock `trigger_hook` using `patch("weft.eval_command.trigger_hook")`
- Run `run_eval_command()` with conditions that lead to training data creation
- Assert `trigger_hook` was called once with `"eval_complete"` and a context dict containing all required variables

**Assertions:**
- `trigger_hook` called exactly once
- First argument is `"eval_complete"`
- Context contains `training_data_dir`, `worktree_path`, `plan_path`, `plan_id`, `repo_root`
- All paths are `Path` objects or strings pointing to correct locations

### Test 2: test_eval_complete_hook_not_triggered_when_training_data_skipped

**Purpose:** Verify the hook is NOT triggered when training data creation is skipped (e.g., when `human_feedback.md` doesn't exist).

**Approach:**
- Set up eval environment without `human_feedback.md` file
- Mock `trigger_hook`
- Run `run_eval_command()`
- Assert `trigger_hook` was NOT called

**Assertions:**
- `trigger_hook` not called (call count is 0)

### Test 3: test_eval_command_no_hooks_flag_prevents_eval_complete

**Purpose:** Verify the `--no-hooks` flag prevents hook execution even when training data is created.

**Approach:**
- Set up complete eval environment (with feedback, all conditions for training data creation)
- Mock `trigger_hook`
- Run `run_eval_command(..., no_hooks=True)`
- Assert `trigger_hook` was NOT called

**Assertions:**
- `trigger_hook` not called when `no_hooks=True`

## Integration Tests

No new integration tests are required.

**Rationale:** The existing tests in `tests/integration/test_hooks_integration.py` already validate:
- Real subprocess execution via hooks works
- Variable substitution works with real execution
- File watcher integration (for plan_file_created)

These integration tests are hook-agnostic and validate the hook execution mechanics. The `eval_complete` hook doesn't introduce any new integration patterns - it uses the same `trigger_hook()` function with the same execution model. Adding an eval-specific integration test would require running the full eval pipeline (judges, tests, feedback) and would be slow with low additional value.
