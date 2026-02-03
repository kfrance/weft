---
plan_id: LW-117-consolidate-tool-name
status: done
evaluation_notes: []
git_sha: 93ba5415e66248f2001d7eaf2ccf2a0fd30fcf1d
---

# Consolidate claude-code-cli to claude-code

## Objectives

Consolidate the tool name from `claude-code-cli` to `claude-code` across the entire codebase to:
1. Eliminate the confusing dual-directory structure (`.weft/prompts/active/claude-code/` and `.weft/prompts/active/claude-code-cli/`)
2. Fix the finalize command loading the wrong prompt (PR workflow instead of merge-to-main for this repo)
3. Align the tool name with the CLI flag (`--tool claude-code`)

## Requirements & Constraints

- All references to `claude-code-cli` must be renamed to `claude-code`
- Auto-migrate existing user directories from `claude-code-cli/` to `claude-code/`
- Centralize tool names in a constants file to eliminate magic strings
- Centralize tool name validation using the constants as single source of truth
- The bundled default finalize prompt remains as "create PR" workflow
- The weft repo's active finalize prompt uses "merge into main" workflow
- No new configuration mechanism for workflow selection — customization is via prompt file editing

## Work Items

### 1. Create constants module

Create `src/weft/constants.py` with:
- `DEFAULT_CODING_TOOL = "claude-code"` — the default tool name
- `SUPPORTED_TOOLS` — set/tuple of valid tool names for validation
- `LEGACY_TOOL_NAMES` — mapping of old names to new names for migration (e.g., `{"claude-code-cli": "claude-code"}`)

### 2. Add auto-migration logic

In `src/weft/prompt_loader.py`, add migration function that:
- Checks if legacy directory `.weft/prompts/active/claude-code-cli/` exists
- If new directory `.weft/prompts/active/claude-code/` does not exist, automatically rename the legacy directory
- Log an info message when migration occurs
- Call this function at the start of `load_prompts()` and `load_finalize_prompt()`

### 3. Centralize tool name validation

Update `src/weft/executors/registry.py` (or wherever `ExecutorRegistry` is defined):
- Import `SUPPORTED_TOOLS` from constants
- Use it as the source of truth for valid tool names
- Ensure error messages reference the constant

### 4. Rename init_templates directory

- Rename `src/weft/init_templates/prompts/claude-code-cli/` to `src/weft/init_templates/prompts/claude-code/`
- Update `src/weft/init_templates/VERSION` to reflect new paths (change all `claude-code-cli` to `claude-code`)

### 5. Update source code references

Replace `claude-code-cli` with import from constants or literal `claude-code`:

| File | Lines | Change |
|------|-------|--------|
| `src/weft/finalize_command.py` | 249 | Remove tool mapping; use `tool` directly instead of `prompt_tool` |
| `src/weft/code_command.py` | 521 | Change `tool="claude-code-cli"` to `tool="claude-code"` |
| `src/weft/prompt_loader.py` | 102, 175 | Change default parameter to `tool="claude-code"` (or import from constants) |
| `src/weft/prompt_loader.py` | 294-295 | Remove the reverse mapping logic (no longer needed) |
| `src/weft/candidate_writer.py` | 26 | Change default to `"claude-code"` (or import from constants) |
| `src/weft/train_command.py` | 128, 162 | Change hardcoded `"claude-code-cli"` to `"claude-code"` (or import from constants) |

### 6. Consolidate weft repo's active prompts

- Move model subdirectories (`haiku/`, `opus/`, `sonnet/`) from `.weft/prompts/active/claude-code-cli/` to `.weft/prompts/active/claude-code/`
- Keep existing `.weft/prompts/active/claude-code/finalize.md` (the merge-into-main workflow)
- Delete `.weft/prompts/active/claude-code-cli/` directory after moving contents

### 7. Unit Tests

Update string literals from `claude-code-cli` to `claude-code` in:

| File | Tests Affected |
|------|----------------|
| `tests/unit/test_prompt_loader.py` | 15 tests |
| `tests/unit/test_prompt_loader_migration.py` | 9 tests |
| `tests/unit/test_candidate_writer.py` | 12 tests |
| `tests/unit/test_init_command.py` | 7 tests |

Add new unit tests:
- Test for auto-migration logic (legacy directory renamed to new)
- Test for migration when both directories exist (should not overwrite)
- Test that `SUPPORTED_TOOLS` constant is used for validation

### 8. Integration Tests

Update `tests/integration/test_train_command_integration.py`:
- Update `create_test_active_prompts()` path (line 130)
- Update `tool="claude-code-cli"` arguments to `tool="claude-code"` (lines 200, 247, 304)

Update comments referencing `claude-code-cli` in:
- `tests/integration/test_setup_commands.py`
- `tests/integration/test_code_env.py`
- `tests/integration/test_command_smoke.py`

**Required integration tests that must pass:**
- `tests/integration/test_finalize_flow.py::test_finalize_flow_orchestration`
- `tests/integration/test_train_command_integration.py::test_train_command_end_to_end`
- `tests/integration/test_setup_commands.py` (all tests)
- `tests/integration/test_code_env.py` (all tests)

## Deliverables

- [ ] New `src/weft/constants.py` module with tool name constants
- [ ] Auto-migration logic in prompt_loader.py
- [ ] Centralized tool validation using constants
- [ ] All `claude-code-cli` references replaced with `claude-code`
- [ ] `init_templates/` directory renamed and VERSION updated
- [ ] Weft repo prompts consolidated under single `claude-code/` directory
- [ ] All unit tests passing (`pytest`)
- [ ] All integration tests passing (`pytest tests/integration/`)

## Out of Scope

- Adding configuration to switch between PR and merge workflows (workflow is customized via prompt file)
- Changing the default finalize behavior for new repos (stays as PR creation)
- Modifying prompt content beyond moving/renaming files
- ADR documentation for workflow decisions
- Prompt directory schema validation
