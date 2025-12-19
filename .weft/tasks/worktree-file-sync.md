---
plan_id: worktree-file-sync
status: done
evaluation_notes: []
git_sha: 193e27460d315f6820667dfcca60fc8fb22974bf
---

# Worktree File Synchronization

## Objectives

Implement a system to automatically copy untracked files (e.g., `.env`, configuration files) from the main repository to temporary worktrees when the `code` command runs. This ensures tests and code execution in isolated worktrees have access to necessary files that aren't tracked in git.

## Requirements & Constraints

### Functional Requirements

1. **Repository-level configuration**: Add `.lw_coder/config.toml` at repository root with versioned schema
2. **Glob pattern matching**: Support glob patterns to match files/directories relative to repo root
3. **Directory support**: Copy matched directories recursively, preserving structure
4. **Symlink preservation**: Copy symlinks as symlinks (not dereferencing them)
5. **File metadata**: Preserve permissions and timestamps using `shutil.copy2()`
6. **Size limits**: Enforce per-file and total size limits to prevent disk issues
7. **Path safety**: Validate patterns to prevent path traversal attacks
8. **Cleanup**: Remove copied files from worktree in finally block
9. **Error handling**: Fail fast with clear error messages on any failure
10. **Init command integration**: Create template config during `lw_coder init`

### Configuration Schema

Configuration lives in `.lw_coder/config.toml` with a `[worktree.file_sync]` section containing: `enabled` (boolean), `patterns` (list of glob strings), `max_file_size_mb` and `max_total_size_mb` (positive integers with defaults of 100 and 500).

**Schema validation requirements**:
- `schema_version` must be "1.0"
- `[worktree.file_sync]` section is optional
- `enabled` must be boolean (default: true)
- `patterns` must be list of strings
- `max_file_size_mb` must be positive integer (default: 100)
- `max_total_size_mb` must be positive integer (default: 500)
- Reject unknown keys in `[worktree.file_sync]` section (strict validation)

### Pattern Safety Rules

Reject patterns that could access files outside repository:
- Contains `..` (parent directory references)
- Starts with `/` (absolute paths)
- Starts with `~` (home directory expansion)
- After resolution, would escape repo root

### Timing & Integration

