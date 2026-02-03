---
plan_id: LW-118-headless-output-formatting
status: done
evaluation_notes: []
git_sha: a7090461cd0d26e51917043af8c92631f89ab65c
---

# LW-118: Improve Headless Mode Output Formatting

## Objectives

Improve the readability of headless output from `weft code` by adding visual distinction between AI conversational text, tool calls, and thinking blocks using the Rich library for styled terminal output.

## Requirements & Constraints

### Functional Requirements
- AI conversational text: `▶` prefix (triangle), default color
- Tool calls: `🛠️` prefix (wrench emoji), cyan color, show description if available
- Thinking blocks: orange color, italics, no prefix
- Graceful fallback to plain text formatting if Rich is unavailable

### Technical Constraints
- Use Rich library for terminal styling (handles terminal compatibility)
- Update `claude-agent-sdk` to latest version (pinned)
- Add `rich` as a dependency (latest version, pinned)
- Create a separate `src/weft/output.py` module for formatting logic (reusability)
- Handle unknown/future block types gracefully (don't crash)

### Styling Summary

| Block Type | Prefix | Color | Style |
|------------|--------|-------|-------|
| TextBlock | `▶ ` | default | normal |
| ToolUseBlock | `🛠️ ` | cyan | normal |
| ThinkingBlock | (none) | orange | italic |

## Work Items

### 1. Update Dependencies
- Run `uv add claude-agent-sdk` to update to the latest version (pins in pyproject.toml)
- Run `uv add rich` to add the Rich library (pins latest version in pyproject.toml)

### 2. Create Output Formatting Module
- Create `src/weft/output.py` with:
  - Rich Console initialization with graceful fallback
  - `format_text_block(block)` - formats TextBlock with ▶ prefix
  - `format_tool_block(block)` - formats ToolUseBlock with 🛠️ prefix, cyan
  - `format_thinking_block(block)` - formats ThinkingBlock with orange italics
  - `print_assistant_message(message)` - handles AssistantMessage with multiple blocks

### 3. Update SDK Runner
- Import `ThinkingBlock` from `claude_agent_sdk`
- Import formatting functions from `src/weft/output.py`
- Replace current `print()` calls in `run_sdk_session()` with `print_assistant_message()`
- Handle unknown block types gracefully (log or skip, don't crash)

### 4. Unit Tests
Create `tests/unit/test_output.py` with tests that verify observable behavior using `capsys`:

- **test_text_block_output_has_prefix**: Verify TextBlock content prints with ▶ prefix
- **test_tool_block_output_has_prefix_and_name**: Verify ToolUseBlock prints with 🛠️ prefix and tool name
- **test_tool_block_shows_description_when_available**: Verify description appears in output
- **test_thinking_block_output_is_styled**: Verify ThinkingBlock content appears in output
- **test_mixed_blocks_all_print**: Verify AssistantMessage with multiple block types prints all blocks
- **test_empty_text_block_handled**: Verify empty TextBlock doesn't crash
- **test_unknown_block_type_handled_gracefully**: Verify unrecognized block types don't crash
- **test_fallback_when_rich_unavailable**: Verify output still works without Rich (mock ImportError)

### 5. Integration Tests (must pass)
These existing integration tests must pass after the changes:

- `tests/integration/test_headless.py::TestCodeHeadless::test_code_command_runs_sdk_in_headless`
- `tests/integration/test_headless.py::TestPlanHeadless::test_plan_command_loads_prompts_and_runs`
- `tests/integration/test_sdk.py::TestRealSDKSession::test_real_sdk_session_returns_session_id`
- `tests/integration/test_sdk.py::TestRealSDKSession::test_trace_capture_from_sdk_session`
- `tests/integration/test_sdk_subagents.py::TestSDKProgrammaticAgents::test_sdk_accepts_agents_parameter`
- `tests/integration/test_sdk_subagents.py::TestSDKProgrammaticAgents::test_sdk_session_without_agents_also_works`

## Deliverables

1. Updated `pyproject.toml` with new dependencies
2. New module `src/weft/output.py` with formatting logic
3. Modified `src/weft/sdk_runner.py` to use new formatting
4. New test file `tests/unit/test_output.py`
5. All integration tests passing

## Out of Scope

- Changes to interactive mode (non-headless)
- Output formatting in other commands (judge, eval) - can be added later using `output.py`
- Logging configuration changes
- User-configurable color themes
- ASCII fallback for emoji (Rich handles terminal compatibility)
