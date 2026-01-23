---
plan_id: weft-sandbox
status: done
evaluation_notes: []
git_sha: 31704fc83f95e8943ff0474e3ee386cfd27ddf26
---

# Weft Sandbox Implementation

Replace Claude Code's internal sandboxing with a custom bwrap-based sandbox ("weft sandbox") that provides consistent filesystem isolation for both Claude Code and Droid executors.

## Objectives

1. Remove dependency on Claude Code's internal sandbox
2. Implement custom bwrap wrapper for consistent isolation across executors
3. Enable repo-level configuration of sandbox paths and disallowed commands
4. Support both Claude Code SDK sessions and Droid execution with the same sandbox

## Requirements & Constraints

### Functional Requirements

- Wrap all executor commands (Claude Code CLI, Droid) with bwrap
- Support configurable read-only, write-only, and read-write path mounts
- Support `~` home directory expansion in configured paths
- Block specific commands via `--disallowed-tools` for Claude Code CLI
- Disable Claude Code's internal sandbox (`sandbox.enabled = false`)
- Error on path collisions (same path in multiple lists)

### Automatic Mounts (hardcoded, not configurable)

| Path | Access | Reason |
|------|--------|--------|
| `/usr`, `/lib`, `/lib64`, `/bin`, `/sbin`, `/etc` | read-only | System libraries |
| `/proc`, `/dev` | special | Process management |
| `/tmp` | tmpfs | Temp files |
| `~/.local` | read-only | Claude installation |
| `~/.claude` | read-write | Claude config/sessions/todos |
| Worktree path | read-write | Working directory |

### Config.toml Schema (repo-level `.weft/config.toml`)

```toml
[sandbox]
read_paths = ["/data/reference"]
write_paths = ["/var/log/myapp"]
read_write_paths = ["~/.weft/dspy_cache"]
disallowed_commands = ["git add:*", "git commit:*", "git push:*", "docker:*"]
```

### Command Blocking Scope

- **Claude Code (headless sessions only)**: Full command blocking via `--disallowed-tools` CLI flag and `can_use_tool` SDK callback. The `disallowed_commands` config only applies to headless sessions run by weft.
- **Claude Code (interactive sessions)**: Use standard `.claude/settings.json` or `.claude/settings.local.json` files (not managed by weft sandbox)
- **Droid**: Filesystem isolation only (no command blocking mechanism available)

### Non-functional Requirements

- Sandbox must work for both SDK sessions and CLI resume mode
- Network access is unaffected (weft sandbox only isolates filesystem)

## Experimentation Results

During planning, we validated the approach with manual testing. Here are the key findings and the correct bwrap configuration:

### Working bwrap Configuration for Claude Code

The following bwrap invocation successfully runs Claude Code CLI in a sandbox:

```bash
bwrap \
    --ro-bind /usr /usr \
    --ro-bind /lib /lib \
    --ro-bind /lib64 /lib64 \
    --ro-bind /bin /bin \
    --ro-bind /sbin /sbin \
    --ro-bind /etc /etc \
    --proc /proc \
    --dev /dev \
    --tmpfs /tmp \
    --share-net \
    --ro-bind "$HOME/.local" "$HOME/.local" \
    --bind "$HOME/.claude" "$HOME/.claude" \
    --bind "$WORKDIR" "$WORKDIR" \
    --setenv HOME "$HOME" \
    --setenv PATH "$HOME/.local/bin:/usr/bin:/bin" \
    --chdir "$WORKDIR" \
    -- claude -p "Your prompt here" --dangerously-skip-permissions
```

**Key flags:**
- `--ro-bind source dest`: Mounts source as read-only at dest
- `--bind source dest`: Mounts source as read-write at dest
- `--tmpfs path`: Creates a temporary filesystem (not persisted)
- `--proc /proc`: Mounts proc filesystem
- `--dev /dev`: Mounts dev filesystem
- `--share-net`: Shares host network (required for API calls)
- `--setenv VAR value`: Sets environment variables inside sandbox
- `--chdir path`: Sets working directory inside sandbox

### Critical Requirements Discovered

1. **`~/.claude` MUST be read-write**: Claude Code writes session data, todos, and other state files. Without write access, Claude fails with `EROFS: read-only file system` errors.

2. **`~/.local` MUST be mounted**: The `claude` binary lives at `~/.local/bin/claude`. Without this mount, bwrap fails with `execvp claude: No such file or directory`.

3. **`~/.claude/skills` directory must exist**: Claude scans for skills at startup. Create with `mkdir -p ~/.claude/skills` if missing.

