---
plan_id: capture-session-traces
status: done
evaluation_notes: []
git_sha: 8ea8cac7fec052d12dbfd6ee52f1d6006053471f
---

# Capture Conversation Traces from Coding Sessions

## Objectives

Automatically capture conversation traces from `lw_coder plan` and `lw_coder code` sessions and store them as human-readable markdown files. These traces will be used for DSPy prompt improvement analysis, providing a clean record of the conversation flow, tool usage, and subagent interactions without the noise of large tool outputs.

This enables:
1. Understanding what conversations led to specific code decisions
2. Analyzing prompt effectiveness across many sessions
3. Iterating on DSPy signatures and optimizer configurations
4. Auditing AI behavior and human refinements

## Requirements & Constraints

### Functional Requirements

1. **Trace Capture Scope**
   - Capture conversations from `lw_coder plan` command (interactive plan development)
   - Capture conversations from `lw_coder code` command (plan implementation)
   - Each command produces a separate trace file
   - Claude-code tool only (droid tool out of scope for this work)

2. **Session Identification and File Discovery**
   - After subprocess completes, search `~/.claude/projects/` for conversation JSONL files
   - Match files by **filesystem modification time** within 5-second buffer around subprocess execution
     - Use `file.stat().st_mtime` to check modification time
     - Search window: `[start_time - 5 seconds, end_time + 5 seconds]`
     - Accounts for filesystem timestamp precision and write buffering
   - Verify match by checking `cwd` field in first line of JSONL file
   - Extract session ID from matched JSONL file

3. **Data Processing and Cleaning**
   - Completely remove file history snapshots (type: "file-history-snapshot")
   - Keep main conversation + all subagent conversations
   - Truncate tool result content > 200 characters:
     - Format: `[first 50 chars][... truncated N chars ...][last 150 chars]`
     - Applied to: Read outputs, Bash command outputs, other large tool results
   - Keep without truncation:
     - User messages (all text)
     - Assistant text responses and thinking blocks
     - Tool call names and parameters
     - Subagent linkage metadata (sessionId, agentId, parentUuid, etc.)
     - Message timestamps and identifiers

4. **Markdown Output Format**
   - Single markdown file per session: `trace.md`
   - Hierarchical structure:
     - Header with session metadata (session ID, command, timestamp, worktree path)
     - "Main Conversation" section with all primary messages
     - Separate "Subagent: <name>" sections for each unique subagent
   - Tool calls formatted with code blocks for readability
   - Include assistant thinking blocks
   - Storage locations:
     - Code traces: `.lw_coder/runs/<plan_id>/<timestamp>/trace.md`
     - Plan traces: `.lw_coder/plan-traces/<timestamp>/trace.md`

5. **Capture Behavior**
   - Capture traces regardless of subprocess exit code (success or failure)
   - Store only processed markdown (no raw JSONL files)
   - Inherit existing 30-day retention policy via run directory pruning

6. **Error Handling**
   - Feature is always-on (no opt-in required)
   - Failures show brief user message: "Warning: Trace capture failed"
   - Log full error details to debug logs
   - Use fail-fast approach: show errors immediately when capture problems occur
   - Never block the command or suppress errors silently

### Technical Constraints

1. **Undocumented API Dependency**
   - Relies on `~/.claude/projects/` folder structure (Claude Code internal implementation)
   - Format may change without notice
   - Extensive error handling required for resilience
   - Fail-fast errors help detect when Claude Code changes break this feature

2. **Timing and Race Conditions**
   - Subprocess execution blocks Python - cannot detect AI completion in real-time
   - File creation timestamp accuracy depends on filesystem precision
   - 5-second buffer window accounts for write buffering and timestamp precision
   - Multiple concurrent `lw_coder` invocations unlikely to conflict within 10-second window

3. **Data Stripping Trade-offs**
   - 200-character truncation may lose some context (acceptable for DSPy analysis)
   - Tool result details removed, but tool calls fully preserved
   - Trade: readability + file size vs. completeness of debugging context

