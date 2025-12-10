# Bash Tab Completion

This document explains how to set up and use bash tab completion for the `lw_coder` CLI.

## Features

The `lw_coder` CLI provides intelligent bash tab completion for:

- **Commands**: `plan`, `code`, `finalize`, `completion`
- **Plan files**: Complete plan IDs (e.g., `fix-bug`) and full paths (e.g., `.lw_coder/tasks/fix-bug.md`)
- **Tools**: Dynamic completion from available executors (`claude-code`, `droid`)
- **Models**: Dynamic completion for Claude Code CLI models (`sonnet`, `opus`, `haiku`)
- **Smart filtering**: Model completions are suppressed when `--tool droid` is specified

## Setup

Tab completion requires three steps to set up:

### 1. Install argcomplete globally

The `argcomplete` package must be installed and activated globally in your shell.

**Recommended (using pipx):**
```bash
pipx install argcomplete
activate-global-python-argcomplete
```

**Alternative (using pip):**
```bash
pip install argcomplete
activate-global-python-argcomplete
```

**Note:**
- `pipx` is the recommended method as it installs CLI tools in isolated environments
- If using `pip`, you may need to use `pip3` instead of `pip` on some systems
- If you encounter permission errors with `pip`, try `pip install --user argcomplete` or `sudo pip install argcomplete`

### 2. Install lw_coder completion script

Run the `lw_coder` completion installer:

```bash
lw_coder completion install
```

This command will:
- Create `~/.bash_completion.d/lw_coder` with the completion script
- Add a source line to `~/.bashrc` if not already present
- Display setup instructions

### 3. Reload your shell

After installation, reload your bash configuration:

```bash
source ~/.bashrc
```

Or simply start a new shell session.

## Usage Examples

Once set up, tab completion works automatically:

### Complete commands
```bash
lw_coder <TAB>
# Shows: plan  code  finalize  completion  --help  --debug
```

### Complete plan files
```bash
lw_coder code <TAB>
# Shows active plan IDs from .lw_coder/tasks/ (excludes plans with status: done)

lw_coder code fix-<TAB>
# Completes to matching plan IDs like: fix-bug  fix-auth  fix-cache
```

### Complete tools
```bash
lw_coder code my-plan --tool <TAB>
# Shows: claude-code  droid
```

### Complete models
```bash
lw_coder code my-plan --model <TAB>
# Shows: sonnet  opus  haiku

lw_coder code my-plan --tool droid --model <TAB>
# Shows nothing (model parameter not valid with droid)
```

### Complete with paths
```bash
lw_coder code .lw_coder/tasks/<TAB>
# Shows plan files in the directory
```

## How It Works

### Plan File Discovery

The completion system:
1. Searches for `.lw_coder/tasks/*.md` files in your repository
2. Parses front matter to check the `status` field
3. Filters out plans where `status: done`
4. Returns plan IDs (filenames without `.md` extension)

### Caching

To improve performance, the completion system caches the list of active plans for 2 seconds. This prevents expensive filesystem scans on every tab press while still keeping completions relatively fresh.

### Performance Optimizations

The completion system includes several performance optimizations to ensure fast tab completion:

1. **Regex-based front matter parsing**: Plan file front matter is parsed using regex instead of PyYAML, eliminating a ~100-150ms import overhead.

2. **Lazy-loaded command modules**: Command modules (code_command, finalize_command, plan_command, recover_command) are imported only when their respective commands are executed, not at CLI startup. This prevents loading heavy dependencies during tab completion.

3. **TTL-based caching**: Plan lists are cached with a 2-second TTL to avoid repeated filesystem scans.

4. **Performance regression testing**: Automated tests verify that tab completion completes within a defined threshold (see `tests/completion/test_performance.py`).

### Dynamic Discovery

Tool and model completions are dynamically discovered from the executor registry and model definitions. If new executors are added to the codebase, they automatically appear in tab completions without any configuration changes.

## Troubleshooting

### Completion doesn't work at all

1. **Check argcomplete installation**:
   ```bash
   python -m argcomplete --version
   ```
   If this fails, argcomplete is not installed. Run `pipx install argcomplete` (or `pip install argcomplete`).

2. **Check global activation**:
   ```bash
   grep argcomplete ~/.bashrc
   ```
   You should see a line like `eval "$(register-python-argcomplete lw_coder)"` or global argcomplete activation.

3. **Verify lw_coder is in PATH**:
   ```bash
   which lw_coder
   ```
   If not found, ensure the package is installed in your environment.

4. **Reload shell**:
   ```bash
   source ~/.bashrc
   ```

### Completions are outdated

The cache has a 2-second TTL. If you just created or modified a plan, wait 2 seconds and try again. You can also start a new shell to clear the cache.

### Completions include "done" plans

The plan file may have malformed YAML front matter. Check that:
- The YAML front matter is surrounded by `---` lines
- The `status` field is properly formatted: `status: done`
- There are no YAML syntax errors

### Model completions show for droid

