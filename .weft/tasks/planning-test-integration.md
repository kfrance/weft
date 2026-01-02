---
plan_id: planning-test-integration
status: done
evaluation_notes: []
git_sha: 5cb1739ec9e6af9f3d92ad085b4b34f7404d1d3b
---

# Planning Test Integration

Integrate testing considerations into the planning workflow by restoring lost plan templates, adding a test-discovery subagent for early test context gathering, and enhancing the main planning prompt to incorporate testing questions.

## Objectives

1. **Restore lost plan.md templates** - The `plan.md` templates were deleted during the lw_coder→weft rename and need to be restored from git history
2. **Add test-discovery subagent** - Enable early test context gathering during planning so the main agent can ask informed testing questions
3. **Enhance planning prompt for testing** - Guide the main agent to consider testing throughout the planning conversation, not just as an afterthought
4. **Improve testability** - Extract subagent configuration to module level for better unit testing

## Requirements & Constraints

### Functional Requirements
- Main planning agent must be able to invoke `test-discovery` subagent when it has gathered enough context about the task
- `test-discovery` must analyze existing tests to identify:
  - Relevant integration tests that intersect with proposed code changes
  - Existing tests that might need modification
  - Reusable fixtures and test patterns
- `test-discovery` provides discovery information only (not recommendations) - the main agent decides what questions to ask
- `test-planner` continues to evaluate final plan's test recommendations alongside `maintainability-reviewer`
- Both `claude-code` and `droid` tools must have identical `plan.md` templates

### Technical Constraints
- `plan.md` templates must contain `{IDEA_TEXT}` placeholder for idea injection (used by `plan_command.py:228`)
- Subagent prompts must be plain markdown without YAML front matter (front matter is generated dynamically by `_write_plan_subagents()`)
- `PLAN_SUBAGENT_CONFIGS` must be a module-level constant in `plan_command.py` for testability

### Design Decisions
- **Two test subagents**: `test-discovery` (early, discovery-focused) + `test-planner` (late, evaluation-focused)
- **Main agent controls timing**: The main agent decides when to invoke `test-discovery` based on gathered context
- **Context passed by main agent**: `test-discovery` receives context from the main agent, not the raw plan idea
- **Keep proposed naming**: Use `test-discovery` and `test-planner` (not alternative names like `existing-test-finder`)

## Work Items

### 1. Restore plan.md Templates

Restore the `plan.md` templates that were lost during the lw_coder→weft rename (commit `60e7482`).

**Files to create:**
- `src/weft/prompts/claude-code/plan.md`
- `src/weft/prompts/droid/plan.md`

**Source:** Recover content from git history:
```bash
git show 266965f:src/lw_coder/prompts/claude-code/plan.md
```

**Updates needed to recovered content:**
- Change `.lw_coder/tasks/` references to `.weft/tasks/`
- Add guidance for invoking `test-discovery` subagent
- Add guidance for asking testing-related clarifying questions
- Update step 3 to mention all three subagents (maintainability-reviewer, test-planner, test-discovery)

### 2. Create test-discovery Subagent Prompt

Create a new discovery-focused subagent that analyzes existing tests.

**File to create:** `src/weft/prompts/plan-subagents/test-discovery.md`

**Prompt responsibilities:**
- Analyze the codebase's test structure (unit vs integration organization)
- Identify existing tests relevant to the proposed changes
- Find tests that may need modification based on the changes
- Discover reusable fixtures, helpers, and test patterns
- Report test coverage gaps in affected areas
- Provide structured output the main agent can use to ask informed questions

**Output format should include:**
- Relevant existing tests (files and descriptions)
- Tests likely needing modification
- Reusable fixtures and patterns
- Coverage observations (areas with/without tests)

**What it should NOT do:**
- Make test recommendations (that's test-planner's job)
- Decide what tests to write
- Evaluate the plan's test strategy

### 3. Update Main Planning Prompt

Enhance the restored `plan.md` to guide testing considerations throughout planning.

