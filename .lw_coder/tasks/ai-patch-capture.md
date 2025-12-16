---
plan_id: ai-patch-capture
status: done
evaluation_notes: []
git_sha: 07d84397b9c6eaa115676e0febdcf1cf447df43d
---

# AI-Only Patch Capture for Eval

## Objectives

Capture AI-only changes as a git patch after the headless SDK session completes, before the interactive CLI resume. This enables the eval command to create a clean "after" worktree that isolates the AI's autonomous work from any subsequent human edits during the interactive session.

### Goals
1. Generate a git patch containing all changes made by the AI during the headless SDK session
2. Store the patch in the session directory for eval to consume
3. Modify eval to use the patch (applied to a temp worktree) for "after" tests instead of the plan worktree
4. Include the patch in training data exports for DSPy optimization

### Motivation
Currently, eval runs "after" tests on the plan worktree, which may include changes made during the interactive CLI session. This conflates AI-autonomous work with human intervention, making it difficult to evaluate the AI's independent coding ability. By capturing a patch at the SDK session boundary, we can precisely measure what the AI accomplished on its own.

## Requirements & Constraints

### Functional Requirements
1. **Patch Generation**: After the headless SDK session completes, capture all changes (new files, modifications, deletions) as a unified diff
2. **Patch Storage**: Save the patch to `.lw_coder/sessions/<plan_id>/code/ai_changes.patch`
3. **Empty Patch Handling**: If the AI made no changes (empty patch), fail the code command with a clear error message
4. **Worktree State Preservation**: After capturing the patch, restore the worktree to its pre-capture state (unstaged changes) so the interactive CLI session starts cleanly
5. **Patch Application**: During eval, create a temporary worktree at `git_sha`, apply the patch, and run "after" tests there
6. **Patch Application Failure**: If the patch fails to apply during eval, fail the entire eval command
7. **Training Data Export**: Copy the patch file to `.lw_coder/training_data/<plan_id>/` alongside other artifacts
8. **Cleanup**: Remove temporary worktrees after eval completes, even on failure

### Technical Constraints
1. Git commands are blocked during SDK session (existing behavior), so patch capture happens after SDK completes
2. Patch format: standard unified diff from `git diff --cached` (after staging with `git add -A`)
3. Git operations (`git add -A`, `git reset`) must be wrapped in try/finally to ensure worktree state is always restored
4. Temporary worktrees should follow existing naming pattern: `.lw_coder/worktrees/temp-<timestamp>-<hash>/`

### Non-Functional Requirements
1. Patch capture should add minimal latency to the code command (git operations are fast)
2. Error messages should be actionable (e.g., "SDK session produced no changes")

## Work Items

### 1. Create `patch_utils.py` Module

Create a new module `src/lw_coder/patch_utils.py` with the following components:

**Exceptions:**
- `PatchError(Exception)` - Base exception for patch operations
- `PatchCaptureError(PatchError)` - Raised when patch capture fails
- `EmptyPatchError(PatchError)` - Raised when SDK produces no changes
- `PatchApplicationError(PatchError)` - Raised when patch fails to apply

**Functions:**
- `capture_ai_patch(worktree_path: Path) -> str` - Captures all changes as a patch
  - Run `git add -A` to stage all changes (including new files)
  - Run `git diff --cached` to generate the patch
  - Run `git reset` to unstage (in finally block)
  - Raise `EmptyPatchError` if patch is empty
  - Raise `PatchCaptureError` on git command failures
  - Return the patch content as a string

- `save_patch(patch_content: str, output_path: Path) -> Path` - Saves patch to file
  - Write patch content to the specified path
  - Return the path for logging

- `apply_patch(patch_path: Path, worktree_path: Path) -> None` - Applies patch to worktree
  - Run `git apply <patch_path>` in the worktree
  - Raise `PatchApplicationError` on failure (conflicts, malformed patch, etc.)

### 2. Modify `code_command.py` for Patch Capture