4. **Separate Traces per Command**
   - Plan and code sessions are captured separately (not combined)
   - Each has its own trace.md file in its storage directory
   - Code traces: organized by plan_id
   - Plan traces: organized by timestamp only (no plan_id yet when planning)
   - No cross-command trace aggregation in this work

### Design Constraints

1. **Modularity**: All trace-related logic in new `trace_capture.py` module
2. **Minimal Changes**: Only integrate capture calls in `code_command.py` and `plan_command.py`
3. **Performance**: File discovery must complete in < 1 second
4. **Observability**: Clear logging for debugging failures
5. **No CLI Flags**: Always-on behavior, no `--no-trace` option

### Claude Code `.claude/projects` Format Reference

This section documents the observed structure of Claude Code's conversation storage for implementers. This format is undocumented and may change without notice.

**Directory Structure:**
```
~/.claude/projects/
├── -home-kfrance-lw-coder--lw-coder-worktrees-ai-human-patch-capture/
│   ├── 4253c8e1-3da0-4ab3-812a-3e6b5267c497.jsonl    # Main conversation
│   ├── agent-4c64dc30.jsonl                          # Subagent conversation
│   ├── agent-6eb5b683.jsonl                          # Another subagent
│   └── .claude/                                      # Metadata folder
├── -home-kfrance-lw-coder--lw-coder-worktrees-temp-20251104-154813-774637-dd83cf6e/
│   └── <session-id>.jsonl
└── ...
```

**Folder Naming Convention:**
- Format: `-` + path with `/` replaced by `-`
- Example: `/home/kfrance/lw_coder/.lw_coder/worktrees/foo` → `-home-kfrance-lw-coder--lw-coder-worktrees-foo`
- Pattern appears consistent but is undocumented (reverse-engineered)

**File Types:**

1. **Main Conversation File**: `<session-id>.jsonl`
   - Named with UUID session ID
   - Contains main conversation between user and assistant
   - One line per message (newline-delimited JSON)
   - Largest file (hundreds of lines typical)

2. **Subagent Files**: `agent-<agent-id>.jsonl`
   - Named with short agent ID (8 hex chars)
   - Contains conversation for a specific subagent (e.g., code-review-auditor)
   - Same format as main conversation
   - Linked to main via `parentUuid` and `sessionId` fields

**JSONL Message Structure:**

Each line is a JSON object. Common message types observed:

1. **file-history-snapshot** (remove completely):
```json
{
    "type": "file-history-snapshot",
    "messageId": "987114b8-cc6c-4ef7-8c6d-d80f7f1db80b",
    "snapshot": {
        "messageId": "...",
        "trackedFileBackups": {},
        "timestamp": "2025-11-04T21:07:27.270Z"
    },
    "isSnapshotUpdate": false
}
```

2. **user** message:
```json
{
    "parentUuid": "85122982-c9fd-4c53-a135-c41d28009d95",
    "isSidechain": false,
    "userType": "external",
    "cwd": "/home/kfrance/lw_coder/.lw_coder/worktrees/ai-human-patch-capture",
    "sessionId": "4253c8e1-3da0-4ab3-812a-3e6b5267c497",
    "version": "2.0.32",
    "gitBranch": "ai-human-patch-capture",
    "agentId": "4c64dc30",  // Present for subagent messages
    "type": "user",
    "message": {
        "role": "user",
        "content": "Text or tool result content here"
    },
    "uuid": "61db4f73-21d2-4688-b716-69824b4f8951",
    "timestamp": "2025-11-04T21:07:30.404Z"
}
```