This suggests left-to-right argument parsing. Make sure you're using the command format:
```bash
lw_coder code plan-id --tool droid --model <TAB>
```

If the tool hasn't been parsed yet (e.g., you haven't typed `--tool droid` before `--model`), completions will still appear. This is a limitation of bash completion left-to-right parsing.

## Uninstallation

To remove bash completion:

1. Remove the completion script:
   ```bash
   rm ~/.bash_completion.d/lw_coder
   ```

2. Remove the source line from `~/.bashrc`:
   ```bash
   # Edit ~/.bashrc and remove the line:
   # source ~/.bash_completion.d/lw_coder
   ```

3. Reload your shell:
   ```bash
   source ~/.bashrc
   ```

---

## Developer Architecture Documentation

This section explains how the bash completion system is architected and how to extend or maintain it.

### Architecture Overview

The completion system consists of four main components:

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI (cli.py)                         │
│  - Creates argparse parser                                  │
│  - Attaches completers to arguments                         │
│  - Calls argcomplete.autocomplete()                         │
└─────────────┬───────────────────────────────────────────────┘
              │
              ├──────────────────────────────────────────────┐
              │                                              │
              ▼                                              ▼
┌─────────────────────────┐                    ┌─────────────────────────┐
│  Completers             │                    │  PlanResolver           │
│  (completers.py)        │                    │  (plan_resolver.py)     │
│  - complete_plan_files  │◄───────────────────│  - resolve()            │
│  - complete_tools       │                    │  - Finds plans by ID    │
│  - complete_models      │                    │  - Handles paths        │
└────────┬────────────────┘                    └─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Cache                  │
│  (cache.py)             │
│  - PlanCompletionCache  │
│  - TTL-based caching    │
│  - Regex front matter   │
│    parsing (for perf)   │
└─────────────────────────┘
```

### Component Details

#### 1. CLI Integration (`src/lw_coder/cli.py`)

The CLI is responsible for:
- Creating the argparse parser with `create_parser()`
- Attaching completer functions to specific arguments using the `.completer` attribute
- Calling `argcomplete.autocomplete(parser)` before parsing arguments

**Key code:**
```python
def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(...)

    # Attach completers to arguments
    plan_path_arg = code_parser.add_argument("plan_path", ...)
    plan_path_arg.completer = complete_plan_files

    tool_arg = code_parser.add_argument("--tool", ...)
    tool_arg.completer = complete_tools

    return parser

def main(argv):
    parser = create_parser()
    argcomplete.autocomplete(parser)  # Must come before parse_args()
    args = parser.parse_args(argv)
    ...
```

**Important:** `argcomplete.autocomplete()` must be called *before* `parse_args()`.

#### 2. Completer Functions (`src/lw_coder/completion/completers.py`)

Completer functions are called by argcomplete during tab completion. They follow a specific signature:

```python
def completer_function(prefix: str, parsed_args, **kwargs) -> list[str]:
    """
    Args:
        prefix: The text the user has typed so far for this argument.
        parsed_args: A Namespace with arguments parsed so far (left-to-right).
        **kwargs: Additional argcomplete metadata (action, parser, etc.).

    Returns:
        List of completion strings. Only items starting with prefix are shown.
    """
```

**Available completers:**

- **`complete_plan_files`**: Completes plan file paths and IDs
  - Uses `PlanCompletionCache` for performance
  - Filters to plans where `status != "done"`
  - Supports both plan IDs (`fix-bug`) and paths (`.lw_coder/tasks/fix-bug.md`)

- **`complete_tools`**: Completes tool names
  - Calls `ExecutorRegistry.list_executors()` dynamically
  - Automatically includes new executors without code changes

- **`complete_models`**: Completes model names
  - Uses `ClaudeCodeExecutor.VALID_MODELS`
  - Suppresses completions if `parsed_args.tool == "droid"`
  - Demonstrates left-to-right parsing awareness

**Error handling:** All completers catch exceptions and return empty lists on error. This prevents completion from breaking the shell experience.

#### 3. Plan Completion Cache (`src/lw_coder/completion/cache.py`)

The cache improves tab completion performance by avoiding repeated filesystem scans.

**Key features:**
- **TTL-based caching**: Default 2-second TTL balances freshness and performance
- **YAML parsing**: Extracts `status` field from plan front matter
- **Error resilience**: Handles malformed YAML, permission errors, missing files gracefully
- **Repository-aware**: Finds `.lw_coder/tasks/` relative to git repo root

**Cache invalidation:**
```python
from lw_coder.completion.cache import get_active_plans

# Invalidate cache manually (useful in tests)
from lw_coder.completion.cache import _global_cache
_global_cache.invalidate()

