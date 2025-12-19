---
plan_id: dspy-cache-worktree-sync
status: done
evaluation_notes: []
git_sha: 6f46ee864333c898136c5693ec85a2cfd912d119
---

# DSPy Cache Worktree Synchronization

## Objectives

Enable DSPy caching to work seamlessly in sandboxed worktree environments by:
1. Fixing DSPy cache configuration to actually use disk caching
2. Implementing bidirectional rsync between global cache and worktree cache
3. Updating .gitignore entries for cache directories

## Requirements & Constraints

### Functional Requirements
- DSPy must actually write cache entries to disk (currently broken)
- Tests running in worktrees must have access to cached LLM responses
- Cache entries created in worktrees must sync back to global cache
- Solution must work in sandboxed environments where `~/.lw_coder/` is not writable

### Performance Requirements
- Cache sync operations should be fast (rsync handles incremental updates efficiently)
- No significant slowdown to command startup/completion

### Constraints
- Sandbox restricts writes outside worktree directory
- Must maintain backward compatibility with existing cache at `~/.lw_coder/dspy_cache/`
- Must work with both main project execution and worktree execution

## Work Items

### 1. Fix DSPy Cache Configuration Bug
**File:** `src/lw_coder/judge_executor.py`

Currently, `create_lm()` accepts `cache_dir` parameter but never configures DSPy to use it. The cache directory is created but DSPy defaults to its own location.

**Changes needed:**
- Update `create_lm()` to pass cache configuration to `dspy.LM()`
- According to DSPy documentation, use: `dspy.LM(..., cache=True)` and configure cache path via `dspy.settings.configure()`
- OR use `dspy.LM(..., cache={"type": "disk", "path": str(cache_dir)})`
- Research correct DSPy cache API and implement properly

**Acceptance criteria:**
- After calling `create_lm()`, DSPy writes cache files to specified `cache_dir`
- Integration test verifies cache files are created

### 2. Implement Cache Synchronization Utilities
**File:** `src/lw_coder/cache_sync.py` (new)

Create utility module for cache synchronization operations.

**Functions to implement:**

```python
def sync_cache_to_worktree(
    source: Path,  # ~/.lw_coder/dspy_cache
    dest: Path,    # worktree/.lw_coder/dspy_cache
) -> None:
    """Sync global cache to worktree before command execution.

    Uses rsync -a --delete to mirror source to dest.
    Creates dest directory if it doesn't exist.
    """

def sync_cache_from_worktree(
    source: Path,  # worktree/.lw_coder/dspy_cache
    dest: Path,    # ~/.lw_coder/dspy_cache
) -> None:
    """Sync worktree cache back to global cache after execution.

    Uses rsync -a (no --delete) to preserve global cache entries.
    Only adds new entries, doesn't remove existing ones.
    """
```

**Rsync availability check:**
```python
def check_rsync_available() -> bool:
    """Check if rsync is available on the system.

    Returns:
        True if rsync is available, False otherwise.
    """
    try:
        subprocess.run(["rsync", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
```

**Error handling:**
- Check for rsync availability before attempting sync
- If rsync not available: log clear error message, display to user, continue without cache sync
- Handle rsync command failures gracefully
- Log warnings if sync fails but don't block command execution

### 3. Update get_cache_dir() to Support Worktrees
**File:** `src/lw_coder/judge_executor.py`

Update `get_cache_dir()` to return appropriate cache location based on execution context.

**Logic:**
```python
def get_cache_dir() -> Path:
    """Get DSPy cache directory.

    Returns local .lw_coder/dspy_cache when in worktree,
    global ~/.lw_coder/dspy_cache otherwise.
    """
    cwd = Path.cwd()

    # Check if we're in a worktree
    if '/.lw_coder/worktrees/' in str(cwd.resolve()):
        # Find worktree root and use local cache
        # Pattern: /path/to/project/.lw_coder/worktrees/temp-xyz/...
        # Return: /path/to/project/.lw_coder/worktrees/temp-xyz/.lw_coder/dspy_cache
        parts = cwd.resolve().parts
        worktree_idx = parts.index('worktrees') + 1
        worktree_root = Path(*parts[:worktree_idx + 1])
        return worktree_root / ".lw_coder" / "dspy_cache"
    else:
        # Use global cache
        return Path.home() / ".lw_coder" / "dspy_cache"
```

