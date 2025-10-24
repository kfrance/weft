---
plan_id: load-optimized-prompts
git_sha: '0000000000000000000000000000000000000000'
status: draft
evaluation_notes: []
---

# Load Optimized Prompts Plan

## Objectives

- Remove DSPy prompt generation from the CLI
- Replace dynamic prompt generation with static prompt loading from disk
- Support model-specific prompts for Claude Code CLI (sonnet, opus, haiku)
- Set up directory structure with placeholder prompt files
- Add model parameter to Claude Code CLI (default: sonnet)
- Configure code command to use Claude Code CLI as default executor
- Set up sub-agents (code-review-auditor, plan-alignment-checker) for Claude Code

## Requirements & Constraints

- Optimized prompts stored at `.lw_coder/optimized_prompts/{tool}/{model}/{prompt_type}.md` (project-relative, not home directory)
- Create placeholder files for all three prompts (main.md, code-review-auditor.md, plan-alignment-checker.md)
- Support Claude Code CLI tool with model parameter: `--model {sonnet|opus|haiku}` (default: sonnet)
- Load prompts from disk at runtime, starting from project root
- Remove entire `src/lw_coder/dspy/` folder
- Remove DSPy-related tests
- Code command uses Claude Code CLI as default executor
- Sub-agents written to `.claude/agents/` in the worktree (project-level)
- Sub-agent files use Claude Code format with YAML frontmatter (name, description, tools, model)
- Droid tool model handling deferred to future task

## Work Items

### 1. Remove DSPy Folder and Related Code

- Delete entire `src/lw_coder/dspy/` folder
- Delete `tests/test_code_prompt_signature.py`
- Delete `tests/test_prompt_orchestrator.py`
- Remove import of `generate_code_prompts` from `src/lw_coder/code_command.py`

### 2. Configure Code Command for Claude Code CLI

- Find how plan command was configured to use Claude Code CLI as default executor
- Apply same configuration pattern to code command
- Ensure code command defaults to Claude Code CLI when no executor is specified

### 3. Create Prompt Loading Function

- Create `load_prompts()` function (in `src/lw_coder/prompt_loader.py` or similar)
- Parameters: `tool` (str, default "claude-code-cli"), `model` (str)
- Returns: dictionary with `main_prompt_content`, `code_review_auditor_content`, `plan_alignment_checker_content`
- Raises error if any prompt file is missing
- Log at INFO level which prompts are being loaded

### 4. Create Directory Structure with Placeholder Files

- Create directories: `.lw_coder/optimized_prompts/{tool}/{model}/` (project-relative) for:
  - claude-code-cli/sonnet/
  - claude-code-cli/opus/
  - claude-code-cli/haiku/
- Create placeholder files in each directory:
  - `main.md` - placeholder content for main prompt
  - `code-review-auditor.md` - placeholder content
  - `plan-alignment-checker.md` - placeholder content

### 5. Add CLI Model Parameter

- Add `--model` parameter to Claude Code CLI command definition
- Default value: "sonnet"
- Valid choices: "sonnet", "opus", "haiku"
- Pass model parameter through to prompt loading in code_command.py

### 6. Update `run_code_command()` Function

- Extract model parameter from CLI args
- Pass `tool="claude-code-cli"` and `model=<value>` to prompt loading function
- Write main prompt as the Claude Code system prompt
- Write code-review-auditor and plan-alignment-checker to `.claude/agents/` with Claude Code format:
  - File: `.claude/agents/code-review-auditor.md` with YAML frontmatter
  - File: `.claude/agents/plan-alignment-checker.md` with YAML frontmatter
- Simplify flow: validate plan → load prompts → write sub-agents → prepare worktree → run Claude Code CLI
- Update log messages to show which model is being used and where sub-agents are written

### 7. Update Tests

- Add tests for `load_prompts()` function:
  - Test successful loading of all three prompts
  - Test error when prompt file missing
  - Test correct model path is constructed
- Add tests for sub-agent file writing:
  - Test correct YAML frontmatter is written
  - Test files are written to `.claude/agents/`
- Update `test_code_command.py` to remove DSPy mocking

## Deliverables

1. Entire `src/lw_coder/dspy/` folder removed
2. DSPy-related tests removed
3. Code command configured to use Claude Code CLI as default executor
4. New prompt loading function
5. Directory structure at `~/.lw_coder/optimized_prompts/` with placeholder files
6. Sub-agent file writing to `.claude/agents/` with proper YAML frontmatter
7. Modified `src/lw_coder/code_command.py` with CLI model parameter
8. Updated test files

## Out of Scope

- Creating optimized prompts (user will do this separately with DSPy)
- Droid tool model parameter integration
- Auto-generation of prompts at runtime
- Documentation updates

## Test Cases

```gherkin
Feature: Load pre-optimized prompts and configure sub-agents for Claude Code CLI

  Scenario: Load sonnet prompts for Claude Code CLI
    Given optimized prompts exist for claude-code-cli/sonnet
    When load_prompts is called with tool="claude-code-cli" and model="sonnet"
    Then all three prompt contents are loaded successfully
    And main prompt content is returned
    And code-review-auditor prompt content is returned
    And plan-alignment-checker prompt content is returned

  Scenario: Load opus prompts for Claude Code CLI
    Given optimized prompts exist for claude-code-cli/opus
    When load_prompts is called with tool="claude-code-cli" and model="opus"
    Then the opus-specific prompts are loaded

  Scenario: Load haiku prompts for Claude Code CLI
    Given optimized prompts exist for claude-code-cli/haiku
    When load_prompts is called with tool="claude-code-cli" and model="haiku"
    Then the haiku-specific prompts are loaded

  Scenario: Error when prompt file is missing
    Given a prompt file is missing at ~/.lw_coder/optimized_prompts/claude-code-cli/haiku/main.md
    When load_prompts is called with tool="claude-code-cli" and model="haiku"
    Then an error is raised indicating the missing file

  Scenario: Claude Code CLI uses default sonnet model
    Given the code command is invoked without --model parameter
    When the plan is validated and prompts are loaded
    Then sonnet model is used
    And prompts are loaded from claude-code-cli/sonnet/

  Scenario: Claude Code CLI respects explicit model parameter
    Given the code command is invoked with --model opus
    When the plan is validated and prompts are loaded
    Then opus model is used
    And prompts are loaded from claude-code-cli/opus/

  Scenario: Sub-agents are written to .claude/agents/ with proper format
    Given prompts are loaded for Claude Code CLI
    When run_code_command executes
    Then .claude/agents/code-review-auditor.md is created with:
      - YAML frontmatter (name, description, tools, model)
      - Prompt content below frontmatter
    And .claude/agents/plan-alignment-checker.md is created with:
      - YAML frontmatter (name, description, tools, model)
      - Prompt content below frontmatter

  Scenario: Code command defaults to Claude Code CLI executor
    Given the code command is invoked
    When no explicit executor is specified
    Then Claude Code CLI is used as the default executor

  Scenario: Placeholder prompts exist for all model variants
    Given the CLI is initialized in a project
    Then .lw_coder/optimized_prompts/ exists in project with structure:
      - claude-code-cli/sonnet/main.md
      - claude-code-cli/sonnet/code-review-auditor.md
      - claude-code-cli/sonnet/plan-alignment-checker.md
      - claude-code-cli/opus/main.md
      - claude-code-cli/opus/code-review-auditor.md
      - claude-code-cli/opus/plan-alignment-checker.md
      - claude-code-cli/haiku/main.md
      - claude-code-cli/haiku/code-review-auditor.md
      - claude-code-cli/haiku/plan-alignment-checker.md
```
