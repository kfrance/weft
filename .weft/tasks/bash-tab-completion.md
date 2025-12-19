---
plan_id: bash-tab-completion
status: done
evaluation_notes: []
git_sha: 193008d670586dedc23af9558450bf6909be5d36
---

# Add Bash Tab Completion to CLI

## Objectives

Add comprehensive bash tab completion to the `lw_coder` CLI to improve developer experience and productivity. This includes migrating from docopt to argparse for better completion support and implementing intelligent completion for commands, options, and plan file paths.

**Key Goals:**
- Migrate CLI argument parsing from docopt to argparse for native completion support
- Implement dynamic tab completion for all commands, options, and plan files
- Enable users to tab-complete plan IDs without typing full paths
- Filter plan completions to show only non-done plans
- Provide smart completion that understands parameter dependencies (e.g., suppress `--model` when `--tool droid`)
- Create installation command to simplify user setup
- Ensure maintainable, well-tested completion infrastructure

## Requirements & Constraints

### Functional Requirements

1. **Argument Parser Migration**
   - Replace docopt with argparse in `src/lw_coder/cli.py`
   - Maintain exact same CLI interface (backward compatible)
   - Preserve all existing commands: `plan`, `code`
   - Preserve all existing options: `--tool`, `--model`, `--text`, `--debug`

2. **Tab Completion Behavior**
   - Commands: `lw_coder <TAB>` → shows `plan`, `code`, `-h`, `--help`
   - Tool option: `--tool <TAB>` → dynamically discovered from `ExecutorRegistry.list_executors()`
   - Model option: `--model <TAB>` → dynamically discovered from `ClaudeCodeExecutor.VALID_MODELS`
   - Smart filtering: `--tool droid --model <TAB>` → no completions (left-to-right only)
   - Plan files: Complete both plan IDs (e.g., `fix-<TAB>`) and full paths (e.g., `.lw_coder/tasks/fix-<TAB>`)
   - Only show plans where `status != "done"` in YAML front matter

3. **Plan Path Resolution**
   - Create `PlanResolver` class to centralize path resolution logic
   - Accept plan IDs: `fix-subagent` → `.lw_coder/tasks/fix-subagent.md`
   - Accept full paths: `.lw_coder/tasks/fix-subagent.md` → unchanged
   - Accept relative/absolute paths: `../tasks/plan.md` → resolved
   - Used by both CLI and completion system for consistency

4. **Performance Optimization**
   - Implement caching for plan file scanning (2-second TTL)
   - Avoid parsing all plan files on every tab press
   - Gracefully handle malformed YAML without crashing completion

5. **Installation Command**
   - Add `lw_coder completion install` command
   - Generates/copies completion script to `~/.bash_completion.d/lw_coder`
   - Adds source line to `~/.bashrc` if not present
   - Provides clear user instructions

### Technical Constraints

- Add `argcomplete>=3.0.0` as required dependency in `pyproject.toml`
- Support bash only (zsh, fish, powershell out of scope)
- Users must install argcomplete globally: `pip install argcomplete`
- Users must run: `activate-global-python-argcomplete` (one-time setup)
- Dynamic discovery: completion always reflects current executors and models
- No breaking changes to existing CLI behavior

### Quality Requirements

- Comprehensive unit tests for all completer functions
- Comprehensive unit tests for PlanResolver
- Comprehensive unit tests for caching logic
- Integration tests for argparse + argcomplete wiring
- Tests must fail (not skip) if dependencies missing (per `docs/BEST_PRACTICES.md`)
- All tests in default pytest run
- Clear error messages for misconfigured completion
- Documentation for user setup and developer maintenance

## Work Items

### 1. Create PlanResolver Class

Create `src/lw_coder/plan_resolver.py` with centralized path resolution logic:
- `PlanResolver.resolve(user_input: str) -> Path` method
- Handles plan IDs, relative paths, absolute paths
- Raises `FileNotFoundError` with helpful message if plan not found
- Unit tests covering all input types and edge cases

**Rationale:** Both CLI and completion need consistent path resolution. This prevents duplication and ambiguity.

### 2. Migrate CLI from docopt to argparse

Replace docopt usage in `src/lw_coder/cli.py`:
- Create argparse parser with subparsers for `plan` and `code` commands
- Define all arguments and options matching current docopt interface
- Maintain exact same behavior (backward compatible)
- Update imports and remove docopt dependency from `pyproject.toml`
- Integrate with PlanResolver for plan path arguments
- Update existing CLI tests to verify argparse migration

**Rationale:** argparse provides native argcomplete support, unlike docopt which requires custom bridging.

### 3. Add argcomplete Dependency

Update `pyproject.toml`:
- Add `argcomplete>=3.0.0` to `dependencies` list
- Run `uv sync` to update lock file

### 4. Create Completion Cache

