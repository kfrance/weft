---
plan_id: trace-compression
status: done
evaluation_notes: []
git_sha: 6eaf2c10a3fd9d427616814f15179205261264f2
---

# Trace Compression for Training Data

## Objectives

Reduce `code_trace.md` files from 266KB-688KB to ~5-10KB for efficient use in the `train` command's DSPy prompt optimization, while preserving the information most valuable for prompt improvement: agent intent, subagent feedback, and response patterns.

## Requirements & Constraints

### Functional Requirements
1. Generate compressed trace summaries (`code_trace_summary.md`) containing:
   - **Structural data** (extracted via Python): tool usage counts, files read/modified/created, bash commands, errors
   - **LLM narrative** (via DSPy with grok-4.1-fast): task intent, subagent feedback (verbatim), how main agent responded to feedback
2. Lazy generation: summaries created on-demand when `train` command loads training data
3. Caching: once generated, summary is reused; regenerate if trace file is newer (mtime comparison)
4. Training loader prioritizes `code_trace_summary.md`, falls back to `code_trace.md` if no summary exists

### Non-Functional Requirements
1. Target compressed size: 1-10KB (95-99% reduction) - this is a goal, not a hard requirement; do not fail if compression doesn't reach target
2. Isolate Claude Code trace format parsing into dedicated module (single point of breakage if format changes)
3. Fail `train` command if summarization fails (no silent fallback to full trace)
4. Store summarization prompt in version control for reproducibility

### Constraints
- Must work with existing training data structure (`.lw_coder/training_data/<plan_id>/`)
- No changes to `TrainingSample` Pydantic model (code_trace field remains `str`)
- Summarization model comes from train command's `--model` parameter (default: `x-ai/grok-4.1-fast`)

## Work Items

### 1. Create trace_parser.py module
**Purpose**: Isolate all Claude Code trace format dependencies

**Location**: `src/lw_coder/trace_parser.py`

**Functions**:
- `parse_trace_metadata(content: str) -> dict` - Extract session ID, command, timestamp, worktree, git branch
- `parse_tool_calls(content: str) -> list[ToolCall]` - Extract tool name, parameters, timestamp
- `parse_tool_results(content: str) -> list[ToolResult]` - Extract tool results (already truncated)
- `parse_subagent_sections(content: str) -> dict[str, str]` - Extract subagent conversation sections
- `detect_errors(content: str) -> list[str]` - Find error messages, test failures, retries

### 2. Create trace_summarizer.py module
**Purpose**: Generate compressed trace summaries

**Location**: `src/lw_coder/trace_summarizer.py`

**Functions**:
- `extract_structural_data(trace_content: str) -> dict` - Use trace_parser to build structural summary
  - Tool counts by type
  - Files read (unique paths)
  - Files modified/created (from Edit/Write calls)
  - Bash commands (command strings only, no output)
  - Error count and messages

- `generate_narrative_summary(trace_content: str, subagent_sections: dict, model: str) -> str` - DSPy call
  - Input: Full trace + extracted subagent sections
  - Output: Focused narrative on intent, subagent feedback (verbatim), response to feedback

- `create_trace_summary(trace_path: Path, model: str) -> Path` - Main entry point
  - Reads trace file
  - Calls structural extraction
  - Calls narrative generation (using provided model)
  - Writes `code_trace_summary.md` alongside trace
  - Returns path to summary

### 3. Create summarization prompt
**Purpose**: Version-controlled prompt for consistent LLM summarization

**Location**: `src/lw_coder/prompts/trace_summarization.md`

**Content focus**:
- What was the agent trying to accomplish (high-level task breakdown)
- Subagent feedback sections preserved verbatim
- How the main agent responded to each piece of feedback
- Problems/blockers encountered

### 4. Modify training_data_loader.py
**Purpose**: Integrate lazy summary generation

