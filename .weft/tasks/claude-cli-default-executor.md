---
plan_id: claude-cli-default-executor
git_sha: 0c298905ba85d3bd07d1fb507ff89b9a051452ebd
status: done
evaluation_notes: []
---

## Objectives
- Introduce Claude Code CLI as a first-class executor for the `lw_coder plan` workflow.
- Make Claude Code CLI the default plan executor while keeping the Droid path available.
- Remove pre-flight authentication checks so activation is delegated to each CLI.

## Requirements & Constraints
- Preserve backward compatibility via `--tool droid`.
- Do not perform explicit token or auth.json validation for any executor.
- Keep prompt templates aligned across executors (shared placeholders & instructions).
- Avoid adding new external Python dependencies; rely solely on existing CLI tooling.
- Limit CLI interface changes to the tool-selection behavior.

## Work Items
1. Refactor `plan_command.py` to introduce an executor abstraction/registry that selects template paths and command builders per tool and drop the `check_droid_auth` call.
2. Implement the Claude Code CLI executor:
   - Add `prompts/claude_code/plan.md` mirroring instructions from the Droid template.
   - Build the host command using Claude CLI conventions (binary lookup, arguments, environment tweaks if needed).
3. Update `cli.py` so `--tool` defaults to Claude Code while still accepting `droid`.
4. Adjust host-runner utilities if executor-specific command building requires configuration changes (e.g., environment variables or settings files).
5. Expand unit/integration tests to cover both executors (template loading, command construction, registry selection) and ensure the absence of auth checks doesn’t break flows.
6. Refresh documentation (README, overview) to explain the default shift and how to opt into Droid explicitly.

## Deliverables
- Executor abstraction code with Claude Code CLI support and Droid fallback.
- New Claude prompt template and any related configuration artifacts.
- Updated tests demonstrating executor coverage.
- Documentation updates outlining execution options and default behavior.

## Out of Scope
- Changes to the `lw_coder code` command executor behavior.
- Implementing additional executors beyond Claude Code CLI and Droid.
- Automatic installation, update, or login flows for external CLIs.

## Test Cases
```gherkin
Feature: Executor selection for lw_coder plan
  Scenario: Default run uses Claude Code CLI
    Given Claude Code CLI is installed
    When I run `lw_coder plan --text "test change"`
    Then the plan command launches a Claude Code CLI session

  Scenario: Explicit Droid selection still works
    Given Droid CLI is installed
    When I run `lw_coder plan --text "test change" --tool droid`
    Then the plan command launches a Droid session
```