Create `src/lw_coder/completion/cache.py`:
- `PlanCompletionCache` class with TTL-based caching (2 seconds)
- `get_active_plans() -> list[str]` method that scans `.lw_coder/tasks/*.md`
- Parses YAML front matter to filter out `status: done` plans
- Gracefully handles malformed YAML, file I/O errors
- Returns plan IDs (file stems without extension)
- Unit tests for cache behavior, TTL, error handling

**Rationale:** Scanning and parsing YAML on every tab press is expensive. Caching with short TTL balances performance and freshness.

### 5. Create Completer Functions

Create `src/lw_coder/completion/completers.py`:
- `complete_plan_files(prefix, parsed_args, **kwargs)` - uses PlanCompletionCache
- `complete_tools(prefix, parsed_args, **kwargs)` - calls `ExecutorRegistry.list_executors()`
- `complete_models(prefix, parsed_args, **kwargs)` - checks if `--tool droid`, uses `ClaudeCodeExecutor.VALID_MODELS`
- Unit tests for each completer function
- Tests verify dynamic discovery, filtering logic, error handling

**Rationale:** Separate completer functions are testable, maintainable, and reusable across commands.

### 6. Wire argcomplete into CLI

Update `src/lw_coder/cli.py`:
- Import argcomplete and call `argcomplete.autocomplete(parser)` before `parser.parse_args()`
- Attach completers to appropriate arguments using `.completer` attribute
- Wire `complete_plan_files` to `<plan_path>` arguments in both commands
- Wire `complete_tools` to `--tool` option
- Wire `complete_models` to `--model` option
- Integration tests verifying completion wiring

**Rationale:** Connects argparse, argcomplete, and custom completers into functional system.

### 7. Create Installation Command

Add `completion` subcommand to CLI:
- `lw_coder completion install` - installs completion script to `~/.bash_completion.d/`
- Adds source line to `~/.bashrc` if not already present
- Provides clear success message and next steps
- Handles errors gracefully (file permissions, existing content)
- Unit tests for installation logic
- Document in README or docs/

**Rationale:** Simplifies user setup by automating bash completion configuration.

### 8. Update Code Commands to Use PlanResolver

Update `src/lw_coder/plan_command.py` and `src/lw_coder/code_command.py`:
- Replace manual path handling with `PlanResolver.resolve()`
- Ensure consistent path resolution throughout codebase
- Update tests to verify resolver integration

**Rationale:** Completion suggests IDs, but CLI must accept them. Resolver ensures consistency.

### 9. Add Integration Tests

Create `tests/completion/test_integration.py`:
- Test argparse parser with argcomplete integration
- Verify completers are called with correct arguments
- Test completion behavior with various command-line states
- Mock filesystem for plan file completion tests
- Tests fail if argcomplete not installed (per best practices)

**Rationale:** Unit tests verify individual pieces; integration tests verify the system works end-to-end.

### 10. Update Documentation

- Add user setup instructions to README.md or docs/COMPLETION.md
- Document the three-step setup: install argcomplete, activate globally, run `lw_coder completion install`
- Add developer documentation explaining completion architecture
- Update CLAUDE.md if needed

## Deliverables

1. **PlanResolver module** (`src/lw_coder/plan_resolver.py`)
   - Centralized path resolution logic
   - Comprehensive unit tests

2. **Argparse migration** (updated `src/lw_coder/cli.py`)
   - CLI uses argparse instead of docopt
   - Backward compatible interface
   - Updated tests

3. **Completion infrastructure** (`src/lw_coder/completion/`)
   - `cache.py` - Plan file caching with TTL
   - `completers.py` - Completer functions for all arguments
   - argcomplete wiring in CLI
   - Unit tests for all components

4. **Installation command** (`lw_coder completion install`)
   - Automated setup for bash completion
   - User-friendly error handling

5. **Integration tests** (`tests/completion/test_integration.py`)
   - End-to-end completion behavior verification
   - Tests fail if dependencies missing

6. **Updated dependencies** (`pyproject.toml`)
   - argcomplete added as required dependency
   - docopt removed

7. **Documentation**
   - User setup guide
   - Developer architecture documentation
   - Updated CLI help text

8. **All tests passing**
   - Unit tests for each component
   - Integration tests for complete workflow
   - No skipped tests (tests fail if environment not set up)

## Out of Scope

- Shell completion for zsh, fish, or other shells (bash only)
- Tab completion for commands beyond `plan`, `code`, and future `finalize`
- Auto-installation of argcomplete globally (user must install manually)
- Completion for plan file contents or structure
- Fuzzy matching for plan IDs
- Completion caching across shell sessions (persistence)
- Migration of existing shell scripts or tooling
- Performance optimization beyond basic caching
- Completion for environment variable values

## Test Cases

