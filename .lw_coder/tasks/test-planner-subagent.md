---
plan_id: test-planner-subagent
status: done
evaluation_notes: []
git_sha: 3ae9629ff7bf153e80c985b30c643b7446485ee5
---

## Objectives

Add a test-planner subagent to the plan command that runs in parallel with the maintainability-reviewer to provide comprehensive test strategy guidance. Refactor subagent infrastructure to use plain markdown prompts with dynamically-generated YAML front matter, ensuring consistency across Droid and Claude Code tools.

## Requirements & Constraints

### Functional Requirements

1. **New test-planner subagent**:
   - Analyzes plans and recommends appropriate test coverage
   - Only suggests tests when they make sense (not all plans need tests)
   - Understands existing test structure to avoid duplication
   - Recommends modifying existing tests before adding new ones
   - Suggests reusing test fixtures when appropriate
   - Focuses only on automated testing (no manual tests)
   - Evaluates test implementability (eliminates non-implementable test suggestions)
   - Emphasizes integration tests for happy paths and critical failures
   - Emphasizes unit tests for edge cases and non-happy paths
   - Maximizes value from each integration test (they're slower to run)
   - Never suggests tests that just verify code exists or check error message quality
   - Only suggests tests that validate actual codebase logic (not external libraries/systems)

2. **Subagent refactoring**:
   - Store prompts as plain markdown (no YAML front matter) in `src/lw_coder/prompts/plan-subagents/`
   - Dynamically generate YAML front matter based on tool and model
   - For Droid: use `model: gpt-5-codex`, write to `.factory/droids/`
   - For Claude Code: use `model: {model}` (inherited from plan command), write to `.claude/agents/`
   - Both subagents use `tools: read-only`
   - Use string-based template assembly (consistent with `_write_sub_agents()` in code command)

3. **Plan template updates**:
   - Update both `src/lw_coder/prompts/claude-code/plan.md` and `src/lw_coder/prompts/droid/plan.md`
   - Modify step 3 to invoke both subagents in parallel with clear descriptions

### Technical Constraints

- Maintain consistency with existing code command patterns (`_write_sub_agents()`)
- Keep tool configuration logic inline (no separate config files)
- Parallel execution is handled by Claude Code/Droid (not our concern)
- Model parameter inheritance will be added in a separate task (use hardcoded "sonnet" for now)

### Quality Requirements

- All existing tests must continue to pass
- New functionality must have comprehensive unit and integration test coverage
- Code must follow existing project patterns and conventions
- Documentation must be clear and complete

## Work Items

### 1. Create test-planner prompt

**File**: `src/lw_coder/prompts/plan-subagents/test-planner.md`

Create a plain markdown prompt (no YAML front matter) with comprehensive guidance for test planning:

- Analyze the plan to understand what code changes are proposed
- Examine existing test structure using Read and Grep tools
- Identify gaps in test coverage
- Determine if tests are appropriate for this plan (some plans don't need tests)
- Recommend specific, implementable automated tests
- Distinguish between unit tests (fast, mocked, edge cases) and integration tests (real APIs, happy paths, critical failures)
- Avoid suggesting tests that verify code existence, error message quality, or external library behavior
- Recommend reusing existing fixtures and modifying existing tests when possible
- Provide clear rationale for each test recommendation
- Flag any tests that seem difficult to implement with explanation

The prompt should emphasize practical, valuable testing that improves code quality without creating maintenance burden.

### 2. Refactor maintainability-reviewer prompt

**Source**: `src/lw_coder/droids/maintainability-reviewer.md`
**Destination**: `src/lw_coder/prompts/plan-subagents/maintainability-reviewer.md`

- Move the file to the new location
- Remove YAML front matter (everything between the `---` delimiters)
- Keep only the markdown prompt content
- Update any references to this file in the codebase

### 3. Create unified subagent writer function

**File**: `src/lw_coder/plan_command.py`

Replace `_copy_droids_for_plan()` and `_write_maintainability_agent()` with a single function:

```python
def _write_plan_subagents(worktree_path: Path, tool: str, model: str) -> None:
    """Write plan subagents with appropriate YAML front matter for the tool.

    Args:
        worktree_path: Path to the temporary worktree.
        tool: Tool name ("droid" or "claude-code").
        model: Model to use (for Claude Code; ignored for Droid which uses gpt-5-codex).

    Raises:
        PlanCommandError: If subagent writing fails.
    """
```

Implementation details:
- Load plain markdown prompts from `src/lw_coder/prompts/plan-subagents/`
- Determine destination directory based on tool:
  - Droid: `<worktree>/.factory/droids/`
  - Claude Code: `<worktree>/.claude/agents/`
- Determine model value based on tool:
  - Droid: `gpt-5-codex`
  - Claude Code: `{model}` parameter
- Generate YAML front matter using string templates (like `_write_sub_agents()`)
- Write both maintainability-reviewer.md and test-planner.md
- Use appropriate error handling and logging

### 4. Update plan command to use new function

**File**: `src/lw_coder/plan_command.py`

In `run_plan_command()`:
- Remove calls to `_copy_droids_for_plan()` and `_write_maintainability_agent()`
- Add single call to `_write_plan_subagents(temp_worktree, tool, "sonnet")`
- Note: Hardcode "sonnet" for now; model parameter will be added in separate task
- Update logging messages to reflect both subagents being configured

### 5. Update plan templates

**Files**:
- `src/lw_coder/prompts/claude-code/plan.md`
- `src/lw_coder/prompts/droid/plan.md`

Update step 3 to:
```
3. Use the maintainability-reviewer and test-planner subagents in parallel:
   - maintainability-reviewer: Evaluates long-term maintenance concerns and technical debt
   - test-planner: Plans comprehensive test coverage (only adds tests when appropriate)
```

### 6. Update related code references

Search for and update any other references to the old file locations or functions:
- Remove `_copy_droids_for_plan()` function definition
- Remove `_write_maintainability_agent()` function definition
- Update any imports or references to `src/lw_coder/droids/maintainability-reviewer.md`

## Deliverables

1. **New Files**:
   - `src/lw_coder/prompts/plan-subagents/test-planner.md` - Test planning subagent prompt
   - `src/lw_coder/prompts/plan-subagents/maintainability-reviewer.md` - Refactored maintainability prompt

2. **Modified Files**:
   - `src/lw_coder/plan_command.py` - New `_write_plan_subagents()` function, updated `run_plan_command()`
   - `src/lw_coder/prompts/claude-code/plan.md` - Updated step 3
   - `src/lw_coder/prompts/droid/plan.md` - Updated step 3

3. **Deleted Files**:
   - `src/lw_coder/droids/maintainability-reviewer.md` - Moved to new location

4. **Tests**:
   - Unit tests for `_write_plan_subagents()` function
   - Integration tests for plan command with both subagents

## Out of Scope

The following items are explicitly excluded from this plan:

- Adding `--model` flag to plan command (separate task already planned)
- Orchestrator patterns or subagent registry architecture
- Extracting tool configuration to separate config files
- Using Jinja2 or other templating engines (maintaining consistency with existing code)
- Detailed documentation of subagent architecture in separate docs
- Validation layer for test recommendations
- Error handling for parallel subagent execution (handled by Claude Code/Droid)
- Performance monitoring for parallel execution
- Changes to the code command or its subagents

## Unit Tests

**Approach**: Leverage existing test patterns from `test_write_sub_agents.py` and update existing tests in `test_plan_command.py` rather than creating a new test file. The existing tests for `_copy_droids_for_plan()` and `_write_maintainability_agent()` provide comprehensive coverage patterns that can be adapted.

**File**: `tests/unit/test_plan_command.py` (updates to existing tests)

Update existing `test_copy_droids_for_plan_*` and `test_write_maintainability_agent_*` tests to become `test_write_plan_subagents_*` tests:

1. **Test `_write_plan_subagents()` for Droid** (update from `test_copy_droids_for_plan_success`):
   - Verify both maintainability-reviewer.md and test-planner.md written to `.factory/droids/`
   - Verify YAML front matter includes `model: gpt-5-codex`
   - Verify YAML front matter includes `tools: read-only` (Droid-specific)
   - Verify prompt content correctly appended after front matter

2. **Test `_write_plan_subagents()` for Claude Code** (update from `test_write_maintainability_agent_success`):
   - Verify both maintainability-reviewer.md and test-planner.md written to `.claude/agents/`
   - Verify YAML front matter includes `model: {model}` parameter (e.g., "sonnet")
   - Verify YAML front matter **omits** `tools:` field (enables tool inheritance, consistent with `_write_sub_agents()` in code command)
   - Verify prompt content correctly appended after front matter

3. **Test model parameter variants** (follow pattern from `test_write_sub_agents_different_models`):
   - Parametrized test with models: "sonnet", "opus", "haiku"
   - Verify model value correctly written to frontmatter for Claude Code
   - Verify Droid always uses `gpt-5-codex` regardless of model parameter

4. **Test error handling** (update from `test_copy_droids_for_plan_errors` and `test_write_maintainability_agent_errors`):
   - Verify appropriate `PlanCommandError` when prompt file missing
   - Verify appropriate error on permission denied during write

5. **Test directory creation** (already covered in success tests):
   - Verify `.factory/droids/` created if missing (Droid)
   - Verify `.claude/agents/` created if missing (Claude Code)

6. **Test plan command integration**:
   - Verify `_write_plan_subagents()` called with correct parameters
   - Verify old functions (`_copy_droids_for_plan`, `_write_maintainability_agent`) removed

**Note on `tools:` field differences**:
- **Droid**: Uses `tools: read-only` in YAML front matter (explicit tool restriction)
- **Claude Code**: Omits `tools:` field entirely to enable tool inheritance from parent agent (consistent with `_write_sub_agents()` pattern in code_command.py, which documents: "Including 'tools: ["*"]' actually prevents tool access")