# Or create a new cache with custom TTL
cache = PlanCompletionCache(ttl_seconds=5.0)
plans = cache.get_active_plans()
```

**Global cache:** The module exports `get_active_plans()` which uses a global cache instance. This is appropriate for CLI usage (short-lived, single-threaded processes).

#### 4. Plan Resolver (`src/lw_coder/plan_resolver.py`)

The `PlanResolver` provides centralized path resolution logic used by both the CLI and completion system.

**Resolution logic:**
1. **Absolute path**: `/full/path/to/plan.md` → returned as-is (after validation)
2. **Relative path**: `./plan.md` or `../tasks/plan.md` → resolved relative to cwd
3. **Plan ID**: `fix-bug` → searches for `.lw_coder/tasks/fix-bug.md` from repo root

**Error handling:**
- Raises `FileNotFoundError` with helpful error messages
- Suggests common troubleshooting steps
- CLI catches this for the `plan` command (new plans) but propagates for `code`/`finalize`

### How to Extend

#### Adding a new completer

1. Create the completer function in `completers.py`:
   ```python
   def complete_my_option(prefix: str, parsed_args, **kwargs) -> list[str]:
       """Complete my custom option."""
       try:
           options = get_my_options()  # Your logic here
           return [opt for opt in options if opt.startswith(prefix)]
       except Exception as exc:
           logger.debug("Error in complete_my_option: %s", exc)
           return []
   ```

2. Attach it to an argument in `cli.py`:
   ```python
   my_arg = parser.add_argument("--my-option", ...)
   my_arg.completer = complete_my_option
   ```

3. Write tests in `tests/completion/test_completers.py`:
   ```python
   def test_complete_my_option():
       result = complete_my_option("", Namespace())
       assert "expected_option" in result
   ```

#### Modifying cache behavior

To change cache TTL or behavior:

1. Update `PlanCompletionCache.__init__()` default TTL
2. Update cache invalidation logic in `get_active_plans()`
3. Update tests in `tests/completion/test_cache.py`

**Note:** The global cache instance is created at module load. If you need per-request configuration, consider passing the cache explicitly instead of using the global instance.

#### Supporting new shells (zsh, fish, etc.)

The current implementation uses `argcomplete`, which supports multiple shells. To add support:

1. Update `completion_install.py` to detect the shell (check `$SHELL`)
2. Generate appropriate completion script for that shell
3. Install to the correct location (e.g., `~/.zshrc` for zsh)
4. Update documentation

**Note:** argcomplete has built-in zsh support via `register-python-argcomplete --shell zsh`.

### Testing Strategy

The completion system has comprehensive test coverage:

- **Unit tests** (`tests/completion/test_cache.py`, `test_completers.py`):
  - Test individual components in isolation
  - Mock external dependencies (filesystem, executors)
  - Cover edge cases and error handling

- **Integration tests** (`tests/completion/test_integration.py`):
  - Test argparse + argcomplete wiring
  - Verify completers are attached correctly
  - Ensure end-to-end completion works

- **CLI tests** (`tests/test_cli.py`):
  - Test argument parsing with argparse
  - Verify backward compatibility
  - Test integration with PlanResolver

**Test fixtures:**
- `autouse` fixture in `test_cache.py` invalidates global cache before each test
- Temporary git repos created with `tmp_path` fixture
- Mock filesystem for plan files

**Best practices:**
- Use `pytest.fail()` for missing dependencies (not `pytest.skip()`) per `CLAUDE.md` best practices section
- Avoid excessive mocking - use real git repos and filesystem when possible
- Test error paths - completion must never break the shell

### Performance Considerations

**Cache TTL:**
- Too short: Excessive filesystem scans slow down completion
- Too long: Outdated completions, especially after creating new plans
- Current: 2 seconds is a good balance for interactive use

**Filesystem operations:**
- Plan scanning is O(n) where n = number of plan files
- Front matter parsing uses regex (not YAML) for fast parsing
- Cache prevents this cost on every tab press

**Memory:**
- Global cache holds plan list in memory
- For typical repos (< 100 plans), memory usage is negligible
- Cache is short-lived (process ends after command completes)

### Troubleshooting for Developers

**Tests failing with "argcomplete not installed":**
- Ensure `argcomplete>=3.0.0` is in `pyproject.toml` dependencies
- Run `uv sync` to update the environment
- Tests use `pytest.fail()` to enforce this requirement

**Completion not working in development:**
- Install in editable mode: `pip install -e .`
- Run `lw_coder completion install`
- Check that `which lw_coder` points to your development version
- Use `python -m lw_coder.cli` to bypass shell PATH issues

**Global cache causing test interference:**
- Use the `autouse` fixture to invalidate cache before each test
- Or create a new `PlanCompletionCache` instance for isolated testing
- Avoid relying on cache state across tests

**Debugging completer functions:**
- Completers log to debug level: enable with `--debug` flag
- Check logs for exceptions in completer functions
- Test completers directly in unit tests with `Namespace()` mock args

### References

- **argcomplete documentation**: https://github.com/kislyuk/argcomplete
- **argparse documentation**: https://docs.python.org/3/library/argparse.html
- **Project best practices**: `CLAUDE.md` (best practices section)
- **Inline code documentation**: Comments in source files provide implementation details
