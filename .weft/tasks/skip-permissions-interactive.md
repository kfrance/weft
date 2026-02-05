---
plan_id: skip-permissions-interactive
status: done
evaluation_notes: []
git_sha: 3468c34626258be9cf41f592d2c98579f81fbfa1
---

# Skip Permissions for Interactive Code and Plan Commands

## Objectives

Add `--dangerously-skip-permissions` and `--disallowed-tools` to Claude Code CLI invocations in `weft code` (CLI resume phase) and `weft plan` (interactive phase), so that Claude Code does not prompt for tool approvals when running inside weft's bwrap sandbox, while still hard-blocking specific commands from `config.toml`. The `weft finalize` command is explicitly excluded — it must continue prompting for user approval on destructive operations like `git add` and `git push`.

## Requirements & Constraints

- **`weft code` CLI resume**: The command `claude -r <session_id> --model <model>` (built directly in `code_command.py:739`) must include `--dangerously-skip-permissions` and `--disallowed-tools` args from sandbox config.
- **`weft plan` interactive**: The command built by `ClaudeCodeExecutor.build_command()` (called from `plan_command.py:305`) must include `--dangerously-skip-permissions` and `--disallowed-tools` args.
- **`weft plan` headless**: Uses `-p` flag which already runs non-interactively. Include both flags for consistency.
- **`weft finalize`**: Must NOT include either flag. The finalize command intentionally requires user approval for git operations.
- **Existing `.claude/settings.json`**: No special handling needed. `--dangerously-skip-permissions` fully overrides Claude Code's permission system — it bypasses both the ask list and the deny list in settings.json. The `--disallowed-tools` flag then re-adds hard blocks for specific commands.
- **SDK phase of `weft code`**: Not in scope. Already uses `permission_mode="acceptEdits"` with a `can_use_tool` callback that enforces the same `disallowed_commands`.
- **Other executors (DroidExecutor)**: New parameters are accepted but ignored, following the existing pattern for the `headless` parameter.

### CLI Flag Behavior (verified by manual testing)

- `--dangerously-skip-permissions` bypasses **all** permission checks in Claude Code, including both the ask list and the deny list in `.claude/settings.json`. Any command will run without prompting.
- `--disallowed-tools "Bash(git commit:*)"` hard-blocks matching commands even when `--dangerously-skip-permissions` is active. Claude receives a denial message and cannot execute the command at all.
- When combining both flags, the `--disallowed-tools` variadic argument consumes subsequent positional arguments. Use `--` separator before the prompt argument, or pass the prompt via stdin. This matters for `build_command()` which embeds the prompt in the command string — the `--disallowed-tools` args must come **after** the prompt argument, or the prompt must be separated with `--`.
- `get_disallowed_tools_args()` in `sandbox.py` already builds the correct CLI format from `config.toml`'s `disallowed_commands` (e.g., `["--disallowed-tools", "Bash(git add:*)", "Bash(git commit:*)"]`). It is currently unused — this plan wires it up.

## Work Items

### 1. Add `skip_permissions` parameter to `Executor.build_command()`

**File**: `src/weft/executors.py`

Add a `skip_permissions: bool = False` parameter to the abstract `build_command()` method on the `Executor` base class and both implementations:

- **`ClaudeCodeExecutor.build_command()`**: When `skip_permissions=True`, append `--dangerously-skip-permissions` to the command string.
- **`DroidExecutor.build_command()`**: Accept the parameter, ignore it (same pattern as `headless`).

### 2. Add `disallowed_tools` parameter to `Executor.build_command()`

**File**: `src/weft/executors.py`

Add a `disallowed_tools: list[str] | None = None` parameter to the abstract `build_command()` method and both implementations:

- **`ClaudeCodeExecutor.build_command()`**: When provided, append the args to the command string. These are the pre-formatted args from `get_disallowed_tools_args()` (e.g., `["--disallowed-tools", "Bash(git add:*)", ...]`). Place them **before** the prompt argument in the command string to avoid the variadic flag consuming the prompt.
- **`DroidExecutor.build_command()`**: Accept the parameter, ignore it.

### 3. Update `weft code` CLI resume command

**File**: `src/weft/code_command.py` (~line 739)

The CLI resume command is built directly (not through the executor) because resume is Claude-specific. Add `--dangerously-skip-permissions` to the command string. Also call `get_disallowed_tools_args(sandbox_config)` and append the result — `sandbox_config` is already loaded and in scope at this point.

Include an inline comment noting this is a parallel code path to `ClaudeCodeExecutor.build_command(skip_permissions=True, disallowed_tools=...)` so future developers keep them in sync.

### 4. Update `weft plan` to pass permission flags

**File**: `src/weft/plan_command.py` (~line 305)

