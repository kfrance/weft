---
plan_id: rename-to-weft
status: done
evaluation_notes: []
git_sha: 8b0d51f40cc94dae5ea16b28c22195b97ff9bf0e
---

# Rename lw_coder to Weft

## Objectives

Complete rebrand from "lw_coder" to "weft" across the entire codebase, including package name, Python module, CLI command, directory structures, and all references. Implement automatic migration for repository directories while preserving historical data integrity.

**Key Goals:**
- Rename PyPI package from `lw-coder` to `weft`
- Rename Python module from `src/lw_coder/` to `src/weft/`
- Rename CLI command from `lw_coder` to `weft`
- Implement automatic `.lw_coder/` → `.weft/` migration in repositories
- Update all forward-facing references (code, docs, tests)
- Preserve historical data as-is
- Maintain full functionality through the rename

## Requirements & Constraints

### Functional Requirements

1. **Package and Module Rename**
   - PyPI package: `lw-coder` → `weft` in pyproject.toml
   - Python module: `src/lw_coder/` → `src/weft/`
   - All imports: `from lw_coder.X` → `from weft.X` (137 imports across 69 files)
   - CLI command: `lw_coder` → `weft` in project.scripts

2. **Repository Directory Migration**
   - Implement automatic migration: `.lw_coder/` → `.weft/` on first command run
   - Migration must be:
     - Idempotent (safe to run multiple times)
     - Logged (record migration action)
     - Simple rename operation (no backup, no user notification)
   - Handle scenarios:
     - Fresh install (no .lw_coder, no .weft) → create .weft normally
     - Legacy repo (has .lw_coder, no .weft) → migrate to .weft
     - Already migrated (no .lw_coder, has .weft) → no action
     - Both exist → prefer .weft, leave .lw_coder alone

3. **Home Directory Paths**
   - Code references: `~/.lw_coder/` → `~/.weft/` in all source files
   - No automatic migration (user migrates manually)
   - Paths affected:
     - `~/.weft/.env` (credentials)
     - `~/.weft/config.toml` (hooks, model defaults)
     - `~/.weft/completion_cache/` (tab completion cache)
     - `~/.weft/logs/` (log files)