4. **Environment variables must be preserved**: `HOME` and `PATH` must be set explicitly inside the sandbox.

### Command Blocking Verification

We verified that `--disallowed-tools` works correctly with `--dangerously-skip-permissions`:

```bash
claude -p "Run git status" \
    --dangerously-skip-permissions \
    --disallowed-tools "Bash(git add:*)" "Bash(git commit:*)" "Bash(git push:*)"
```

**Behavior verified via session JSONL files:**
- `git status` executes successfully (not in disallowed list)
- `git add` returns: `"Permission to use Bash with command git add testfile.txt has been denied."`

The pattern `Bash(git add:*)` blocks any bash command starting with `git add`.

### Test Results Summary

| Test | Description | Result |
|------|-------------|--------|
| Read-only mount | Write to `--ro-bind` directory fails | PASS |
| Read-write mount | Write to `--bind` directory succeeds | PASS |
| Mixed permissions | Read-write succeeds, read-only fails in same session | PASS |
| Claude in sandbox | Claude Code CLI runs and creates files | PASS |
| Claude isolation | Claude blocked from writing to read-only paths | PASS |
| Command deny (broad) | `--disallowed-tools "Bash(git:*)"` blocks all git | PASS |
| Command deny (granular) | `git status` allowed, `git add` blocked | PASS |
| Missing ~/.local | Claude fails to start without this mount | PASS (expected failure) |

## Work Items

### 1. Extract SDK Settings Path Utility

Create utility function to eliminate duplication (prerequisite for other work):
- Add `get_sdk_settings_path()` to `src/weft/paths.py` or similar utility module
- Update `code_command.py`, `feedback_collector.py`, `test_runner.py` to use it

### 2. Create Sandbox Module

Create `src/weft/sandbox.py` with:
- `SandboxConfig` dataclass for parsed config
- `load_sandbox_config(config_path)` - loads from `.weft/config.toml`
- `build_bwrap_command(command, config, worktree_path)` - builds wrapped command
- `expand_path(path)` - handles `~` expansion
- `validate_config(config)` - errors on path collisions between lists
- Automatic mount logic for required paths
- `get_disallowed_commands(config)` - shared function for SDK and CLI

### 3. Update SDK Settings

Modify `src/weft/sdk_settings.json`:
```json
{
  "sandbox": {
    "enabled": false
  }
}
```

Remove dynamic permission injection since weft sandbox handles filesystem access.

### 4. Update SDK Runner

Modify `src/weft/sdk_runner.py`:
- Remove `add_dirs` parameter from `ClaudeAgentOptions`
- Remove or simplify `generate_sdk_settings()` (no longer needs to inject cache permissions)
- Update `can_use_tool` callback to use `get_disallowed_commands()` from sandbox module
- Remove DSPy cache permission logic

### 5. Update Host Runner

Modify `src/weft/host_runner.py`:
- Import sandbox module
- Wrap command execution with bwrap using `build_bwrap_command()`
- Pass worktree path for automatic mount
- Add `--disallowed-tools` flags for Claude Code CLI commands

### 6. Update Executors

Modify `src/weft/executors.py`:
- Ensure DroidExecutor commands go through sandboxed execution path
- No changes to command building (droid remains interactive mode)

### 7. Update Dependency Check

