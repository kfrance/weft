---
plan_id: command-scoped-file-sync
status: done
evaluation_notes: []
git_sha: 31704fc83f95e8943ff0474e3ee386cfd27ddf26
---

# Command-Scoped File Sync Configuration

## Objectives

Add a `commands` field to the file sync configuration, allowing users to specify which weft commands should trigger file synchronization. Currently only `code` syncs files to worktrees; this enables file sync for `plan`, `finalize`, `eval`, and `judge` commands as well.

## Requirements & Constraints

1. **Backward compatible**: Default to `["code"]` when `commands` field is not specified, preserving existing behavior
2. **Valid commands**: Only accept `code`, `plan`, `finalize`, `eval`, `judge` as valid values
3. **Empty array behavior**: `commands = []` effectively disables file sync for all commands
4. **Error handling**: Follow existing pattern—catch `FileSyncError`, log the error, return exit code 1
5. **Cleanup tracking**: Use `WorktreeFileCleanup` in all commands to track and clean up synced files
6. **Centralized constants**: Define valid command names in a single constant for maintainability

## Work Items

### 1. Add FILE_SYNC_COMMANDS constant (file_sync.py)

Define a constant set containing valid command names that support file sync:

```python
FILE_SYNC_COMMANDS = frozenset({"code", "plan", "finalize", "eval", "judge"})
```

### 2. Update FileSyncConfig dataclass (file_sync.py)

Add `commands` field with default value `["code"]`:

```python
@dataclass
class FileSyncConfig:
    enabled: bool = True
    patterns: list[str] = field(default_factory=list)
    max_file_size_mb: int = 100
    max_total_size_mb: int = 500
    commands: list[str] = field(default_factory=lambda: ["code"])
```

### 3. Update validate_worktree_file_sync_config() (file_sync.py)

- Add `"commands"` to the `valid_keys` set
- Validate `commands` field:
  - Must be a list
  - Each element must be a string
  - Each element must be in `FILE_SYNC_COMMANDS`
- Return default `["code"]` when field not specified

### 4. Add helper function (file_sync.py)

Create a function to check if file sync should run for a given command:

```python
def should_sync_for_command(config: FileSyncConfig, command: str) -> bool:
    """Check if file sync should run for the given command."""
```

Returns `True` only if `config.enabled` is `True` AND `command` is in `config.commands`.

### 5. Update code_command.py

Before calling `sync_files_to_worktree()`, check if `"code"` is in the config's commands list using the helper function. Skip file sync with a debug log message if not enabled for this command.

### 6. Add file sync to plan_command.py

After worktree creation:
- Load file sync config from repo
- Check if `"plan"` is enabled using the helper function
- If enabled, create `WorktreeFileCleanup` tracker and call `sync_files_to_worktree()`
- Handle `FileSyncError` with logging and exit code 1

### 7. Add file sync to finalize_command.py

At command start (after worktree validation):
- Load file sync config from repo
- Check if `"finalize"` is enabled using the helper function
- If enabled, create `WorktreeFileCleanup` tracker and call `sync_files_to_worktree()`
- Handle `FileSyncError` appropriately

### 8. Add file sync to eval_command.py

At command start:
- Load file sync config from repo
- Check if `"eval"` is enabled using the helper function
- If enabled, create `WorktreeFileCleanup` tracker and call `sync_files_to_worktree()`
- Handle `FileSyncError` appropriately

### 9. Add file sync to judge_command.py

At command start:
- Load file sync config from repo
- Check if `"judge"` is enabled using the helper function
- If enabled, create `WorktreeFileCleanup` tracker and call `sync_files_to_worktree()`
- Handle `FileSyncError` appropriately

### 10. Update docs/CONFIGURATION.md

- Add `commands` field to the configuration schema example:
  ```toml
  [worktree.file_sync]
  enabled = true
  commands = ["code", "plan"]  # Which commands trigger file sync
  patterns = [".linear.toml"]
  ```
- Add entry to Configuration Options table explaining the field
- Document valid command values
- Document default behavior (`["code"]`) for backward compatibility
- Add example use case for enabling file sync on multiple commands

### Unit Tests

#### Validation tests (tests/unit/worktree/test_file_sync.py)

Extend `TestConfigValidation` with parametrized tests for the `commands` field:
- Valid commands list accepted (e.g., `["code", "plan"]`)
- Default value is `["code"]` when field not specified (backward compatibility)
- Empty list `[]` accepted (disables file sync)
- Single valid command accepted (e.g., `["plan"]`)
- All five commands accepted together
- Invalid command name rejected with `ConfigValidationError`
- Non-list type rejected (e.g., `commands = "code"`)
- Non-string element rejected (e.g., `commands = [1, 2]`)
- Mixed valid/invalid commands rejected

#### Helper function tests (tests/unit/worktree/test_file_sync.py)

Test `should_sync_for_command()`:
- Returns `True` when command is in list and `enabled=True`
- Returns `False` when command is not in list
- Returns `False` when `enabled=False` regardless of commands list
- Returns `False` when commands list is empty
- Handles all five valid command names correctly

#### Command module tests

For each command module (`code_command.py`, `plan_command.py`, `finalize_command.py`, `eval_command.py`, `judge_command.py`), add tests that mock `sync_files_to_worktree` to verify:
- File sync is called when command is in the `commands` list
- File sync is skipped when command is not in the `commands` list
- File sync is skipped when `commands` is empty array

### Integration Tests

- `tests/integration/test_command_smoke.py` must pass—verifies commands initialize and complete setup without errors

## Deliverables

- `src/weft/worktree/file_sync.py`: `FILE_SYNC_COMMANDS` constant, updated `FileSyncConfig`, updated validation, helper function
- `src/weft/code_command.py`: Command check before file sync
- `src/weft/plan_command.py`: File sync logic added
- `src/weft/finalize_command.py`: File sync logic added
- `src/weft/eval_command.py`: File sync logic added
- `src/weft/judge_command.py`: File sync logic added
- `docs/CONFIGURATION.md`: Documentation for `commands` field
- `tests/unit/worktree/test_file_sync.py`: Extended validation and helper function tests
- `tests/unit/test_code_command.py`: File sync call/skip verification
- `tests/unit/test_plan_command.py`: File sync call/skip verification
- `tests/unit/test_finalize_command.py`: File sync call/skip verification
- `tests/unit/test_eval_command.py`: File sync call/skip verification
- `tests/unit/test_judge_command.py`: File sync call/skip verification

## Out of Scope

- Adding file sync to `abandon` command (cleanup-only command)
- Changes to `WorktreeFileCleanup` behavior
- New integration tests specifically for file sync functionality
- Changes to size limits or pattern matching logic
- Per-command patterns or size limits (potential future enhancement)
