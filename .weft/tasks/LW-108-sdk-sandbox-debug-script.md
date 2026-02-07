---
plan_id: LW-108-sdk-sandbox-debug-script
status: done
evaluation_notes: []
git_sha: b6653e38acc1f42ca7e90a3162936716b9948bb4
---

# LW-108: Create manual SDK runner / sandbox debug script

## Objectives

Create a lightweight standalone script at `scripts/test_sdk_headless.py` that enables manual testing and debugging of the SDK runner and bwrap sandbox without going through the full `weft code` workflow. The script supports two modes: running a Claude Code SDK session with an arbitrary prompt, or running an arbitrary bash command inside the bwrap sandbox.

## Requirements & Constraints

- **Location**: `scripts/test_sdk_headless.py`, runnable from repo root
- **Pattern**: Follow existing script conventions (see `scripts/generate_template_version.py`) — use `sys.path.insert` for imports
- **Two subcommands**:
  - `sdk <prompt>` — run an SDK session with the given prompt
  - `bash <command>` — run a bash command inside the bwrap sandbox
- **Shared options**:
  - `--workdir <path>` — target directory (default: current working directory)
  - `--no-sandbox` — bypass sandbox isolation
- **SDK-specific options**:
  - `--model <model>` — override model selection (uses `get_effective_model()` 3-tier precedence: CLI flag > config.toml `[defaults].code_model` > hardcoded default "sonnet")
- **Config loading**: Auto-detect repo root via `find_repo_root()`, then load sandbox config from `.weft/config.toml` via `load_sandbox_config()`
- **Output**: Both modes stream stdout/stderr to the terminal
- **Exit codes**: Forward the exit code from the sandboxed command (bash mode) or SDK session (SDK mode)
- **Verbose mode**: `--verbose` flag enables debug-level logging for troubleshooting the script itself
- **Error handling**: Clear, actionable error messages for common failures (bwrap not installed, not in a git repo, SDK settings missing)
- **No automated tests**: The underlying modules are already well-tested; this is a manual debugging tool

## Work Items

### 1. Create `scripts/test_sdk_headless.py`

Create the script with the following structure:

**Argument parsing** (argparse with subcommands):
- `sdk` subcommand: positional `prompt` argument, optional `--model`
- `bash` subcommand: positional `command` argument
- Shared: `--workdir` (default `.`), `--no-sandbox` flag, `--verbose` flag

**Logging setup**:
- If `--verbose`, configure logging at DEBUG level; otherwise WARNING level
- Uses weft's `get_logger()` for consistency

**Config loading** (shared between both modes):
- Resolve `--workdir` to an absolute path; exit with clear error if it doesn't exist
- Call `find_repo_root(workdir)` to locate the repository root; exit with actionable message if not in a git repo
- Load sandbox config from `<repo_root>/.weft/config.toml` via `load_sandbox_config()`
- If `--no-sandbox` is set, use an empty `SandboxConfig()` instead

**SDK mode** (`sdk` subcommand):
- Resolve model via `get_effective_model(args.model, "code")`
- Locate SDK settings via `get_sdk_settings_path()`
- Call `run_sdk_session_sync()` with:
  - `worktree_path`: the resolved workdir
  - `prompt_content`: the positional prompt argument
  - `model`: resolved model
  - `sdk_settings_path`: from `get_sdk_settings_path()`
  - `sandbox_config`: loaded config (or `None` if `--no-sandbox`)
- Print the returned session ID
- Exit 0 on success, 1 on `SDKRunnerError`

**Bash mode** (`bash` subcommand):
- If `--no-sandbox`:
  - Run the command directly via `subprocess.run(["bash", "-c", command], cwd=workdir)`
- If sandbox enabled:
  - Derive `repo_git_dir` from `<repo_root>/.git`
  - Call `build_bwrap_command(command, sandbox_config, workdir, repo_git_dir)`
  - Run the resulting command list via `subprocess.run(cmd, cwd=workdir)`
- Forward the subprocess exit code as the script's exit code

### Unit Tests

No unit tests — this is a manual debugging tool and the underlying modules (`sandbox.py`, `sdk_runner.py`, `param_validation.py`, `repo_utils.py`) are already well-covered.

### Integration Tests

No new integration tests. The following existing integration tests must continue to pass (they cover the modules this script depends on):

- `tests/integration/test_sdk_sandbox.py` — bwrap sandbox filesystem isolation
- `tests/integration/test_sdk.py` — real SDK session execution
- `tests/integration/test_headless.py` — headless SDK execution flow

## Deliverables

- `scripts/test_sdk_headless.py` — the new debugging script

## Out of Scope

- Worktree creation (the script operates on an existing directory)
- Plan validation, prompt loading, session management, file sync, hooks
- Sub-agent registration (SDK sessions run without agents)
- CLI resume after SDK session (debugging only needs the SDK phase)
- Automated tests for the script itself
- Modifications to existing modules