3. **assistant** message:
```json
{
    "parentUuid": "3667ccd3-61ff-4c3e-aa4c-012b24b32fd2",
    "isSidechain": false,
    "userType": "external",
    "cwd": "/home/kfrance/lw_coder/.lw_coder/worktrees/ai-human-patch-capture",
    "sessionId": "4253c8e1-3da0-4ab3-812a-3e6b5267c497",
    "version": "2.0.32",
    "gitBranch": "ai-human-patch-capture",
    "message": {
        "model": "claude-sonnet-4-5-20250929",
        "id": "msg_013W6Y8N6Mop8k6ggpH5aNk3",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "I'll help you implement the plan."
            }
        ],
        "stop_reason": null,
        "stop_sequence": null,
        "usage": {
            "input_tokens": 3,
            "cache_creation_input_tokens": 18452,
            "cache_read_input_tokens": 0,
            "output_tokens": 1
        }
    },
    "requestId": "req_011CUoXnpeJUFJUh5d2PR1yh",
    "type": "assistant",
    "uuid": "3667ccd3-61ff-4c3e-aa4c-012b24b32fd2",
    "timestamp": "2025-11-04T21:07:30.129Z"
}
```

4. **assistant** with tool_use:
```json
{
    "message": {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_01LRAsH5iwAZEtPKckuHNSZp",
                "name": "Read",
                "input": {
                    "file_path": "/home/kfrance/lw_coder/.lw_coder/worktrees/ai-human-patch-capture/plan.md"
                }
            }
        ]
    },
    "type": "assistant",
    ...
}
```

5. **user** with tool_result:
```json
{
    "type": "user",
    "message": {
        "role": "user",
        "content": [
            {
                "tool_use_id": "toolu_01LRAsH5iwAZEtPKckuHNSZp",
                "type": "tool_result",
                "content": "     1→---\n     2→plan_id: ai-human-patch-capture\n..."
            }
        ]
    },
    ...
}
```

**Key Fields for Implementation:**

- **`cwd`**: Current working directory - use to match session to worktree
- **`sessionId`**: UUID identifying the session - use for main conversation
- **`agentId`**: Short ID for subagents - use to group subagent messages
- **`timestamp`**: ISO 8601 timestamp - message creation time (for trace output/ordering only, NOT for file discovery)
- **`type`**: Message type (`user`, `assistant`, `file-history-snapshot`, etc.)
- **`message.role`**: `user` or `assistant`
- **`message.content`**: Array of content blocks (text, tool_use, tool_result)
- **`parentUuid`**: Links messages in conversation chain
- **`isSidechain`**: `true` for subagent messages, `false` for main

**Note on File Discovery:**
File discovery uses **filesystem modification time** (`st_mtime`), NOT the `timestamp` field inside the JSON.

**Message Linking:**
- Messages form a chain via `parentUuid` → `uuid` references
- Main conversation: `isSidechain: false`
- Subagent conversations: `isSidechain: true`, has `agentId`
- All messages from same session share `sessionId`

**Content Blocks in `message.content`:**
- `{"type": "text", "text": "..."}` - Plain text
- `{"type": "tool_use", "id": "...", "name": "Read", "input": {...}}` - Tool call
- `{"type": "tool_result", "tool_use_id": "...", "content": "..."}` - Tool result
- `{"type": "thinking", "thinking": "..."}` - Assistant thinking block

**Observed Characteristics:**
- Main conversation files: 100s-1000s of lines
- Subagent files: typically 2-50 lines
- **File discovery uses filesystem modification time** (`st_mtime`), not the `timestamp` field in JSON
- Filesystem modification time updates as conversation progresses
- Files created shortly after subprocess starts (within 1-2 seconds)
- Last modification typically within 1-2 seconds of subprocess completion

## Work Items

### 1. Create Trace Capture Module

**File**: `src/lw_coder/trace_capture.py`

Implement the core trace capture functionality with these components.

