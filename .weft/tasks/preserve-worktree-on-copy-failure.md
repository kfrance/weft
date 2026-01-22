---
plan_id: preserve-worktree-on-copy-failure
status: done
evaluation_notes: []
git_sha: d1036ff51939b08ecae86dc596c549ff67e2db5d
---

# Preserve Worktree When Plan File Copy Fails

**Linear Issue**: LW-98

## Objectives

Prevent loss of work when the plan command fails to copy plan files from the worktree to the main repository. When copy fails, preserve the worktree so users can manually recover their plan files.

## Requirements & Constraints

### Functional Requirements

1. **Preserve worktree on copy failure**: If `copy_plan_files` raises `PlanFileCopyError` OR any individual file fails to copy, the worktree must NOT be removed.

2. **Preserve worktree when no files copied**: If `copy_plan_files` returns an empty `file_mapping` (no new files found), preserve the worktree.

3. **Log at ERROR level**: When copy fails or no files are copied, log at ERROR level (not WARNING) to indicate significant failure.

4. **Print worktree path to console**: Display the preserved worktree path prominently so users can manually recover files. Include context about what was expected but missing.

5. **KeyboardInterrupt unchanged**: User interrupt should exit cleanly and clean up the worktree normally (no preservation).

6. **Detect partial copy failures**: Compare the number of new files found to the number successfully copied to detect when some files failed.

### Constraints

- Exit code remains 0 for successful Claude execution even when copy fails (copy is post-processing)
- File watcher and prompt file cleanup should still occur even when worktree is preserved
- Must not break existing tests

## Work Items

### 1. Modify `copy_plan_files` Return Type

**File**: `src/weft/plan_file_copier.py`

Update `copy_plan_files` to return information about files found vs files copied:

```python
@dataclass
class CopyResult:
    """Result of copying plan files from worktree."""
    file_mapping: Dict[str, str]  # original -> final filename
    files_found: int              # number of new files detected
    files_failed: List[str]       # filenames that failed to copy
```

Update the function to:
- Track files that fail to copy (currently just logged as warnings)
- Return the `CopyResult` dataclass instead of just `Dict[str, str]`

### 2. Update Plan Command Cleanup Logic

**File**: `src/weft/plan_command.py`

Add tracking and conditional cleanup:

1. Add boolean flag `should_cleanup_worktree = True` before the try block
2. After `copy_plan_files` call, check the `CopyResult`:
   - If `files_found == 0`: set `should_cleanup_worktree = False`, log ERROR about no files found
   - If `files_failed` is non-empty: set `should_cleanup_worktree = False`, log ERROR about failed copies
   - If `file_mapping` is empty but `files_found > 0`: set `should_cleanup_worktree = False`
3. If `PlanFileCopyError` is raised: set `should_cleanup_worktree = False`, log ERROR
4. When `should_cleanup_worktree = False`, print worktree path to console with guidance
5. In finally block, only call `remove_temp_worktree` if `should_cleanup_worktree is True`

### 3. Define Error Messages

**File**: `src/weft/plan_command.py`

Add module-level constants for consistent messaging:

```python
WORKTREE_PRESERVED_NO_FILES = (
    "No new plan files found in worktree .weft/tasks/. "
    "Worktree preserved at: {worktree_path}"
)

WORKTREE_PRESERVED_COPY_FAILED = (
    "Failed to copy plan files from worktree. "
    "Worktree preserved at: {worktree_path}"
)

WORKTREE_PRESERVED_PARTIAL_FAILURE = (
    "Some plan files failed to copy ({failed_count} of {total_count}). "
    "Worktree preserved at: {worktree_path}"
)
```

### 4. Unit Tests

**File**: `tests/unit/test_plan_command.py`

Add new tests (separate from existing tests per Option B):

| Test Name | Description |
|-----------|-------------|
| `test_worktree_preserved_when_copy_raises_error` | Verify `remove_temp_worktree` NOT called when `PlanFileCopyError` raised |
| `test_worktree_preserved_when_no_files_found` | Verify preservation when `files_found == 0` |
| `test_worktree_preserved_on_partial_copy_failure` | Verify preservation when `files_failed` is non-empty |
| `test_worktree_removed_on_successful_copy` | Verify normal cleanup when all files copied |
| `test_error_logged_with_worktree_path` | Verify ERROR level log includes absolute worktree path |
| `test_console_output_shows_worktree_path` | Verify console output includes full absolute path using `capsys` |

**File**: `tests/unit/test_plan_file_copier.py`

Add tests for new `CopyResult` return type:

| Test Name | Description |
|-----------|-------------|
| `test_copy_result_tracks_files_found` | Verify `files_found` count matches new files detected |
| `test_copy_result_tracks_failed_files` | Verify `files_failed` populated when individual copies fail |
| `test_copy_result_empty_when_no_new_files` | Verify `files_found == 0` when no new files exist |

### 5. Integration Tests

The following existing integration test must pass:

- `tests/integration/test_command_smoke.py::TestPlanCommandSmoke::test_plan_command_setup_completes`

No new integration tests required - the changes are in cleanup logic that's difficult to test end-to-end without mocking.

## Deliverables

1. Modified `src/weft/plan_file_copier.py` with `CopyResult` dataclass and updated return type
2. Modified `src/weft/plan_command.py` with conditional worktree cleanup logic
3. New unit tests in `tests/unit/test_plan_command.py` for worktree preservation
4. New unit tests in `tests/unit/test_plan_file_copier.py` for `CopyResult`

## Out of Scope

- Recovery command (e.g., `weft plan recover <worktree-path>`) - future enhancement
- Tracking preserved worktrees in a registry - future enhancement
- Automatic cleanup of old preserved worktrees - future enhancement
- Changes to the code command's worktree handling (different use case)
