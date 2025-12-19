---
plan_id: configurable-viewer-hooks
status: done
git_sha: a59340cdec9471939c45e6a1dbe7e747cb8ad3cd
evaluation_notes: []
---

# Configurable Viewer Hooks

## Objectives

- Add configurable hook system to open viewers/editors at key workflow points
- Enable users to customize post-execution actions (e.g., open code-oss after plan creation)
- Implement safe command execution with proper security safeguards
- Support three hook points: plan_file_created, code_sdk_complete, eval_complete
- Use global configuration file at `~/.lw_coder/config.toml`

## Requirements & Constraints

### Functional Requirements

**1. Configuration File**
- Location: `~/.lw_coder/config.toml`
- Global user config only (no project-level config for security)
- TOML format with hooks section
- Example structure:
  ```toml
  [hooks.plan_file_created]
  command = "code-oss ${worktree_path}"
  enabled = true

  [hooks.code_sdk_complete]
  command = "code-oss ${worktree_path}"
  enabled = true

  [hooks.eval_complete]
  command = "code-oss ${training_data_dir}"
  enabled = true
  ```

**2. Hook Points**
- **plan_file_created**: When plan file appears in `.lw_coder/tasks/` during interactive session
  - Timing: During plan session (file watcher)
  - Variables: `worktree_path`, `plan_path`, `plan_id`, `repo_root`

- **code_sdk_complete**: After SDK session completes, before CLI resume
  - Timing: Between SDK finishing and CLI launching
  - Variables: `worktree_path`, `plan_path`, `plan_id`, `repo_root`

 **eval_complete**: After evaluation finishes and training data created
  - Timing: After training data export succeeds
  - Variables: `training_data_dir`, `worktree_path`, `plan_path`, `plan_id`, `repo_root`

**3. Variable Substitution**
- Use `${variable}` syntax (similar to shell variables)
- Available variables per hook documented above
- All paths are absolute Path objects converted to strings
- Validation: Raise clear error if undefined variable used
- Use Python's string.Template for safe substitution

**4. Command Execution**
- Asynchronous (background) execution - commands run without blocking
- Use subprocess.Popen with argument lists (NOT shell=True)
- Parse commands with shlex.split for proper shell word splitting
- Track spawned processes for cleanup on exit
- Hooks execute even if process fails - failures don't block main workflow

**5. Error Handling**
- Hook failures logged but don't fail main command
- Clear user feedback when hooks execute
- Log hook execution details to `~/.lw_coder/logs/hooks-YYYY-MM-DD.log`
- Structured logging with command, variables, success/failure
- Show warnings for hook failures but continue workflow

**6. CLI Integration**
- Add `--no-hooks` flag to all commands to disable hook execution
- Global flag that works with: plan, code, eval commands
- When disabled, log message: "Hooks disabled via --no-hooks flag"

### Security Considerations

**Command Execution Trust Model**
- Hooks execute commands configured by the developer in their own `~/.lw_coder/config.toml`
- This is the developer's own machine and configuration - no untrusted input
- Similar to shell aliases, git hooks, or npm scripts - trusted developer configurations
- See `docs/adr/NNN-hook-injection-trust.md` and `docs/THREAT_MODEL.md` for detailed rationale

**Implementation Approach**
- Use shell=True for simplicity (developer controls the command)
- Variable substitution uses string.Template for clarity
- No complex argument list parsing needed
- Focus on usability over defense-in-depth (developer is the user, not an attacker)

**Process Lifecycle Management**
- Track all spawned processes in HookManager
- Register atexit handler to clean up processes on CLI exit
- Terminate child processes gracefully (terminate, then kill if needed)
- Prevent zombie/orphan processes
- Prune completed processes from tracking list to avoid memory leaks

**Configuration Validation**
- Validate TOML syntax on load
- Check that hook names are recognized
- Validate 'enabled' is boolean
- Provide clear error messages for config problems
- Fail gracefully if config file is malformed

### Technical Constraints

