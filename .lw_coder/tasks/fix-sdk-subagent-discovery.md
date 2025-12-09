---
plan_id: fix-sdk-subagent-discovery
status: done
evaluation_notes: []
git_sha: a59340cdec9471939c45e6a1dbe7e747cb8ad3cd
---

# Fix SDK Subagent Discovery for Code Review and Plan Alignment Agents

## Objectives

Enable code-review-auditor and plan-alignment-checker subagents to be available during SDK execution in the `lw_coder code` command. Currently, these subagents work in pure CLI sessions but are not available when running via the Claude Agent SDK.

## Requirements & Constraints

### Requirements

1. **SDK session must have access to subagents**: The code-review-auditor and plan-alignment-checker agents must be available during the initial SDK execution phase (before CLI resume)
2. **Maintain CLI resume compatibility**: Filesystem agents in `.claude/agents/` must remain for CLI resume sessions to discover them
3. **Single source of truth**: Both filesystem and programmatic agent definitions must be built from the same prompts dictionary
4. **No behavioral changes**: Agent functionality should remain identical, just availability is fixed
5. **Comprehensive testing**: Integration tests must verify agents work in both SDK and CLI modes

### Constraints

- Cannot rely on filesystem-based agent discovery in the SDK (tests show it doesn't work)
- Must maintain backward compatibility with existing CLI resume workflow
- Changes should be minimal and localized to sdk_runner.py and code_command.py
- Must not break existing agent behavior in plan command (maintainability-reviewer)

### Technical Context

**Root Cause**: The Claude Agent SDK does not discover filesystem-based agents in `.claude/agents/` directories during execution. Tests demonstrate:
- Filesystem agents: SDK tries to invoke them but returns "agent not available" error
- Programmatic agents (via `agents` parameter): Work perfectly
- Settings file presence: Does not affect discovery

**Current Flow**:
1. `code_command.py` line 278: Write agents to `.claude/agents/` via `_write_sub_agents()`
2. `code_command.py` line 366: Run SDK session with `run_sdk_session_sync()`
3. `code_command.py` line 378: Resume with CLI using session ID

**Proposed Fix**: Pass agents programmatically to SDK via the `agents` parameter in `ClaudeAgentOptions` while keeping filesystem agents for CLI compatibility.

## Work Items

### 1. Add agents parameter to run_sdk_session function

**File**: `src/lw_coder/sdk_runner.py`

**Changes**:
- Add `agents` parameter to `run_sdk_session()` function signature (line 76-81)
  - Type: `dict[str, AgentDefinition] | None = None`
- Add `agents` parameter to `run_sdk_session_sync()` wrapper (line 177-182)
- Pass `agents` parameter to `ClaudeAgentOptions` (line 113)
- Update docstrings to document the new parameter

**Example**:
```python
async def run_sdk_session(
    worktree_path: Path,
    prompt_content: str,
    model: str,
    sdk_settings_path: Path,
    agents: dict[str, AgentDefinition] | None = None,  # NEW
) -> str:
    """Run SDK session and capture session ID.

    Args:
        worktree_path: Path to the worktree directory where the session runs.
        prompt_content: The main prompt content to execute.
        model: Model variant to use (e.g., "sonnet", "opus", "haiku").
        sdk_settings_path: Path to the SDK settings JSON file.
        agents: Optional dict of agent definitions for programmatic registration.
                If None, agents are only available via filesystem discovery.
    ...
    """
    options = ClaudeAgentOptions(
        cwd=worktree_path,
        model=model,
        settings=str(sdk_settings_path),
        permission_mode="default",
        can_use_tool=_can_use_tool_callback,
        agents=agents,  # NEW
    )
```

### 2. Add import for AgentDefinition

**File**: `src/lw_coder/sdk_runner.py`

**Changes**:
- Add `AgentDefinition` to the imports from `claude_agent_sdk` (line 23-33)

**Example**:
```python
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AgentDefinition,  # NEW
    ResultMessage,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
```

### 3. Create helper function to build agent definitions from prompts

**File**: `src/lw_coder/code_command.py`

**Changes**:
- Add new helper function `_build_agent_definitions()` after `_write_sub_agents()` function (after line 117)
- Function should accept `prompts` dict and `model` string
- Return dict mapping agent names to `AgentDefinition` objects
- Import `AgentDefinition` from `claude_agent_sdk`

**Example**:
```python
def _build_agent_definitions(
    prompts: dict[str, str], model: str
) -> dict[str, AgentDefinition]:
    """Build programmatic agent definitions from prompts dictionary.

    Creates AgentDefinition objects for SDK execution. These are built from
    the same prompts used for filesystem agents, ensuring synchronization.

    Args:
        prompts: Dictionary containing agent prompts.
        model: Model variant being used.

    Returns:
        Dictionary mapping agent names to AgentDefinition objects.
    """
    agents = {
        "code-review-auditor": AgentDefinition(
            description="Reviews code changes for quality and compliance",
            prompt=prompts["code_review_auditor"],
            model=model,
        ),
        "plan-alignment-checker": AgentDefinition(
            description="Verifies implementation aligns with the original plan",
            prompt=prompts["plan_alignment_checker"],
            model=model,
        ),
    }
    return agents
```

### 4. Pass agents to SDK session in code command

**File**: `src/lw_coder/code_command.py`

**Changes**:
- Build agent definitions before calling SDK session (line 364, before "Running initial SDK session" log)
- Pass `agents` parameter to `run_sdk_session_sync()` call (line 366-371)

**Example**:
```python
logger.info("Running initial SDK session...")

# Build agent definitions for SDK execution
agents = _build_agent_definitions(prompts, effective_model)

try:
    session_id = run_sdk_session_sync(
        worktree_path=worktree_path,
        prompt_content=prompts["main_prompt"],
        model=effective_model,
        sdk_settings_path=sdk_settings_path,
        agents=agents,  # NEW
    )
    logger.info("SDK session completed. Session ID: %s", session_id)
```

### 5. Add integration tests for SDK subagent availability

**File**: `tests/integration/test_sdk_subagents.py` (new file)

**Changes**:
- Create integration tests that verify agents work via SDK execution (not CLI)
- Use SDK directly (`ClaudeSDKClient` and `ClaudeAgentOptions`) to avoid interactive sessions
- Test programmatic agent registration and invocation
- Document filesystem discovery limitation

**Test cases**:
1. `test_sdk_programmatic_agents_work`:
   - Use `ClaudeSDKClient` with programmatic `AgentDefinition` objects
   - Query asks to use the agent
   - Verify agent is invoked (Task tool called with agent name in messages)
   - This is an integration test - makes real API calls

2. `test_build_agent_definitions`:
   - Unit test for `_build_agent_definitions()` helper
   - Verify it creates correct `AgentDefinition` objects from prompts
   - Check descriptions, models, prompts are set correctly
   - No SDK/API calls

**Important**: Do NOT test CLI resume mode in automated tests - that requires interactive `claude` CLI sessions which would hang. CLI compatibility is verified manually.

### 6. Update existing unit tests

**File**: `tests/unit/test_sdk_runner.py`

**Changes**:
- Update tests that call `run_sdk_session()` to handle new `agents` parameter
- Add test for `agents` parameter being passed through correctly
- Mock `AgentDefinition` creation

### 7. Add documentation comments

**Files**: `src/lw_coder/sdk_runner.py`, `src/lw_coder/code_command.py`

**Changes**:
- Document WHY we use both filesystem and programmatic agents
- Link to the SDK limitation (filesystem discovery doesn't work)
- Explain that both are built from the same prompts source (single source of truth)
- Note that filesystem agents remain for CLI resume compatibility

**Example comment in code_command.py**:
```python
# NOTE: Agents are registered in two ways due to SDK limitation:
# 1. Filesystem (.claude/agents/*.md) - for CLI resume sessions
# 2. Programmatic (agents parameter) - for SDK execution
# Both are built from the same prompts source to ensure synchronization.
```

## Deliverables

1. **Modified src/lw_coder/sdk_runner.py**:
   - Added `agents` parameter to both `run_sdk_session()` and `run_sdk_session_sync()`
   - Added `AgentDefinition` import
   - Updated docstrings
   - Pass agents to `ClaudeAgentOptions`

2. **Modified src/lw_coder/code_command.py**:
   - Added `_build_agent_definitions()` helper function
   - Added `AgentDefinition` import
   - Build and pass agents to SDK session
   - Added documentation comments explaining dual-mode approach

3. **New tests/integration/test_sdk_subagents.py**:
   - Integration tests verifying SDK agent availability
   - Tests covering both programmatic and filesystem modes
   - Regression test documenting filesystem discovery limitation

4. **Updated tests/unit/test_sdk_runner.py**:
   - Tests handle new `agents` parameter
   - Mock verification for agent definitions

5. **Verification**:
   - Integration tests pass showing agents work in SDK mode
   - Unit tests pass with updated signatures
   - CLI resume still works with filesystem agents
   - No behavioral changes to agent functionality

## Out of Scope

The following are explicitly NOT part of this plan:

1. **Fixing SDK filesystem discovery**: We're working around the SDK limitation, not fixing it upstream
2. **Agent registry abstraction**: No need for `AgentRegistry` class - prompts dict is already single source of truth
3. **Agent versioning or A/B testing**: Not changing agent functionality, just availability
4. **Dynamic agent selection**: All agents are always registered
5. **Removing filesystem agents**: CLI resume still needs them
6. **Filing SDK bug report**: Can be done separately if desired
7. **Agent configuration beyond prompts**: Only implementing what's needed for current agents
8. **Changes to plan command agents**: maintainability-reviewer works differently and is unaffected