- Load `sandbox_config` from `.weft/config.toml` (same pattern as `code_command.py:501-512`).
- Call `get_disallowed_tools_args(sandbox_config)` to get the CLI args.
- Pass `skip_permissions=True` and `disallowed_tools=get_disallowed_tools_args(sandbox_config)` to `executor.build_command()`.

### 5. Document finalize exclusion

**File**: `src/weft/finalize_command.py` (~line 273)

No code change needed — both `skip_permissions` and `disallowed_tools` default to `False`/`None`. Add a code comment documenting that this is intentional, since finalize requires user approval for git operations.

### 6. Unit Tests

**File**: `tests/unit/test_executors.py`

- Add parametrized tests for `ClaudeCodeExecutor.build_command()` with `skip_permissions=True` and `skip_permissions=False`, verifying the flag is present/absent in the command string.
- Add tests for `disallowed_tools` parameter: verify the args appear in the command string when provided, and are absent when `None`.
- Add a combination test for `headless=True` + `skip_permissions=True` + `disallowed_tools=[...]` to verify all flags coexist correctly in the command.
- Verify that `--disallowed-tools` args are placed before the prompt argument in the command string (to avoid the variadic flag consuming the prompt).
- Fix the brittle assertion in `test_build_command_produces_safe_commands` (line 230): replace `command.count("--") == 1` with explicit verification of expected flags (e.g., check that `--model` appears and no unexpected flags are present, rather than counting all `--` occurrences).
- Add a test verifying `DroidExecutor.build_command()` accepts `skip_permissions` and `disallowed_tools` without error and ignores them.

**File**: `tests/unit/test_code_command.py`

- In `test_code_command_patch_capture_workflow`, update the mock `subprocess.run` to capture and verify that the CLI resume command includes `--dangerously-skip-permissions` and `--disallowed-tools`.

**File**: `tests/unit/test_plan_command.py`

- Add a test that mocks `executor.build_command()` and verifies `skip_permissions=True` and `disallowed_tools` are passed when the plan command runs.

**File**: `tests/unit/test_finalize_command.py`

- Add a regression guard test verifying that the finalize command's `executor.build_command()` call does NOT pass `skip_permissions=True` or `disallowed_tools` (or that the resulting command does not contain `--dangerously-skip-permissions` or `--disallowed-tools`).

**File**: `tests/conftest.py`

- Update `mock_executor_factory` fixture to accept the new `skip_permissions` and `disallowed_tools` parameters in its `build_command` mock, so existing tests continue to work.

### 7. Integration Tests

The following existing integration tests must pass:

- `tests/integration/test_headless.py::TestCodeHeadless::test_code_command_runs_sdk_in_headless`
- `tests/integration/test_headless.py::TestPlanHeadless::test_plan_command_loads_prompts_and_runs`
- `tests/integration/test_command_smoke.py::TestPlanCommandSmoke::test_plan_command_setup_completes`
- `tests/integration/test_command_smoke.py::TestCodeCommandSmoke::test_code_command_setup_completes`
- `tests/integration/test_finalize_flow.py::test_finalize_flow_orchestration`
- `tests/integration/test_sdk_sandbox.py::TestBwrapSandboxOperational::test_bwrap_sandbox_blocks_write_to_home_directory`
- `tests/integration/test_sdk_sandbox.py::TestBwrapSandboxOperational::test_bwrap_sandbox_allows_write_to_worktree`
- `tests/integration/test_sdk_sandbox.py::TestBwrapSandboxOperational::test_bwrap_sandbox_allows_write_to_configured_paths`

## Deliverables

1. Modified `src/weft/executors.py` with `skip_permissions` and `disallowed_tools` parameters on `Executor.build_command()` and both implementations
2. Modified `src/weft/code_command.py` with both flags on CLI resume command + sync comment
3. Modified `src/weft/plan_command.py` loading sandbox config and passing both flags
4. Comment in `src/weft/finalize_command.py` documenting intentional omission
5. Updated `tests/conftest.py` mock_executor_factory fixture
6. Updated and new unit tests in `tests/unit/test_executors.py`, `tests/unit/test_code_command.py`, `tests/unit/test_plan_command.py`, `tests/unit/test_finalize_command.py`
7. All listed integration tests passing

## Out of Scope

- SDK phase of `weft code` (already uses `permission_mode="acceptEdits"` with `can_use_tool` callback)
- Modifying or generating `.claude/settings.json` or `.claude/settings.local.json` files
- Changes to the bwrap sandbox configuration
- Changes to `weft finalize` permission behavior
- Adding a config option to toggle the permission bypass
- Refactoring the `Executor` abstraction (noted as future consideration when Claude-specific parameters exceed 3-4)
