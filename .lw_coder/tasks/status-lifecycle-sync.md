---
plan_id: status-lifecycle-sync
git_sha: 5dbdbefd3098dcdc34134171f9a4d7b2ffcc1aed
status: done
evaluation_notes: []
---

# Objectives
- Set plan status to `coding` when `lw_coder code` starts executing.
- Set `git_sha` to the current repository HEAD commit when `lw_coder code` starts executing.
- Persist status `done` to the plan file when the host-based droid session exits cleanly.
- Leave status as `coding` if the command aborts or raises an error.

# Requirements & Constraints
- Update the original plan file's YAML front matter directly; no locking or backup needed.
- Handle only the `coding` ↔ `done` transitions; other statuses remain unchanged.
- Set `git_sha` to the current HEAD commit before worktree creation (worktrees are created from this SHA).
- The `plan` command should set `git_sha` to placeholder `0000000000000000000000000000000000000000`.
- Plan validator should accept the all-zeros placeholder for `draft` status only.
- The `code` command should overwrite placeholder git_sha; error if real SHA exists and differs from HEAD.
- Plan must remain valid under existing `PlanValidator` rules.

# Work Items
1. Create new module `plan_lifecycle.py` for plan mutation logic (separates concerns from validation).
2. In `plan_lifecycle.py`, implement `update_plan_fields(plan_path, updates)` that:
   - Reads plan file and parses YAML front matter
   - Updates specified fields in the front matter dict
   - Writes back with proper YAML formatting (following the pattern established in tests/conftest.py)
3. In `plan_lifecycle.py`, implement `get_current_head_sha(repo_root)` using git rev-parse HEAD.
4. Update `plan_validator.py` to accept all-zeros SHA (`0000000000000000000000000000000000000000`) for `draft` status only.
5. Update `plan_command.py` to set `git_sha` to all-zeros placeholder when creating plans.
6. In `code_command.py`, before loading metadata (line ~75 in `run_code_command`):
   - Get current HEAD SHA
   - Check existing git_sha in plan: if real SHA and differs from HEAD, error with helpful message
   - Update plan file: set `git_sha` to HEAD and `status` to `coding`
   - On failure: exit with code 1 (this is a critical operation)
7. In `code_command.py`, after successful session exit (line ~184-187 in `run_code_command`, when returncode == 0):
   - Update plan file: set `status` to `done`
   - On failure: log warning but preserve session exit code (not critical)
8. Add comprehensive tests covering all scenarios.

# Deliverables
- New `plan_lifecycle.py` module with plan mutation utilities.
- Updated `plan_validator.py` accepting all-zeros placeholder for draft status.
- Updated `plan_command.py` setting git_sha to all-zeros placeholder.
- Updated `code_command.py` with status and git_sha lifecycle management.
- Comprehensive test coverage as detailed in Test Scenarios section below.

# Out of Scope
- Introducing additional statuses such as `ready`, `review`, or `abandoned`.
- File locking, collision handling, or backups for plan files.
- Broader refactors of worktree preparation or validation logic.
- Try/finally pattern for status updates (simpler approach: direct updates on success only).

# Implementation Notes
- **Module design**: New `plan_lifecycle.py` separates mutation logic from validation concerns.
- **Placeholder approach**: All-zeros SHA allows draft plans to validate while clearly indicating "not yet set".
- **Error handling**: Initial git_sha/status update is critical (fail fast); final status=done is best-effort.
- **No try/finally**: Direct update on success is clearer and handles edge cases naturally (Ctrl+C, errors).
- **Timing**: Initial update before worktree creation; final update after session success, inside context managers.
- **Architecture note**: The codebase has shifted from Docker container execution to host-based droid sessions (via `subprocess.run()` in `run_code_command`). This simplifies the implementation—no Docker exit code forwarding needed; we directly check the subprocess `returncode` (line ~184-187). The logic remains the same: update status on successful exit (returncode == 0), leave status as `coding` on failure.

# Test Scenarios

## Unit Tests - plan_lifecycle.py

### test_update_plan_fields_basic
```gherkin
Given a plan file with front matter and body content
When I call update_plan_fields with {"status": "coding"}
Then the status field should be updated in the file
And the body content should remain unchanged
And the YAML formatting should be valid
```

### test_update_plan_fields_multiple_fields
```gherkin
Given a plan file with git_sha placeholder and status "draft"
When I call update_plan_fields with {"git_sha": "<real-sha>", "status": "coding"}
Then both fields should be updated in the file
And other fields should remain unchanged
```

### test_update_plan_fields_nonexistent_file
```gherkin
Given a path to a nonexistent file
When I call update_plan_fields
Then it should raise an appropriate error
```