**Changes to `load_training_sample()`**:
1. Add `model: str` parameter (passed from train command's `--model`)
2. Check if `code_trace_summary.md` exists
3. If exists and newer than `code_trace.md`: use summary
4. If `code_trace.md` exists but no summary (or summary older): generate summary using model, then use it
5. If neither exists: return empty string (existing behavior)

**New helper**:
- `_get_or_create_summary(sample_dir: Path, model: str) -> str` - Handles lazy generation logic, passes model to summarizer

**Error handling**:
- If summary generation fails, raise `TrainingDataLoadError` (fail train command)

### 5. Add --regenerate-summaries flag to train command
**Purpose**: Allow force rebuild of all summaries

**Changes to `train_command.py`**:
- Add `--regenerate-summaries` CLI flag
- When set, delete existing summaries before loading training batch
- Useful when summarization prompt is updated

**Changes to `cli.py`**:
- Wire up new flag to train command

### 6. Unit Tests
**Purpose**: Validate parsing and structural extraction using real committed trace data

**Location**: `tests/unit/test_trace_parser.py`, `tests/unit/test_trace_summarizer.py`

**Approach**: Use the committed trace file `.lw_coder/training_data/test-planner-subagent/code_trace.md` as test fixture. Parse once, assert many properties.

**Known properties of test-planner-subagent trace**:
- Session ID: `8f88f3a8-a30f-4065-be5f-63fb6e62b2b1`
- Command: `code`
- Git branch: `test-planner-subagent`
- Tool counts: Read(46), Bash(45), Edit(17), Grep(17), TodoWrite(9), Task(4), Write(2), Glob(2)
- Subagent sections: 8 agents (agent-579107c8, agent-663f4526, agent-74754666, etc.)
- Edited files include: `plan_command.py`, `prompts/claude-code/plan.md`, `prompts/droid/plan.md`

**test_trace_parser.py**:
1. `test_parse_real_trace` - Parse committed trace once, verify all properties:
   - Metadata: session ID, command, git branch
   - Tool counts: Read=46, Bash=45, Edit=17, etc.
   - File paths from Edit/Write calls
   - 8 subagent sections found
2. `test_parse_malformed_trace` - Verify graceful degradation on bad input

**test_trace_summarizer.py**:
1. `test_extract_structural_data_from_real_trace` - Extract structural data, verify dict has expected keys and values match parser output

**test_training_data_loader.py** (additions):
1. `test_load_training_sample_summary_handling` - Verify summary prioritization, fallback to full trace, and empty when both missing

### 7. Integration Tests
**Purpose**: Validate end-to-end LLM summarization with real API calls

**Location**: `tests/integration/test_trace_summarizer_api.py`

**Approach**: Use real DSPy calls with grok-4.1-fast. DSPy caching ensures first run hits API, subsequent runs use cache.

**test_trace_summarizer_api.py**:
1. `test_create_trace_summary_end_to_end` - Full workflow on real test-planner-subagent trace:
   - Creates summary file with both structural and narrative sections
   - Verifies summary is significantly smaller than original
   - Verifies lazy generation works when loading training sample

## Deliverables

### New Files
1. `src/lw_coder/trace_parser.py` - Trace format parsing (isolates Claude Code dependency)
2. `src/lw_coder/trace_summarizer.py` - Summary generation logic
3. `src/lw_coder/prompts/trace_summarization.md` - Summarization prompt
4. `tests/unit/test_trace_parser.py` - Unit tests for parsing
5. `tests/unit/test_trace_summarizer.py` - Unit tests for structural extraction
6. `tests/integration/test_trace_summarizer_api.py` - Integration test for LLM summarization

### Modified Files
1. `src/lw_coder/training_data_loader.py` - Add summary preference and lazy generation
2. `src/lw_coder/train_command.py` - Add --regenerate-summaries flag
3. `src/lw_coder/cli.py` - Wire up new flag
4. `tests/unit/test_training_data_loader.py` - Add tests for summary loading

## Out of Scope

1. **Retroactive compression of existing traces** - Users can run `train --regenerate-summaries` manually
2. **Streaming/chunked training** - Alternative approach not pursued
3. **Trace database (SQLite)** - Future consideration for 1000+ traces
4. **Compression of plan-traces** - Only affects training_data code traces
5. **Changes to trace_capture.py** - Full traces still captured; compression is post-processing
6. **Cleanup of old summaries** - Summaries small enough that disk space not a concern