1. Load config from `.lw_coder/config.toml` (if doesn't exist, skip silently with debug log)
2. Execute file copy **after worktree creation, before writing sub-agents** in `code_command.py` (around line 334, after `ensure_worktree()` completes)
3. Track all copied files for cleanup
4. In finally block, remove copied files (best-effort, log warnings on failure)

### Logging Requirements

- **DEBUG level**: Individual file operations ("Copying .env to worktree", "Preserving symlink: config/db.json")
- **INFO level**: Summary message ("Copied 3 files (2.5MB) to worktree based on repo config")
- **ERROR level**: Validation failures, copy failures, size limit violations

### Constraints

1. **No negation patterns in v1**: Deferred to future enhancement (e.g., `!.env.production`)
2. **Reuse config loading**: Use `config.load_config()` from `src/lw_coder/config.py` which handles TOML parsing from `~/.lw_coder/config.toml`
3. **Strict validation**: Catch configuration errors early with helpful messages
4. **Fail fast**: Any error during pattern matching or copying should halt the `code` command
5. **Security first**: Validate all patterns for safety before executing

## Work Items

### 1. Config Schema & Validation

**Files to modify**:
- `src/lw_coder/config.py` - Add validation for `[worktree.file_sync]` section (follow pattern used by `hooks.py` for `[hooks]` section validation)

**Implementation**:
- Define typed config schema for `[worktree.file_sync]` section
- Implement `validate_worktree_file_sync_config()` function:
  - Check schema_version = "1.0"
  - Validate enabled is boolean
  - Validate patterns is list of strings
  - Validate max_file_size_mb and max_total_size_mb are positive integers
  - Check for unknown keys in [worktree.file_sync] (strict validation)
  - Raise clear ConfigValidationError with helpful messages
- Implement `validate_pattern_safety()` function:
  - Reject patterns with `..`, `/`, or `~`
  - Ensure patterns cannot escape repo root
  - Raise UnsafePatternError with security-focused message

### 2. Pattern Matching & File Discovery

**Files to create**:
- `src/lw_coder/worktree/file_sync.py` (new module for worktree file sync logic)

**Implementation**:
- Create `FileSyncPattern` class:
  - `__init__(pattern: str, repo_root: Path)`
  - `find_matches() -> list[Path]`: Use `pathlib.Path.glob()` to find matches
  - Handle files, directories, and symlinks
  - Return empty list if no matches (caller will error)
  - Log matches at DEBUG level with pattern info
- Create `FileSyncOperation` class:
  - Track source path, destination path, size
  - `validate()`: Check file size against limits
  - `execute()`: Perform the actual copy with proper error handling
  - Handle files, directories, and symlinks appropriately

**Edge cases to handle**:
- Empty directories: Create them in worktree
- Symlinks: Preserve as symlinks using `os.symlink(os.readlink(src), dst)`
- Nested symlinks within directories: Preserve all symlinks
- Large files: Error if file exceeds max_file_size_mb
- Total size: Track cumulative size, error if exceeds max_total_size_mb

### 3. File Copy Implementation

**Implementation in `FileSyncOperation.execute()`**:
- For regular files:
  - Use `shutil.copy2(src, dst)` to preserve metadata
  - Create parent directories as needed
  - Verify size limits before copying
- For directories:
  - Recurse through directory tree
  - Preserve structure in destination
  - Copy each file/symlink using appropriate method
  - Track total size across all files
- For symlinks:
  - Read link target with `os.readlink(src)`
  - Create symlink in destination with `os.symlink(target, dst)`
  - Log at DEBUG: "Preserving symlink: {relative_path} -> {target}"

### 4. Cleanup Implementation

**Files to modify**:
- `src/lw_coder/code_command.py`

**Implementation**:
- Create `WorktreeFileCleanup` class:
  - Track list of copied files/directories
  - `register_copied_file(path: Path)`: Add to tracking list
  - `cleanup()`: Best-effort removal in finally block
    - Iterate in reverse order (for directory cleanup)
    - Log warnings for failures, don't raise exceptions
    - Collect errors for potential reporting
- Integrate in `run_code_command()` finally block:
  - Call cleanup after cache sync
  - Handle cleanup failures gracefully (we're already in finally block)

### 5. Integration with code Command

**Files to modify**:
- `src/lw_coder/code_command.py`

**Implementation**:
- After `ensure_worktree()` completes (around line 333), call file sync with the repo root, worktree path, and a cleanup tracker
- On `FileSyncError`, log the error and return exit code 1
- In the finally block (after line 582), call cleanup on the tracker

**Main sync function** should:
1. Load config (silent skip if doesn't exist)
2. Validate config schema and check if enabled
3. Validate pattern safety
4. Find matches for each pattern (error if pattern matches nothing)
5. Validate total size against limits
6. Copy files/directories/symlinks to worktree
7. Register copied paths with cleanup tracker
8. Log INFO summary

### 6. Init Command Integration

**Files to modify**:
- `src/lw_coder/init_command.py`

**Implementation**:
- Create template `.lw_coder/config.toml` during init with `schema_version = "1.0"` and a commented-out `[worktree.file_sync]` section showing example patterns (`.env*`, `config/secrets.json`, etc.)
- Check if config.toml already exists before creating
- Include helpful comments explaining the feature

### 7. Documentation

**Files to modify**:
- `docs/configuration.md` - Add section on worktree file sync config schema
- `README.md` - Add brief section on worktree file sync in the appropriate location (near Init Command or Code Command sections)

**Content to document**:
- Configuration syntax for `[worktree.file_sync]` section
- Pattern syntax and limitations (glob patterns, no negation)
- Size limits and defaults
- Security constraints (no `..`, `/`, `~` in patterns)
- Example use cases (`.env` files, test configs)

### 8. Error Messages & User Experience

Error messages should be clear and actionable, covering:
- **Config validation**: Invalid schema version, unknown keys in `[worktree.file_sync]`
- **Pattern safety**: Parent directory refs (`..`), absolute paths, home directory expansion
- **Pattern matching**: Pattern matched no files
- **Size limits**: File exceeds per-file limit, total exceeds aggregate limit
- **Copy failures**: Permission errors, disk space issues

Each message should identify the problematic value and suggest how to fix it.

## Deliverables

### Code Artifacts

1. **New module**: `src/lw_coder/worktree/file_sync.py`
   - `FileSyncPattern` class for pattern matching
   - `FileSyncOperation` class for copy operations
   - `WorktreeFileCleanup` class for cleanup tracking
   - `FileSyncError` exception hierarchy
   - Main `sync_files_to_worktree()` function

2. **Config validation**: Add to `src/lw_coder/config.py`
   - Schema validation for `[worktree.file_sync]`
   - Pattern safety validation
   - Type checking and unknown key detection

3. **Modified**: `src/lw_coder/code_command.py`
   - Call file sync after worktree creation
   - Cleanup integration in finally block

4. **Modified**: `src/lw_coder/init_command.py`
   - Create template `.lw_coder/config.toml`
   - Document worktree file sync feature

5. **Documentation**:
   - Updated `docs/configuration.md` with worktree file sync config schema
   - Updated `README.md` with worktree file sync section

### Unit Tests

**Test file**: `tests/unit/worktree/test_file_sync.py`

**Test coverage** (combine related assertions where possible, use `stat()` to verify multiple file properties in single tests):

- `TestFileSyncPattern`:
  - Pattern matching: glob patterns, nested directories, symlinks, directories
  - No matches returns empty list

- `TestPatternSafety` (use parametrize):
  - Rejects unsafe patterns: `..`, absolute paths (`/`), home directory (`~`)
  - Allows safe patterns

- `TestFileSyncOperation`:
  - `test_copy_file_preserves_metadata`: Copy file and verify permissions + timestamps via `stat()`
  - `test_copy_symlink`: Symlink preserved as symlink (check `is_symlink()` and target)
  - `test_copy_directory`: Recursive copy with structure, including nested symlinks
  - `test_size_limits`: Parametrize per-file and total size limit errors
  - `test_creates_parent_directories`

- `TestWorktreeFileCleanup`:
  - `test_cleanup`: Files/directories removed in reverse order, errors logged not raised

- `TestConfigValidation` (use parametrize for invalid cases):
  - Valid config accepted
  - Invalid configs: missing/wrong schema_version, unknown keys, wrong types, negative limits

- `TestSyncFilesToWorktree`:
  - `test_no_config_skips_silently`
  - `test_disabled_skips_sync`
  - `test_end_to_end`: Copies files, preserves structure, registers for cleanup, logs summary
  - `test_pattern_match_nothing_errors`

### Filesystem Tests

These are unit tests that use real filesystem operations with temporary directories (not integration tests since they don't make external API calls):

- `test_sync_workflow`: Create temp repo with `.env`, config.toml, and simulated worktree dir. Call `sync_files_to_worktree()` directly, verify files copied, call cleanup, verify files removed.
- `test_sync_symlink_handling`: Symlink in temp repo copied as symlink to temp worktree
- `test_sync_error_cases` (parametrize): Size limit exceeded, invalid config, unsafe pattern

## Out of Scope

### Deferred to Future Enhancements

1. **Negation patterns**: Exclusion patterns like `!.env.production` (requires more complex pattern engine like `wcmatch`)
2. **Template substitution**: Copying `.env.template` and substituting variables
3. **Conditional sync**: Optional patterns that don't fail if missing
4. **Per-pattern options**: Different size limits or behaviors per pattern
5. **Sync strategies**: Options for copy vs symlink vs bind mount
6. **Bidirectional sync**: Copying changes from worktree back to main repo
7. **File watching**: Detecting changes in main repo during long-running sessions
8. **Compression**: Compressing large files before copying

### Explicitly Not Included

1. **Copying git-tracked files**: Only untracked files are synced (tracked files are already in worktree)
2. **Modifying files during copy**: No transformations, substitutions, or modifications
3. **Network/remote files**: Only local filesystem files in the repository
4. **Special file types**: Block devices, FIFOs, sockets are not supported
5. **Windows support**: Initial implementation targets Linux only (aligned with current lw_coder platform support)
6. **Global config patterns**: Only repo-level config supported (not ~/.lw_coder/config.toml)

## Notes

### Design Decisions

1. **Why glob patterns, not gitignore syntax?**: Simpler for v1, easier to understand. Can add gitignore syntax later if needed.

2. **Why fail if pattern matches nothing?**: Prevents silent failures from typos. User should know if their pattern isn't working.

3. **Why strict config validation?**: Catch errors early during config loading, not during execution. Better UX.

4. **Why preserve symlinks instead of following?**: Saves disk space, keeps files in sync with main repo, and our testing confirms SDK can read symlinked files.

5. **Why size limits?**: Prevents accidentally filling disk with large files. Common mistake would be matching build artifacts or node_modules.

6. **Why [worktree.file_sync] instead of flat [worktree]?**: Easier to add other worktree features later (cleanup settings, environment config, etc.) without cluttering the namespace.

### Implementation Risks

1. **Glob pattern edge cases**: Pattern matching has subtle behaviors (e.g., `**/` vs `*/`, hidden files, symlinks).
   - **Mitigation**: Comprehensive unit tests for pattern matching. Clear documentation of limitations.

2. **Cleanup failures**: Files might not be cleanable (permissions, locked files, disk full).
   - **Mitigation**: Best-effort cleanup with error logging. Don't fail the session just because cleanup failed.

3. **Large file performance**: Copying many large files could slow down `code` command startup.
   - **Mitigation**: Size limits help. Can add progress indicator or async copy in future if needed.

### Testing Strategy

1. **Unit tests**: Test pattern matching, file operations, and cleanup in isolation with temporary directories
2. **Manual testing**: Test with real `.env` files and verify tests run correctly in worktree
3. **Edge case testing**: Symlinks, large files, permissions, nested directories, empty directories

### Success Criteria

1. ✅ `lw_coder init` creates `.lw_coder/config.toml` template
2. ✅ User can configure patterns in `.lw_coder/config.toml`
3. ✅ `lw_coder code` copies matched files to worktree before execution
4. ✅ Copied files are accessible during code session (tests pass)
5. ✅ Copied files are cleaned up after session
6. ✅ Size limits prevent disk issues
7. ✅ Pattern validation prevents security issues
8. ✅ Clear error messages guide user to fix config problems
9. ✅ Documentation explains feature and provides examples
10. ✅ All unit and integration tests pass
