---
plan_id: code-command-simple-fix-mode
status: done
evaluation_notes: []
git_sha: fed13dc32303a55d6bcdf90560dc4a27c84e8521
---

# Objectives

Add a `--text` flag to the `code` command that allows users to bypass the interactive planning process for simple fixes while maintaining documentation trail and code review agent support.

# Requirements & Constraints

## CLI Interface
- Add `--text` argument to `code` command: `uv run lw_coder code --text "description"`
- `--text` and `plan_path` arguments must be mutually exclusive
- Support existing `--tool` (claude-code, droid) and `--model` (sonnet, opus, haiku) flags unchanged
- Default behavior matches normal code command (claude-code tool, sonnet model)

## Plan ID Generation
- Pattern: `quick-fix-YYYY.MM-NNN` where YYYY is year, MM is month, NNN is 3-digit counter (001-999)
- Prefix "quick-fix" is hardcoded (not configurable)
- Monthly counter resets: January uses 001-999, February uses 001-999, etc.
- Scan existing files matching `quick-fix-YYYY.MM-*.md` in `.lw_coder/tasks/` to find highest counter
- Increment highest counter by 1 to generate next ID
- On overflow (>999 fixes in a month): seamlessly fallback to timestamp format `quick-fix-YYYY.MM.DD-HHMMSS`
- Generated plan_id must comply with existing validation pattern: `^[a-zA-Z0-9._-]{3,100}$`

## Plan File Creation
- Generate minimal valid plan file in `.lw_coder/tasks/<plan_id>.md`
- YAML front matter structure:
  ```yaml
  ---
  plan_id: quick-fix-2025.11-001
  git_sha: 0000000000000000000000000000000000000000
  status: draft
  evaluation_notes: []
  ---
  ```
- Body: user's text exactly as provided (no modifications, no title added)
- Must be valid according to existing `plan_validator.py` rules

## Input Validation
- Reject if both `--text` and `plan_path` are provided
- Reject if `--text` is empty or contains only whitespace
- Otherwise accept any text input (no length limits, allow multi-line)

## Integration with Code Command
- After creating plan file, pass its path to existing `run_code_command()` function
- No modifications to core code command flow (worktree, agents, status updates all unchanged)
- Plan lifecycle proceeds normally: draft → coding → implemented → done

## Code Reuse Requirements
- Reuse `find_repo_root()` from `repo_utils.py` to locate `.lw_coder/tasks/` directory
- Follow existing plan file YAML format pattern: `---\n{yaml}\n---\n{body}`
- Reuse all zeros placeholder pattern for git_sha (40 zeros)
- Plan file must pass validation by existing `load_plan_metadata()` function

# Work Items

1. **Create new module `src/lw_coder/quick_fix.py`**
   - Implement `generate_quick_fix_id(tasks_dir: Path) -> str`:
     - Get current year and month
     - Glob for `quick-fix-YYYY.MM-*.md` files in tasks_dir
     - Parse counter numbers from matching filenames
     - Find highest counter and increment (handle edge case of no existing files)
     - If counter would exceed 999, generate timestamp-based ID instead
     - Return formatted plan_id string
   - Implement `create_quick_fix_plan(text: str) -> Path`:
     - Validate text is not empty/whitespace-only
     - Get repository root using `find_repo_root()`
     - Determine tasks directory path
     - Generate unique plan_id using `generate_quick_fix_id()`
     - Create minimal plan file with YAML front matter and text body
     - Write file to `.lw_coder/tasks/<plan_id>.md`
     - Return Path to created plan file
   - Add comprehensive error handling for filesystem errors, permission issues
   - Add logging for ID generation and file creation

2. **Update CLI argument parsing in `src/lw_coder/cli.py`**
   - Add `--text` argument to code subcommand parser
   - Add mutual exclusion validation: error if both `plan_path` and `--text` provided
   - Import and call `quick_fix.create_quick_fix_plan()` when `--text` is used
   - Pass generated plan path to existing `run_code_command()` flow
   - Ensure existing `--tool` and `--model` argument handling works unchanged

3. **Write unit tests in `tests/test_quick_fix.py`**
   - Test ID generation with no existing files (should return 001)
   - Test ID generation with existing files (should increment highest)
   - Test ID generation with gaps in sequence (001, 003 exists → should return 004)
   - Test ID generation across different months (separate counters)
   - Test overflow scenario (999 files exist → fallback to timestamp)
   - Test plan file creation with valid text
   - Test rejection of empty/whitespace-only text
   - Test YAML structure matches validation requirements
   - Test filesystem error handling (permissions, disk full simulation)
   - Test concurrent ID generation safety (basic checks)
   - Use `conftest.py` fixtures for temporary test directories

4. **Write unit tests in `tests/test_cli.py` for CLI integration**
   - Test CLI argument parsing with `--text` flag
   - Test mutual exclusivity validation: both `plan_path` and `--text` provided returns error
   - Mock `create_quick_fix_plan()` to verify it's called when `--text` is provided
   - Mock `run_code_command()` to verify it receives correct plan path
   - Test that `--text` works with `--tool` and `--model` flags
   - DO NOT run actual `lw_coder code` commands (they launch interactive sessions and will hang)

5. **Write integration test in `tests/test_quick_fix.py` for end-to-end validation**
   - Test that a generated plan file passes `load_plan_metadata()` validation
   - Verify the created plan can be read by existing plan validation logic