### test_update_plan_fields_preserves_body_formatting
```gherkin
Given a plan file with complex markdown body (headers, lists, code blocks)
When I call update_plan_fields with any update
Then the body content should be byte-for-byte identical
```

### test_get_current_head_sha
```gherkin
Given a valid git repository
When I call get_current_head_sha(repo_root)
Then it should return a 40-character hex string
And it should match the output of "git rev-parse HEAD"
```

### test_get_current_head_sha_not_a_repo
```gherkin
Given a directory that is not a git repository
When I call get_current_head_sha
Then it should raise an appropriate error
```

## Unit Tests - plan_validator.py

### test_validate_git_sha_all_zeros_draft_status
```gherkin
Given a plan with git_sha all-zeros and status "draft"
When I call load_plan_metadata
Then validation should succeed
And metadata.git_sha should be the all-zeros string
```

### test_validate_git_sha_all_zeros_coding_status
```gherkin
Given a plan with git_sha all-zeros and status "coding"
When I call load_plan_metadata
Then validation should fail with error about invalid git_sha for non-draft status
```

### test_validate_git_sha_all_zeros_done_status
```gherkin
Given a plan with git_sha all-zeros and status "done"
When I call load_plan_metadata
Then validation should fail with error about invalid git_sha for non-draft status
```

### test_validate_git_sha_real_sha_any_status
```gherkin
Given a plan with a real 40-char hex git_sha and any status
When I call load_plan_metadata
Then validation should succeed (existing behavior preserved)
```

## Unit Tests - plan_command.py

### test_plan_command_sets_placeholder_git_sha
```gherkin
Given I run the plan command with valid inputs
When the plan file is created
Then the git_sha field should be set to all-zeros placeholder
And the status should be "draft"
```

## Integration Tests - code_command.py

### test_code_command_replaces_placeholder_git_sha
```gherkin
Given a plan file with git_sha all-zeros placeholder and status "draft"
And the repository HEAD is at commit <real-sha>
When I run the code command
Then the plan file git_sha should be updated to <real-sha>
And the status should be updated to "coding"
And this should happen before worktree creation
```

### test_code_command_status_done_on_success
```gherkin
Given a plan file with git_sha matching HEAD
And the code command starts successfully
When the droid session exits with code 0
Then the plan file status should be updated to "done"
And the git_sha should remain unchanged
```

### test_code_command_status_stays_coding_on_failure
```gherkin
Given a plan file with git_sha matching HEAD
And the code command starts successfully
When the droid session exits with code 1
Then the plan file status should remain "coding"
And the git_sha should remain unchanged
```

### test_code_command_error_when_sha_mismatch
```gherkin
Given a plan file with git_sha set to <commit-A>
And the repository HEAD is at <commit-B> (different from commit-A)
When I run the code command
Then it should fail with exit code 1
And the error message should explain the SHA mismatch
And suggest checking for uncommitted work or rebasing the plan
And the plan file should not be modified
```

### test_code_command_error_on_initial_update_failure
```gherkin
Given a plan file with placeholder git_sha
And the plan file becomes read-only (chmod 444)
When I run the code command
Then it should fail with exit code 1
And the error should indicate failure to update plan file
And no worktree should be created
```

### test_code_command_warning_on_final_update_failure
```gherkin
Given a plan file with git_sha matching HEAD
And the code command starts successfully
And the droid session exits with code 0
And the plan file is deleted/made read-only before status update
When attempting to update status to "done"
Then a warning should be logged
But the command should still return exit code 0
```

### test_code_command_interrupted_by_user
```gherkin
Given a plan file with git_sha matching HEAD
And the code command starts successfully
When the user presses Ctrl+C during droid session execution
Then the plan file status should remain "coding"
And the command should exit with code 130
```

### test_code_command_validation_failure_no_update
```gherkin
Given a plan file with invalid front matter
When I run the code command
Then validation should fail
And the plan file should not be modified at all
And the command should exit with code 1
```

### test_code_command_worktree_uses_updated_sha
```gherkin
Given a plan file with placeholder git_sha
And the repository HEAD is at <commit-sha>
When I run the code command
Then the plan git_sha should be updated to <commit-sha>
And the worktree should be created from <commit-sha>
And the worktree branch should point to <commit-sha>
```

### test_code_command_real_sha_matches_head_no_error
```gherkin
Given a plan file with git_sha set to <commit-sha>
And the repository HEAD is also at <commit-sha>
When I run the code command
Then it should proceed without error
And the git_sha should remain <commit-sha>
And status should be updated to "coding"
```

## Test Files
- `tests/test_plan_lifecycle.py` - New file for plan_lifecycle module tests
- `tests/test_plan_validator.py` - Add all-zeros placeholder tests
- `tests/test_plan_command.py` - Add placeholder git_sha tests
- `tests/test_code_command.py` - Add lifecycle and error handling tests