**Update test:**
- `tests/unit/test_judge_executor.py::test_get_cache_dir()` needs updating
- Add test for worktree cache path resolution
- Add test for main project cache path

### 4. Integrate Cache Sync into Code Command
**File:** `src/lw_coder/code_command.py`

Add cache synchronization before SDK session and after completion.

**Before SDK session:**
1. Sync cache from `~/.lw_coder/dspy_cache/` to worktree

**After SDK session:**
1. Sync cache from worktree back to `~/.lw_coder/dspy_cache/`

**Integration points:**
- In `run_code_command()` before calling `run_sdk_session_sync()`
- After SDK session completes, before returning

**Rsync availability handling:**
- Check if rsync is available using `check_rsync_available()`
- If not available: display clear error to user, log warning, skip cache sync
- Error message should explain rsync is required for cache functionality
- Command should continue normally without cache sync

**Error handling:**
- Log sync failures as warnings, don't block execution
- If sync fails, command continues (just won't benefit from cache)

### 5. Integrate Cache Sync into Eval Command
**File:** `src/lw_coder/eval_command.py`

Similar integration as code command:
- Before judge execution: sync cache to worktree
- After judge execution: sync cache back to global

**Integration points:**
- In `run_eval_command()` after worktree path validation
- After `execute_judges_parallel()` completes

**Rsync availability handling:**
- Same as code command: check availability, display error if missing, continue without sync

### 6. Update .gitignore Entries

**File:** `.gitignore` (project root)

Add cache directory to ignored paths:
```
# .lw_coder cache and temporary files
.lw_coder/dspy_cache/
.lw_coder/worktrees/
.lw_coder/runs/
.lw_coder/plan-traces/
```

**File:** `src/lw_coder/init_command.py`

Update the `init` command to add cache entries to target project's `.gitignore`:

When initializing a project:
1. Check if `.gitignore` exists in target directory
2. If exists: append cache entries if not already present (check for "# .lw_coder cache" marker)
3. If doesn't exist: create `.gitignore` with cache entries
4. Entries to add:
   - `.lw_coder/dspy_cache/`
   - `.lw_coder/worktrees/`
   - `.lw_coder/runs/`
   - `.lw_coder/plan-traces/`

**Implementation:**
```python
def update_gitignore(project_root: Path) -> None:
    """Add lw_coder cache directories to .gitignore."""
    gitignore_path = project_root / ".gitignore"

    entries = """
# lw_coder cache and temporary files
.lw_coder/dspy_cache/
.lw_coder/worktrees/
.lw_coder/runs/
.lw_coder/plan-traces/
"""

    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if "# lw_coder cache" not in content:
            # Append to existing .gitignore
            gitignore_path.write_text(content.rstrip() + "\n" + entries)
    else:
        # Create new .gitignore
        gitignore_path.write_text(entries.lstrip())
```

### 7. Add Integration Test for Cache Functionality
**File:** `tests/integration/test_dspy_cache.py` (new)

Create integration test that verifies DSPy cache actually works.

**Test structure:**
```python
@pytest.mark.integration
def test_dspy_cache_creates_files(tmp_path: Path) -> None:
    """Verify DSPy cache actually writes files to disk.

    This test:
    1. Creates an empty cache directory
    2. Executes a judge with real DSPy/LLM call
    3. Verifies cache files were created
    4. Executes same judge again
    5. Verifies cache was used (faster, no new API call)
    """
    cache_dir = tmp_path / "test_cache"
    cache_dir.mkdir()

    # Verify cache is empty
    assert list(cache_dir.iterdir()) == []

    # Execute judge (will hit API)
    api_key = get_openrouter_api_key()
    judge = JudgeConfig(...)

    result1 = execute_judge(judge, plan_content, git_changes, api_key, cache_dir)

    # Verify cache files were created
    cache_files = list(cache_dir.rglob("*"))
    assert len(cache_files) > 0, "Cache should contain files after execution"

    # Execute again (should use cache)
    result2 = execute_judge(judge, plan_content, git_changes, api_key, cache_dir)

    # Results should be identical
    assert result1.score == result2.score
    assert result1.feedback == result2.feedback
```

**Additional test:**
```python
@pytest.mark.integration
def test_cache_sync_workflow(tmp_path: Path) -> None:
    """Test bidirectional cache sync workflow."""
    # Setup
    global_cache = tmp_path / "global"
    worktree_cache = tmp_path / "worktree"

    # Create some files in global cache
    # Sync to worktree
    # Verify files copied
    # Add new files to worktree
    # Sync back
    # Verify new files in global cache
```

### 8. Add Unit Tests for Cache Utilities
**File:** `tests/unit/test_cache_sync.py` (new)

Test cache sync utilities in isolation:

```python
def test_sync_cache_to_worktree(tmp_path: Path) -> None:
    """Test syncing cache from global to worktree."""

def test_sync_cache_from_worktree(tmp_path: Path) -> None:
    """Test syncing cache from worktree to global."""

def test_check_rsync_available() -> None:
    """Test rsync availability check."""
    # Should return True if rsync is installed
    # Should return False if rsync not found

def test_sync_handles_missing_rsync(monkeypatch) -> None:
    """Test graceful handling when rsync not available."""
    # Mock check_rsync_available to return False
    # Verify sync functions handle this gracefully
    # Verify warning is logged
```

### 9. Update Documentation

**File:** `README.md`

Add rsync requirement to the README:

**In Requirements/Dependencies section:**
```markdown
## Requirements

- Python 3.10+
- Git
- `rsync` command (for DSPy cache synchronization in worktrees)
  - Linux/macOS: Usually pre-installed
  - Windows: Install via WSL, Cygwin, or `choco install rsync`
  - Verify installation: `rsync --version`

If `rsync` is not available, commands will run but cache synchronization will be disabled.
```

**File:** `docs/configuration.md` and `docs/code-config.md`

Update cache documentation:

**In configuration.md and code-config.md:**
- Document cache location: `~/.lw_coder/dspy_cache/` (global)
- Document automatic sync for worktrees
- Document manual cache clearing: `rm -rf ~/.lw_coder/dspy_cache`
- Add troubleshooting section for rsync issues

**New section example:**
```markdown
### DSPy Cache

DSPy caches LLM responses at `~/.lw_coder/dspy_cache/` to speed up repeated operations:
- Cache is automatically synced to worktrees before command execution
- Cache entries created in worktrees sync back to global cache
- Cache can be cleared manually: `rm -rf ~/.lw_coder/dspy_cache`

**Requirements:**
- `rsync` command must be available on system
- Cache sync is fast due to rsync's incremental updates

**Troubleshooting:**
- If rsync not installed, you'll see an error message on command startup
- Commands continue without cache sync if rsync unavailable
- Install rsync to enable cache functionality
- Verify rsync is installed: `which rsync`
```

## Deliverables

1. **Fixed DSPy cache configuration** - Cache files actually written to disk at specified location
2. **Cache sync utilities** - `src/lw_coder/cache_sync.py` with sync functions and rsync availability check
3. **Updated get_cache_dir()** - Returns worktree-local or global cache path
4. **Code command integration** - Bidirectional sync before/after SDK session with rsync check
5. **Eval command integration** - Bidirectional sync before/after judge execution with rsync check
6. **Updated .gitignore** - Cache directories ignored in both project and init template
7. **Integration test** - Verifies cache files are created and reused
8. **Unit tests** - Full coverage of cache sync utilities including rsync availability check
9. **Updated documentation** - README with rsync requirement, configuration docs with cache behavior

## Out of Scope

- Cache encryption or security hardening
- Cross-project cache sharing beyond global `~/.lw_coder/dspy_cache/`
- Cache invalidation strategies (handled by DSPy internally)
- Alternative sync mechanisms (rsync is required)
- Cache size limiting or automatic cleanup
- Cache compression or optimization
- Monitoring cache hit rates or statistics
