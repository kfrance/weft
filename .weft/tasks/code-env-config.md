---
plan_id: code-env-config
status: done
evaluation_notes: []
linear_issue_id: LW-105
git_sha: 90a3bb4a338f5cd4e800e40a8c12f59d0ba3e414
---

# Add `[code.env]` Configuration Section

## Objectives

Enable developers to define environment variables in `.weft/config.toml` that are injected into the entire `weft code` workflow (setup commands + Claude Code session).

## Requirements & Constraints

### Functional Requirements

1. New `[code.env]` section in `.weft/config.toml` with key-value pairs
2. Values are literal strings only (no variable expansion)
3. Env vars injected into both setup commands and Claude Code session
4. Config values override existing environment variables (config wins)
5. Strict validation: keys must be valid env var names (alphanumeric + underscore, not starting with digit)

### Configuration Schema

```toml
[code.env]
DATABASE_URL = "postgres://localhost:5432/dev"
DEBUG = "true"
MY_CUSTOM_VAR = "value"
```

### Constraints

- Follow existing validation patterns from `setup_commands.py`
- Invalid keys produce clear error messages
- Empty `[code.env]` section is valid (no env vars injected)

## Work Items

### 1. Create new code_env.py module

Create `src/weft/code_env.py` with:

- `CodeEnvError` exception class
- `load_code_env(repo_root: Path) -> dict[str, str]` function
- Validate keys match regex `^[A-Za-z_][A-Za-z0-9_]*$`
- Validate values are strings
- Raise `CodeEnvError` with clear message for invalid keys/values
- Return empty dict if `[code.env]` section is missing

### 2. Modify setup_commands.py

- Modify `run_setup_commands()` to accept optional `code_env: dict[str, str]` parameter
- Inject `code_env` vars into environment before `WEFT_*` vars (so `WEFT_*` can override if same key)

### 3. Integrate with code_command.py

- Import `load_code_env` from new module
- Load `[code.env]` after worktree creation, before setup commands
- Pass loaded env vars to `run_setup_commands()`
- Inject into `os.environ` before SDK session (so SDK inherits them)
- Include in `host_env` for CLI resume command

### 4. Update init_command.py config template

Add commented `[code.env]` example to `_CONFIG_TEMPLATE`:

```toml
# Environment variables for coding session (optional)
# These are available to both setup commands and the Claude Code session.
# Values are literal strings (no variable expansion).
#
# [code.env]
# DATABASE_URL = "postgres://localhost:5432/dev"
# DEBUG = "true"
```

### 5. Update documentation

Add `[code.env]` section to `docs/CONFIGURATION.md` with:

- Configuration schema
- Example use cases
- Note that values are literal (no expansion)
- Note that config overrides existing env vars

### Unit Tests

`tests/unit/test_code_env.py` (new file):

- Test `load_code_env()` with valid config returns dict
- Test `load_code_env()` with no `[code.env]` section returns empty dict
- Test `load_code_env()` with invalid key name (starts with digit) raises error
- Test `load_code_env()` with invalid key name (contains hyphen) raises error
- Test `load_code_env()` with non-string value raises error
- Test `load_code_env()` with empty string value succeeds
- Test `load_code_env()` with special characters in value succeeds

`tests/unit/test_setup_commands.py` (additions):

- Test `run_setup_commands()` injects `code_env` vars into environment
- Test `run_setup_commands()` with `code_env` + `WEFT_*` vars, verify `WEFT_*` wins on conflict

### Integration Tests

**Must pass (existing):**

- `tests/integration/test_setup_commands.py::test_setup_commands_execute_before_session`
- `tests/integration/test_setup_commands.py::test_setup_commands_not_configured_gracefully_skipped`
- `tests/integration/test_setup_commands.py::test_setup_command_failure_aborts_code_command`

**New integration test:**

`tests/integration/test_code_env.py::test_code_env_available_to_setup_commands`:

- Creates repo with `[code.env]` containing `TEST_VAR = "test_value"`
- Setup command writes `$TEST_VAR` to a marker file
- Verifies marker file contains "test_value"

## Deliverables

- New file: `src/weft/code_env.py`
- New file: `tests/unit/test_code_env.py`
- New file: `tests/integration/test_code_env.py`
- Modified: `src/weft/setup_commands.py`
- Modified: `src/weft/code_command.py`
- Modified: `src/weft/init_command.py`
- Modified: `docs/CONFIGURATION.md`
- Modified: `tests/unit/test_setup_commands.py`

## Out of Scope

- Variable expansion (`${VAR}` syntax)
- User-level env config (`~/.weft/config.toml`)
- Environment-specific profiles (dev/staging/prod)
- Secrets management or encryption
- Reserved variable blocklist
- Secret detection warnings
