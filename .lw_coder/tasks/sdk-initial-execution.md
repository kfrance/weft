---
plan_id: sdk-initial-execution
status: done
evaluation_notes: []
git_sha: 1042bc0452b7363249c6b3925ef3aa4637be19d2
---

# SDK Initial Execution for Code Command

## Objectives

Modify the `lw_coder code` command to use the Claude Code SDK for initial prompt execution, then automatically resume with the Claude Code CLI for interactive continuation. This enables programmatic capture of the initial session for future trace analysis and patch generation.

## Requirements & Constraints

### Functional Requirements

1. **SDK Integration for Code Command**
   - Use Claude Code SDK for initial prompt execution
   - Execute single query with the main implementation prompt
   - Collect all messages until query completes
   - Capture session ID from SDK's `ResultMessage`
   - Automatically resume conversation with CLI using captured session ID

2. **Configuration Management**
   - Create new `src/lw_coder/sdk_settings.json` for SDK session configuration with sandbox settings
   - Remove legacy `container_settings.json` and all references (housekeeping)

3. **Prompt Modifications**
   - Update all Claude Code main prompts (sonnet/opus/haiku) in `.lw_coder/optimized_prompts/claude-code-cli/{model}/main.md`
   - Add instruction: "When using uv commands, always include the `--no-cache` parameter"

4. **SDK Session Behavior**
   - Use `permission_mode="default"` with callback function
   - Callback blocks git commands using regex pattern `\bgit\b` (same as test script)
   - Pass model parameter to SDK (e.g., "sonnet", "opus", "haiku")
   - Use same optimized prompts as CLI session
   - Run in sandbox environment with settings from `sdk_settings.json`

5. **CLI Resume**
   - After SDK session completes successfully, automatically execute `claude -r <session_id> --model <model>`
   - Resume in same worktree to maintain conversation continuity
   - Preserve all SDK session context via session ID

6. **Trace Capture Enhancement**
   - Update `trace_capture.py` to accept optional `session_id` parameter
   - When `session_id` provided, use it directly instead of timing-based folder matching
   - Apply enhancement to both `plan` and `code` commands
   - Maintain fallback to timing-based approach when session ID not available

7. **Error Handling**
   - Fail fast on SDK session errors (no fallback to direct CLI)
   - Exit with clear error messages if session ID capture fails
   - Exit with error if CLI resume fails

### Technical Constraints

1. **Scope Limitations**
   - Only modify `code` command - do NOT change `plan`, `finalize`, or `eval` commands
   - Droid tool executor must remain unchanged and function identically
   - SDK integration only applies to `claude-code` tool, not `droid`

2. **Dependencies**
   - Add `claude-agent-sdk` via `uv add` (will install latest version)
   - SDK session ID API is stable and core to the SDK (despite light documentation)
   - Maintain compatibility with existing trace capture for non-SDK sessions

3. **Testing Requirements**
   - Create test script to verify session ID capture from `ResultMessage`
   - Verify SDK settings work correctly with sandbox and callback
   - Test auto-resume with CLI preserves conversation context

### Example SDK Code

The following example demonstrates the core SDK integration pattern to implement:

```python
import asyncio
import re
from pathlib import Path
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    ResultMessage,
    AssistantMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

# Pattern to match 'git' as a standalone word
GIT_COMMAND_PATTERN = re.compile(r'\bgit\b')

async def can_use_tool_callback(
    tool_name: str,
    input_data: dict,
    context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """Callback to inspect and control tool usage."""
    # Block git commands
    if tool_name == "Bash":
        command = input_data.get("command", "")
        if GIT_COMMAND_PATTERN.search(command):
            return PermissionResultDeny(message="Git commands are not allowed")

    return PermissionResultAllow()

async def run_sdk_session(prompt: str, model: str, settings_path: str) -> str:
    """Run SDK session and capture session ID.

    Returns:
        session_id from the ResultMessage
    """
    options = ClaudeAgentOptions(
        settings=settings_path,
        permission_mode="default",
        model=model,
        can_use_tool=can_use_tool_callback,
    )

    session_id = None

    async with ClaudeSDKClient(options=options) as client:
        await client.query(prompt)

        async for message in client.receive_response():
            if isinstance(message, ResultMessage):
                session_id = message.session_id
            elif isinstance(message, AssistantMessage):
                # Process assistant messages as needed
                pass

    if not session_id:
        raise RuntimeError("Failed to capture session ID from SDK session")

    return session_id
```

