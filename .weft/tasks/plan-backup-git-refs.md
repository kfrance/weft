---
plan_id: plan-backup-git-refs
status: done
git_sha: e0485693df6d8adeafda17ba564fab7ba2d38215
evaluation_notes: []
---

# Plan File Backup via Git Orphan Branch References

## Objectives

Implement automatic backup of plan files to git orphan branch references, providing a durable recovery mechanism for uncommitted plans while preserving the existing "plan + implementation in one commit" workflow pattern.

**Key Goals:**
1. Automatically backup plan files when created/modified during the `plan` command
2. Store backups as git orphan commits referenced at `refs/plan-backups/<plan_id>`
3. Automatically cleanup backup references when plans are finalized (merged to main)
4. Provide `recover-plan` command to list and restore backed-up plans
5. Integrate tab completion for easy discovery of backed-up plans
6. Maintain invisible operation with no workflow changes for users

## Requirements & Constraints

### Functional Requirements

1. **Backup Creation**
   - Trigger backup at end of `plan` command, after `plan_file_copier.py` copies files to `.lw_coder/tasks/`
   - Create orphan commit containing single file: `.lw_coder/tasks/<plan_id>.md`
   - Store reference at `refs/plan-backups/<plan_id>`
   - Commit message format: `Backup of plan: <plan_id>`
   - Force-update ref on subsequent backups (no history preservation)
   - If backup creation fails, command exits with non-zero exit code