**Reusable Code:**
- **Timestamped directory creation**: Adapt `run_manager.py:create_run_directory()` (lines 31-68) - changes path structure but keeps race condition handling and error logic (~30 lines)
- **30-day retention pruning**: Adapt `run_manager.py:prune_old_runs()` (lines 122-194) - changes target directory but keeps pruning logic and error handling (~70 lines)
- **Logging**: Import `get_logger(__name__)` from `logging_config.py` - use directly
- **Repo root finding**: Import `find_repo_root()` from `repo_utils.py` - use directly
- **Custom exception pattern**: Follow `RunManagerError` / `RepoUtilsError` pattern for defining `TraceCaptureError`

**Components to implement:**

**1.1 Project Folder Discovery**
- Function `find_project_folder(worktree_path: Path, execution_window: Tuple[float, float]) -> Optional[Path]`
- Search `~/.claude/projects/` for folders with JSONL files
- Filter by **filesystem modification time** (`file.stat().st_mtime`) within execution window
- Execution window: 5 seconds before subprocess start, 5 seconds after subprocess end
- Return folder path or None if no match found
- Log search process for debugging
- Include module-level comment referencing ADR: `docs/adr/001-trace-capture-claude-dependency.md`

**1.2 JSONL File Collection**
- Function `collect_jsonl_files(project_folder: Path) -> List[Path]`
- Find all `.jsonl` files in project folder and subfolders
- Sort by modification time
- Return list of files

**1.3 Session Matching**
- Function `match_session_files(jsonl_files: List[Path], worktree_path: Path) -> Optional[str]`
- Read first line of each JSONL file to check `cwd` field
- Match against provided worktree path
- Extract and return session ID from `sessionId` field
- Return None if no match found

**1.4 JSONL Parsing**
- Function `parse_jsonl_file(file_path: Path) -> List[dict]`
- Read JSONL file line by line
- Parse each line as JSON
- Skip invalid lines, log warnings
- Return list of message objects

**1.5 Message Filtering**
- Function `filter_and_clean_messages(messages: List[dict]) -> List[dict]`
- Remove file history snapshot messages (type: "file-history-snapshot")
- Group messages by agent (main vs. subagents by agentId)
- Preserve all other message data
- Return cleaned messages grouped by agent

**1.6 Content Truncation**
- Function `truncate_content(content: str, max_chars: int = 200) -> str`
- If content length <= max_chars: return as-is
- If longer: return `content[:50] + f"[... {len(content) - 200} chars truncated ...]" + content[-150:]`
- Apply only to tool result content, not to user/assistant messages

**1.7 Tool Result Cleaning**
- Function `clean_tool_results(messages: List[dict]) -> List[dict]`
- For each message with tool_result type:
  - If content > 200 chars: truncate using truncate_content()
  - Preserve tool_use_id and type fields
- For user messages with tool results: apply truncation to content array items
- Return modified messages

**1.8 Markdown Generation**
- Function `generate_markdown(messages: List[dict], session_metadata: dict) -> str`
- Create header with metadata: session_id, command, timestamp, worktree, git branch
- Section "Main Conversation" with messages where no agentId or agentId == sessionId
- Separate sections for each subagent (by agentId):
  - Header: "Subagent: <name> (agent-<id>)"
  - All messages with that agentId
- Format each message:
  - User messages: `[timestamp] **User**\n<content>`
  - Assistant messages: `[timestamp] **Assistant**\n<content>`
  - Tool calls: `**Tool: <tool_name>**\n<code block with parameters>`
  - Tool results: `**Result:**\n<content or truncated content>`
  - Include thinking blocks if present
- Return formatted markdown string

**1.9 Main Capture Function**
- Function `capture_session_trace(worktree_path: Path, command: str, run_dir: Path, execution_start: float, execution_end: float) -> Path | None`
- Takes: worktree path, command type (plan/code), run directory, subprocess start/end times
- Execution flow:
  1. Calculate execution window: `(execution_start - 5, execution_end + 5)` seconds
  2. Find project folder via `find_project_folder()`
  3. If not found: log warning, return None
  4. Collect JSONL files via `collect_jsonl_files()`
  5. Match session via `match_session_files()`
  6. If no match: log warning, return None
  7. Parse JSONL via `parse_jsonl_file()`
  8. Clean messages via `filter_and_clean_messages()` and `clean_tool_results()`
  9. Generate markdown via `generate_markdown()`
  10. Write to `run_dir / "trace.md"`
  11. Log success with path
  12. Return path to created file
