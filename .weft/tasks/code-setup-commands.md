---
plan_id: code-setup-commands
status: done
evaluation_notes: []
git_sha: 318d0d46097ac2d19707581aa3443bb4fd3faa91
---

# Pre-Execution Setup Commands for Code Command

## Objectives

Enable developers to run arbitrary setup commands on the host system before the sandboxed `weft code` session begins. This allows preparation of the execution environment (starting services, configuring system resources, etc.) that cannot be done from within the sandbox.

## Requirements & Constraints

### Functional Requirements

1. Setup commands are defined in the **repository's** `.weft/config.toml` file using `[[code.setup]]` sections
2. Each command has: `name` (required), `command` (required), `working_dir` (optional), `continue_on_failure` (optional)
3. Commands execute sequentially on the host system after worktree creation but before the Claude Code session
4. Commands inherit the current shell environment plus weft-specific variables:
   - `WEFT_REPO_ROOT` - absolute path to repository root
   - `WEFT_WORKTREE_PATH` - absolute path to created worktree
   - `WEFT_PLAN_ID` - identifier of the current plan
   - `WEFT_PLAN_PATH` - path to the plan file
5. Commands run from the repository root by default, with optional per-command `working_dir` override
6. Command output is captured; shown only when a command fails
7. Failed commands abort execution by default; `continue_on_failure = true` allows non-critical commands

### Configuration Schema

```toml
[[code.setup]]
name = "start-services"           # Required: descriptive name
command = "docker-compose up -d"  # Required: shell command to run
working_dir = "./services"        # Optional: relative to repo root, defaults to repo root
continue_on_failure = true        # Optional: defaults to false (abort on failure)
```

### Constraints

- Commands run on the host with full system access (trusted because user configures them in their repo)
- Commands execute synchronously via `subprocess.run()` with `shell=True`
- No timeout enforcement - commands that hang will block (documented limitation)
- Injected `WEFT_*` variables override any existing environment variables with the same names

## Work Items

### 1. Create setup_commands module

Create `src/weft/setup_commands.py` with:

- `SetupCommand` dataclass: name, command, working_dir (Optional[str]), continue_on_failure (bool)
- `load_setup_commands(repo_root: Path) -> list[SetupCommand]`: Parse `[[code.setup]]` sections using existing `load_repo_config()` from `file_sync.py`
- `run_setup_commands(commands, repo_root, worktree_path, plan_id, plan_path) -> None`: Execute commands sequentially with environment injection
- Validation: required fields, reject unknown keys, validate working_dir exists and is within repo
- Output capture and display on failure (include command name, working_dir, and captured output in error)
- Security comment explaining trust model (following `hooks.py` pattern)

### 2. Integrate with code_command.py

Modify `run_code_command()` to:

- Load setup commands from repo config after worktree creation
- Execute setup commands before Claude Code session starts
- Add comment explaining why setup runs at this point (needs worktree path, must be before sandbox)
- Handle `SetupCommandError` and display appropriate error messages
- Log setup command execution at info level (command name only, not full command for security)

### 3. Update init_command.py config template

Modify the `_CONFIG_TEMPLATE` constant in `init_command.py` to include a commented example of setup commands, so new repositories created with `weft init` will have this example in their `.weft/config.toml`:

```toml
# Setup commands run on the host before the coding session (optional)
# Commands execute sequentially after worktree creation.
# Available environment variables: WEFT_REPO_ROOT, WEFT_WORKTREE_PATH, WEFT_PLAN_ID, WEFT_PLAN_PATH
#
# [[code.setup]]
# name = "start-services"
# command = "docker-compose up -d"
# working_dir = "./services"        # Optional: defaults to repo root
# continue_on_failure = false       # Optional: defaults to false
```

### 4. Update documentation

Update `docs/CONFIGURATION.md` with:

- New "Setup Commands" section
- Configuration schema and all options
- Example use cases
- Environment variables available to commands
- Error handling behavior
- Documented limitation: no timeout (hanging commands will block)

### 5. Update threat model

Update `docs/THREAT_MODEL.md`:

- Add new "Setup Command Execution Security" subsection after "Hook Execution Security" (around line 127)
- Document the trust model: user initiates `weft code` in their own repo, opting into the repo's setup commands
- Risk accepted: cloning and running `weft code` on an untrusted repo could execute malicious commands
- Justification: same trust model as npm scripts, Makefiles, git hooks in repos
- Mitigation: commands only run when user explicitly invokes `weft code`
- Update "Future Considerations" section to note that project-level command execution is now implemented via setup commands

### Unit Tests

`tests/unit/test_setup_commands.py`:

**Config Loading:**
- Test `load_setup_commands()` with valid config
- Test `load_setup_commands()` with missing required fields (name, command)
- Test `load_setup_commands()` with unknown keys (should raise error)
- Test `load_setup_commands()` with no setup commands configured (returns empty list)
- Test `load_setup_commands()` with empty/whitespace-only command string (should raise error)

**Command Execution:**
- Test `run_setup_commands()` executes commands in order
- Test `run_setup_commands()` injects WEFT_* environment variables
- Test `run_setup_commands()` injected vars override existing environment variables

**Working Directory:**
- Test `run_setup_commands()` uses repo root as default working directory
- Test `run_setup_commands()` resolves custom working_dir relative to repo root
- Test `run_setup_commands()` with invalid working_dir (non-existent) raises error
- Test `run_setup_commands()` with working_dir outside repo raises error
- Test `run_setup_commands()` with `.` and `..` in working_dir paths

**Failure Handling:**
- Test `run_setup_commands()` aborts on first failure by default
- Test `run_setup_commands()` continues when continue_on_failure=true
- Test `run_setup_commands()` with multiple failures (first continues, second aborts)
- Test `run_setup_commands()` captures and displays output on failure
- Test `run_setup_commands()` succeeds silently when commands pass

### Integration Tests

- `tests/integration/test_command_smoke.py::TestCodeCommandSmoke.test_code_command_setup_completes` - must continue to pass (setup commands not configured, gracefully skipped)
- `tests/integration/test_setup_commands.py::test_setup_commands_execute_before_session` - new test that:
  - Creates a repo with two simple setup commands:
    1. `touch $WEFT_WORKTREE_PATH/.setup-first`
    2. `touch $WEFT_WORKTREE_PATH/.setup-second`
  - Mocks the Claude Code SDK/CLI session
  - Runs `run_code_command()`
  - Verifies both marker files exist in the worktree (proving commands ran with correct environment)
  - Verifies the mocked session was called (proving setup ran before session)

## Deliverables

- New file: `src/weft/setup_commands.py`
- New file: `tests/unit/test_setup_commands.py`
- New file: `tests/integration/test_setup_commands.py`
- Modified: `src/weft/code_command.py`
- Modified: `src/weft/init_command.py`
- Modified: `docs/CONFIGURATION.md`
- Modified: `docs/THREAT_MODEL.md`

## Out of Scope

- Command timeouts (documented limitation)
- Parallel command execution
- Command dependencies or ordering beyond sequential
- Teardown/cleanup commands after session ends
- User-level (`~/.weft/config.toml`) setup commands (repo-level only)
- Variable substitution in command strings (use environment variables instead)
