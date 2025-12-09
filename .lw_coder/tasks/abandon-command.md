---
plan_id: abandon-command
status: done
evaluation_notes: []
git_sha: 69f854e7d020209c65fd1f3c0120704ea0e7ba6f
---

## Objectives

Implement a `lw_coder abandon` command that provides a clean way to abandon failed or unwanted plans by deleting the worktree, branch, and plan file while preserving the backup reference in a separate "abandoned" namespace for potential future recovery.

## Requirements & Constraints

### Functional Requirements

- **Command signature**: `lw_coder abandon <plan_path> [--reason "text"] [--yes]`
  - `<plan_path>`: Path to plan file or plan ID (required)
  - `--reason "text"`: Optional reason for abandonment (logged only if provided)
  - `--yes`: Skip confirmation prompt (useful for automation)

- **Abandonment process**:
  1. Load plan_id from plan file (or resolve from plan ID argument)
  2. Detect what artifacts exist (worktree, branch, plan file, backup ref)
  3. Show confirmation prompt listing what will be destroyed (unless `--yes` provided)
  4. Force-delete worktree at `.lw_coder/worktrees/<plan_id>` (regardless of uncommitted changes)
  5. Force-delete branch `<plan_id>` (regardless of unmerged commits)
  6. Delete plan file at `.lw_coder/tasks/<plan_id>.md`
  7. Move git backup reference from `refs/plan-backups/<plan_id>` to `refs/plan-abandoned/<plan_id>` (overwrite if exists)
  8. If `--reason` provided, append entry to `.lw_coder/abandoned-plans.log` in Markdown format
  9. Return success (exit code 0) if all operations succeeded, error (exit code 1) if any failed

- **Confirmation prompt format**:
  ```
  Plan 'my-feature' will be abandoned:
    - Worktree will be force-deleted (has uncommitted changes)
    - Branch will be force-deleted (has 3 unmerged commits)
    - Plan file will be deleted
    - Backup moved to refs/plan-abandoned/my-feature

  Continue? (y/n)
  ```
  - Only show warnings for artifacts that actually exist
  - Skip prompt entirely if `--yes` flag provided

- **Abandoned plans log format** (`.lw_coder/abandoned-plans.log`):
  ```markdown
  ## plan-id - 2025-12-08 15:30:45 -0800
  Reason text provided by user goes here.
  Can span multiple lines if needed.

  ## another-plan - 2025-12-08 16:22:10 -0800
  Bug was already fixed in another PR
  ```
  - Use local timezone with offset (e.g., `-0800`)
  - Only append to log if `--reason` flag provided
  - Create file if it doesn't exist

- **Best-effort cleanup**:
  - Attempt all cleanup operations even if some artifacts don't exist
  - Don't fail if worktree already deleted, branch already deleted, etc.
  - Log what was cleaned up vs. what was already missing
  - Return error code if any operation that should have succeeded actually failed
  - Continue attempting remaining operations even after a failure