- Raises TraceCapturError on any failures

**1.10 Error Handling**
- Define `TraceCaptureError` exception class (follow pattern from `RunManagerError`, `RepoUtilsError`)
- Wrap all external operations in try/catch
- Use `get_logger(__name__)` from `logging_config.py`
- Log full details to debug logs with appropriate levels:
  - INFO for successful operations
  - DEBUG for detailed flow
  - WARNING for non-critical failures
  - ERROR for critical failures
- Provide brief user-facing error messages

### 2. Modify Code Command

**File**: `src/lw_coder/code_command.py`

Integrate trace capture after subprocess completes.

**2.1 Import and Setup**
- Import `trace_capture` module
- Import TraceCapturError

**2.2 Capture After Subprocess**
- After `subprocess.run()` returns (line ~383), capture execution start time before subprocess
- After subprocess completes, call `trace_capture.capture_session_trace()`
- Pass: worktree_path, "code", run_dir, execution_start_time
- Catch TraceCapturError and log brief warning to user: "Warning: Trace capture failed"
- Log full error details to debug logs
- Do not let errors block command execution

**2.3 Timing**
- Store execution start time before subprocess: `execution_start = time.time()`
- Store execution end time after subprocess: `execution_end = time.time()`
- Call capture after subprocess completes
- Pass both start and end times to capture function

### 3. Modify Plan Command

**File**: `src/lw_coder/plan_command.py`

Integrate trace capture after subprocess completes.

**3.1 Import and Setup**
- Import `trace_capture` module
- Import TraceCapturError

**3.2 Capture After Subprocess**
- Locate subprocess.run() call (around line 251)
- Before subprocess: `execution_start = time.time()`
- After subprocess: `execution_end = time.time()`
- After subprocess completes, call `trace_capture.capture_session_trace()`
- Store traces in persistent location: `.lw_coder/plan-traces/<timestamp>/trace.md`
  - Create timestamped directory using same format as code runs
  - Directory structure: `.lw_coder/plan-traces/<YYYYMMDD_HHMMSS>/trace.md`
  - Plan traces inherit same 30-day retention policy
- Pass: temp_worktree, "plan", plan_trace_dir, execution_start, execution_end
- Handle errors same as code command

**3.3 Plan Trace Storage Helper**
- Reuse timestamped directory creation pattern from `run_manager.py:create_run_directory()`
- Adapt to create `.lw_coder/plan-traces/<timestamp>/` instead of `runs/<plan_id>/<timestamp>/`
- Include race condition handling (microsecond suffix if timestamp exists)
- Return path for trace storage
- Create pruning function based on `run_manager.py:prune_old_runs()` pattern
- Use same 30-day retention constant (`RUN_RETENTION_DAYS = 30`)

### 4. Add Comprehensive Unit Tests

**File**: `tests/test_trace_capture.py`

Test the trace capture module in isolation.

**Test Cases:**
- `test_truncate_content_under_limit` - Content < 200 chars returns unchanged
- `test_truncate_content_over_limit` - Content > 200 chars truncates to first 50 + last 150
- `test_truncate_content_exact_limit` - Boundary condition at exactly 200 chars
- `test_filter_removes_file_snapshots` - File history snapshots removed from message list
- `test_filter_preserves_other_messages` - Non-snapshot messages preserved
- `test_clean_tool_results_truncates` - Tool results > 200 chars truncated
- `test_clean_tool_results_preserves_small` - Small tool results kept as-is
- `test_markdown_generation_basic` - Basic markdown output structure correct
- `test_markdown_generation_with_subagents` - Subagent sections created correctly
- `test_markdown_generation_preserves_thinking_blocks` - Thinking blocks included in output
- `test_parse_jsonl_handles_invalid_lines` - Invalid JSON lines skipped with warning
- `test_match_session_finds_correct_cwd` - Session matching by cwd field works
- `test_match_session_returns_none_on_no_match` - Returns None when no matching cwd found