**1. File Watcher Implementation**
- Use watchdog library for cross-platform file watching
- Watch `.lw_coder/tasks/` directory in worktree during plan session
- Start watcher before launching interactive session
- Stop watcher after session completes
- Handle race conditions: verify file exists and has content before triggering
- Debounce: Wait 100ms after file creation to ensure write is complete
- Timeout: Stop watching after plan session exits

**2. Module Structure**
- New module: `src/lw_coder/hooks.py`
  - `HookManager` class for lifecycle management
  - `load_hook_config()` - Load and validate TOML config
  - `substitute_variables()` - Safe variable substitution
  - `execute_hook()` - Safe command execution
  - `trigger_hook()` - Public API for triggering hooks
- Integration points:
  - `plan_command.py` - plan_file_created hook with file watcher
  - `code_command.py` - code_sdk_complete hook
  - `eval_command.py` - eval_complete hook (after round-out-eval-command plan)
- Note: eval_complete hook integration is blocked by round-out-eval-command plan

**3. Logging Configuration**
- Hook logs separate from main application logs
- Location: `~/.lw_coder/logs/hooks-YYYY-MM-DD.log`
- Daily log rotation (keep last 7 days)
- Log format: timestamp, hook_name, command, variables, result
- Use Python's logging module with RotatingFileHandler
- Console feedback: "[dim]→ Running {hook_name} hook in background[/dim]"

**4. Dependencies**
- Add `watchdog` to pyproject.toml for file watching
- Use stdlib: pathlib, logging, subprocess, atexit, string
- Already have: tomli (for TOML parsing)

**5. Testing Strategy**
- Dependency injection: HookManager accepts ProcessExecutor interface
- Mock executor for unit tests (captures commands without executing)
- Integration tests with real subprocess (mark with @pytest.mark.integration)
- Test file watcher with temporary directories
- Test config validation and error handling
- Test process cleanup on exit

### Design Constraints

**1. Configuration Scope**
- Global user config ONLY (`~/.lw_coder/config.toml`)
- NO project-level config (`.lw_coder/config.toml` in repo)
- Reason: Security - project config could execute malicious commands
- Future: Could add project config with security review/approval flow

**2. Execution Model**
- All hooks run asynchronously (background)
- Main workflow doesn't wait for hooks to complete
- Hook failures don't block or fail main command
- User sees brief notification that hook executed
- Detailed output/errors go to log file

**3. Variable Expansion**
- Only predefined variables available (no arbitrary environment variables)
- Variables are Path objects converted to strings
- All paths are absolute
- No recursive substitution (${${var}} not supported)
- Clear error if undefined variable referenced

**4. Hook Configuration**
- Each hook has: command (string), enabled (boolean)
- Optional future: timeout, retry_count, env_vars
- No conditional execution (always run if enabled)
- No hook dependencies or ordering (future enhancement)

## Work Items

### 1. Create Hook Manager Infrastructure

**1.1 Create hooks.py module**
- File: `src/lw_coder/hooks.py`
- Classes: `HookManager`, `ProcessExecutor` (Protocol)
- Functions: `load_hook_config()`, `substitute_variables()`, `execute_hook()`
- Exceptions: `HookError`, `HookConfigError`

**1.2 Implement ProcessExecutor protocol**
- Define Protocol for dependency injection:
  ```python
  from typing import Protocol

  class ProcessExecutor(Protocol):
      def execute(self, command: str) -> None:
          """Execute command string with shell"""
          ...
  ```
- Implement RealProcessExecutor using subprocess.Popen with shell=True
- Implement MockProcessExecutor for testing

**1.3 Implement HookManager class**
- Singleton pattern for process tracking
- Methods:
  - `__init__(executor: ProcessExecutor = None)`
  - `execute_hook(hook_name: str, config: dict, variables: dict[str, Path])`
  - `_cleanup()` - atexit handler for process cleanup
  - `_prune_completed()` - Remove finished processes from tracking
