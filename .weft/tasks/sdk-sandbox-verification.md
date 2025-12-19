---
plan_id: sdk-sandbox-verification
status: done
evaluation_notes: []
git_sha: f556fa316a5bb71a0fdc23fed44215d627f0d394
---

# SDK Sandbox Verification

## Objectives

1. Add a preflight check to the `code` command that verifies sandbox dependencies (`bubblewrap`, `socat`) are installed before starting a session
2. Create an integration test that verifies Claude Code's sandbox is operational and blocking file writes outside allowed directories

The preflight check catches missing dependencies at runtime. The integration test catches sandbox failures in CI and verifies the sandbox actually works (not just that dependencies are present).

## Requirements & Constraints

### Functional Requirements

#### Preflight Dependency Check
- `code` command must verify `bubblewrap` (`bwrap`) and `socat` are installed before starting
- If either is missing, fail immediately with a clear error message listing what to install
- Check must happen early, before any SDK session setup
- Error message must be actionable (e.g., "Install with: sudo apt install bubblewrap socat")

#### Integration Test
- Test must detect when sandbox is non-functional (file write succeeds)
- Test must pass when sandbox is functional (file write blocked)
- Test must clean up any created files regardless of test outcome
- Test must use a path outside the sandbox allowlist (`~` is blocked; `/tmp` is allowed)
- **Module docstring** must explain:
  - This test verifies the sandbox is **operational on the current system**, not that the SDK's sandbox logic is correct
  - Real-world problem: On a new system, sandbox can silently fail if `bubblewrap` and `socat` aren't installed
  - Why this matters: User believes they're protected but writes are actually allowed
  - Why we test `~` not `/tmp`: The sandbox allowlist includes `/tmp`, so writes there succeed even with working sandbox
  - This is an **environmental/operational** test, not a **unit/integration** test of lw_coder code
- **Test docstring** must explain:
  - The specific failure mode this catches (missing system dependencies)
  - Why the test writes to home directory (outside sandbox allowlist)
  - What to do if this test fails (install bubblewrap and socat)
- **Inline comments** must explain:
  - Why `Path.home()` is used (consistent cross-platform home directory)
  - Why we check for pre-existing file (avoid false positive from previous failed run)
  - Why cleanup is in `finally` (guarantee no pollution even on assertion failure)
  - Why we use explicit Bash command in prompt (avoid LLM interpretation ambiguity)

### Technical Constraints
- **Dependency check**: Use `shutil.which()` to check for `bwrap` and `socat` binaries
- **Home directory target**: Uses `~/test.txt` because `/tmp` is within sandbox allowlist
- **Cleanup guarantee**: Must use `finally` block to ensure cleanup even on test failure
- **Explicit prompt**: Must instruct Claude to use specific Bash command, not rely on LLM interpretation
- **Integration test**: Makes real SDK API calls; belongs in `tests/integration/`

### Non-Goals
- This test does NOT verify comprehensive sandbox coverage (all blocked paths)
- This test does NOT validate sandbox implementation details
- This is a smoke test for operational sandbox availability

## Work Items

### 1. Add sandbox dependency check to `src/lw_coder/code_command.py`

**Objective**: Fail fast with clear error if sandbox dependencies are missing.

**New function: `_check_sandbox_dependencies()`**
- Use `shutil.which("bwrap")` and `shutil.which("socat")` to check for binaries
- If either is missing, raise an error with:
  - Which dependencies are missing
  - How to install them (e.g., `sudo apt install bubblewrap socat`)
  - Why they're needed (Claude Code sandbox requires them)
- Add docstring explaining this prevents silent sandbox failures

**Call location**: Early in the code command execution, before SDK session setup

**Error class**: Can use existing `CodeCommandError` or create specific `SandboxDependencyError`

### 2. Create `tests/integration/test_sdk_sandbox.py`

**Objective**: Integration test that verifies sandbox blocks writes to home directory.

**Test: `test_sdk_sandbox_blocks_write_to_home_directory`**

Test structure:
1. Calculate target path: `Path.home() / "test.txt"`
2. Ensure target doesn't already exist (fail fast if it does, to avoid false positives)
3. Create SDK settings with `{"sandbox": {"enabled": true}}`
4. Run SDK session with explicit prompt: "Use the Bash tool to run: `echo 'hello world' > ~/test.txt`"
5. After session completes, check if target file exists
6. In `finally` block: delete target file if it exists
7. Assert: file should NOT exist (sandbox blocked the write)

**Assertions**:
- If file exists after SDK session: `pytest.fail()` with message explaining sandbox is non-functional and how to fix it
- If file doesn't exist: test passes

**Model**: Use `haiku` for speed/cost efficiency (same as other SDK integration tests)

### 3. Add unit test for dependency check

**Objective**: Unit test the dependency check function without requiring real binaries.

**File**: `tests/unit/test_code_command.py` (or new file if needed)

**Test cases**:
- `test_sandbox_dependency_check_passes_when_both_installed`: Mock `shutil.which` to return paths, verify no error
- `test_sandbox_dependency_check_fails_when_bwrap_missing`: Mock `shutil.which` to return `None` for bwrap, verify error with correct message
- `test_sandbox_dependency_check_fails_when_socat_missing`: Mock `shutil.which` to return `None` for socat, verify error with correct message
- `test_sandbox_dependency_check_fails_when_both_missing`: Mock both missing, verify error lists both

## Deliverables

### Code Changes

**File**: `src/lw_coder/code_command.py`
- New `_check_sandbox_dependencies()` function
- Call to check function early in code command execution

### Integration Tests

**File**: `tests/integration/test_sdk_sandbox.py`

| Test | Purpose |
|------|---------|
| `test_sdk_sandbox_blocks_write_to_home_directory` | Verifies sandbox is operational by attempting blocked write |

### Unit Tests

**File**: `tests/unit/test_code_command.py` (or appropriate location)

| Test | Purpose |
|------|---------|
| `test_sandbox_dependency_check_passes_when_both_installed` | Verify check passes with dependencies |
| `test_sandbox_dependency_check_fails_when_bwrap_missing` | Verify clear error when bwrap missing |
| `test_sandbox_dependency_check_fails_when_socat_missing` | Verify clear error when socat missing |
| `test_sandbox_dependency_check_fails_when_both_missing` | Verify error lists all missing deps |

## Out of Scope

### Not Included
- Testing writes to other blocked paths (e.g., `/etc`, `/usr`)
- Testing sandbox allows writes to permitted paths (worktree, `/tmp`)
- Verifying specific error messages from sandbox violations
- Testing sandbox behavior with different SDK settings
- Cross-platform support (this is Linux-specific; bubblewrap doesn't exist on macOS/Windows)

### Future Enhancements
- Add parametrized tests for multiple blocked paths
- Add positive test that writes to worktree succeed
- Capture SDK logs/traces to verify sandbox actively blocked (not just file absence)
- Platform-specific sandbox dependency checks (different sandboxing on macOS)
