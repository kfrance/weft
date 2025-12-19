---
plan_id: code-command-tool-parameter
status: done
evaluation_notes: []
git_sha: f156fa703f1e36f8cda52a0124d97db939515a5f
---

# Enable --tool Parameter for Code Command

## Objectives

Fix bug where the `code` command is hardcoded to use the `claude-code` executor, preventing users from using `droid` as they could before recent CLI changes. This restores feature parity between the `plan` and `code` commands and improves API consistency.

**Key Goals:**
- Add `--tool` parameter to `code` command
- Enable users to choose between `claude-code` and `droid` executors
- Validate that incompatible parameter combinations are rejected with clear errors
- Extract shared validation logic to avoid duplication
- Maintain backward compatibility

## Requirements & Constraints

### Functional Requirements

1. Add `--tool` parameter to `code` command that defaults to `claude-code`
2. Support both `claude-code` and `droid` as valid tool values
3. Raise clear error if `--model` is specified with `--tool droid` (since droid doesn't support model selection)
4. Default to `sonnet` model when using `claude-code` without explicit model
5. Maintain backward compatibility - existing command invocations must work unchanged

### Technical Constraints

- Leverage existing `ExecutorRegistry` abstraction
- Follow pytest best practices per project guidelines
- Maintain consistency with `plan` command's `--tool` parameter behavior
- Use keyword-only arguments with defaults for backward compatibility

### Quality Requirements

- Clear, actionable error messages
- Comprehensive test coverage for parameter combinations
- Updated documentation (CLI help, docstrings, user guides)

## Work Items

### 1. Create Shared Validation Module
Create a new validation utility module with a function to validate tool/model parameter compatibility. This prevents duplicate validation logic between commands.

### 2. Update CLI Signature and Parsing
Add `--tool` parameter to the `code` command's CLI signature. Parse the parameter and call validation before executing the command. Handle validation errors with user-friendly messages.

### 3. Update Code Command Implementation
Modify the `run_code_command()` function to accept a `tool` parameter and use it to select the executor dynamically instead of hardcoding `claude-code`. Ensure default model is applied when needed.

### 4. Add Comprehensive Tests
Write parametrized tests covering all valid tool/model combinations and error cases. Ensure tests verify correct executor selection and proper error handling for invalid combinations.

### 5. Add Validation Tests
Create focused tests for the validation function covering all parameter combinations, error messages, and edge cases.

### 6. Update CLI Tests
Add tests verifying CLI argument parsing for the new `--tool` parameter, default values, error propagation, and exit codes.

### 7. Update Documentation
Update CLI help text, docstrings, and user documentation to reflect the new parameter. Document valid values, defaults, and parameter compatibility rules.

## Deliverables

1. Shared validation module with tool/model compatibility checking
2. Updated CLI with `--tool` parameter support
3. Modified code command accepting tool parameter
4. Comprehensive test coverage for parameter combinations and error cases
5. Updated documentation (CLI help, docstrings, user guides)
6. All tests passing with manual verification of key scenarios

## Out of Scope

- Adding `--model` parameter to `plan` command (separate enhancement)
- Config file integration for tool/model preferences
- Adding new executors beyond `claude-code` and `droid`
- Shell completion script updates
- Telemetry/usage tracking
- Generic parameter filtering system for executors

## Test Cases

The implementation must be verified with tests covering:

1. **Default behavior** - Command works without `--tool` parameter (uses claude-code with sonnet)
2. **Explicit tool selection** - Both `--tool claude-code` and `--tool droid` work correctly
3. **Model selection** - Different models work with claude-code (sonnet, opus, haiku)
4. **Error handling** - Clear error when using `--model` with `--tool droid`
5. **Invalid input** - Appropriate error for invalid tool names

---

## Appendix: Gherkin Test Scenarios

```gherkin
Feature: Tool parameter support for code command

  Scenario: Use code command with defaults
    Given I have a valid plan file
    When I run "lw_coder code <plan_path>"
    Then the command should use claude-code with sonnet model
    And the exit code should be 0

  Scenario: Use code command with explicit model
    Given I have a valid plan file
    When I run "lw_coder code <plan_path> --tool claude-code --model opus"
    Then the command should use claude-code with opus model
    And the exit code should be 0

  Scenario: Use code command with droid
    Given I have a valid plan file
    When I run "lw_coder code <plan_path> --tool droid"
    Then the command should use droid executor
    And the exit code should be 0

  Scenario: Error when using model with droid
    Given I have a valid plan file
    When I run "lw_coder code <plan_path> --tool droid --model sonnet"
    Then the command should fail with validation error
    And the error should explain droid doesn't support model selection
    And the exit code should be 1

  Scenario: Error with invalid tool
    Given I have a valid plan file
    When I run "lw_coder code <plan_path> --tool invalid-tool"
    Then the command should fail with executor error
    And the exit code should be 1
```