4. **Reference Updates**
   - Update ALL forward-facing references to "lw_coder" → "weft":
     - Source code (module names, imports, docstrings, comments)
     - Tests (unit and integration)
     - Documentation (README, CLAUDE.md, docs/*)
     - Configuration files (pyproject.toml, .gitignore)
     - Error messages and help text
     - Template files (src/lw_coder/init_templates/)
   - Leave historical data unchanged (see Out of Scope)

5. **Git References**
   - No changes needed to git refs (they don't contain "lw_coder"):
     - `refs/plan-backups/<plan_id>` (keep as-is)
     - `refs/plan-abandoned/<plan_id>` (keep as-is)

### Non-Functional Requirements

1. **Testing**
   - All existing tests must pass after rename
   - Add migration tests for new automatic directory migration logic
   - Update test fixtures and path references
   - Follow existing test patterns from `test_prompt_loader_migration.py`

2. **Maintainability**
   - Use automated refactoring tools for import changes (avoid manual find/replace)
   - Create ADR documenting the rebrand decision
   - Phase changes across focused commits
   - Clear commit messages for each category of changes

3. **Data Integrity**
   - Migration must preserve all file contents
   - No data loss during directory rename
   - Existing worktrees, sessions, training data must remain intact

### Constraints

- Single user currently (you), no backward compatibility needed
- Clean break approach - no compatibility shims
- No rollback mechanism required (can fix manually if needed)
- Home directory migration is manual (user already migrated `~/.lw_coder` → `~/.weft`)

## Work Items

### 1. Package and Module Rename

**1.1 Rename Python Module Directory**
- Rename `src/lw_coder/` → `src/weft/`
- Verify all files moved correctly

**1.2 Update pyproject.toml**
- Change `name = "lw-coder"` → `name = "weft"`
- Change `lw_coder = "lw_coder.cli:main"` → `weft = "weft.cli:main"` in `[project.scripts]`
- Update `[tool.setuptools.package-data]` from `lw_coder = [...]` → `weft = [...] `

**1.3 Update All Python Imports**
- Update 137 import statements across 69 Python files
- Change all `from lw_coder.X import Y` → `from weft.X import Y`
- Change all `import lw_coder.X` → `import weft.X`
- Use automated refactoring tool (IDE rename or rope) rather than manual find/replace
- Files affected include:
  - All files in `src/weft/` (formerly `src/lw_coder/`)
  - All test files in `tests/unit/` and `tests/integration/`
  - Configuration files (`tests/conftest.py`, etc.)

### 2. Directory Path Updates

**2.1 Update Repository Directory References**
- Find all hardcoded `.lw_coder/` path references in code
- Change to `.weft/` in:
  - Path construction: `repo_root / ".lw_coder"` → `repo_root / ".weft"`
  - String literals in error messages
  - Documentation strings
  - Comments explaining paths
- Key files to update:
  - `src/weft/worktree_utils.py`
  - `src/weft/init_command.py`
  - `src/weft/session_manager.py`
  - `src/weft/temp_worktree.py`
  - `src/weft/plan_backup.py`
  - `src/weft/git_context.py`
  - All other files found by grep

**2.2 Update Home Directory References**
- Change `~/.lw_coder/` → `~/.weft/` in:
  - `src/weft/home_env.py` (line 40: `Path.home() / ".lw_coder"`)
  - `src/weft/config.py` (line 41: `CONFIG_PATH = Path.home() / ".lw_coder" / "config.toml"`)
  - `src/weft/logging_config.py` (log directory path)
  - `src/weft/completion/cache.py` (cache directory path)
  - `src/weft/hooks.py` (if it references home config)
  - Documentation and error messages

**2.3 Update .gitignore**
- Change `.lw_coder/dspy_cache/` → `.weft/dspy_cache/`
- Change `.lw_coder/worktrees/` → `.weft/worktrees/`
- Change `.lw_coder/runs/` → `.weft/runs/`
- Change `.lw_coder/plan-traces/` → `.weft/plan-traces/`
- Change `.lw_coder/sessions/` → `.weft/sessions/`
- Change `.lw_coder/temp-worktrees/` → `.weft/temp-worktrees/`

### 3. Migration Logic Implementation

**3.1 Create Migration Helper Function**
- Add function to detect and migrate `.lw_coder/` → `.weft/` automatically
- Location: Add to `src/weft/repo_utils.py` or create new `src/weft/migration.py`
- Function signature: `migrate_repo_dir_if_needed(repo_root: Path) -> bool`
- Logic:
  ```python
  def migrate_repo_dir_if_needed(repo_root: Path) -> bool:
      """Migrate .lw_coder/ to .weft/ if needed.

      Returns True if migration occurred, False otherwise.
      """
      old_dir = repo_root / ".lw_coder"
      new_dir = repo_root / ".weft"

      # Scenario: Both exist → prefer .weft, no action
      if old_dir.exists() and new_dir.exists():
          logger.debug("Both .lw_coder and .weft exist, using .weft")
          return False

      # Scenario: Already migrated → no action
      if not old_dir.exists():
          logger.debug("No .lw_coder directory found, no migration needed")
          return False

      # Scenario: Legacy repo → migrate
      logger.info("Migrating .lw_coder/ to .weft/ in %s", repo_root)
      shutil.move(str(old_dir), str(new_dir))
      logger.info("Migration complete: .lw_coder/ → .weft/")
      return True
  ```

**3.2 Integrate Migration into Commands**
- Call migration function early in command initialization
- Add to key entry points:
  - `src/weft/cli.py` main() function (before command dispatch)
  - OR add to `find_repo_root()` in `repo_utils.py` to run automatically
- Ensure migration runs before any operations that reference `.weft/`

**3.3 Add Migration Logging**
- Use existing logging infrastructure (`logging_config.py`)
- Log at INFO level when migration occurs
- Log at DEBUG level when no migration needed
- Include paths in log messages for clarity

### 4. Documentation Updates

**4.1 Update README.md**
- Already partially updated with "Weft" branding
- Verify all references changed:
  - Installation commands: `uv tool install weft`
  - Command examples: `weft init`, `weft plan`, `weft code`, etc.
  - Directory paths: `.weft/` instead of `.lw_coder/`
  - Home directory: `~/.weft/` instead of `~/.lw_coder/`

**4.2 Update CLAUDE.md**
- Change project description references
- Update command examples: `lw_coder` → `weft`
- Update directory paths in examples
- Update any references to package name

**4.3 Update Documentation Files**
- `docs/HOOKS.md` - update command examples and paths
- `docs/COMPLETION.md` - update completion installation examples
- `docs/configuration.md` - update config file paths
- `docs/code-config.md` - update configuration examples
- `docs/THREAT_MODEL.md` - update any tool name references
- `decisions.md` - update if it references the tool name
- `overview.md` - update project description
- `CONTRIBUTING.md` - update command examples
- `CLA.md` - likely no changes needed

**4.4 Create ADR for Rebrand**
- Create `docs/adr/003-rebrand-to-weft.md`
- Document:
  - Context: Why rebrand from lw_coder to weft
  - Decision: Complete rename approach
  - Consequences: What changes, what stays the same
  - Migration strategy: Automatic repo dir migration
  - Historical data: Preserved as-is
  - Alternatives considered: Backward compatibility shims (rejected)

### 5. Template and Metadata Updates

**5.1 Update Init Templates**
- Update `src/weft/init_templates/VERSION` file
- Update template files in `src/weft/init_templates/`:
  - Prompts that reference "lw_coder"
  - Judges that reference "lw_coder"
  - Any metadata files

**5.2 Update CLI Metadata**
- `src/weft/cli.py` - update ArgumentParser `prog="weft"`
- Help text and descriptions
- Error messages that mention "lw_coder"

**5.3 Update Finalize Prompts**
- `src/weft/prompts/claude-code/finalize.md`
- `src/weft/prompts/droid/finalize.md`
- Update any references to "lw_coder" in prompt content

### 6. Test Updates

See **Unit Tests** and **Integration Tests** sections below for detailed test requirements.

**6.1 Update Test Path References**
- Update all hardcoded path references in tests
- Files to update (~20 unit tests):
  - `tests/unit/test_home_env.py` - `~/.lw_coder/` → `~/.weft/`
  - `tests/unit/test_config.py` - config path references
  - `tests/unit/test_completion_cache.py` - cache path references
  - `tests/unit/test_logging_config.py` - log file paths
  - `tests/unit/test_worktree_utils.py` - `.lw_coder/worktrees/` references
  - `tests/unit/test_init_command.py` - `.lw_coder/` directory references
  - All other tests found by grep `.lw_coder`

**6.2 Update Integration Tests**
- `tests/integration/test_command_smoke.py` - update path assertions (lines 93, 129, 181)
- Other integration tests that reference `.lw_coder/` paths

**6.3 Add Migration Tests**
- Create `tests/unit/test_repo_migration.py` (see Unit Tests section)
- Follow pattern from `tests/unit/test_prompt_loader_migration.py`
- Test all migration scenarios

**6.4 Update Test Fixtures**
- `tests/conftest.py` - update any fixtures that reference "lw_coder"
- `tests/unit/conftest.py` - update fixtures
- `tests/integration/conftest.py` - update fixtures

### 7. Miscellaneous Updates

**7.1 Update Shell Scripts**
- `scripts/count_lines.sh` - if it references lw_coder
- Any other scripts in `scripts/`

**7.2 Verify No Missed References**
- Run comprehensive grep: `grep -r "lw_coder" . --exclude-dir=.git`
- Manually review any remaining references
- Exclude from updates (intentionally preserved):
  - Historical task files in `.weft/tasks/` (already done)
  - Historical training data in `.weft/training_data/`
  - Git history and commit messages

**7.3 Update Active Prompts and Judges**
- Files in `.lw_coder/prompts/active/` that reference "lw_coder"
- Files in `.lw_coder/judges/` that reference "lw_coder"
- These are templates used for new work, so should be updated

## Deliverables

1. **Working `weft` CLI Command**
   - Installable via `uv tool install weft`
   - All commands functional: `weft init`, `weft plan`, `weft code`, `weft eval`, etc.
   - Shell completion working with new command name

2. **Automatic Migration Logic**
   - `.lw_coder/` → `.weft/` migration working in repositories
   - Idempotent and safe
   - Properly logged

3. **Updated Test Suite**
   - All existing tests passing with new names
   - New migration tests added and passing
   - 100% test coverage maintained

4. **Updated Documentation**
   - README.md fully updated
   - CLAUDE.md updated
   - All docs/ files updated
   - ADR created documenting rebrand

5. **Clean Codebase**
   - No references to "lw_coder" in forward-facing code
   - All imports updated
   - All paths updated
   - Historical data preserved

## Out of Scope

1. **Home Directory Migration**
   - No automatic migration of `~/.lw_coder/` → `~/.weft/`
   - User manually migrates (already done for single user)
   - No documentation needed (single user context)

2. **Backward Compatibility**
   - No `lw_coder` → `weft` command alias
   - No import compatibility shims
   - Clean break approach

3. **Historical Data Updates**
   - `.weft/tasks/` - task files left as-is (all marked "done")
   - `.weft/training_data/` - training data traces preserved unchanged
   - These are historical records from when project was "lw_coder"

4. **Git Repository Rename**
   - GitHub repository URL change out of scope for this plan
   - Can be done separately (GitHub provides automatic redirects)

5. **Rollback Mechanism**
   - No automated rollback command
   - No backup creation during migration
   - Manual recovery if needed (single user context)

## Unit Tests

Create `tests/unit/test_repo_migration.py` following the pattern from `tests/unit/test_prompt_loader_migration.py`.

### Test Cases to Add

**Test 1: `test_migrate_repo_dir_legacy_to_new(tmp_path)`**
- **Setup**: Create `.lw_coder/` directory with sample files
- **Action**: Call `migrate_repo_dir_if_needed(tmp_path)`
- **Assert**:
  - Returns `True` (migration occurred)
  - `.lw_coder/` no longer exists
  - `.weft/` exists with all files preserved
  - File contents unchanged
- **Why**: Primary migration path for existing users

**Test 2: `test_migrate_repo_dir_already_migrated(tmp_path)`**
- **Setup**: Create `.weft/` directory (no `.lw_coder/`)
- **Action**: Call `migrate_repo_dir_if_needed(tmp_path)`
- **Assert**:
  - Returns `False` (no migration)
  - `.weft/` still exists unchanged
  - No errors or exceptions
- **Why**: Prevents double-migration and data corruption

**Test 3: `test_migrate_repo_dir_fresh_install(tmp_path)`**
- **Setup**: Empty directory (no `.lw_coder/`, no `.weft/`)
- **Action**: Call `migrate_repo_dir_if_needed(tmp_path)`
- **Assert**:
  - Returns `False` (no migration needed)
  - No directories created
  - No errors
- **Why**: New users shouldn't see migration logic run

**Test 4: `test_migrate_repo_dir_both_exist_prefers_new(tmp_path)`**
- **Setup**: Create both `.lw_coder/` and `.weft/` with different content
- **Action**: Call `migrate_repo_dir_if_needed(tmp_path)`
- **Assert**:
  - Returns `False` (no migration)
  - `.weft/` unchanged (original content preserved)
  - `.lw_coder/` still exists (not deleted)
- **Why**: Prevents data loss in conflict scenario

**Test 5: `test_migrate_repo_dir_preserves_content(tmp_path)`**
- **Setup**: Create `.lw_coder/` with nested structure:
  - `tasks/plan1.md`
  - `prompts/active/main.md`
  - `training_data/session1/trace.md`
- **Action**: Call `migrate_repo_dir_if_needed(tmp_path)`
- **Assert**:
  - All files exist at new paths in `.weft/`
  - File contents exactly match original
  - Directory structure preserved
  - File permissions preserved (if applicable)
- **Why**: Critical for data integrity

**Test 6: `test_migrate_repo_dir_logs_migration(tmp_path, caplog)`**
- **Setup**: Create `.lw_coder/` directory
- **Action**: Call `migrate_repo_dir_if_needed(tmp_path)` with caplog
- **Assert**:
  - Log message contains "Migrating .lw_coder/ to .weft/"
  - Log level is INFO
  - Log message contains "Migration complete"
- **Why**: Verify logging requirement met

### Modify Existing Tests

**Update `tests/unit/test_home_env.py`**
- Change all `Path.home() / ".lw_coder"` → `Path.home() / ".weft"`
- Update test assertions for path strings
- Verify env file loading still works

**Update `tests/unit/test_config.py`**
- Change `CONFIG_PATH = Path.home() / ".lw_coder" / "config.toml"` → `.weft`
- Update all test fixtures
- Verify config loading works

**Update `tests/unit/test_completion_cache.py`**
- Update cache path assertions
- Verify completion cache works with new path

**Update `tests/unit/test_logging_config.py`**
- Update log file path assertions (`~/.weft/logs/weft.log`)
- Verify logging still works

**Update ~20 other unit tests** that reference `.lw_coder/` paths in assertions or setup

## Integration Tests

### Modify Existing Tests

**Update `tests/integration/test_command_smoke.py`**
- Lines 93, 129, 181: Change `.lw_coder/worktrees/` → `.weft/worktrees/`
- Update any other path assertions
- Verify commands still work end-to-end

**Update other integration tests** found by grep to reference `.weft/` paths

### Optional Integration Test

**`tests/integration/test_migration_integration.py`** (optional, nice-to-have)
- **Test**: Create real git repo with `.lw_coder/` structure
- **Action**: Run actual `weft init` command
- **Assert**: Directory migrated, command works
- **Why**: End-to-end verification, but covered by unit tests + smoke tests

## Implementation Notes

1. **Phased Approach**: Implement in order:
   - Phase 1: Rename module directory and update imports
   - Phase 2: Update pyproject.toml and verify package builds
   - Phase 3: Update path references in source code
   - Phase 4: Implement migration logic
   - Phase 5: Update tests
   - Phase 6: Update documentation
   - Each phase should be a separate commit for easy review

2. **Testing Strategy**:
   - Update test fixtures and expectations FIRST
   - Then update source code to make tests pass
   - Run test suite after each phase

3. **Migration Safety**:
   - Migration uses `shutil.move()` - atomic on same filesystem
   - No backup created (simple rename, recoverable from git)
   - Logged at INFO level for traceability

4. **Grep Verification**:
   - After all changes, run: `grep -r "lw_coder" . --exclude-dir=.git --exclude-dir=.weft`
   - Review remaining references to ensure only historical data remains

5. **Reference Pattern from Existing Migration**:
   - See `src/weft/prompt_loader.py` `_migrate_prompts_if_needed()` for migration pattern
   - See `tests/unit/test_prompt_loader_migration.py` for test pattern
   - Follow same structure for consistency
