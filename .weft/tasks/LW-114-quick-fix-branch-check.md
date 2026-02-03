---
plan_id: LW-114-quick-fix-branch-check
status: done
evaluation_notes: []
git_sha: 93ba5415e66248f2001d7eaf2ccf2a0fd30fcf1d
---

# LW-114: Quick-fix ID Generation Should Check for Existing Git Branches

## Objectives

Fix the `generate_quick_fix_id()` function to check both task files AND git branches when determining the next available quick-fix counter. This prevents ID collisions when a quick-fix branch exists but its corresponding task file was deleted or moved.

## Requirements & Constraints

1. **Check both sources**: The ID generator must check existing task files in `.weft/tasks/` AND git branches matching `quick-fix-YYYY.MM-*`
2. **Check local and remote branches**: Both local branches and remote tracking branches (e.g., `origin/quick-fix-2026.02-001`) must be considered
3. **Use maximum counter**: The next ID should be max(file_counters, branch_counters) + 1
4. **Graceful degradation**: If git commands fail (corrupted repo, no remotes, etc.), log a warning and fall back to file-only checking
5. **Counter format only**: The fix applies only to counter-based IDs (`quick-fix-YYYY.MM-NNN`), not timestamp fallback format
6. **Optional repo_root**: The `repo_root` parameter defaults to `None`; when `None`, only file checking is performed (preserves existing behavior)

## Work Items

### 1. Add branch listing utility to `worktree_utils.py`

Create a new function `list_branches_matching_pattern()` that:
- Accepts `repo_root: Path` and `pattern: str` parameters
- Uses `git for-each-ref` with pattern-specific refs (e.g., `refs/heads/quick-fix-*` and `refs/remotes/*/quick-fix-*`) for performance
- Returns a list of branch names (short form, without `refs/heads/` or `refs/remotes/origin/` prefix)
- Raises `WorktreeError` on git command failure (caller handles gracefully)

### 2. Extract counter parsing into a helper function

Create a helper function `extract_quick_fix_counter()` in `quick_fix.py` that:
- Accepts a name string (filename or branch name) and year/month parameters
- Returns the extracted counter as an integer, or `None` if the name doesn't match the pattern
- Works for both `quick-fix-YYYY.MM-NNN.md` (files) and `quick-fix-YYYY.MM-NNN` (branches)
- Silently skips malformed names (returns `None`)

### 3. Modify `generate_quick_fix_id()` function

Update the function signature and behavior:
- Add optional `repo_root: Path | None = None` parameter
- When `repo_root` is provided:
  - Call the branch listing utility to get branches matching `quick-fix-{year}.{month:02d}-*`
  - On git failure, log a warning and continue with file-only checking
  - Use the shared counter extraction helper for both filenames and branch names
  - Combine counters from both sources and use max + 1
- When `repo_root` is `None`: current file-only behavior (backward compatible)
- Update docstring to document:
  - The dual-source checking behavior
  - Limitation: remote branches only checked via local tracking refs (stale refs possible)
  - Graceful degradation on git failure

### 4. Update `create_quick_fix_plan()` caller

Modify the call site to pass `repo_root` to `generate_quick_fix_id()`.

### 5. Unit Tests

**New tests for branch collision detection** (add to `TestGenerateQuickFixId` class):

| Test Name | Description |
|-----------|-------------|
| `test_existing_branch_no_task_file` | Branch `quick-fix-2026.02-003` exists but no task file; next ID should be 004 |
| `test_branch_and_file_both_exist` | Task file for 001-002, branch for 005; next ID should be 006 |
| `test_same_counter_in_file_and_branch` | Counter 003 exists as both file and branch; next ID should be 004 (no duplication) |
| `test_remote_branch_detected` | Remote branch `origin/quick-fix-2026.02-002` exists; next ID should be 003 |
| `test_git_failure_falls_back_to_files` | Mock git failure; verify warning logged and file-only checking proceeds |
| `test_repo_without_remotes` | Repository has no remotes configured; verify local branches still checked |
| `test_timestamp_branches_ignored` | Timestamp-format branch exists; verify it's ignored by counter logic |
| `test_repo_root_none_skips_branch_check` | Pass `repo_root=None`; verify only files are checked (backward compat) |

**New tests for helper functions**:

| Test Name | Description |
|-----------|-------------|
| `test_list_branches_matching_pattern_local` | Verify local branches matching pattern are listed |
| `test_list_branches_matching_pattern_remote` | Verify remote tracking branches are listed |
| `test_list_branches_matching_pattern_no_matches` | Pattern matches nothing; returns empty list |
| `test_extract_quick_fix_counter_from_filename` | Extract counter from `quick-fix-2026.02-005.md` |
| `test_extract_quick_fix_counter_from_branch` | Extract counter from `quick-fix-2026.02-005` |
| `test_extract_quick_fix_counter_invalid_format` | Invalid format returns `None` |
| `test_extract_quick_fix_counter_wrong_month` | Different month returns `None` |

**Updates to existing tests**:
- Existing `TestGenerateQuickFixId` tests remain unchanged (use `tmp_path`, don't pass `repo_root`)
- These tests validate file-only behavior continues to work

### 6. Integration Tests

The following existing integration tests must continue to pass:
- `tests/integration/test_abandon_integration.py::test_end_to_end_abandon_workflow`
- `tests/integration/test_abandon_integration.py::test_recover_abandoned_plan_workflow`
- `tests/integration/test_abandon_integration.py::test_git_refs_integrity_after_operations`

No new integration tests are required since the branch listing uses standard git commands already exercised by the integration test suite.

## Deliverables

1. Updated `src/weft/quick_fix.py` with:
   - New `extract_quick_fix_counter()` helper function
   - Modified `generate_quick_fix_id()` with optional `repo_root` parameter and graceful degradation
   - Updated `create_quick_fix_plan()` to pass `repo_root`
   - Comprehensive docstring documenting behavior and limitations

2. Updated `src/weft/worktree_utils.py` with:
   - New `list_branches_matching_pattern()` function using pattern-specific `git for-each-ref`

3. Updated `tests/unit/test_quick_fix.py` with:
   - New tests for branch collision detection (using `git_repo` fixture)
   - New tests for helper functions
   - Existing tests unchanged (backward compatibility validated)

## Out of Scope

- Checking branches for timestamp-format IDs (these are already unique by nature)
- Automatically cleaning up orphaned branches
- Auto-fetching remote refs before checking
- Changes to the worktree creation flow
- Changes to the branch naming convention
