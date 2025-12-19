# ADR 001: Trace Capture Claude Code Dependency

## Status

Accepted

## Context

The weft platform uses DSPy signatures and the GEPA optimizer to coordinate specialized subagents for improved code quality. To iterate on these prompts effectively, we need to capture conversation traces from coding sessions that show:

- What conversations led to specific code decisions
- How prompts performed across many sessions
- Where subagents were invoked and what they produced
- The full context of AI behavior and human refinements

These traces enable data-driven prompt improvement and systematic analysis of the multi-agent system's effectiveness.

### Requirements

1. **Automated Capture**: Traces must be captured automatically during `weft plan` and `weft code` sessions without user intervention
2. **Clean Format**: Traces should be human-readable markdown files, not raw API logs
3. **Selective Content**: Keep conversation flow and tool usage, but truncate large outputs to maintain readability
4. **Subagent Visibility**: Separate sections for each subagent conversation
5. **Non-Blocking**: Trace capture failures should never block or interrupt coding sessions

### Available Options

1. **Manual Export**: User manually exports conversations after each session
   - Pros: No dependency on internals
   - Cons: Poor UX, likely to be forgotten, not automatable for batch analysis

2. **Contribute to Claude Code**: Propose official trace export API to Anthropic
   - Pros: Stable, supported API
   - Cons: Out of scope for this project, uncertain timeline, may not be accepted

3. **Depend on Claude Code Internals**: Use `~/.claude/projects/` folder structure
   - Pros: Immediate availability, works today, minimal implementation
   - Cons: Undocumented API, may break without notice

## Decision

We will depend on Claude Code's internal `~/.claude/projects/` directory structure and JSONL conversation format to capture traces automatically.

This decision prioritizes:
- **Immediate Value**: Feature works today for DSPy prompt iteration
- **Developer Productivity**: Automatic capture means no workflow interruption
- **Acceptable Risk**: Breaking changes are detectable via fail-fast error handling

## Consequences

### Positive

- Traces are captured automatically after every coding session
- Clean markdown format ready for human review and analysis
- Subagent conversations are clearly separated
- 30-day retention matches existing run directory policy
- Non-blocking: trace failures don't interrupt coding workflow

### Negative

- **Stability Risk**: Claude Code updates may break this feature silently
- **No API Contract**: No guarantees about format stability or backward compatibility
- **Maintenance Burden**: Must monitor for Claude Code updates and fix breakage reactively
- **Limited Documentation**: Must reverse-engineer and document the format ourselves

### Mitigations

1. **Fail-Fast Error Handling**: Show errors immediately when capture problems occur
   - Brief user message: "Warning: Trace capture failed"
   - Full error details in debug logs
   - Helps detect breaking changes quickly

2. **Comprehensive Error Logging**: Log all discovery steps for debugging
   - Project folder search process
   - File modification time checks
   - Session matching attempts
   - Parsing failures

3. **Detailed Format Documentation**: Document observed structure in ADR and code
   - Project folder naming convention
   - JSONL file types and schema
   - Message linking via UUID references
   - Example structures with real paths

4. **Non-Critical Feature Design**: Never block core commands
   - Trace capture runs after subprocess completes
   - Failures logged but don't affect exit code
   - User can continue working even if traces fail

## Claude Code `.claude/projects` Format

This section documents the observed internal structure for reference and future maintenance.

### Directory Structure

```
~/.claude/projects/
├── -home-kfrance-weft--weft-worktrees-plan-id/
│   ├── 4253c8e1-3da0-4ab3-812a-3e6b5267c497.jsonl    # Main conversation
│   ├── agent-4c64dc30.jsonl                          # Subagent conversation
│   ├── agent-6eb5b683.jsonl                          # Another subagent
│   └── .claude/                                      # Metadata folder
└── ...
```

### Folder Naming Convention

- Algorithm: Strip leading `/`, replace `/`, `.`, `_` with `-`, then prefix with `-`
- Example: `/home/user/weft/.weft/worktrees/foo` → `-home-user-weft--weft-worktrees-foo`
- Appears consistent but undocumented (reverse-engineered)

### File Types

**Main Conversation**: `<session-id>.jsonl`
- Named with UUID session ID
- Contains primary user-assistant conversation
- One message per line (newline-delimited JSON)
- Typically largest file (hundreds of lines)

**Subagent Files**: `agent-<agent-id>.jsonl`
- Named with short agent ID (8 hex chars)
- Contains conversation for specific subagent (e.g., code-review-auditor, plan-alignment-checker)
- Same JSONL format as main conversation
- Linked to main via `parentUuid` and `sessionId` fields

### JSONL Message Structure

Each line is a JSON object representing one message. Common types:

**1. file-history-snapshot** (removed by trace capture):
```json
{
    "type": "file-history-snapshot",
    "messageId": "987114b8-cc6c-4ef7-8c6d-d80f7f1db80b",
    "snapshot": {
        "messageId": "...",
        "trackedFileBackups": {},
        "timestamp": "2025-11-04T21:07:27.270Z"
    }
}
```