Key aspects to implement:
- Use `ClaudeAgentOptions` with `settings`, `permission_mode="default"`, `model`, and `can_use_tool` callback
- Callback blocks git commands using regex pattern `\bgit\b`
- Iterate through all messages with `async for message in client.receive_response()`
- Capture `session_id` from `ResultMessage`
- Handle the async context properly with `async with` and `await`

## Work Items

### 1. Add Claude Code SDK Dependency

- Add `claude-agent-sdk` to project dependencies using `uv add claude-agent-sdk`
- Verify SDK installation and imports work correctly

### 2. Create SDK Settings File

- Create `src/lw_coder/sdk_settings.json` with sandbox configuration:
  ```json
  {
    "sandbox": {
      "enabled": true,
      "autoAllowBashIfSandboxed": true,
      "allowUnsandboxedCommands": false
    }
  }
  ```
- This enables sandbox mode with automatic bash approval when sandboxed, but prevents unsandboxed command execution

### 3. Remove Legacy Container Settings

- Remove `src/lw_coder/container_settings.json` file
- Update `code_command.py` to remove references to `container_settings.json`
- Update `plan_command.py` to remove references to `container_settings.json`
- Update `finalize_command.py` to remove references to `container_settings.json`
- Update `host_runner.py` to remove `settings_file` parameter and validation
- Update all test files that reference `container_settings.json`
- Verify all commands still work after removal

### 4. Update Main Prompts with uv --no-cache Instruction

- Modify `.lw_coder/optimized_prompts/claude-code-cli/sonnet/main.md`
- Modify `.lw_coder/optimized_prompts/claude-code-cli/opus/main.md`
- Modify `.lw_coder/optimized_prompts/claude-code-cli/haiku/main.md`
- Add instruction in appropriate section: "When using uv commands, always include the `--no-cache` parameter"
- Ensure instruction is clear and actionable for the AI

### 5. Create SDK Session Runner Module

- Create `src/lw_coder/sdk_runner.py` module
- Implement async `run_sdk_session()` function following the example SDK code pattern above
- Key implementation details:
  - Accepts: worktree_path, prompt_content, model, sdk_settings_path
  - Creates `ClaudeSDKClient` with `ClaudeAgentOptions`
  - Uses `permission_mode="default"`
  - Implements `can_use_tool` callback blocking git commands (regex: `\bgit\b`)
  - Sends single query with prompt content
  - Iterates through all response messages via `client.receive_response()`
  - Captures session ID from `ResultMessage`
  - Returns: session_id on success
  - Raises: Exception on any failure (fail fast)
- Implement synchronous wrapper `run_sdk_session_sync()` that calls `asyncio.run()` on the async function
- Add `if __name__ == "__main__":` block for manual testing:
  - Parse command line arguments (worktree_path, prompt, model, settings_path)
  - Call `run_sdk_session_sync()`
  - Print session ID on success
  - This enables direct invocation: `python -m lw_coder.sdk_runner <args>`
- Use `add_dirs` parameter if needed for worktree access

### 6. Integrate SDK Session into Code Command

- Modify `src/lw_coder/code_command.py`:
  - Import SDK runner module
  - Load SDK settings from `src/lw_coder/sdk_settings.json`
  - After worktree setup and before CLI execution:
    - Load optimized main prompt for the model
    - Call `run_sdk_session()` with prompt, model, worktree, settings
    - Capture returned session_id
    - Log session ID for debugging
  - Build CLI resume command: `claude -r <session_id> --model <model>`
  - Execute CLI resume command instead of normal CLI command
  - Handle SDK errors by failing fast with clear error messages

### 7. Update Trace Capture for Session ID

- Modify `src/lw_coder/trace_capture.py`:
  - Add optional `session_id` parameter to `capture_session_trace()` function
  - When `session_id` is provided:
    - Skip `find_project_folder()` timing-based search
    - Use session ID directly to find matching JSONL files
    - Filter messages by the provided session ID
  - When `session_id` is None:
    - Fall back to existing timing-based approach
    - Maintain backward compatibility
