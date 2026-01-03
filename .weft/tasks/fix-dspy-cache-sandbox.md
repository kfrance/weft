---
plan_id: fix-dspy-cache-sandbox
status: done
evaluation_notes: []
git_sha: 5cb1739ec9e6af9f3d92ad085b4b34f7404d1d3b
---

# Fix DSPy Cache Access via SDK Sandbox Configuration

## Objectives

Replace the rsync-based DSPy cache synchronization with direct cache access through SDK sandbox configuration. This eliminates SQLite corruption issues caused by concurrent rsync operations across multiple worktrees.

## Requirements & Constraints

### Requirements
1. DSPy cache must be accessible from within SDK sandbox sessions
2. Multiple concurrent worktrees must not corrupt the cache
3. Cache must persist across sessions (not worktree-local)
4. Sandbox security model must be preserved

### Constraints
1. Cannot disable sandbox - it protects filesystem from unintended changes
2. SDK sandbox restricts all commands (including Python/DSPy file operations)
3. Permission rules require absolute paths (no `~` expansion in JSON)
4. Must generate sdk_settings.json dynamically at runtime

### Validated Approach (Tested)
The following configuration was validated to grant write access to `~/.weft/dspy_cache/`:
- `add_dirs=[Path.home() / ".weft" / "dspy_cache"]` in ClaudeAgentOptions
- `permission_mode="acceptEdits"`
- Permission allow rules: `Edit(<cache_path>/**)` and `Write(<cache_path>/**)`

## Work Items

### 1. Update SDK Runner Configuration
**File**: `src/weft/sdk_runner.py`

Changes:
- Add `add_dirs` parameter to `ClaudeAgentOptions` with path to global DSPy cache (`Path.home() / ".weft" / "dspy_cache"`)
- Change `permission_mode` from `"default"` to `"acceptEdits"`

### 2. Generate SDK Settings Dynamically
**File**: `src/weft/sdk_runner.py` (or new module)

The sdk_settings.json must include permission rules with absolute paths. Since `~` is not expanded in JSON, settings must be generated at runtime.

Changes:
- Create function to generate settings dict with user's home path
- Write settings to temporary file before SDK session
- Include sandbox config + permission allow rules for cache directory

Settings structure:
```json
{
  "sandbox": {
    "enabled": true,
    "autoAllowBashIfSandboxed": true,
    "allowUnsandboxedCommands": false
  },
  "permissions": {
    "allow": [
      "Edit(/home/<user>/.weft/dspy_cache/**)",
      "Write(/home/<user>/.weft/dspy_cache/**)"
    ]
  }
}
```

### 3. Simplify Cache Directory Logic
**File**: `src/weft/judge_executor.py`

Changes:
- Update `get_cache_dir()` to always return global cache path `~/.weft/dspy_cache/`
- Remove worktree detection logic (no longer needed)
- Remove `get_worktree_cache_dir()` function if present

### 4. Remove Cache Sync Module
**File**: `src/weft/cache_sync.py`

Action: DELETE entire file

Functions being removed:
- `check_rsync_available()`
- `sync_cache_to_worktree()`
- `sync_cache_from_worktree()`
- `get_global_cache_dir()`
- `get_worktree_cache_dir()`

### 5. Remove Cache Sync Calls from Code Command
**File**: `src/weft/code_command.py`

Changes:
- Remove import of cache_sync functions
- Remove `sync_cache_to_worktree()` call (around line 614)
- Remove `sync_cache_from_worktree()` call (around line 812)

### 6. Remove Cache Sync Calls from Eval Command
**File**: `src/weft/eval_command.py`

Changes:
- Remove import of cache_sync functions
- Remove any cache sync calls (around lines 188-189)

### 7. Update Documentation
**File**: `docs/CONFIGURATION.md`

Changes:
- Remove rsync requirement from DSPy Caching section
- Update "How It Works" to describe direct cache access
- Remove rsync troubleshooting section
- Update cache behavior description

**File**: `README.md`

Changes:
- Remove rsync from Requirements section
- Update any references to cache synchronization

## Deliverables

### Code Changes
- [ ] `src/weft/sdk_runner.py` - Add `add_dirs`, change `permission_mode`, generate dynamic settings
- [ ] `src/weft/judge_executor.py` - Simplify `get_cache_dir()` to always return global cache
- [ ] `src/weft/cache_sync.py` - DELETE entire module
- [ ] `src/weft/code_command.py` - Remove cache sync imports and calls
- [ ] `src/weft/eval_command.py` - Remove cache sync imports and calls

### Documentation
- [ ] `docs/CONFIGURATION.md` - Updated cache documentation
- [ ] `README.md` - Remove rsync requirement

### Unit Tests
**File**: `tests/unit/test_judge_executor.py`

Update existing tests for `get_cache_dir()`:
- Consolidate 3 existing tests into 1 test
- Verify function always returns global cache `~/.weft/dspy_cache/`
- Test from both worktree and non-worktree paths

### Integration Tests
**File**: `tests/integration/test_dspy_cache.py`

Changes:
- DELETE cache sync workflow tests (3 tests)
- KEEP `test_dspy_cache_creates_files` (validates DSPy caching works)

**File**: `tests/integration/test_sdk_dspy_cache.py` (NEW)

Add test to verify SDK sandbox allows Python file I/O to cache directory:
- Run SDK session that executes a Bash command with Python file I/O (e.g., `uv run python -c "open('<cache_path>/test.txt', 'w').write('test')"`)
- Verify file was created in global cache directory
- This tests the actual permission path: sandboxed Bash → Python subprocess → file I/O
- More accurate than testing Claude's Write tool since DSPy uses Python file operations

## Out of Scope

1. **SQLite WAL mode**: Not implementing WAL mode for concurrent access. The current approach eliminates concurrent rsync, which was the source of corruption. DSPy/SQLite's built-in locking should handle concurrent reads.

2. **Fallback mechanism**: Not implementing rsync fallback if SDK approach fails. This is a clean replacement, not a gradual migration.

3. **Cache migration**: Not migrating existing worktree-local caches to global. Users can manually delete worktree caches.

4. **Multi-user support**: Cache is per-user at `~/.weft/dspy_cache/`. Shared/system-wide caching is out of scope.

5. **ADR documentation**: The maintainability reviewer suggested creating an ADR for this SDK dependency. Deferring this decision - can be added later if the approach proves problematic.