**2. user message**:
```json
{
    "parentUuid": "85122982-c9fd-4c53-a135-c41d28009d95",
    "isSidechain": false,
    "userType": "external",
    "cwd": "/home/user/repo/.weft/worktrees/plan-id",
    "sessionId": "4253c8e1-3da0-4ab3-812a-3e6b5267c497",
    "version": "2.0.32",
    "gitBranch": "plan-id",
    "agentId": "4c64dc30",  // Only present for subagent messages
    "type": "user",
    "message": {
        "role": "user",
        "content": [
            {"type": "text", "text": "User message text"},
            {
                "type": "tool_result",
                "tool_use_id": "toolu_xxx",
                "content": "Tool output..."
            }
        ]
    },
    "uuid": "61db4f73-21d2-4688-b716-69824b4f8951",
    "timestamp": "2025-11-04T21:07:30.404Z"
}
```

**3. assistant message**:
```json
{
    "parentUuid": "3667ccd3-61ff-4c3e-aa4c-012b24b32fd2",
    "isSidechain": false,
    "cwd": "/home/user/repo/.weft/worktrees/plan-id",
    "sessionId": "4253c8e1-3da0-4ab3-812a-3e6b5267c497",
    "message": {
        "model": "claude-sonnet-4-5-20250929",
        "id": "msg_xxx",
        "type": "message",
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Assistant response"},
            {"type": "thinking", "thinking": "Internal reasoning..."},
            {
                "type": "tool_use",
                "id": "toolu_xxx",
                "name": "Read",
                "input": {"file_path": "/path/to/file"}
            }
        ],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50
        }
    },
    "type": "assistant",
    "uuid": "3667ccd3-61ff-4c3e-aa4c-012b24b32fd2",
    "timestamp": "2025-11-04T21:07:30.129Z"
}
```

### Key Fields

- **`cwd`**: Current working directory - used to match session to worktree
- **`sessionId`**: UUID identifying the session
- **`agentId`**: Short ID for subagents (8 hex chars)
- **`timestamp`**: ISO 8601 timestamp (message creation time)
- **`type`**: Message type (`user`, `assistant`, `file-history-snapshot`)
- **`message.role`**: `user` or `assistant`
- **`message.content`**: Array of content blocks
- **`parentUuid`**: Links messages in conversation chain
- **`isSidechain`**: `true` for subagent messages, `false` for main

### Content Block Types

- **Text**: `{"type": "text", "text": "..."}`
- **Thinking**: `{"type": "thinking", "thinking": "..."}`
- **Tool Use**: `{"type": "tool_use", "id": "...", "name": "Read", "input": {...}}`
- **Tool Result**: `{"type": "tool_result", "tool_use_id": "...", "content": "..."}`

### File Discovery Mechanism

**Timing-Based Discovery**:
- Cannot detect AI completion in real-time (subprocess blocks Python)
- Use filesystem modification time (`file.stat().st_mtime`) for discovery
- Search window: [subprocess_start - 5s, subprocess_end + 5s]
- 5-second buffer accounts for write buffering and filesystem timestamp precision

**Verification**:
- Check `cwd` field in first JSONL line matches worktree path
- Extract `sessionId` from matching file
- Load all files with same `sessionId`

### Observed Characteristics

- Main files: 100s-1000s of lines
- Subagent files: typically 2-50 lines
- Files created within 1-2 seconds of subprocess start
- Last modification typically within 1-2 seconds of subprocess completion
- Modification time updates as conversation progresses

## Alternative Approaches Considered

### 1. Wait for Official API

**Description**: Delay this feature until Anthropic provides an official trace export API in Claude Code.

**Rejected Because**:
- Uncertain timeline (could be months or never)
- Feature is needed now for DSPy prompt iteration
- May not meet our specific requirements even if provided
- Can migrate to official API later if it becomes available

### 2. Intercept Claude API Calls

**Description**: Hook into the Claude API client to capture request/response pairs.

**Rejected Because**:
- More invasive than reading files from disk
- Requires understanding API client internals
- Harder to separate subagent conversations
- Doesn't capture tool results and full conversation flow

### 3. Manual Log Export

**Description**: User manually runs a command after each session to export traces.

**Rejected Because**:
- Poor developer experience (extra step)
- Likely to be forgotten
- Not suitable for automated batch analysis
- Interrupts workflow

## Future Considerations

### Monitoring Strategy

1. **Version Tracking**: Log Claude Code version when trace capture succeeds
2. **Error Pattern Analysis**: Monitor debug logs for new error types
3. **Format Drift Detection**: Periodic validation that expected fields are present
4. **User Reports**: Encourage users to report trace capture failures

### Migration Path

If Anthropic provides an official API:
1. Implement new capture backend using official API
2. Run both in parallel for validation period
3. Switch to official API once proven stable
4. Deprecate internal format dependency
5. Remove legacy code after grace period

### Upstream Contribution

Consider proposing to Anthropic:
- Feature request: Official trace export API
- Use case: Multi-agent prompt optimization workflows
- Requirements: Subagent separation, tool usage visibility, clean format
- Reference this implementation as proof of value

## Implementation Notes

- All trace logic isolated in `src/weft/trace_capture.py`
- Module-level comment references this ADR
- Comprehensive error handling with fail-fast behavior
- Non-blocking integration in `code_command.py` and `plan_command.py`
- 30-day retention via existing run directory pruning
- Markdown output format optimized for human review

## References

- Plan document: `.weft/tasks/capture-session-traces.md`
- Implementation: `src/weft/trace_capture.py`
- Tests: `tests/test_trace_capture.py`, `tests/test_trace_capture_integration.py`
- Claude Code: https://claude.ai/code