Modify `src/weft/code_command.py`:
- Remove `socat` from `_check_sandbox_dependencies()`
- Keep `bwrap` check (now for weft sandbox, not Claude's)
- Update error message to reference weft sandbox

### 8. Update Weft Repo Config

Add to this repo's `.weft/config.toml`:
```toml
[sandbox]
read_write_paths = ["~/.weft/dspy_cache", "~/.cache/uv"]
disallowed_commands = ["git add:*", "git commit:*", "git push:*", "docker:*"]
```

### Unit Tests

**New `tests/unit/test_sandbox.py`:**
- Test `load_sandbox_config()` with valid config
- Test `load_sandbox_config()` with missing `[sandbox]` section (defaults)
- Test `load_sandbox_config()` with empty lists
- Test `load_sandbox_config()` with invalid TOML (error handling)
- Test `load_sandbox_config()` with nonexistent file (error handling)
- Test path expansion (`~` to home directory)
- Test `validate_config()` errors on path collision (same path in read_paths and read_write_paths)
- Test `build_bwrap_command()` generates correct flags
- Test automatic mounts are always included
- Test read-only vs read-write mount flag generation (`--ro-bind` vs `--bind`)
- Test `get_disallowed_commands()` parses patterns correctly
- Test disallowed command pattern matching (`git add:*` matches `git add file.txt`)

**Update `tests/unit/test_code_command.py`:**
- Remove `test_sandbox_dependency_check_fails_when_socat_missing()`
- Update `test_sandbox_dependency_check_fails_when_both_missing()` to only check bwrap
- Update error message assertions to reference weft sandbox
- Add `test_sandbox_dependency_check_passes_when_bwrap_present()`

**Update `tests/unit/test_config.py`:**
- Add tests for `[sandbox]` section parsing
- Test default values when section missing

### Integration Tests

**Update `tests/integration/test_sdk_sandbox.py`:**
- Verify weft sandbox blocks writes to home directory
- Test should continue to pass with new implementation

**Update `tests/integration/test_sdk_dspy_cache.py`:**
The 4 existing tests in this file test `generate_sdk_settings()` permission injection which is being removed:
- `test_generate_sdk_settings_adds_cache_permissions()` - revise to verify DSPy cache access via weft sandbox config
- `test_generate_sdk_settings_preserves_existing_permissions()` - likely obsolete, remove
- `test_generate_sdk_settings_no_duplicate_rules()` - likely obsolete, remove
- `test_generate_sdk_settings_creates_missing_sections()` - likely obsolete, remove

**New `tests/integration/test_weft_sandbox.py`:**

These tests mirror the experimentation done during planning, using temporary test directories:

1. **test_sandbox_readonly_blocks_writes**
   - Create temp directory, mount as read-only in sandbox
   - Run claude code CLI (`claude -p`) with `--dangerously-skip-permissions`
   - Ask Claude to write a file to the read-only directory
   - Verify file was NOT created

2. **test_sandbox_readwrite_allows_writes**
   - Create temp directory, mount as read-write in sandbox
   - Run claude code CLI asking it to create a file using Bash tool
   - Verify file WAS created with correct content

3. **test_sandbox_isolation_mixed_permissions**
   - Create two temp directories: one read-only, one read-write
   - Run claude code CLI asking it to write to both
   - Verify: read-write succeeded, read-only failed

4. **test_disallowed_commands_blocked**
   - Configure sandbox with `disallowed_commands = ["git add:*"]`
   - Run claude code CLI asking it to run `git add`
   - Verify command was blocked (check session JSONL for permission denied)

5. **test_allowed_commands_work**
   - Configure sandbox with `disallowed_commands = ["git add:*"]`
   - Run claude code CLI asking it to run `git status` and `echo hello`
   - Verify commands succeeded

6. **test_droid_executor_in_sandbox**
   - Run `droid exec` (headless mode) inside weft sandbox
   - Verify filesystem isolation works (can write to allowed paths, blocked from others)
   - Note: Production droid runs interactive, but tests use `droid exec` for automation

7. **test_symlink_escape_blocked**
   - Create symlink inside allowed directory pointing outside
   - Verify writes through symlink are blocked

### Existing Integration Tests That Must Pass

These tests exercise affected code paths and must continue passing after implementation:

**SDK Session Tests (`tests/integration/test_sdk.py`):**
- `test_real_sdk_session_returns_session_id()`
- `test_trace_capture_from_sdk_session()`

**Network/Environment Tests (`tests/integration/test_sdk_network.py`):**
- `test_sdk_network_succeeds_with_no_proxy()`
- `test_no_proxy_restored_after_successful_session()`
- `test_no_proxy_restored_on_sdk_error()`

**Sandbox Tests (`tests/integration/test_sdk_sandbox.py`):**
- `test_sdk_sandbox_blocks_write_to_home_directory()` - validates sandbox blocks writes to ~

## Deliverables

1. New `src/weft/sandbox.py` module
2. New/updated utility module with `get_sdk_settings_path()`
3. Updated `src/weft/sdk_runner.py` (simplified)
4. Updated `src/weft/host_runner.py` (bwrap integration)
5. Updated `src/weft/code_command.py` (socat removal)
6. Updated `src/weft/sdk_settings.json` (minimal)
7. New/updated unit tests
8. New/updated integration tests
9. Updated `.weft/config.toml` for this repo

## Out of Scope

- Network isolation (weft sandbox only isolates filesystem, not network)
- Windows/macOS support (bwrap is Linux-only)
- GUI/interactive sandbox configuration
- Per-session sandbox overrides
- Sandbox for non-executor code paths
- Command blocking for Droid (filesystem isolation only)
