---
plan_id: add-ruff-step
status: done
evaluation_notes: []
git_sha: 4d948aa0ff259790099c4ace598a480690e19904
---

# Add Ruff Linting Step to Code Command

## Objectives

Add ruff as a linting/auto-fix step in the weft code command's SDK session. The step will run `uv run ruff check --fix .` before pytest in the Review Loop, ensuring AI-generated code is automatically formatted and linted before tests run.

## Requirements & Constraints

- **Scope**: This is a weft-specific enhancement, not a general feature for all projects using weft
- **Configuration**: Use ruff defaults (no custom configuration needed)
- **Consistency**: All three model variants (haiku, opus, sonnet) must be updated identically
- **Integrity**: VERSION file hashes must be updated to match modified template files
- **Error handling**: Let ruff fail if not installed (it will be added as a dev dependency)

## Work Items

### 1. Add ruff as a dev dependency

- Run `uv add --dev ruff` to add ruff to `pyproject.toml`
- No additional configuration required (using ruff defaults)

### 2. Modify prompt template files

Update the Review Loop section in each of these files:
- `src/weft/init_templates/prompts/claude-code-cli/haiku/main.md`
- `src/weft/init_templates/prompts/claude-code-cli/opus/main.md`
- `src/weft/init_templates/prompts/claude-code-cli/sonnet/main.md`

Change the Review Loop from:
```markdown
## Review Loop (run up to 4 iterations or until no issues remain)

1. Use the **Bash** tool to run `uv run pytest`. If tests fail, fix the problems and rerun until they pass before continuing.
```

To:
```markdown
## Review Loop (run up to 4 iterations or until no issues remain)

1. Use the **Bash** tool to run `uv run ruff check --fix .` to auto-fix linting issues.
2. Use the **Bash** tool to run `uv run pytest`. If tests fail, fix the problems and rerun until they pass before continuing.
```

Renumber subsequent steps (2→3, 3→4, etc.) accordingly.

### 3. Update VERSION file hashes

- Modify `src/weft/init_templates/VERSION`
- Recalculate SHA256 hashes for the three modified `main.md` files using `calculate_file_hash()` from `src/weft/init_command.py`
- Update the hash values in the JSON for:
  - `prompts/claude-code-cli/haiku/main.md`
  - `prompts/claude-code-cli/opus/main.md`
  - `prompts/claude-code-cli/sonnet/main.md`

### Unit Tests

No new unit tests required. The changes are to:
- A dev dependency addition (declarative, no logic to test)
- Prompt template content (treated as opaque strings, not structurally validated)

### Integration Tests

**Required to pass:**
- `tests/unit/test_init_command.py::test_version_file_hashes_match_template_files`
  - This test validates that template file hashes match the VERSION file
  - Will pass after updating VERSION file with recalculated hashes

## Deliverables

1. Updated `pyproject.toml` with ruff as a dev dependency
2. Updated prompt templates (3 files) with ruff step before pytest
3. Updated `src/weft/init_templates/VERSION` with correct hashes
4. All existing tests passing, including hash validation test

## Out of Scope

- Ruff configuration files (`ruff.toml` or `[tool.ruff]` in pyproject.toml)
- Error handling for missing ruff installation
- Changes to other projects using weft (this is weft-specific)
- Documentation updates (README.md)
- Alternative orderings (check → test → fix → retest)
- Shared template/include system for Review Loop (future improvement)