6. **Update documentation**
   - Add `--text` usage example to CLAUDE.md CLI Usage section
   - Document quick-fix naming pattern and monthly counter behavior
   - Note overflow fallback mechanism for >999 fixes/month

# Deliverables

- New module `src/lw_coder/quick_fix.py` with ID generation and plan creation functions
- Updated `src/lw_coder/cli.py` with `--text` argument support and integration
- New test file `tests/test_quick_fix.py` with comprehensive unit tests
- Updated `tests/test_code_command.py` with integration tests
- Updated `CLAUDE.md` with usage documentation
- All existing tests passing unchanged
- New tests achieving >90% coverage of new code

# Out of Scope

- Making "quick-fix" prefix configurable (hardcoded for simplicity)
- Caching highest counter for performance optimization (simple scan is sufficient)
- LLM-based expansion of user text into structured plan
- Different plan lifecycle for simple fixes (use standard draft → coding → implemented → done)
- Adding `simple_mode` metadata flag to plan YAML
- Archive/cleanup strategy for old quick-fix plans
- Migration of existing plans to new format
- Validation of plan_id uniqueness during generation (relies on existing validation in `load_plan_metadata`)
- Bash tab completion for `--text` argument (no auto-complete needed for free text)
- GUI or interactive mode for simple fixes

# Test Cases

## Feature: Simple Fix Mode for Code Command
Users should be able to quickly execute simple fixes without going through the full interactive planning process, while still maintaining documentation and using code review agents.

### Scenario: Create and execute simple fix with text flag
```gherkin
Given I am in a valid git repository
When I run "lw_coder code --text 'Fix the login button styling'"
Then a plan file should be created in .lw_coder/tasks/ with pattern "quick-fix-YYYY.MM-NNN.md"
And the plan file should contain status "draft"
And the plan file should contain git_sha with 40 zeros
And the plan file body should contain "Fix the login button styling"
And the code command should execute with the generated plan
```

### Scenario: Generate sequential plan IDs
```gherkin
Given .lw_coder/tasks/ contains "quick-fix-2025.11-001.md"
And .lw_coder/tasks/ contains "quick-fix-2025.11-002.md"
When I run "lw_coder code --text 'Another fix'"
Then the generated plan_id should be "quick-fix-2025.11-003"
```

### Scenario: Handle gaps in sequence
```gherkin
Given .lw_coder/tasks/ contains "quick-fix-2025.11-001.md"
And .lw_coder/tasks/ contains "quick-fix-2025.11-005.md"
When I run "lw_coder code --text 'Fix something'"
Then the generated plan_id should be "quick-fix-2025.11-006"
```

### Scenario: Separate counters for different months
```gherkin
Given .lw_coder/tasks/ contains "quick-fix-2025.10-050.md"
And .lw_coder/tasks/ contains "quick-fix-2025.11-001.md"
And the current date is in November 2025
When I run "lw_coder code --text 'November fix'"
Then the generated plan_id should be "quick-fix-2025.11-002"
```

### Scenario: Fallback to timestamp on overflow
```gherkin
Given .lw_coder/tasks/ contains "quick-fix-2025.11-999.md"
When I run "lw_coder code --text 'One more fix'"
Then the generated plan_id should match pattern "quick-fix-2025.11.DD-HHMMSS"
And the plan file should be created successfully
```

### Scenario: Reject empty text input
```gherkin
Given I am in a valid git repository
When I run "lw_coder code --text ''"
Then the command should fail with an error
And the error should indicate text cannot be empty
```

### Scenario: Reject whitespace-only text input
```gherkin
Given I am in a valid git repository
When I run "lw_coder code --text '   \n  '"
Then the command should fail with an error
And the error should indicate text cannot be empty
```

### Scenario: Reject both plan_path and text arguments
```gherkin
Given I am in a valid git repository
When I run "lw_coder code my-plan.md --text 'Fix something'"
Then the command should fail with an error
And the error should indicate arguments are mutually exclusive
```

### Scenario: Simple fix works with different tools
```gherkin
Given I am in a valid git repository
When I run "lw_coder code --text 'Fix bug' --tool droid"
Then a plan file should be created
And the code command should execute using droid
```

### Scenario: Simple fix works with different models
```gherkin
Given I am in a valid git repository
When I run "lw_coder code --text 'Fix bug' --model opus"
Then a plan file should be created
And the code command should execute using opus model
```

### Scenario: Generated plan passes validation
```gherkin
Given I run "lw_coder code --text 'Test fix'"
And a plan file "quick-fix-2025.11-001.md" is created
When the plan file is validated by load_plan_metadata
Then validation should succeed
And metadata.plan_id should equal "quick-fix-2025.11-001"
And metadata.status should equal "draft"
And metadata.git_sha should equal "0000000000000000000000000000000000000000"
```

### Scenario: Multi-line text input is preserved
```gherkin
Given I am in a valid git repository
When I run "lw_coder code --text 'Fix login\n\nUpdate button styles\nAdd hover effect'"
Then a plan file should be created
And the plan body should contain all three lines exactly as provided
```

### Scenario: Plan lifecycle proceeds normally
```gherkin
Given I run "lw_coder code --text 'Simple fix'" and the session completes successfully
And a plan file is created with status "draft"
When the code command starts execution
Then the plan status should change to "coding"
When the code command session exits with code 0
Then the plan status should change to "implemented"
```