- Track spawned processes in list
- Register atexit handler in __init__

**1.4 Implement config loading**
- Function: `load_hook_config() -> dict`
- Load from `~/.lw_coder/config.toml`
- Return empty dict if file doesn't exist (hooks disabled)
- Validate TOML syntax with try/except
- Validate hook structure (enabled is bool, command is string)
- Log config load success/failure
- Cache loaded config (reload on each trigger is expensive)

**1.5 Implement variable substitution**
- Function: `substitute_variables(command: str, variables: dict[str, Path]) -> str`
- Use string.Template for substitution
- Convert Path objects to strings in variable dict
- Substitute variables with ${variable} syntax
- Raise HookError if undefined variable referenced
- Return substituted command string ready for shell=True
- Example:
  ```python
  from string import Template

  command = "code-oss ${worktree_path} --new-window"
  variables = {"worktree_path": Path("/tmp/worktree")}

  # Convert paths to strings
  str_vars = {k: str(v) for k, v in variables.items()}

  # Substitute and return
  template = Template(command)
  return template.substitute(str_vars)  # Returns: "code-oss /tmp/worktree --new-window"
  ```

**1.6 Add error handling**
- Define custom exceptions:
  - `HookError(Exception)` - Base exception for hook errors
  - `HookConfigError(HookError)` - Config loading/validation errors
- Catch FileNotFoundError for missing executables
- Catch subprocess errors
- Log all errors with full context
- Show user-friendly warnings in console

**1.7 Add logging infrastructure**
- Create `~/.lw_coder/logs/` directory on first use
- Configure daily rotating file handler
- Log format: `%(asctime)s [%(levelname)s] %(message)s`
- Log hook execution: name, command template, substituted args, result
- Log errors with full exception details
- Console output: Brief notification using rich console

### 2. Implement File Watcher for plan_file_created Hook

**2.1 Add watchdog dependency**
- Update `pyproject.toml`:
  ```toml
  dependencies = [
      "watchdog>=3.0.0",
      # ... existing dependencies
  ]
  ```

**2.2 Create file watcher helper**
- File: `src/lw_coder/file_watcher.py`
- Class: `PlanFileWatcher`
- Methods:
  - `__init__(watch_dir: Path, on_file_created: Callable[[Path], None])`
  - `start()` - Start watching in background thread
  - `stop()` - Stop watching and cleanup
- Use watchdog's Observer and FileSystemEventHandler
- Filter for .md files only
- Debounce: Wait 100ms after creation to ensure file is complete
- Thread-safe: Use threading.Lock for callback