Use pytest fixtures with mock JSONL data (don't require real Claude projects folder).

### 5. Add Integration Tests

**File**: `tests/test_trace_capture_integration.py`

Test the trace capture module end-to-end with realistic mock JSONL data.

**Important**: Do NOT run `lw_coder code` or `lw_coder plan` commands in tests—these are interactive and cannot be automated. Instead, test the `trace_capture` module functions directly with mock JSONL files and controlled inputs.

**Test Cases:**
- `test_capture_session_trace_with_mock_jsonl` - End-to-end test with mock JSONL files in temp directory
- `test_trace_file_contains_metadata` - Trace file header has session_id, timestamp, etc.
- `test_trace_file_hierarchical_structure` - Main section + subagent sections present
- `test_error_on_file_discovery_failure` - TraceCaptureError raised when no matching files found
- `test_error_on_format_mismatch` - TraceCaptureError raised when JSONL format unexpected
- `test_project_folder_discovery` - Test find_project_folder() with mock ~/.claude/projects/ structure

Use pytest fixtures to create temporary mock `~/.claude/projects/` directory structure with JSONL files.

### 6. Create ADR for Claude Code Dependency

**File**: `docs/adr/001-trace-capture-claude-dependency.md`

Create an Architecture Decision Record documenting the dependency on Claude Code's internal structure.

**Required content:**
- **Context**: Need to capture conversation traces for DSPy prompt improvement
- **Decision**: Rely on `~/.claude/projects/` folder structure and JSONL format
- **Consequences**:
  - Feature may break silently when Claude Code updates
  - No API stability guarantees
  - Fail-fast error handling helps detect breakage quickly
- **Detailed Structure Documentation**:
  - Project folder naming convention (path conversion with dashes)
  - JSONL file format and schema
  - Expected message types and fields
  - Example folder structure with real paths
  - Example JSONL message structure
- **Risks and Mitigations**:
  - Risk: Format changes without notice
  - Mitigation: Fail-fast error handling shows immediate feedback
  - Mitigation: Comprehensive error logging for debugging
- **Alternatives Considered**:
  - Contributing to Claude Code for stable API (rejected: out of scope)
  - Manual trace export (rejected: poor UX for automated DSPy workflows)
- **Future Considerations**:
  - Monitor for Claude Code updates that break compatibility
  - Consider upstreaming feature request to Anthropic

### 7. Documentation Updates

**File**: `docs/BEST_PRACTICES.md`

- Add section on "Architecture Decision Records (ADRs)"
- Document when to create ADRs (significant architectural choices, external dependencies, trade-off decisions)
- Reference ADR template and location (`docs/adr/`)

**Note**: No additional user-facing documentation needed. Feature is automatic/internal. Developers can refer to:
- ADR (docs/adr/001-trace-capture-claude-dependency.md) for architectural details
- Module docstrings in trace_capture.py for implementation details

## Deliverables

1. **`src/lw_coder/trace_capture.py`**
   - Complete module with all functions (10+ functions)
   - TraceCapturError exception class
   - Comprehensive docstrings for all public functions
   - Full error handling for Claude projects folder operations
   - Module-level comment referencing ADR: `docs/adr/001-trace-capture-claude-dependency.md`

2. **Modified `src/lw_coder/code_command.py`**
   - Trace capture integration after subprocess
   - Timing and error handling
   - Brief user-facing error messages

3. **Modified `src/lw_coder/plan_command.py`**
   - Trace capture integration after subprocess
   - Plan trace directory creation in `.lw_coder/plan-traces/<timestamp>/`
   - Timing and error handling
   - Plan trace pruning (30-day retention)

4. **Test Suite**
   - `tests/test_trace_capture.py` - 13+ unit tests
   - `tests/test_trace_capture_integration.py` - 6+ integration tests
   - All tests passing
   - Good coverage of edge cases
   - Note: Tests use mock JSONL data, do NOT run interactive commands

5. **ADR Documentation**
   - `docs/adr/001-trace-capture-claude-dependency.md` - Complete ADR
   - Documents Claude Code dependency with detailed structure examples
   - Explains risks, consequences, and alternatives considered

6. **Documentation**
   - Updated `docs/BEST_PRACTICES.md` with ADR guidance
   - No additional user-facing documentation (feature is automatic/internal)

7. **Working Feature**
   - Traces automatically captured during `lw_coder code` and `lw_coder plan` sessions
   - Clean markdown files with conversation flow
   - Subagent conversations in separate sections
   - Persistent storage with 30-day retention
   - Ready for DSPy prompt analysis

## Out of Scope

1. **Droid tool support** - Capturing traces for droid invocations (future work)
2. **Plan-to-code trace linking** - Connecting plan traces to subsequent code traces (future work)
3. **Trace analysis tooling** - Scripts to analyze/compare traces (manual review only)
4. **Trace upload/sync** - Sending traces to external systems
5. **Real-time trace streaming** - Capturing conversations as they happen
6. **Alternative formats** - Only markdown output, no JSON/CSV exports
7. **Configuration options** - No environment variables for truncation length, retention, etc.
8. **Patch integration** - No automatic comparison with patch capture feature
9. **Claude Code format change detection** - No automatic migration when format changes
10. **API stabilization** - Not contributing changes to Claude Code to stabilize this API

## Test Strategy

**Important**: Automated tests cannot run `lw_coder code` or `lw_coder plan` commands as these are interactive. Instead, tests should:

1. **Unit tests** - Test individual functions in `trace_capture.py` with mock data
2. **Integration tests** - Test end-to-end flow with mock `~/.claude/projects/` directory structure
3. **Manual testing** - Verify actual trace capture by running commands manually

### Expected Behavior (Manual Testing)

These scenarios describe the expected behavior when manually testing the feature:

1. **Successful code session captures trace**
   - Run `lw_coder code <plan_path>` and complete session
   - Verify trace.md exists at `.lw_coder/runs/<plan_id>/<timestamp>/trace.md`
   - Check trace contains: session metadata, main conversation section, user/assistant messages, thinking blocks, tool calls, truncated results

2. **Trace captures subagent conversations**
   - Run session that launches subagents
   - Verify trace.md has separate sections for each subagent
   - Check subagent sections show agent name and ID

3. **File history snapshots removed**
   - Verify trace.md does not contain file-history-snapshot messages
   - Verify other message types are preserved

4. **Large tool outputs truncated**
   - Verify outputs > 200 chars show: first 50 + `[... N chars truncated ...]` + last 150
   - Verify outputs < 200 chars are kept intact

5. **Session failures still capture trace**
   - Run session that exits with non-zero code
   - Verify trace.md is still created with conversation up to failure

6. **Trace capture failures are graceful**
   - Simulate trace discovery failure (e.g., delete ~/.claude/projects/)
   - Verify user sees: "Warning: Trace capture failed"
   - Verify command completes normally

7. **Thinking blocks included**
   - Verify trace.md includes assistant thinking blocks

8. **Tool call parameters preserved**
   - Verify tool call names and parameters are fully shown (not truncated)
   - Verify only tool results are truncated

9. **Plan command creates persistent trace**
   - Run `lw_coder plan` and complete session
   - Verify trace.md exists at `.lw_coder/plan-traces/<timestamp>/trace.md`
   - Verify 30-day retention policy applies

