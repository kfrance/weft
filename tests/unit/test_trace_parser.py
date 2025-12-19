"""Unit tests for trace_parser module.

Uses the committed trace file at .weft/training_data/test-planner-subagent/code_trace.md
as a real-world test fixture (provided by conftest.py).
"""

from __future__ import annotations

import pytest

from weft.trace_parser import (
    TraceMetadata,
    ToolCall,
    count_tools_by_type,
    detect_errors,
    extract_bash_commands,
    extract_file_paths,
    parse_subagent_sections,
    parse_tool_calls,
    parse_trace_metadata,
)


# real_trace_content fixture is provided by tests/unit/conftest.py


class TestParseTraceMetadata:
    """Tests for parse_trace_metadata function."""

    def test_parse_real_trace_metadata(self, real_trace_content: str) -> None:
        """Parses metadata from real trace file."""
        metadata = parse_trace_metadata(real_trace_content)

        assert metadata.session_id == "8f88f3a8-a30f-4065-be5f-63fb6e62b2b1"
        assert metadata.command == "code"
        assert metadata.git_branch == "test-planner-subagent"
        assert metadata.worktree != "unknown"
        assert "worktrees" in metadata.worktree

    def test_parse_metadata_missing_fields(self) -> None:
        """Returns 'unknown' for missing fields."""
        content = "# Trace without metadata"
        metadata = parse_trace_metadata(content)

        assert metadata.session_id == "unknown"
        assert metadata.command == "unknown"
        assert metadata.git_branch == "unknown"

    def test_parse_metadata_partial_fields(self) -> None:
        """Parses available fields, defaults missing."""
        content = """
- **Session ID**: abc123
- **Git Branch**: main
"""
        metadata = parse_trace_metadata(content)

        assert metadata.session_id == "abc123"
        assert metadata.git_branch == "main"
        assert metadata.command == "unknown"


class TestParseToolCalls:
    """Tests for parse_tool_calls function."""

    def test_parse_real_trace_tool_counts(self, real_trace_content: str) -> None:
        """Parses tool calls from real trace and verifies counts."""
        tool_calls = parse_tool_calls(real_trace_content)
        counts = count_tools_by_type(tool_calls)

        # Known tool counts from the test-planner-subagent trace
        # Read(46), Bash(45), Edit(17), Grep(17), TodoWrite(9), Task(4), Write(2), Glob(2)
        assert counts.get("Read", 0) >= 40  # May vary slightly due to parsing
        assert counts.get("Bash", 0) >= 40
        assert counts.get("Edit", 0) >= 15
        assert counts.get("Grep", 0) >= 15
        assert counts.get("TodoWrite", 0) >= 5
        assert counts.get("Task", 0) >= 1
        assert counts.get("Write", 0) >= 1
        assert counts.get("Glob", 0) >= 1

    def test_parse_tool_calls_extracts_parameters(self, real_trace_content: str) -> None:
        """Tool calls include their parameters."""
        tool_calls = parse_tool_calls(real_trace_content)

        # Find a Read tool call
        read_calls = [tc for tc in tool_calls if tc.name == "Read"]
        assert len(read_calls) > 0

        # Should have file_path parameter
        read_with_path = [tc for tc in read_calls if "file_path" in tc.parameters]
        assert len(read_with_path) > 0

    def test_parse_tool_calls_empty_content(self) -> None:
        """Empty content returns empty list."""
        tool_calls = parse_tool_calls("")
        assert tool_calls == []

    def test_parse_tool_calls_no_tools(self) -> None:
        """Content without tools returns empty list."""
        content = "# Just text\n\nNo tools here."
        tool_calls = parse_tool_calls(content)
        assert tool_calls == []


class TestParseSubagentSections:
    """Tests for parse_subagent_sections function."""

    def test_parse_real_trace_subagent_count(self, real_trace_content: str) -> None:
        """Finds all 8 subagent sections from real trace."""
        sections = parse_subagent_sections(real_trace_content)

        # Known subagent IDs from the test-planner-subagent trace
        # 579107c8, 663f4526, 74754666, b291b123, d7366c92, 5e1b09f4, 53abd508, 46e37990
        assert len(sections) == 8

    def test_parse_subagent_sections_content_not_empty(self, real_trace_content: str) -> None:
        """Each subagent section has content."""
        sections = parse_subagent_sections(real_trace_content)

        for agent_id, content in sections.items():
            assert len(content) > 0, f"Subagent {agent_id} has empty content"

    def test_parse_subagent_sections_no_subagents(self) -> None:
        """Content without subagents returns empty dict."""
        content = """
# Trace

## Main Conversation

Just main conversation here.
"""
        sections = parse_subagent_sections(content)
        assert sections == {}

    def test_parse_subagent_sections_single_agent(self) -> None:
        """Parses a single subagent section."""
        content = """
## Main Conversation

Main content.

## Subagent: agent-abc123

Subagent content here.
More subagent content.
"""
        sections = parse_subagent_sections(content)

        assert len(sections) == 1
        assert "abc123" in sections
        assert "Subagent content here" in sections["abc123"]