**Location:** After SDK session completes (~line 463), before CLI resume command is built (~line 480)

**Changes:**
1. Import `capture_ai_patch`, `save_patch`, `EmptyPatchError`, `PatchCaptureError` from `patch_utils`
2. After `run_sdk_session_sync()` returns successfully:
   ```python
   # Capture AI changes as patch
   try:
       patch_content = capture_ai_patch(worktree_path)
       patch_path = session_dir / "ai_changes.patch"
       save_patch(patch_content, patch_path)
       logger.info("AI changes captured to: %s", patch_path)
   except EmptyPatchError:
       logger.error("SDK session produced no changes. Cannot proceed without AI modifications.")
       return 1
   except PatchCaptureError as exc:
       logger.error("Failed to capture AI changes: %s", exc)
       return 1
   ```
3. Move the `code_sdk_complete` hook trigger to after patch capture (so hook has access to patch file)

### 3. Modify `eval_command.py` for Patch-Based After Tests

**Changes to `run_after_tests()` or equivalent section (~lines 344-368):**

1. Import `apply_patch`, `PatchApplicationError` from `patch_utils`
2. Import temp worktree utilities from `worktree_utils`
3. Read patch file path: `session_dir / "code" / "ai_changes.patch"`
4. Validate patch file exists, fail with actionable error if missing
5. Create temporary worktree at `git_sha`:
   ```python
   temp_worktree = create_temp_worktree(repo_root, metadata.git_sha)
   ```
6. Apply patch to temp worktree:
   ```python
   try:
       apply_patch(patch_path, temp_worktree)
   except PatchApplicationError as exc:
       logger.error("Failed to apply AI patch: %s", exc)
       # Clean up temp worktree
       return 1
   ```
7. Run after-tests on `temp_worktree` instead of plan worktree
8. Clean up temp worktree in finally block (even on test failure)

**Changes to training data export (~lines 412-449):**

1. Add `ai_changes.patch` to the list of files copied to training data directory
2. Copy from `.lw_coder/sessions/<plan_id>/code/ai_changes.patch` to `.lw_coder/training_data/<plan_id>/ai_changes.patch`

### 4. Add/Update Worktree Utilities

**In `worktree_utils.py`:**

If not already present, add or expose:
- `create_temp_worktree(repo_root: Path, git_sha: str) -> Path` - Creates a temporary worktree at the specified commit
- `remove_temp_worktree(repo_root: Path, worktree_path: Path) -> None` - Removes a temporary worktree

These may already exist for the "before tests" functionality - reuse if available.

### 5. Update Existing Tests

Review and update any existing tests in `test_code_command.py` and `test_eval_command.py` that mock the SDK session or eval flow to account for the new patch capture step.

## Deliverables

### New Files
- `src/lw_coder/patch_utils.py` - Patch capture, save, and apply utilities
- `tests/unit/test_patch_utils.py` - Unit tests for patch utilities

### Modified Files
- `src/lw_coder/code_command.py` - Add patch capture after SDK session
- `src/lw_coder/eval_command.py` - Use patch-based temp worktree for after-tests, copy patch to training data
- `src/lw_coder/worktree_utils.py` - Add/expose temp worktree utilities if needed
- `tests/unit/test_code_command.py` - Add tests for patch capture integration
- `tests/unit/test_eval_command.py` - Add tests for patch application integration

### Artifacts Generated at Runtime
- `.lw_coder/sessions/<plan_id>/code/ai_changes.patch` - Patch file (created by code command)
- `.lw_coder/training_data/<plan_id>/ai_changes.patch` - Patch file copy (created by eval command)
- `.lw_coder/worktrees/temp-<timestamp>-<hash>/` - Temporary worktree (created and cleaned up by eval)

## Unit Tests

### `tests/unit/test_patch_utils.py` (New File)

**Test: `test_capture_ai_patch_all_change_types`**
- Create a single git repo with:
  - A new untracked file
  - A modified tracked file
  - A deleted tracked file