- Update `code_command.py` to pass session_id to trace capture after CLI session completes
- Update `plan_command.py` to pass `session_id=None` (uses fallback)

### 8. Create Integration Test for SDK Session

- Create `tests/test_sdk_integration.py`
- Implement integration test following pytest best practices:
  - Mark test with `@pytest.mark.integration` (can be slow, runs real SDK)
  - Use `tmp_path` fixture to create minimal test project
  - Set up simple worktree with basic file structure
  - Call `sdk_runner.run_sdk_session_sync()` with simple prompt (e.g., "List files in current directory")
  - Assert that session ID is returned and is non-empty
  - Validate session ID format if applicable
- Test should complete in under 1 minute
- This provides automated validation that SDK integration works end-to-end
- Can also be run manually via: `pytest -v tests/test_sdk_integration.py::test_sdk_session_integration`

### 9. Update Documentation

- Document SDK integration approach in code comments
- Add inline comments explaining session ID handoff logic
- Update any relevant docstrings in modified modules
- Note in comments that SDK session ID API is stable but documentation is light

## Deliverables

1. **Updated Dependencies**
   - `pyproject.toml` includes `claude-agent-sdk` (latest version)
   - Dependency locked in `uv.lock`

2. **New SDK Settings File**
   - `src/lw_coder/sdk_settings.json` with sandbox configuration

3. **Legacy Settings Cleanup**
   - `src/lw_coder/container_settings.json` removed
   - All references to `container_settings.json` removed from codebase
   - Tests updated to not reference removed file

4. **Updated Prompts**
   - All three main prompts (sonnet/opus/haiku) include `uv --no-cache` instruction

5. **SDK Integration Module**
   - `src/lw_coder/sdk_runner.py` with async `run_sdk_session()` and sync wrapper
   - Callback implementation blocking git commands
   - Session ID capture logic
   - `__main__` entry point for manual testing (`python -m lw_coder.sdk_runner`)

6. **Modified Code Command**
   - `src/lw_coder/code_command.py` executes SDK session then auto-resumes CLI
   - Session ID captured and used for CLI resume
   - Error handling with fail-fast behavior

7. **Enhanced Trace Capture**
   - `src/lw_coder/trace_capture.py` accepts optional session_id parameter
   - Direct session ID lookup when available
   - Fallback to timing-based approach maintained

8. **Integration Test**
   - `tests/test_sdk_integration.py` with `@pytest.mark.integration` test
   - Validates SDK session ID capture end-to-end
   - Can be run manually or in CI
   - Manual testing via `python -m lw_coder.sdk_runner` also available

9. **Working Implementation**
   - `lw_coder code` command executes SDK session first
   - CLI automatically resumes with captured session ID
   - Conversation continuity maintained between SDK and CLI
   - Droid tool continues to work unchanged

## Out of Scope

1. **Patch Capture** - Capturing git diffs or patches from SDK session (motivation for this work, but not implemented in this plan)
2. **Plan Command Modification** - No changes to `lw_coder plan` command
3. **Finalize Command Modification** - No changes to `lw_coder finalize` command
4. **Eval Command Modification** - No changes to `lw_coder eval` command
5. **Droid Tool Changes** - Droid executor must remain unchanged
6. **SDK Documentation** - Not creating or requesting official SDK documentation from Anthropic
7. **Fallback Strategies** - No graceful degradation or fallback to direct CLI on SDK failures
8. **Alternative Architectures** - Not exploring pure SDK or pure CLI approaches

## Test Cases

```gherkin
Feature: SDK Initial Execution for Code Command

  Scenario: Integration test validates SDK session
    Given a minimal test project in tmp_path
    When the integration test runs sdk_runner.run_sdk_session_sync()
    Then a session ID is returned
    And the session ID is a non-empty string
    And the test completes in under 1 minute
```

**Note on test scope**: Per BEST_PRACTICES.md, automated tests should not run interactive commands like `lw_coder code`. The scenario above tests the SDK runner module directly. Integration of SDK session into the full `code` command flow should be verified through manual testing, not automated tests.