**Changes to make:**
- Add instruction to consider testing implications when asking clarifying questions
- Add guidance on when to invoke `test-discovery` (when enough context about the task is gathered)
- Explain how to pass context to `test-discovery` (describe the proposed changes, affected files/modules)
- Add instruction to use discovery results to ask informed testing questions
- Update subagent invocation step to show `test-discovery` can run earlier than the other subagents

### 4. Extract PLAN_SUBAGENT_CONFIGS to Module Level

Refactor `plan_command.py` to make subagent configuration testable.

**Current state (lines 102-106):**
```python
# Inside _write_plan_subagents()
subagent_configs = {
    "maintainability-reviewer": "Evaluates plans from a long-term maintenance perspective",
    "test-planner": "Plans comprehensive test coverage (only adds tests when appropriate)"
}
```

**Target state:**
```python
# Module level constant
PLAN_SUBAGENT_CONFIGS = {
    "maintainability-reviewer": "Evaluates plans from a long-term maintenance perspective",
    "test-discovery": "Analyzes existing tests to inform testing questions during planning",
    "test-planner": "Plans comprehensive test coverage (only adds tests when appropriate)"
}

def _write_plan_subagents(worktree_path: Path, tool: str, model: str) -> None:
    # ... use PLAN_SUBAGENT_CONFIGS instead of local variable
```

### 5. Add test-discovery to Subagent Configuration

Add the new subagent to the configuration dict.

**Entry to add:**
```python
"test-discovery": "Analyzes existing tests to inform testing questions during planning"
```

## Deliverables

### New Files
| File | Purpose |
|------|---------|
| `src/weft/prompts/claude-code/plan.md` | Planning prompt template for Claude Code |
| `src/weft/prompts/droid/plan.md` | Planning prompt template for Droid |
| `src/weft/prompts/plan-subagents/test-discovery.md` | Test discovery subagent prompt |

### Modified Files
| File | Changes |
|------|---------|
| `src/weft/plan_command.py` | Extract `PLAN_SUBAGENT_CONFIGS` to module level, add `test-discovery` entry |
| `tests/unit/test_plan_command.py` | Add tests for three-subagent setup |

## Out of Scope

- **Modifying test-planner.md** - The existing test-planner prompt is already well-designed for evaluation; no changes needed
- **Modifying maintainability-reviewer.md** - No changes required
- **Integration tests for planning workflow** - Per CLAUDE.md guidelines, interactive commands should not have automated tests
- **ADR documentation** - While the maintainability-reviewer suggested ADR 003, this can be added separately if needed
- **Changing subagent execution order** - The main agent controls when to invoke test-discovery; no orchestration changes needed in plan_command.py

## Unit Tests

### Existing Coverage (No Changes Needed)

**test_repo_utils.py** - The parametrized test `test_load_prompt_template_different_tools()` at lines 115-120 already includes `("claude-code", "plan")` and `("droid", "plan")` in its test cases. No modifications needed.

### Extend Existing Tests

**test_plan_command.py - Verify three subagents created:**
- Modify `test_write_plan_subagents_droid()` to verify `test-discovery.md` is created alongside existing subagents
- Modify `test_write_plan_subagents_claude_code()` to verify `test-discovery.md` is created

### New Tests

**test_plan_command.py:**

1. `test_plan_subagent_configs_is_module_constant()` - Verify `PLAN_SUBAGENT_CONFIGS` is accessible at module level
2. `test_write_plan_subagents_creates_all_configured()` - Verify number of created files matches `len(PLAN_SUBAGENT_CONFIGS)`
3. `test_plan_template_has_idea_placeholder()` - Verify restored templates contain `{IDEA_TEXT}`

## Integration Tests

No new integration tests recommended. The planning workflow is interactive (`weft plan` launches an interactive session), which per CLAUDE.md guidelines should not have automated tests. The unit tests above adequately cover the new functionality.

Existing integration tests in `tests/integration/test_command_smoke.py` provide basic verification that the plan command can be invoked without errors.