```gherkin
Feature: Plan path resolution
  Scenario: Resolve plan ID to full path
    Given a plan file exists at ".lw_coder/tasks/fix-subagent.md"
    When PlanResolver.resolve("fix-subagent") is called
    Then it returns the absolute path to ".lw_coder/tasks/fix-subagent.md"

  Scenario: Resolve full path unchanged
    Given a plan file exists at ".lw_coder/tasks/fix-subagent.md"
    When PlanResolver.resolve(".lw_coder/tasks/fix-subagent.md") is called
    Then it returns the absolute path to ".lw_coder/tasks/fix-subagent.md"

  Scenario: Handle non-existent plan
    Given no plan file exists with ID "nonexistent"
    When PlanResolver.resolve("nonexistent") is called
    Then it raises FileNotFoundError with helpful message

Feature: Bash tab completion for commands
  Scenario: Complete main command
    Given the user types "lw_coder <TAB>"
    When bash completion is triggered
    Then completions include "plan", "code", "--help", "-h"

  Scenario: Complete subcommand for plan
    Given the user types "lw_coder plan --tool <TAB>"
    When bash completion is triggered
    Then completions include "claude-code" and "droid"

  Scenario: Complete subcommand for code
    Given the user types "lw_coder code --model <TAB>"
    When bash completion is triggered
    Then completions include "sonnet", "opus", "haiku"

Feature: Smart model completion filtering
  Scenario: Suppress model completions for droid tool
    Given the user types "lw_coder code --tool droid --model <TAB>"
    When bash completion is triggered
    Then no completions are shown

  Scenario: Show model completions for claude-code tool
    Given the user types "lw_coder code --tool claude-code --model <TAB>"
    When bash completion is triggered
    Then completions include "sonnet", "opus", "haiku"

Feature: Plan file completion
  Scenario: Complete plan IDs for non-done plans
    Given plan files exist: "active.md" (status: draft), "done.md" (status: done)
    When the user types "lw_coder code <TAB>"
    Then completions include "active" but not "done"

  Scenario: Complete plan file paths
    Given plan file exists at ".lw_coder/tasks/fix-subagent.md" with status "draft"
    When the user types "lw_coder code .lw_coder/tasks/fix-<TAB>"
    Then completions include ".lw_coder/tasks/fix-subagent.md"

  Scenario: Handle malformed plan YAML gracefully
    Given a plan file with invalid YAML front matter exists
    When bash completion is triggered
    Then completion does not crash
    And may include or exclude the malformed plan (implementation-defined)

Feature: Plan completion caching
  Scenario: Cache active plans for performance
    Given 100 plan files exist in ".lw_coder/tasks/"
    When the user triggers completion twice within 2 seconds
    Then the filesystem is only scanned once

  Scenario: Refresh cache after TTL expires
    Given cached plan list is 3 seconds old
    When the user triggers completion
    Then the filesystem is scanned again
    And the cache is updated

Feature: Completion installation
  Scenario: Install completion script successfully
    Given the user runs "lw_coder completion install"
    When the installation completes
    Then a completion script exists at "~/.bash_completion.d/lw_coder"
    And "~/.bashrc" contains a source line for the completion script
    And the user sees success message with next steps

  Scenario: Handle existing installation gracefully
    Given completion is already installed
    When the user runs "lw_coder completion install"
    Then the installation succeeds without duplication
    And the user is informed completion is already set up

Feature: Argparse migration backward compatibility
  Scenario: Existing plan command works unchanged
    Given the CLI has been migrated to argparse
    When the user runs "lw_coder plan --text 'new idea' --tool droid"
    Then the command executes identically to the docopt version

  Scenario: Existing code command works unchanged
    Given the CLI has been migrated to argparse
    When the user runs "lw_coder code .lw_coder/tasks/plan.md --tool claude-code --model opus"
    Then the command executes identically to the docopt version

  Scenario: Help output remains clear
    Given the CLI has been migrated to argparse
    When the user runs "lw_coder --help"
    Then the help text shows all commands and options clearly

Feature: Dynamic completion discovery
  Scenario: Tool completion reflects executor registry
    Given ExecutorRegistry contains "claude-code" and "droid"
    When the user types "lw_coder code --tool <TAB>"
    Then completions match ExecutorRegistry.list_executors()

  Scenario: Model completion reflects executor capabilities
    Given ClaudeCodeExecutor.VALID_MODELS contains {"sonnet", "opus", "haiku"}
    When the user types "lw_coder code --model <TAB>"
    Then completions match ClaudeCodeExecutor.VALID_MODELS

  Scenario: New executors automatically get completion
    Given a new executor "new-tool" is added to ExecutorRegistry
    When the user types "lw_coder code --tool <TAB>"
    Then completions include "new-tool" without code changes

Feature: Error handling and resilience
  Scenario: Handle missing .lw_coder/tasks directory
    Given the ".lw_coder/tasks" directory does not exist
    When bash completion is triggered for plan files
    Then completion returns empty list without crashing

  Scenario: Handle permission errors reading plans
    Given a plan file exists but is not readable
    When bash completion is triggered for plan files
    Then completion skips the unreadable file and continues

  Scenario: Handle concurrent plan modifications
    Given a plan file is being modified during completion
    When bash completion is triggered
    Then completion handles the error gracefully
    And returns completions for remaining valid plans
```
