---
plan_id: claude-cli-model-default
status: done
evaluation_notes: []
git_sha: b0757f3928bb27d2051125cf79ecf6a2a860dd94
---

## Objectives
- Ensure `lw_coder code` always launches Claude Code CLI with the intended model, defaulting to `sonnet` when the flag is omitted.
- Propagate the selected model through executor configuration so prompts, sub-agents, and CLI invocation remain consistent.
- Add regression coverage confirming both default and explicit model selections are honored.

## Requirements & Constraints
- Default behavior must pass `--model sonnet` to Claude Code CLI when the user omits `--model`.
- Supported models remain `sonnet`, `haiku`, and `opus`; invalid values should continue to raise existing validation errors.
- Command construction must remain shell-safe (use `shlex.quote` for interpolated arguments).
- Backward compatibility for existing executor signatures is not required; they can be updated to accept the model explicitly.
- Tests should run via `uv run pytest`.

## Work Items
1. Update `ClaudeCodeExecutor.build_command` (and other concrete executors, if necessary) to accept a required `model` argument and include `--model <value>` in the assembled command.
2. Adjust all executor call sites (`run_code_command`, `plan_command`, and related helpers) to supply the correct model string.
3. Review prompt-loading and sub-agent generation paths to confirm they still use the same model value (no changes expected, just ensure integration points stay consistent).
4. Add unit tests exercising default (`sonnet`) and override (`haiku`, `opus`) scenarios to confirm the executor command contains the correct flag.
5. Run `uv run pytest` and address any failures.

## Deliverables
- Updated executor and command orchestration code ensuring Claude Code CLI receives the intended model flag.
- Unit tests covering default and custom model selections.
- Test run results demonstrating the suite passes.

## Out of Scope
- Changes to Droid executor behavior or other tooling integrations.
- Modifications to user configuration files or external documentation.
- Alterations to plan-generation workflows beyond ensuring updated executor usage.

## Test Cases
```gherkin
Feature: Claude Code CLI model selection
  Scenario: Default model enforced when no flag is provided
    Given the user runs "lw_coder code" without specifying "--model"
    When run_code_command executes
    Then the Claude Code CLI command includes "--model sonnet"

  Scenario: Explicit model override is respected
    Given the user runs "lw_coder code --model haiku"
    When run_code_command executes
    Then the Claude Code CLI command includes "--model haiku"
```