2. **Backup Cleanup**
   - Trigger cleanup in `finalize_command.py` after successful merge to main
   - Delete backup reference at `refs/plan-backups/<plan_id>`
   - Cleanup must be idempotent (safe to call if ref doesn't exist)
   - Log warning but don't fail finalize if cleanup fails

3. **Recovery Command**
   - Command: `lw_coder recover-plan [<plan_id>]`
   - Without plan_id: List all backed-up plans with timestamps and existence status
   - With plan_id: Restore plan file to `.lw_coder/tasks/<plan_id>.md`
   - If target file exists: Fail with error requiring `--force` flag to overwrite
   - If no backup found: Display clear error message
   - Strip status suffix from tab completion input (e.g., `plan-id (exists)` → `plan-id`)

4. **Tab Completion**
   - `lw_coder recover-plan <TAB>` shows all backup refs
   - Format: `<plan_id> (exists)` for plans with existing files
   - Format: `<plan_id> (missing)` for plans without existing files
   - New completer function in `completion/completers.py`
   - Cache backup ref list with TTL for performance

### Technical Constraints

1. **Git Operations**
   - Use low-level git commands: `hash-object`, `mktree`, `commit-tree`, `update-ref`
   - Follow existing subprocess error handling patterns
   - All operations must work with existing worktree-based workflow

2. **Code Reuse Requirements**
   - **Must use** `find_repo_root()` from `repo_utils.py` before git operations
   - **Must use** `extract_front_matter()` / `load_plan_id()` from `plan_validator.py` for reading plan files
   - **Must use** `PlanResolver.resolve()` from `plan_resolver.py` for user input handling
   - **Must follow** subprocess error handling pattern from existing git operations
   - **Must follow** command structure pattern from `finalize_command.py`
   - **Must follow** custom exception pattern (create `PlanBackupError`)
   - **Must use** test fixtures (`git_repo`, `write_plan`) from `conftest.py`

3. **Integration Points**
   - Hook into `plan_command.py` after plan file copying
   - Hook into `finalize_command.py` after successful merge
   - Register new subcommand in `cli.py`
   - Add completer to `completion/completers.py`

4. **Security & Safety**
   - Trust existing plan_id validation (no re-validation needed)
   - Follow path traversal validation patterns from `worktree_utils.py`
   - Proper error messages with recovery instructions

### Non-Functional Requirements

1. **Invisibility**: Backup operations must not change existing user workflows
2. **Durability**: Backup refs persist until explicitly deleted (no time limits)
3. **Performance**: Tab completion caching to avoid repeated git operations
4. **Maintainability**: Clear separation of concerns with dedicated `plan_backup.py` module

## Work Items

### 1. Create Core Backup Module (`src/lw_coder/plan_backup.py`)

**Tasks:**
- Create `PlanBackupError` exception class hierarchy
- Implement `create_backup(repo_root: Path, plan_id: str) -> None`
  - Read plan file content using `load_plan_id()` from plan_validator.py
  - Create orphan commit using `git hash-object`, `git mktree`, `git commit-tree`
  - Force-update ref at `refs/plan-backups/<plan_id>` using `git update-ref`
  - Follow subprocess error handling pattern from existing code
  - Raise `PlanBackupError` with clear message on failure
- Implement `cleanup_backup(repo_root: Path, plan_id: str) -> None`
  - Delete ref using `git update-ref -d refs/plan-backups/<plan_id>`
  - Log warning but don't raise if ref doesn't exist (idempotent)
  - Follow subprocess error handling pattern
- Implement `list_backups(repo_root: Path) -> list[tuple[str, int, bool]]`
  - Use `git for-each-ref refs/plan-backups/` to list all refs
  - Extract plan_id from each ref name
  - Get commit timestamp for each ref
  - Check if `.lw_coder/tasks/<plan_id>.md` exists
  - Return list of (plan_id, timestamp, file_exists) tuples sorted by plan_id
- Implement `recover_backup(repo_root: Path, plan_id: str, force: bool = False) -> Path`
  - Verify backup ref exists, raise `PlanBackupError` if not
  - Use `git show refs/plan-backups/<plan_id>:.lw_coder/tasks/<plan_id>.md` to get content
  - Check if target file exists, raise `BackupExistsError` if exists and not force
  - Write content to `.lw_coder/tasks/<plan_id>.md`
  - Return path to recovered file
- Add comprehensive docstrings explaining lifecycle and edge cases
- Add module-level docstring explaining architecture

**Reuse:**
- `find_repo_root()` from repo_utils.py
- `load_plan_id()` from plan_validator.py
- Subprocess error handling pattern from existing git operations
- Custom exception pattern from existing modules

### 2. Integrate Backup Creation into Plan Command

**Tasks:**
- Modify `plan_command.py` to call `create_backup()` after plan file copying
- Add import for `plan_backup` module
- Call `create_backup(repo_root, plan_id)` after `plan_file_copier.copy_plan_files()`
- Let `PlanBackupError` propagate (command exits with non-zero code)
- Add logging to indicate backup creation success/failure

**Files Modified:**
- `src/lw_coder/plan_command.py`

### 3. Integrate Backup Cleanup into Finalize Command

**Tasks:**
- Modify `finalize_command.py` to call `cleanup_backup()` after successful merge
- Add import for `plan_backup` module
- Call `cleanup_backup(repo_root, plan_id)` after merge verification
- Catch and log any cleanup failures but don't fail finalize command
- Add logging to indicate cleanup success

**Files Modified:**
- `src/lw_coder/finalize_command.py`

### 4. Implement Recovery Command

**Tasks:**
- Create `src/lw_coder/recover_command.py`
- Implement `run_recover_command(plan_id: str | None, force: bool = False) -> None`
  - If plan_id is None: call `list_backups()` and display formatted list
  - If plan_id provided:
    - Strip status suffix if present (e.g., `plan-id (exists)` → `plan-id`)
    - Use `PlanResolver.resolve()` to handle plan_id/path input
    - Call `recover_backup(repo_root, plan_id, force)`
    - Display success message with recovered file path
  - Handle `PlanBackupError` and `BackupExistsError` with user-friendly messages
- Follow command structure pattern from `finalize_command.py`
- Include validation phase, execution phase, and proper error handling
- Add comprehensive logging

**Reuse:**
- `find_repo_root()` from repo_utils.py
- `PlanResolver.resolve()` from plan_resolver.py
- Command structure pattern from finalize_command.py

### 5. Register Recovery Command in CLI

**Tasks:**
- Modify `cli.py` to add `recover-plan` subcommand
- Add parser for recover-plan with:
  - Optional positional argument: `plan_id`
  - Optional flag: `--force` (action='store_true')
- Wire up completer: `parser.completer = complete_backup_plans`
- Call `run_recover_command()` from recover_command.py
- Follow subcommand registration pattern from existing commands

**Files Modified:**
- `src/lw_coder/cli.py`

### 6. Implement Tab Completion for Recovery

**Tasks:**
- Add `complete_backup_plans(prefix, parsed_args, **kwargs) -> list[str]` to `completion/completers.py`
- Use `list_backups()` from plan_backup module
- Format results as `<plan_id> (exists)` or `<plan_id> (missing)`
- Return only items matching prefix
- Handle errors gracefully (return empty list on failure)
- Follow completer pattern from `complete_plan_files()`
- Consider caching with TTL (60 seconds) using pattern from `completion/cache.py`

**Files Modified:**
- `src/lw_coder/completion/completers.py`

**Optional Enhancement:**
- Extend `PlanCompletionCache` in `completion/cache.py` to cache backup refs

### 7. Update Documentation

**Tasks:**
- Add "Recover Plan Command" section to README.md after "Code Command" section
- Document command usage: `lw_coder recover-plan [<plan_id>]`
- Include examples:
  - Listing all backups: `lw_coder recover-plan`
  - Recovering a specific plan: `lw_coder recover-plan my-feature`
  - Force overwrite: `lw_coder recover-plan my-feature --force`
- Explain what backups are and when they're created
- Explain when backups are automatically cleaned up
- Include tab completion tip

**Files Modified:**
- `README.md`

### 8. Comprehensive Testing

**Tasks:**
- Create `tests/test_plan_backup.py` with:
  - Test `create_backup()` creates orphan commit and ref
  - Test `create_backup()` force-updates on subsequent calls
  - Test `cleanup_backup()` deletes ref
  - Test `cleanup_backup()` is idempotent (safe when ref missing)
  - Test `list_backups()` returns correct data
  - Test `recover_backup()` restores file content correctly
  - Test `recover_backup()` fails when file exists without force
  - Test `recover_backup()` succeeds with force flag
  - Test `recover_backup()` raises error when ref doesn't exist
  - Use `git_repo` fixture from conftest.py for isolated git repos
  - Use `write_plan()` helper from conftest.py for test plan files
- Create `tests/test_recover_command.py` with:
  - Test listing backups displays correct format
  - Test recovery with valid plan_id
  - Test recovery strips status suffix from input
  - Test --force flag behavior
  - Test error handling for missing backups
- Update `tests/test_plan_command.py`:
  - Test backup creation is called after plan creation
  - Test plan command fails if backup creation fails
- Update `tests/test_finalize_command.py`:
  - Test cleanup is called after successful finalize
  - Test finalize succeeds even if cleanup fails
- Create `tests/completion/test_backup_completers.py`:
  - Test `complete_backup_plans()` returns correct format
  - Test status indicators (exists/missing)
  - Test prefix filtering

**Testing Best Practices (from docs/BEST_PRACTICES.md):**
- Use `pytest.fail()` for missing dependencies, not `pytest.skip()`
- Avoid mocking git operations - use real git in isolated repos
- Use parametrization for similar test cases
- Write descriptive test names
- Keep tests in default run (no skip markers)

## Deliverables

1. **New Module**: `src/lw_coder/plan_backup.py`
   - `PlanBackupError` exception class
   - `create_backup()` function
   - `cleanup_backup()` function
   - `list_backups()` function
   - `recover_backup()` function
   - Comprehensive docstrings

2. **New Module**: `src/lw_coder/recover_command.py`
   - `run_recover_command()` function
   - Error handling and user-friendly messages

3. **Modified Files**:
   - `src/lw_coder/plan_command.py` - integrate backup creation
   - `src/lw_coder/finalize_command.py` - integrate backup cleanup
   - `src/lw_coder/cli.py` - register recover-plan subcommand
   - `src/lw_coder/completion/completers.py` - add backup completer
   - `README.md` - document recover-plan command

4. **Test Files**:
   - `tests/test_plan_backup.py` - comprehensive backup module tests
   - `tests/test_recover_command.py` - recovery command tests
   - `tests/completion/test_backup_completers.py` - tab completion tests
   - Updates to `tests/test_plan_command.py`
   - Updates to `tests/test_finalize_command.py`

5. **Documentation**:
   - README.md section for recover-plan command with usage examples

## Out of Scope

The following items are explicitly excluded from this plan:

1. **Re-validating plan_id format in backup module** - Plan IDs are already validated by `plan_validator.py` before backup creation, making additional validation redundant

2. **Backup history preservation** - Only the latest backup is kept per plan; force-updating refs destroys previous backup versions

3. **Automatic garbage collection of orphaned refs** - Backup refs persist forever until explicitly deleted; no time-based or automated cleanup beyond finalize

4. **Manual cleanup utility** - No separate command or flag for cleaning up orphaned refs (e.g., when cleanup fails during finalize)

5. **Ref namespace versioning** - Using `refs/plan-backups/<plan_id>` directly without version prefix (e.g., `refs/plan-backups/v1/<plan_id>`)

6. **Backup metadata storage** - No separate index file (e.g., `.lw_coder/backups.json`) tracking backup state; relying solely on git refs

7. **Backup compression** - Plan files stored as-is in git objects without additional compression

8. **Architecture documentation file** - No separate `docs/BACKUP_ARCHITECTURE.md`; documentation lives in README.md and inline code comments

9. **Backup retry mechanism** - No automatic retry if backup creation fails; user must retry entire plan command

10. **Interactive recovery prompts** - No confirmation dialogs or diff display before overwrite; use --force flag explicitly

11. **Cross-repository backup sync** - Backups are local to each repository

## Test Cases

### Feature: Plan File Backup Creation

```gherkin
Scenario: Backup created after successful plan creation
  Given a git repository with lw_coder initialized
  And I create a plan file using "lw_coder plan --text 'test feature'"
  When the plan command completes successfully
  Then a backup ref should exist at "refs/plan-backups/<plan_id>"
  And the backup commit should contain the plan file
  And the commit message should be "Backup of plan: <plan_id>"

Scenario: Backup force-updates on subsequent plan edits
  Given a plan file with an existing backup ref
  When I edit the plan using "lw_coder plan <plan_id>"
  And the plan command completes successfully
  Then the backup ref should point to a new commit
  And the new commit should contain the updated plan content
  And the old backup commit should be unreachable

Scenario: Plan command fails if backup creation fails
  Given a git repository with lw_coder initialized
  And git operations will fail due to corrupted repo
  When I create a plan using "lw_coder plan --text 'test feature'"
  Then the plan command should exit with non-zero code
  And an error message should indicate backup failure
```

### Feature: Backup Cleanup on Finalization

```gherkin
Scenario: Backup ref deleted after successful finalize
  Given a plan with status "implemented" and an existing backup ref
  When I run "lw_coder finalize <plan_id>"
  And the finalize command successfully merges to main
  Then the backup ref at "refs/plan-backups/<plan_id>" should be deleted
  And the plan status should be "done"

Scenario: Finalize succeeds even if cleanup fails
  Given a plan with status "implemented" and an existing backup ref
  And git ref deletion will fail
  When I run "lw_coder finalize <plan_id>"
  Then the finalize command should succeed
  And the plan should be merged to main
  And a warning should be logged about cleanup failure
  And the backup ref should still exist

Scenario: Cleanup is idempotent when ref already deleted
  Given a plan with status "implemented"
  And no backup ref exists at "refs/plan-backups/<plan_id>"
  When I run "lw_coder finalize <plan_id>"
  Then the finalize command should succeed
  And no errors should be raised about missing ref
```

### Feature: Plan Recovery

```gherkin
Scenario: List all backed-up plans
  Given multiple plan backup refs exist
  And some plan files exist and others are missing
  When I run "lw_coder recover-plan"
  Then I should see a list of all backed-up plans
  And each entry should show plan_id, timestamp, and existence status
  And the list should be sorted by plan_id

Scenario: Recover plan file successfully
  Given a backup ref exists for "my-feature"
  And the plan file does not exist at ".lw_coder/tasks/my-feature.md"
  When I run "lw_coder recover-plan my-feature"
  Then the plan file should be restored to ".lw_coder/tasks/my-feature.md"
  And the content should match the backup
  And a success message should be displayed

Scenario: Recovery fails when file already exists
  Given a backup ref exists for "my-feature"
  And the plan file already exists at ".lw_coder/tasks/my-feature.md"
  When I run "lw_coder recover-plan my-feature"
  Then the command should fail with non-zero exit code
  And an error message should indicate file exists
  And the error should suggest using "--force" flag
  And the existing file should remain unchanged

Scenario: Recovery with force flag overwrites existing file
  Given a backup ref exists for "my-feature"
  And the plan file already exists with different content
  When I run "lw_coder recover-plan my-feature --force"
  Then the existing file should be overwritten
  And the content should match the backup
  And a success message should be displayed

Scenario: Recovery fails when backup ref doesn't exist
  Given no backup ref exists for "nonexistent-plan"
  When I run "lw_coder recover-plan nonexistent-plan"
  Then the command should fail with non-zero exit code
  And a clear error message should indicate no backup found

Scenario: Recovery strips status suffix from tab completion
  Given a backup ref exists for "my-feature"
  When tab completion provides "my-feature (exists)"
  And I select that option
  Then the command should receive "my-feature (exists)"
  And should strip the suffix to recover "my-feature"
  And the plan file should be restored successfully
```

### Feature: Tab Completion for Recovery

```gherkin
Scenario: Tab completion lists backup refs with status
  Given backup refs exist for "feature-a" and "feature-b"
  And "feature-a" plan file exists
  And "feature-b" plan file is missing
  When I press TAB after "lw_coder recover-plan "
  Then I should see "feature-a (exists)"
  And I should see "feature-b (missing)"

Scenario: Tab completion filters by prefix
  Given backup refs exist for "feature-a", "feature-b", and "bugfix-c"
  When I press TAB after "lw_coder recover-plan feature"
  Then I should see "feature-a (exists)"
  And I should see "feature-b (missing)"
  And I should not see "bugfix-c"

Scenario: Tab completion handles empty backup list
  Given no backup refs exist
  When I press TAB after "lw_coder recover-plan "
  Then I should see no completions
  And no errors should be raised

Scenario: Tab completion handles git errors gracefully
  Given git operations will fail
  When I press TAB after "lw_coder recover-plan "
  Then I should see no completions
  And no errors should be displayed to the user
```

### Feature: Integration with Existing Workflow

```gherkin
Scenario: Complete workflow from plan to finalize with backup
  Given a git repository with lw_coder initialized
  When I create a plan using "lw_coder plan --text 'new feature'"
  Then a backup ref should exist
  When I implement the plan using "lw_coder code <plan_id>"
  Then the backup ref should still exist
  When I finalize using "lw_coder finalize <plan_id>"
  And the plan is merged to main
  Then the backup ref should be deleted
  And the plan should be in git history on main branch

Scenario: Plan recovery after accidental deletion
  Given I created a plan and have a backup ref
  When I accidentally delete ".lw_coder/tasks/<plan_id>.md"
  And I run "lw_coder recover-plan <plan_id>"
  Then the plan file should be restored
  And I can continue with "lw_coder code <plan_id>"
```