class TestDetectErrors:
    """Tests for detect_errors function."""

    def test_detect_errors_finds_tracebacks(self) -> None:
        """Finds Python tracebacks."""
        content = """
Traceback (most recent call last):
  File "test.py", line 10, in <module>
    raise ValueError("test")
ValueError: test

Some other text.
"""
        errors = detect_errors(content)

        assert len(errors) >= 1
        assert any("Traceback" in e for e in errors)

    def test_detect_errors_finds_error_messages(self) -> None:
        """Finds Error: style messages."""
        content = """
Error: Something went wrong
FAILED: Another failure
"""
        errors = detect_errors(content)

        assert len(errors) >= 1

    def test_detect_errors_deduplicates(self) -> None:
        """Duplicate errors are not repeated."""
        content = """
Error: Same error message
Error: Same error message
Error: Same error message
"""
        errors = detect_errors(content)

        # Should deduplicate
        assert len(errors) == 1

    def test_detect_errors_no_errors(self) -> None:
        """Clean content returns empty list."""
        content = "Everything is fine. No issues here."
        errors = detect_errors(content)
        assert errors == []


class TestExtractFilePaths:
    """Tests for extract_file_paths function."""

    def test_extract_file_paths_from_real_trace(self, real_trace_content: str) -> None:
        """Extracts file paths from real trace."""
        tool_calls = parse_tool_calls(real_trace_content)
        file_paths = extract_file_paths(tool_calls)

        # Should have files in each category
        assert len(file_paths["read"]) > 0
        assert len(file_paths["modified"]) > 0

        # Known files that were edited in the test-planner-subagent trace
        modified_paths = file_paths["modified"]
        assert any("plan_command.py" in p for p in modified_paths)

    def test_extract_file_paths_empty_list(self) -> None:
        """Empty tool calls returns empty sets."""
        file_paths = extract_file_paths([])

        assert file_paths["read"] == set()
        assert file_paths["modified"] == set()
        assert file_paths["created"] == set()

    def test_extract_file_paths_categorizes_correctly(self) -> None:
        """Files are categorized by tool type."""
        tool_calls = [
            ToolCall(name="Read", parameters={"file_path": "/path/to/read.py"}),
            ToolCall(name="Edit", parameters={"file_path": "/path/to/edit.py"}),
            ToolCall(name="Write", parameters={"file_path": "/path/to/write.py"}),
        ]

        file_paths = extract_file_paths(tool_calls)

        assert "/path/to/read.py" in file_paths["read"]
        assert "/path/to/edit.py" in file_paths["modified"]
        assert "/path/to/write.py" in file_paths["created"]


class TestExtractBashCommands:
    """Tests for extract_bash_commands function."""

    def test_extract_bash_commands_from_real_trace(self, real_trace_content: str) -> None:
        """Extracts bash commands from real trace."""
        tool_calls = parse_tool_calls(real_trace_content)
        bash_commands = extract_bash_commands(tool_calls)

        # Real trace has many bash commands
        assert len(bash_commands) > 30

    def test_extract_bash_commands_empty_list(self) -> None:
        """Empty tool calls returns empty list."""
        commands = extract_bash_commands([])
        assert commands == []

    def test_extract_bash_commands_ignores_non_bash(self) -> None:
        """Only extracts Bash tool calls."""
        tool_calls = [
            ToolCall(name="Read", parameters={"file_path": "/path/to/file"}),
            ToolCall(name="Bash", parameters={"command": "ls -la"}),
            ToolCall(name="Edit", parameters={"file_path": "/path/to/file"}),
            ToolCall(name="Bash", parameters={"command": "pwd"}),
        ]

        commands = extract_bash_commands(tool_calls)

        assert len(commands) == 2
        assert "ls -la" in commands
        assert "pwd" in commands


class TestCountToolsByType:
    """Tests for count_tools_by_type function."""

    def test_count_tools_by_type_basic(self) -> None:
        """Counts tools correctly."""
        tool_calls = [
            ToolCall(name="Read", parameters={}),
            ToolCall(name="Read", parameters={}),
            ToolCall(name="Read", parameters={}),
            ToolCall(name="Edit", parameters={}),
            ToolCall(name="Bash", parameters={}),
            ToolCall(name="Bash", parameters={}),
        ]

        counts = count_tools_by_type(tool_calls)

        assert counts == {"Read": 3, "Edit": 1, "Bash": 2}

    def test_count_tools_by_type_empty(self) -> None:
        """Empty list returns empty dict."""
        counts = count_tools_by_type([])
        assert counts == {}


class TestParseMalformedTrace:
    """Tests for graceful degradation on malformed input."""

    def test_parse_malformed_json_parameters(self) -> None:
        """Handles malformed JSON in tool parameters."""
        content = """
**Tool: Read**
```json
{ not valid json }
```
"""
        tool_calls = parse_tool_calls(content)

        # Should still capture the tool call with empty parameters
        assert len(tool_calls) >= 1
        read_calls = [tc for tc in tool_calls if tc.name == "Read"]
        assert len(read_calls) == 1
        assert read_calls[0].parameters == {}

    def test_parse_truncated_trace(self) -> None:
        """Handles truncated trace content."""
        content = """
# Conversation Trace

## Session Metadata

- **Session ID**: abc123
- **Command**: code

## Main Conversation

### [2025-01-01T00:00:00Z] User

Starting the work...

### [2025-01-01T00:00:01Z] Assistant

**Tool: Read**
```json
{
  "file_path": "/path/to/file.py"
}
```
"""
        # Should not raise any errors
        metadata = parse_trace_metadata(content)
        assert metadata.session_id == "abc123"

        tool_calls = parse_tool_calls(content)
        assert len(tool_calls) >= 1

        sections = parse_subagent_sections(content)
        assert sections == {}  # No subagent sections

        errors = detect_errors(content)
        assert errors == []  # No errors
