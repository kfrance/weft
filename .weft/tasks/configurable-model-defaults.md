---
plan_id: configurable-model-defaults
status: done
evaluation_notes: []
git_sha: 3ae9629ff7bf153e80c985b30c643b7446485ee5
---

# Configurable Model Defaults via config.toml

## Objectives

Enable users to configure default models for lw_coder commands (plan, code, finalize) via `~/.lw_coder/config.toml`, while maintaining backwards compatibility with existing hardcoded defaults.

## Requirements & Constraints

### Functional Requirements
- Add `--model` parameter to `plan` command (currently missing)
- Support model configuration via `~/.lw_coder/config.toml` using `[defaults]` section
- Implement 3-tier precedence chain: CLI flag > config.toml > hardcoded defaults
- Validate model values and fall back gracefully on invalid input
- Maintain backwards compatibility: keep existing hardcoded defaults (sonnet for plan/code, haiku for finalize)

### Config File Structure
```toml
[defaults]
plan_model = "opus"
code_model = "sonnet"
finalize_model = "haiku"
```

### Precedence Chain
1. **CLI `--model` flag** (highest priority) - user explicitly specifies model
2. **config.toml `[defaults]` section** - user's persistent preference
3. **Hardcoded defaults** (lowest priority) - fallback when nothing configured

### Valid Models
- `sonnet` (default for plan and code)
- `opus` (most capable, slower, more expensive)
- `haiku` (default for finalize - fast and cheap)

### Backwards Compatibility
- **No breaking changes**: Keep existing hardcoded defaults
- Users opt-in to different models via config.toml
- Existing workflows continue working without configuration

### Error Handling
- Invalid model names in config.toml → log warning and fall back to hardcoded default
- Missing config.toml → fall back silently to hardcoded defaults (no error, expected case)
- Corrupted TOML syntax → show user-friendly error message explaining the issue and file location, then fall back to hardcoded defaults
- Invalid model in CLI flag → validate and reject with clear error message

### Documentation Reorganization Requirements
- **CLAUDE.md scope change**: This file is for Claude Code (AI agent) guidance only, not user-facing documentation
- Remove user-facing CLI usage docs from CLAUDE.md (init, plan, code, eval, finalize commands)
- Move best practices from docs/BEST_PRACTICES.md into CLAUDE.md
- Delete docs/BEST_PRACTICES.md after migration
- Update all references to BEST_PRACTICES.md to point to CLAUDE.md instead
- Add note in CLAUDE.md clarifying that user docs belong in README.md

## Work Items

### 1. Create Configuration Module

**File**: `src/lw_coder/config.py` (create new file)

Create a new dedicated configuration module separate from hooks:
- Add `load_config()` function to load all sections from `~/.lw_coder/config.toml`
- Add `get_model_defaults()` function to load `[defaults]` section
- Handle missing config file gracefully (return empty dict, no error, no message)
- Handle corrupted TOML with user-friendly error message:
  ```python
  try:
      config = tomllib.loads(content.decode("utf-8"))
  except tomllib.TOMLDecodeError as exc:
      logger.error(
          "Failed to parse config file: %s\n"
          "TOML syntax error at line %d: %s\n"
          "Fix the syntax error or remove the file to use defaults.",
          CONFIG_PATH, exc.lineno if hasattr(exc, 'lineno') else '?', exc
      )
      return {}
  ```
- Show error to user (not just debug log) so they know their config is broken
- Use simple function-based API (no classes, no instance state)
- Add module docstring documenting model selection precedence chain