- Call `capture_ai_patch()`
- Verify patch contains all three change types (new file marker, diff hunks, deletion marker)
- Verify worktree has no staged changes after capture (git reset worked)

**Test: `test_capture_ai_patch_empty_raises_error`**
- Create a git repo with no changes
- Call `capture_ai_patch()`
- Verify `EmptyPatchError` is raised

**Test: `test_capture_ai_patch_restores_state_on_error`**
- Create a git repo with changes, mock `git diff --cached` to fail
- Call `capture_ai_patch()`
- Verify `git reset` was still called (no staged changes remain)
- Verify `PatchCaptureError` is raised

**Test: `test_apply_patch_success_and_failure`**
- Create a git repo, generate a valid patch from changes
- Apply patch to a clean worktree at the same base commit - verify success
- Create a conflicting state (modify same lines), attempt apply - verify `PatchApplicationError`

### `tests/unit/test_code_command.py` (Additions)

Note: These tests call `run_code_command()` with mocked SDK session and mocked subprocess.run (for CLI resume) to avoid interactive behavior.

**Test: `test_code_command_patch_capture_workflow`**
- Mock `run_sdk_session_sync` to succeed and simulate file changes in worktree
- Mock `subprocess.run` to skip CLI resume
- Call `run_code_command()`
- Verify `ai_changes.patch` exists in session directory with expected content
- Verify worktree has no staged changes (state restored)
- Verify `code_sdk_complete` hook is called after patch is saved

**Test: `test_code_command_fails_on_empty_patch`**
- Mock `run_sdk_session_sync` to succeed but make no changes in worktree
- Call `run_code_command()`
- Verify command returns exit code 1
- Verify error log mentions "no changes"

### `tests/unit/test_eval_command.py` (Additions)

Note: These tests call the underlying functions (e.g., `run_after_tests()`, `create_training_data()`), not the interactive `run_eval_command()` which includes human feedback collection.

**Test: `test_after_tests_uses_patch_based_worktree`**
- Create git repo, session directory with valid patch file, and plan metadata
- Call the after-tests function directly (mock the test runner SDK call)
- Verify temp worktree was created at `git_sha`
- Verify patch was applied to temp worktree
- Verify test runner was invoked with temp worktree path (not plan worktree)
- Verify temp worktree cleaned up after completion

**Test: `test_after_tests_fails_when_patch_missing`**
- Create session directory without `ai_changes.patch`
- Call the after-tests function
- Verify it raises an appropriate error with actionable message

**Test: `test_after_tests_fails_when_patch_conflicts`**
- Create session with patch that won't apply cleanly to `git_sha`
- Call the after-tests function
- Verify it raises an error about patch application
- Verify temp worktree is still cleaned up

**Test: `test_training_data_includes_patch`**
- Create session with valid patch file and other eval artifacts
- Call the training data export function
- Verify `ai_changes.patch` copied to training data directory

## Integration Tests

No integration tests are recommended for this feature. The behavior is fully testable with:
- Real git operations (not mocked)
- Mocked SDK calls (to avoid API costs)
- Mocked test runner (to avoid running actual tests)

Integration tests would add significant cost (real API calls) with minimal additional coverage beyond the unit tests.

## Out of Scope

The following are explicitly excluded from this plan:

1. **Binary file support** - Standard `git diff` limitations apply; binary files will show as "Binary files differ" in the patch
2. **Submodule changes** - Git patches don't capture submodule state changes
3. **Patch compression** - Patches are stored as plain text; compression could be added later if storage becomes a concern
4. **Multiple patch files** - Only one patch per code session; incremental patches are not supported
5. **Patch viewer/UI** - No CLI command to view or inspect patches; users can read the patch file directly
6. **Configurable empty patch behavior** - Empty patch always fails; no config.toml option to make it a warning
7. **Configurable patch application failure behavior** - Patch application failure always fails eval; no fallback to plan worktree
8. **ADR documentation** - While the maintainability reviewer suggested an ADR, it is not included in this plan's scope