- **Git ref handling**:
  - Move backup from `refs/plan-backups/<plan_id>` to `refs/plan-abandoned/<plan_id>`
  - Force-update if `refs/plan-abandoned/<plan_id>` already exists (overwrite previous abandonment)
  - If no backup exists, skip this step (don't fail)

- **No safety checks**:
  - Don't check if worktree is currently in use / active
  - Don't validate uncommitted changes before deletion
  - Don't validate unmerged commits before branch deletion
  - Trust the user - rely only on confirmation prompt for safety

### Integration Requirements

- **Update `recover-plan` command**:
  - Add `--abandoned` flag: show only abandoned plans (from `refs/plan-abandoned/`)
  - Add `--all` flag: show both active backups and abandoned plans
  - Default behavior (no flags): show only active backups (from `refs/plan-backups/`)
  - When recovering an abandoned plan, move ref back to `refs/plan-backups/<plan_id>`
  - Display format should show plan_id, timestamp, and reason (if available from log)

- **Update README.md documentation**:
  - Document the `abandon` command and its usage
  - Document `.lw_coder/abandoned-plans.log` file and its purpose
  - Explain the difference between `refs/plan-backups/` and `refs/plan-abandoned/`
  - Document that abandoned plans can be recovered using `lw_coder recover-plan --abandoned`

### Non-Functional Requirements

- **Consistency**: Follow same architectural patterns as existing commands (`code_command.py`, `finalize_command.py`)
- **Error handling**: Comprehensive error messages with actionable guidance
- **Logging**: Info-level logging for normal operations, debug-level for detailed git operations
- **Testing**: Unit tests with mocked git operations, integration tests with real repository

### Constraints

- Must work with partial states (some artifacts exist, others don't)
- Must be idempotent (can run multiple times safely)
- Git operations use subprocess (follow existing patterns in `worktree_utils.py`, `plan_backup.py`)
- Log file must be human-readable Markdown (not JSON)
- No interactive operations beyond confirmation prompt

## Work Items

### 1. Create abandon command module
**File**: `src/lw_coder/abandon_command.py`

Implement `run_abandon_command(plan_path: Path | str, reason: str | None, skip_confirmation: bool) -> int`:
- Load plan_id from plan file using existing `plan_validator.load_plan_id()`
- Find repository root using `repo_utils.find_repo_root()`
- Detect existing artifacts (worktree, branch, plan file, backup ref)
- Show confirmation prompt with details of what will be destroyed (unless `skip_confirmation=True`)
- Call helper functions to perform cleanup operations
- Log abandonment reason to `.lw_coder/abandoned-plans.log` if provided
- Return 0 if all operations succeeded, 1 if any failed

Helper functions to implement:
- `_detect_plan_artifacts(repo_root: Path, plan_id: str) -> PlanArtifacts` - Check what exists
- `_show_confirmation_prompt(plan_id: str, artifacts: PlanArtifacts) -> bool` - Get user confirmation
- `_cleanup_worktree(repo_root: Path, plan_id: str) -> CleanupResult` - Force-delete worktree
- `_cleanup_branch(repo_root: Path, plan_id: str) -> CleanupResult` - Force-delete branch
- `_cleanup_plan_file(repo_root: Path, plan_id: str) -> CleanupResult` - Delete plan file
- `_move_backup_to_abandoned(repo_root: Path, plan_id: str) -> CleanupResult` - Move git ref
- `_log_abandonment(repo_root: Path, plan_id: str, reason: str) -> None` - Append to log file

Data structures:
```python
@dataclass
class PlanArtifacts:
    worktree_exists: bool
    worktree_has_changes: bool  # For prompt message
    branch_exists: bool
    branch_unmerged_commits: int  # For prompt message
    plan_file_exists: bool
    backup_ref_exists: bool

@dataclass
class CleanupResult:
    success: bool
    already_clean: bool  # Artifact didn't exist
    error_message: str | None
```

### 2. Update plan_backup module
**File**: `src/lw_coder/plan_backup.py`

Add new functions:
- `move_backup_to_abandoned(repo_root: Path, plan_id: str) -> None` - Move ref from `refs/plan-backups/` to `refs/plan-abandoned/`
- `move_abandoned_to_backup(repo_root: Path, plan_id: str) -> None` - Move ref back (for recovery)
- `list_abandoned_plans(repo_root: Path) -> list[tuple[str, int]]` - List plans in `refs/plan-abandoned/`
- `backup_exists_in_namespace(repo_root: Path, plan_id: str, namespace: str) -> bool` - Check if ref exists

Update existing functions:
- `list_backups()` - Add optional `namespace` parameter to filter by refs namespace

### 3. Update recover command
**File**: `src/lw_coder/recover_command.py`

Add new function:
- `run_recover_command(plan_id: str | None, force: bool, show_abandoned: bool, show_all: bool) -> int`
  - If `plan_id` is None: list available plans based on flags
  - If `show_abandoned=True`: list only `refs/plan-abandoned/` plans
  - If `show_all=True`: list both `refs/plan-backups/` and `refs/plan-abandoned/` plans
  - Default: list only `refs/plan-backups/` plans
  - When recovering from abandoned namespace, call `move_abandoned_to_backup()` first

Update display format:
- Show plan_id, timestamp, and abandonment reason (if available from log)
- Parse `.lw_coder/abandoned-plans.log` to extract reasons for abandoned plans

### 4. Add CLI integration
**File**: `src/lw_coder/cli.py`

Add abandon subcommand:
```python
abandon_parser = subparsers.add_parser(
    "abandon",
    help="Abandon a plan by cleaning up worktree, branch, and plan file",
)
abandon_parser.add_argument("plan_path", help="Path to plan file or plan ID")
abandon_parser.add_argument("--reason", help="Reason for abandoning the plan")
abandon_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
```

Update recover-plan subcommand:
```python
recover_parser.add_argument("--abandoned", action="store_true", help="Show only abandoned plans")
recover_parser.add_argument("--all", action="store_true", help="Show both active and abandoned plans")
```

Handle command dispatch:
```python
if args.command == "abandon":
    from .abandon_command import run_abandon_command
    plan_path = PlanResolver.resolve(args.plan_path)
    return run_abandon_command(plan_path, reason=args.reason, skip_confirmation=args.yes)
```

### 5. Update documentation
**File**: `README.md`

Add section documenting abandon command:
```markdown
#### Abandon Command
The `abandon` command cleans up failed or unwanted plans:
- **Command**: `uv run lw_coder abandon <plan_path>`
- **What it does**:
  - Force-deletes the worktree (regardless of uncommitted changes)
  - Force-deletes the branch (regardless of unmerged commits)
  - Deletes the plan file
  - Moves backup reference to abandoned namespace (`refs/plan-abandoned/`)
  - Optionally logs reason to `.lw_coder/abandoned-plans.log`
- **Flags**:
  - `--reason "text"` - Record why plan was abandoned
  - `--yes` - Skip confirmation prompt
- **Examples**:
  - `uv run lw_coder abandon my-feature --reason "Decided on different approach"`
  - `uv run lw_coder abandon quick-fix-2025.11-003 --yes`

#### Abandoned Plans Log
The `.lw_coder/abandoned-plans.log` file tracks abandoned plans with reasons:
- Human-readable Markdown format
- Only populated when `--reason` flag is used
- Shows plan_id, timestamp, and abandonment reason
- View abandoned plans: `uv run lw_coder recover-plan --abandoned`
```

Update recover-plan documentation to mention `--abandoned` and `--all` flags.

### 6. Unit Tests
**File**: `tests/unit/test_abandon_command.py`

Test scenarios:
- Abandon with all artifacts present (worktree, branch, plan file, backup ref)
- Abandon with partial artifacts (some missing)
- Abandon with no artifacts (all already cleaned)
- Abandon with `--reason` flag (verify log entry created)
- Abandon without `--reason` flag (verify no log entry)
- Abandon with `--yes` flag (verify no prompt shown)
- Abandon without `--yes` flag and user confirms (verify prompt shown)
- Abandon without `--yes` flag and user cancels (verify nothing deleted)
- Partial failures (worktree deleted but branch deletion fails)
- Ref collision (abandoned ref already exists, verify overwrite)
- Error cases (invalid plan_id, no plan file found, etc.)

**Testing Infrastructure Notes**:

Use existing test fixtures and patterns from the codebase:
- **`git_repo` fixture** (`tests/conftest.py:32-45`): Creates a temporary git repository in `tmp_path/repo` with initial commit. Use this for all tests to ensure `.lw_coder/abandoned-plans.log` is written to temp directory, not the real repo.
- **`write_plan()` helper** (`tests/conftest.py:48-58`): Creates plan files with proper YAML front matter.
- **Mocking `builtins.input`**: User confirmation prompts can be easily mocked using `monkeypatch.setattr("builtins.input", mock_fn)`. See `tests/unit/test_init_command.py:359-640` for extensive examples of:
  - Capturing prompts shown to user (`prompts_asked.append(prompt)`)
  - Returning specific responses (`return "y"` or `return "n"`)
  - Simulating multi-step input with `iter()` and `next()`
  - Verifying prompts were/weren't shown based on flags
- **Mocking `find_repo_root`**: Use `patch("lw_coder.abandon_command.find_repo_root", return_value=git_repo.path)` to point to temp repo.

All file operations (including `.lw_coder/abandoned-plans.log`) will naturally use the temp directory when using the `git_repo` fixture.

### 7. Integration Tests
**File**: `tests/integration/test_abandon_command.py`

Mark with `@pytest.mark.integration` decorator.

Test scenarios:
- End-to-end abandon workflow with real git repository
- Recover abandoned plan and verify ref moved back
- Multiple abandon/recover cycles
- List abandoned plans with `--abandoned` flag
- List all plans with `--all` flag
- Verify log file format and content
- Verify git refs are correctly moved between namespaces

### 8. Update plan_backup tests
**Files**:
- `tests/unit/test_plan_backup.py`
- `tests/integration/test_plan_backup.py`

Add tests for new functions:
- `move_backup_to_abandoned()`
- `move_abandoned_to_backup()`
- `list_abandoned_plans()`
- `backup_exists_in_namespace()`

### 9. Update recover_command tests
**Files**:
- `tests/unit/test_recover_command.py`
- `tests/integration/test_recover_command.py`

Add tests for new flags:
- `--abandoned` flag filters correctly
- `--all` flag shows both namespaces
- Recovery from abandoned namespace moves ref back
- Display shows abandonment reason from log file

## Deliverables

1. New command module: `src/lw_coder/abandon_command.py`
2. Updated module: `src/lw_coder/plan_backup.py` (new functions for abandoned namespace)
3. Updated module: `src/lw_coder/recover_command.py` (new flags and abandoned plan handling)
4. Updated CLI: `src/lw_coder/cli.py` (abandon subcommand and updated recover-plan flags)
5. Updated documentation: `README.md` (abandon command and abandoned-plans.log)
6. Comprehensive test coverage:
   - `tests/unit/test_abandon_command.py`
   - `tests/integration/test_abandon_command.py`
   - Updates to `tests/unit/test_plan_backup.py`
   - Updates to `tests/integration/test_plan_backup.py`
   - Updates to `tests/unit/test_recover_command.py`
   - Updates to `tests/integration/test_recover_command.py`

## Out of Scope

The following are explicitly out of scope for this plan:

- **Automatic cleanup/retention policies**: No automated pruning of old abandoned refs (future enhancement)
- **Undo mechanism**: No way to undo an abandon operation (recovery is manual)
- **Bulk operations**: No support for abandoning multiple plans at once
- **GUI/TUI interface**: Command-line only
- **Telemetry/analytics**: No tracking of abandon patterns or reasons
- **Migration of existing backups**: Existing `refs/plan-backups/` refs stay in their namespace
- **Transaction semantics**: No rollback if operations partially fail (best-effort cleanup)
- **Concurrent access protection**: No checks for active worktrees or locked files
- **Alternative storage formats**: Markdown log only (no JSON, SQLite, etc.)
- **Integration with external tools**: No hooks, webhooks, or notifications

## Unit Tests

Unit tests will mock git operations, file system operations, and user input to verify business logic without external dependencies:

- Test abandonment with various artifact combinations (all present, some missing, none present)
- Test confirmation prompt display and user response handling
- Test log file creation and formatting
- Test error handling for invalid inputs and failed operations
- Test idempotency (running abandon multiple times)
- Test ref namespace operations (move to abandoned, overwrite existing)
- Test plan_backup module functions for abandoned namespace
- Test recover_command flag parsing and display filtering

## Integration Tests

Integration tests will use real git repositories and file system to verify end-to-end workflows:

- Test complete abandon workflow with real git operations
- Test recovery from abandoned namespace and ref movement
- Test multiple abandon/recover cycles on same plan
- Test log file persistence and format across multiple abandonments
- Test interaction between abandon and recover commands
- Test git ref integrity across operations
- Test handling of git errors and partial states
- Verify no corruption of repository state after operations