**Implementation Notes**:
- Use `CONFIG_PATH = Path.home() / ".lw_coder" / "config.toml"`
- Import tomllib (Python 3.11+) with tomli fallback for older Python
- Return empty dict on any error (fail gracefully, don't block commands)
- Use logger.error() for TOML parse errors so user sees the message

### 2. Update Parameter Validation

**File**: `src/lw_coder/param_validation.py`

- Update `get_effective_model()` signature to accept `command: str` parameter
- Implement 3-tier precedence logic:
  1. Return CLI model if provided
  2. Check config.toml for `{command}_model` key (e.g., "plan_model")
  3. Fall back to hardcoded default from `COMMAND_DEFAULTS` dict
- Add `COMMAND_DEFAULTS` constant with backwards-compatible defaults:
  ```python
  COMMAND_DEFAULTS = {
      "plan": "sonnet",
      "code": "sonnet",
      "finalize": "haiku",
  }
  ```
- Add `VALID_MODELS = {"sonnet", "opus", "haiku"}` constant
- Add validation: if config provides invalid model, log warning and use hardcoded default
- Update module docstring with model selection precedence documentation

### 3. Add --model Parameter to plan Command

**File**: `src/lw_coder/cli.py`

- Add `--model` argument to `plan_parser` (similar to code_parser)
- Set up argcomplete completer: `plan_model_arg.completer = complete_models`
- Add help text: `"Model variant for Claude Code CLI (default: sonnet)"`
- Pass model parameter to `run_plan_command()` call
- Handle model validation for droid tool (droid doesn't support --model)

### 4. Update plan Command Implementation

**File**: `src/lw_coder/plan_command.py`

- Add `model: str | None = None` parameter to `run_plan_command()` signature
- Update docstring to document model parameter
- Replace hardcoded `model="sonnet"` at line 249 with:
  ```python
  effective_model = get_effective_model(model, "plan")
  command = executor.build_command(prompt_file, model=effective_model)
  ```
- Import `get_effective_model` from `param_validation`

### 5. Update code Command Implementation

**File**: `src/lw_coder/code_command.py`

- Update `get_effective_model()` call at line 205 to pass command name:
  ```python
  effective_model = get_effective_model(model, "code")
  ```
- No other changes needed (code command already has --model parameter)

### 6. Update finalize Command Implementation

**File**: `src/lw_coder/finalize_command.py`

- Add `model: str | None = None` parameter to `run_finalize_command()` signature
- Add `--model` argument to `finalize_parser` in cli.py
- Replace hardcoded `model="haiku"` at line 240 with:
  ```python
  effective_model = get_effective_model(model, "finalize")
  command = executor.build_command(prompt_file, model=effective_model)
  ```
- Import `get_effective_model` from `param_validation`
- Update docstring to document model parameter

### 7. Update CLI Argument Parsing for finalize

**File**: `src/lw_coder/cli.py`

- Add `--model` argument to `finalize_parser`
- Set up argcomplete completer
- Pass model parameter to `run_finalize_command()` call

### 8. Refactor hooks.py to Use config.py

**File**: `src/lw_coder/hooks.py`

- Update `HookManager.load_config()` to call `config.load_config()` instead of duplicating TOML parsing
- Remove direct TOML parsing code (delegate to config.py)
- Keep the method signature and caching behavior unchanged (backwards compatible)
- Update imports to use config module
- The HookManager can keep its own caching layer if needed (implementation detail)

### 9. Update Documentation - README.md

**File**: `README.md`

Extend existing "Configurable Hooks" section (around line 504) to include model defaults:
- Add new `[defaults]` section example showing model configuration
- Document precedence chain (CLI > config > hardcoded)
- Add valid model values (sonnet, opus, haiku) with brief descriptions
- Show example combining hooks and model defaults in same config.toml
- Update plan/code/finalize command sections to mention `--model` flag
- Keep it concise - this is user-facing quick reference

**Example addition to README**:
```markdown
### Model Defaults

Configure default models for commands in the same config file:

```toml
[defaults]
plan_model = "opus"      # Most capable for planning
code_model = "sonnet"    # Balanced for implementation
finalize_model = "haiku" # Fast for finalization

[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = true
```

Available models:
- `sonnet`: Balanced capability and speed (default for plan and code)
- `opus`: Most capable, slower, more expensive
- `haiku`: Fast and economical (default for finalize)

CLI flags override config: `lw_coder code plan.md --model opus`
```

### 10. Reorganize CLAUDE.md

**File**: `CLAUDE.md`

This file should contain guidance for Claude Code (the AI agent), not user-facing documentation.

**Remove these sections** (they belong in README.md, which already has them):
- "CLI Usage" section (entire section with all command examples)
- "Init Command" section
- "Quick Fix Mode" section
- "Eval Command" section

**Add at the top**:
```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Note**: For user-facing documentation on how to use lw_coder commands, see [README.md](README.md).
```

**Add new "Best Practices" section** (move content from docs/BEST_PRACTICES.md):
- Keep tests in the default run
- Use pytest.fail() for missing dependencies, not pytest.skip()
- Avoid mocking DSPy and LLMs
- Documentation is verified manually
- Don't test interactive commands
- ADR guidelines (when to create, format, location)
- Test organization rules
- Test optimization guidelines

### 11. Remove docs/BEST_PRACTICES.md

**File**: `docs/BEST_PRACTICES.md`

- Delete this file (content moved to CLAUDE.md)

### 12. Update References to BEST_PRACTICES.md

**Files**: Search codebase for references to BEST_PRACTICES.md and update them

Likely locations:
- Prompts in `.lw_coder/optimized_prompts/` or templates
- Any code comments referencing the best practices doc
- Other documentation files

Update all references to point to `CLAUDE.md` instead:
- Change "See `docs/BEST_PRACTICES.md`" → "See `CLAUDE.md` best practices section"
- Change file paths in prompts accordingly

## Deliverables

### Code Changes
- [ ] New src/lw_coder/config.py module with `load_config()` and `get_model_defaults()`
- [ ] Updated param_validation.py with config-aware `get_effective_model()`
- [ ] Refactored hooks.py to use config.py (remove duplicate TOML parsing)
- [ ] Added --model parameter to plan command (cli.py + plan_command.py)
- [ ] Added --model parameter to finalize command (cli.py + finalize_command.py)
- [ ] Updated code command to use config-aware model resolution

### Documentation
- [ ] Updated README.md with model defaults section (extend "Configurable Hooks")
- [ ] Reorganized CLAUDE.md (remove user docs, add best practices)
- [ ] Removed docs/BEST_PRACTICES.md (content moved to CLAUDE.md)
- [ ] Updated all references to BEST_PRACTICES.md to point to CLAUDE.md
- [ ] Updated docstrings in all modified modules
- [ ] Added inline comments documenting precedence chain

### Tests

#### Unit Tests

**File**: `tests/unit/test_config.py` (create new file) - 10 tests

Core functionality:
- [ ] `test_load_config_valid_toml()` - Loads all sections from valid config
- [ ] `test_load_config_handles_multiple_sections()` - Tests [defaults] + [hooks.*] in same file
- [ ] `test_get_model_defaults_valid_config()` - Extracts [defaults] section successfully
- [ ] `test_get_model_defaults_partial_defaults()` - Handles incomplete defaults (e.g., only plan_model set)

Error handling:
- [ ] `test_load_config_missing_file()` - Returns empty dict, no error logged (silent fallback)
- [ ] `test_load_config_corrupted_toml()` - Returns empty dict, logs ERROR with line number and guidance
- [ ] `test_load_config_permission_error()` - Returns empty dict on OSError (permissions, disk full, etc.)
- [ ] `test_get_model_defaults_missing_config()` - Returns empty dict when no config file
- [ ] `test_get_model_defaults_missing_defaults_section()` - Returns empty dict when [defaults] missing

Validation:
- [ ] `test_get_model_defaults_invalid_model_values()` - Logs warning for invalid model values (e.g., "gpt-4")

**File**: `tests/unit/test_param_validation.py` - 3 parametrized test functions

- [ ] `test_get_effective_model_cli_priority()` - Parametrized for all commands (plan/code/finalize), CLI flag overrides config/defaults
- [ ] `test_get_effective_model_config_priority()` - Parametrized for command/model combos, config overrides hardcoded defaults
- [ ] `test_get_effective_model_fallback_to_hardcoded()` - Parametrized for all commands, tests defaults (plan=sonnet, code=sonnet, finalize=haiku)
- [ ] `test_get_effective_model_invalid_config_value()` - Parametrized, invalid config falls back to default with warning (uses caplog)

**File**: `tests/unit/test_hooks.py` - 1 test

- [ ] `test_hooks_uses_config_module()` - Verify hooks.py delegates to config.load_config() instead of parsing TOML directly

**File**: `tests/unit/test_cli.py` - 2 parametrized tests

- [ ] `test_command_accepts_model_parameter()` - Parametrized for plan/code/finalize commands, verifies --model flag is parsed
- [ ] `test_command_model_passed_to_implementation()` - Parametrized for plan/code/finalize, verifies model flows through to run_*_command()

**File**: `tests/unit/test_plan_command.py` - 1 parametrized test

- [ ] `test_run_plan_command_model_handling()` - Parametrized to test: explicit model, default model (sonnet), config model

**File**: `tests/unit/test_finalize_command.py` - 1 parametrized test

- [ ] `test_run_finalize_command_model_handling()` - Parametrized to test: explicit model, default model (haiku), config model

**File**: `tests/unit/test_code_command.py` - 1 test

- [ ] `test_run_code_command_uses_config_defaults()` - Verify code command respects config.toml model defaults

**Total: ~22 test cases (many via parametrization, so fewer actual test functions)**

#### Integration Tests

**File**: `tests/integration/test_config_loading.py` (create new file)

- [ ] `test_config_file_loading_real_filesystem()` - End-to-end config.toml parsing with real file
- [ ] `test_model_defaults_with_real_config()` - Verify actual config.toml reading works

**Note**: These integration tests are optional/low-priority. The unit tests provide sufficient coverage for the config loading logic.

## Out of Scope

- Changing hardcoded defaults (keeping sonnet/haiku for backwards compatibility)
- Adding model configuration for other commands (init, eval, completion, etc.)
- Supporting model aliases or shortcuts
- Adding per-project config.toml (only global ~/.lw_coder/config.toml)
- Validating that selected model is compatible with user's API keys
- Auto-detecting optimal model based on task complexity
- Adding config.toml schema validation beyond basic type checking