**2.3 Implement event handler**
- Extend watchdog.events.FileSystemEventHandler
- Override on_created() method
- Filter: Only .md files in tasks directory
- Debounce: time.sleep(0.1) after creation
- Verify file exists and has content (st_size > 0)
- Call callback with file path
- Handle exceptions in callback (log, don't crash watcher)

**2.4 Integrate into plan_command.py**
- Import from hooks and file_watcher modules
- Create watcher before launching interactive session
- Start watcher monitoring `.lw_coder/tasks/` in worktree
- On file creation callback:
  - Extract plan_id from filename
  - Trigger plan_file_created hook with variables
- Stop watcher after session completes (in finally block)
- Handle watcher errors gracefully (log warning, continue)

**2.5 Handle edge cases**
- Multiple files created quickly: Trigger hook for each
- File created before watcher starts: No hook (acceptable limitation)
- File deleted immediately: Check exists() before triggering
- Session exits before file created: Watcher stops, no hook
- Watcher thread cleanup: Ensure thread stops on exit

### 3. Integrate Hooks into Commands

**3.1 Add CLI flag to all commands**
- File: `src/lw_coder/cli.py`
- Add global flag to parser:
  ```python
  parser.add_argument(
      "--no-hooks",
      action="store_true",
      help="Disable execution of configured hooks"
  )
  ```
- Pass flag to all command functions
- Store in global context or pass as parameter

**3.2 Integrate into plan_command.py**
- Import hooks module and file_watcher
- Check --no-hooks flag before starting watcher
- If hooks disabled: Skip watcher entirely, log message
- If hooks enabled:
  - Create file watcher callback that calls hooks.trigger_hook()
  - Start watcher before subprocess.run()
  - Stop watcher in finally block
- Hook variables:
  ```python
  variables = {
      'worktree_path': temp_worktree,
      'plan_path': final_plan_path,  # After file_mapping
      'plan_id': plan_id,
      'repo_root': repo_root
  }
  ```

**3.3 Integrate into code_command.py**
- After SDK session completes (line ~372, after run_sdk_session_sync)
- Before CLI resume command is built
- Check --no-hooks flag
- Trigger code_sdk_complete hook with variables:
  ```python
  from hooks import trigger_hook

  if not no_hooks:
      trigger_hook('code_sdk_complete', {
          'worktree_path': worktree_path,
          'plan_path': plan_path,
          'plan_id': metadata.plan_id,
          'repo_root': metadata.repo_root
      })
  ```

**3.4 Integrate into eval_command.py (future)**
- NOTE: Blocked by round-out-eval-command plan
- After training data export succeeds
- Trigger eval_complete hook with variables:
  ```python
  trigger_hook('eval_complete', {
      'training_data_dir': training_data_dir,
      'worktree_path': worktree_path,
      'plan_path': plan_path,
      'plan_id': plan_id,
      'repo_root': repo_root
  })
  ```
- Document in plan: eval_complete hook will be added after round-out-eval-command

**3.5 Update command signatures**
- Add no_hooks parameter to:
  - `run_plan_command(plan_path, text_input, tool, no_hooks=False)`
  - `run_code_command(plan_path, tool, model, no_hooks=False)`
  - `run_eval_command(plan_id, no_hooks=False)` (future)
- Pass from CLI args to command functions

### 4. Implement Process Lifecycle Management

**4.1 Add process tracking to HookManager**
- Instance variable: `self._processes: List[subprocess.Popen]`
- After Popen(), append to list
- Call `_prune_completed()` after each execute to prevent unbounded growth

**4.2 Implement _prune_completed() method**
- Iterate over processes list
- Call poll() to check if finished
- Remove finished processes from list
- Keep only running processes
- Called after each hook execution

**4.3 Implement _cleanup() method**
- Called via atexit on program exit
- Iterate over all tracked processes
- For each process:
  - Try terminate() with 5 second timeout
  - If still running, call kill()
- Log cleanup actions
- Handle exceptions gracefully

**4.4 Register atexit handler**
- In HookManager.__init__():
  ```python
  import atexit
  atexit.register(self._cleanup)
  ```
- Ensures cleanup even on Ctrl+C or exception

**4.5 Test cleanup behavior**
- Unit test: Mock processes, verify cleanup called
- Integration test: Spawn real long-running process, verify termination
- Test graceful shutdown vs forced kill

### 5. Add Comprehensive Logging

**5.1 Configure hook logger**
- Separate logger from main application: `logging.getLogger('lw_coder.hooks')`
- File handler: `~/.lw_coder/logs/hooks-YYYY-MM-DD.log`
- Use RotatingFileHandler with maxBytes and backupCount
- Format: Include timestamp, level, hook name, message
- Console handler: Brief notifications only

**5.2 Create log directory on first use**
- Check if `~/.lw_coder/logs/` exists
- Create with parents=True if missing
- Handle permission errors gracefully

**5.3 Log hook execution flow**
- On trigger: Log hook name, command template, variables
- On substitution: Log substituted argument list
- On execute: Log Popen creation
- On error: Log exception with full traceback
- On cleanup: Log process termination

**5.4 Console feedback**
- Use rich.console for formatted output
- On hook trigger: `[dim]→ Running {hook_name} hook in background[/dim]`
- On error: `[yellow]⚠ Hook '{hook_name}' failed: {error}[/yellow]`
- Keep console output minimal, details in log file

**5.5 Log rotation policy**
- Daily rotation: New file each day
- Keep last 7 days of logs
- Max file size: 10MB (backup before rotation)
- Format: hooks-2025-11-26.log, hooks-2025-11-27.log, etc.

### 6. Testing

**6.1 Unit tests for hooks module**
- File: `tests/test_hooks.py`
- Test load_hook_config():
  - Valid TOML
  - Invalid TOML (syntax error)
  - Missing file (returns empty dict)
  - Invalid structure (missing fields)
- Test substitute_variables():
  - Valid substitution
  - Undefined variable (raises error)
  - Multiple variables
  - No variables
  - Edge cases (spaces in paths, special chars)
- Test HookManager with MockProcessExecutor:
  - Verify commands captured correctly
  - Verify argument list construction
  - Verify process tracking
  - Verify cleanup

**6.2 Unit tests for file watcher**
- File: `tests/test_file_watcher.py`
- Test watcher lifecycle (start/stop)
- Test file creation detection
- Test .md file filtering
- Test callback invocation
- Test debounce behavior
- Test cleanup on stop
- Use temporary directories for isolation

**6.3 Integration tests with real processes**
- File: `tests/test_hooks_integration.py`
- Mark with @pytest.mark.integration
- Test real subprocess execution:
  - Create marker file via hook command
  - Verify file exists after execution
- Test process cleanup:
  - Spawn long-running process
  - Trigger cleanup
  - Verify process terminated
- Test file watcher with real files:
  - Create file in watched directory
  - Verify callback triggered
  - Verify hook executed

**6.4 Test CLI integration**
- Update tests in `tests/test_cli.py`
- Test --no-hooks flag parsing
- Test flag passed to command functions
- Mock hooks.trigger_hook() and verify:
  - Called when hooks enabled
  - Not called when --no-hooks used

**6.5 Test error handling**
- Config errors (malformed TOML)
- Missing executable (FileNotFoundError)
- Subprocess errors
- Watcher errors
- Verify all errors logged
- Verify main workflow continues despite hook failures

**6.6 Test variable substitution edge cases**
- Paths with spaces: `/path/with spaces/file.md`
- Paths with special chars: `/path/with-dashes_underscores.ext`
- Multiple variables in one command
- Undefined variables (should raise clear error)
- Empty variable values (edge case)

### 7. Documentation

**7.1 Update README.md**
- Add new "Configurable Hooks" section after "Eval Command" section
- Content:
  ```markdown
  ## Configurable Hooks

  You can configure commands to run automatically at key workflow points by creating `~/.lw_coder/config.toml` in your home directory.

  ### Quick Start

  Create `~/.lw_coder/config.toml`:
  ```toml
  [hooks.plan_file_created]
  command = "code-oss ${worktree_path}"
  enabled = true

  [hooks.code_sdk_complete]
  command = "notify-send 'Code Complete' 'Ready for review'"
  enabled = true
  ```

  ### Hook Points

  - **plan_file_created**: Triggered when plan file is created during interactive session
  - **code_sdk_complete**: Triggered after SDK session completes, before CLI resume
  - **eval_complete**: Triggered after evaluation completes (requires round-out-eval-command)

  ### Available Variables

  Use `${variable}` syntax in commands:
  - All hooks: `${worktree_path}`, `${plan_path}`, `${plan_id}`, `${repo_root}`
  - eval_complete also has: `${training_data_dir}`

  ### Common Examples

  ```toml
  # Open editor when plan is created
  [hooks.plan_file_created]
  command = "code-oss ${worktree_path} --new-window"
  enabled = true

  # Desktop notification when code completes
  [hooks.code_sdk_complete]
  command = "notify-send 'lw_coder' 'Code generation complete for ${plan_id}'"
  enabled = true

  # Open file manager to training data
  [hooks.eval_complete]
  command = "nautilus ${training_data_dir}"
  enabled = true
  ```

  ### Disabling Hooks

  Use the `--no-hooks` flag to disable all hooks for a single command:
  ```bash
  lw_coder code plan.md --no-hooks
  ```

  For complete documentation, see `docs/HOOKS.md`.
  ```

**7.2 Create hooks configuration guide**
- File: `docs/HOOKS.md`
- Document all hook points and timing in detail
- Document all available variables per hook with examples
- Provide common use cases:
  - Open VS Code/other editors
  - Desktop notifications (notify-send, osascript)
  - Custom scripts
  - File managers
- Document --no-hooks flag
- Troubleshooting guide (check logs, test commands manually, etc.)

**7.3 Create ADR for injection trust model**
- File: `docs/adr/NNN-hook-injection-trust.md` (use next available number)
- Title: "ADR NNN: Hook Command Injection Trust Model"
- Status: Accepted
- Context: Hooks execute user-configured shell commands, similar to git hooks or shell aliases
- Decision: Trust developer-controlled configuration, use shell=True for simplicity
- Rationale:
  - Developer creates their own `~/.lw_coder/config.toml` on their own machine
  - No untrusted input - developer would be attacking themselves
  - Similar trust model to: git hooks, shell aliases, npm scripts, make targets
  - Usability over defense-in-depth for single-developer CLI tools
- Consequences:
  - Simpler implementation using string.Template
  - No complex argument list parsing
  - Clear security boundary: user home directory config is trusted
  - Future: If project-level config added, would need security review
- Alternatives Considered:
  - Argument list parsing with shlex.split - rejected as over-engineering
  - Whitelist of allowed commands - rejected as too restrictive
  - Webhook-only integration - rejected as less flexible

**7.4 Update THREAT_MODEL.md**
- Add section on hook execution trust model:
  ```markdown
  ### Hook Execution Security

  **Decision: Trust developer-controlled hook configurations**
  - **Rationale:** Hooks configured in `~/.lw_coder/config.toml` by developer
  - **Risk Accepted:** Hooks execute arbitrary commands with developer's permissions
  - **Justification:** Developer creates their own config on their own machine
    - Similar trust model to git hooks, shell aliases, npm scripts
    - No untrusted input - developer would be attacking themselves
    - Standard pattern for CLI developer tools
  - **Implementation:** Use shell=True with string.Template substitution
  - **Mitigation:**
    - Global config only (no project-level to prevent malicious repos)
    - --no-hooks flag to disable if needed
    - Logs show exactly what commands execute
  - **Future Consideration:** If project-level config added, would require:
    - Explicit user approval workflow
    - Whitelist/review mechanism
    - Clear warnings about executing project-provided hooks
  ```
- Add to "Trust Boundaries & Assumptions" section:
  - Trusted: `~/.lw_coder/config.toml` (user-created configuration)

**7.5 Add inline code documentation**
- Docstrings for all public functions
- Note in execute_hook() docstring: "Executes developer-controlled commands with shell=True"
- Examples in docstrings for substitute_variables()
- Type hints throughout

## Deliverables

1. **Hook Manager Module** (`src/lw_coder/hooks.py`)
   - HookManager class with process lifecycle management
   - Command execution with shell=True (trusted developer config)
   - Variable substitution using string.Template
   - Config loading and validation
   - Comprehensive error handling

2. **File Watcher Module** (`src/lw_coder/file_watcher.py`)
   - PlanFileWatcher class for monitoring plan creation
   - Cross-platform file watching via watchdog
   - Debounce and edge case handling

3. **CLI Integration**
   - --no-hooks flag in all commands
   - Hook triggers in plan_command.py and code_command.py
   - Note: eval_command.py integration blocked by round-out-eval-command

4. **Process Lifecycle Management**
   - Process tracking in HookManager
   - Automatic cleanup on exit via atexit
   - Graceful termination with fallback to kill

5. **Logging Infrastructure**
   - Separate hook logs at `~/.lw_coder/logs/hooks-YYYY-MM-DD.log`
   - Daily rotation with 7-day retention
   - Structured logging with full context
   - Brief console feedback via rich

6. **Comprehensive Tests**
   - Unit tests for hooks module (mocked execution)
   - Unit tests for file watcher
   - Integration tests with real subprocesses
   - CLI integration tests
   - Error handling tests

7. **Documentation**
   - Updated README.md with hooks section (comprehensive quick start and examples)
   - New docs/HOOKS.md configuration guide (detailed reference)
   - New docs/adr/NNN-hook-injection-trust.md (security rationale)
   - Updated docs/THREAT_MODEL.md with hook execution trust model
   - Common usage examples throughout

## Out of Scope

1. **Project-Level Configuration**
   - No `.lw_coder/config.toml` in repositories
   - Would break trust model: project configs not developer-controlled
   - Could allow malicious repos to execute arbitrary commands
   - May add in future with explicit approval workflow (see ADR)

2. **Webhook/HTTP Integration**
   - No HTTP POST hooks to external services
   - Could add as alternative to shell commands in future

3. **Plugin System**
   - No Python-based plugin hooks
   - Arbitrary commands only for now

4. **Hook Timeouts**
   - Hooks run until completion, no timeout
   - Could add timeout configuration in future

5. **Hook Dependencies/Ordering**
   - No way to run hooks sequentially or conditionally
   - All enabled hooks run independently

6. **Dry-Run Mode**
   - No --dry-run flag to preview hook execution
   - Could add in future for debugging

7. **Environment Variable Forwarding**
   - Only predefined path variables available
   - No ${ENV_VAR} substitution from environment

8. **Hook Result Tracking**
   - No way to check if hook succeeded/failed programmatically
   - Only logging, no API for hook status

9. **Conditional Hook Execution**
   - No if/then logic in config
   - Hooks always run if enabled

10. **Multiple Commands Per Hook**
    - One command per hook only
    - Could add command array in future

11. **eval_complete Hook Implementation**
    - Blocked by round-out-eval-command plan
    - Will be added when training_data_dir is available

## Test Cases

```gherkin
Feature: Configurable Viewer Hooks
  Scenario: Execute hook when plan file created
    Given a config file with plan_file_created hook enabled
    And the hook command is "touch ${worktree_path}/marker.txt"
    When I run "lw_coder plan --text 'test plan'"
    And Claude creates a plan file during the session
    Then the file watcher detects the new plan file
    And the hook executes in the background
    And marker.txt exists in the worktree

  Scenario: Execute hook after SDK completes
    Given a config file with code_sdk_complete hook enabled
    And a valid plan file exists
    When I run "lw_coder code <plan_id>"
    And the SDK session completes successfully
    Then the hook executes before CLI resume
    And the hook receives correct variable values

  Scenario: Disable hooks with --no-hooks flag
    Given a config file with multiple hooks enabled
    When I run "lw_coder plan --text 'test' --no-hooks"
    Then no hooks execute
    And I see "Hooks disabled via --no-hooks flag" in output

  Scenario: Handle missing config file gracefully
    Given no config file exists at ~/.lw_coder/config.toml
    When I run "lw_coder plan --text 'test'"
    Then the command completes successfully
    And no hooks execute
    And no error is shown

  Scenario: Handle hook execution failure
    Given a config file with hook command that fails
    When I run "lw_coder code <plan_id>"
    Then the hook fails
    And the failure is logged to hooks log file
    And a warning is shown in console
    And the main command completes successfully

  Scenario: Variable substitution with paths containing spaces
    Given a config with command "echo ${worktree_path} > output.txt"
    And worktree_path contains spaces: "/path/with spaces/worktree"
    When the hook executes
    Then the path is properly substituted
    And the command executes successfully

  Scenario: Process cleanup on exit
    Given a hook that spawns a long-running background process
    When the lw_coder command exits
    Then all spawned hook processes are terminated
    And no zombie processes remain
```
