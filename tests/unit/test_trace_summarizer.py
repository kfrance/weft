"""Unit tests for trace_summarizer module.

Tests structural data extraction and formatting, not the LLM-based
narrative generation (which requires integration tests).

Uses the real_trace_content fixture from conftest.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.trace_summarizer import (
    TraceSummarizationError,
    _format_structural_section,
    extract_structural_data,
    needs_regeneration,
)


# real_trace_content fixture is provided by tests/unit/conftest.py


class TestExtractStructuralData:
    """Tests for extract_structural_data function."""

    def test_extract_structural_data_from_real_trace(self, real_trace_content: str) -> None:
        """Extracts structural data from real trace."""
        data = extract_structural_data(real_trace_content)

        # Check metadata
        assert "metadata" in data
        assert data["metadata"]["session_id"] == "8f88f3a8-a30f-4065-be5f-63fb6e62b2b1"
        assert data["metadata"]["command"] == "code"
        assert data["metadata"]["git_branch"] == "test-planner-subagent"

        # Check tool counts
        assert "tool_counts" in data
        assert data["tool_counts"].get("Read", 0) >= 40
        assert data["tool_counts"].get("Bash", 0) >= 40
        assert data["tool_counts"].get("Edit", 0) >= 15

        # Check files
        assert "files" in data
        assert len(data["files"]["read"]) > 0
        assert len(data["files"]["modified"]) > 0

        # Check bash commands
        assert "bash_commands" in data
        assert len(data["bash_commands"]) > 30

        # Check error tracking
        assert "error_count" in data
        assert "errors" in data

    def test_extract_structural_data_empty_trace(self) -> None:
        """Handles empty trace gracefully."""
        data = extract_structural_data("")

        assert data["metadata"]["session_id"] == "unknown"
        assert data["tool_counts"] == {}
        assert data["files"]["read"] == []
        assert data["files"]["modified"] == []
        assert data["files"]["created"] == []
        assert data["bash_commands"] == []
        assert data["error_count"] == 0
        assert data["errors"] == []

    def test_extract_structural_data_minimal_trace(self) -> None:
        """Handles minimal trace with only metadata."""
        content = """
# Conversation Trace

## Session Metadata

- **Session ID**: test-session
- **Command**: plan
- **Timestamp**: 2025-01-01T00:00:00
- **Worktree**: /tmp/test
- **Git Branch**: main

## Main Conversation

User asked a question.
"""
        data = extract_structural_data(content)

        assert data["metadata"]["session_id"] == "test-session"
        assert data["metadata"]["command"] == "plan"
        assert data["metadata"]["git_branch"] == "main"
        assert data["tool_counts"] == {}


class TestFormatStructuralSection:
    """Tests for _format_structural_section function."""

    def test_format_structural_section_complete(self) -> None:
        """Formats complete structural data correctly."""
        data = {
            "metadata": {
                "session_id": "abc123",
                "command": "code",
                "timestamp": "2025-01-01T00:00:00",
                "worktree": "/tmp/test",
                "git_branch": "main",
            },
            "tool_counts": {"Read": 10, "Edit": 5, "Bash": 3},
            "files": {
                "read": ["/path/to/file1.py", "/path/to/file2.py"],
                "modified": ["/path/to/edit.py"],
                "created": ["/path/to/new.py"],
            },
            "bash_commands": ["pytest", "ls -la"],
            "error_count": 1,
            "errors": ["Error: Something went wrong"],
        }

        section = _format_structural_section(data)

        # Check metadata section
        assert "## Session Metadata" in section
        assert "abc123" in section
        assert "code" in section
        assert "main" in section

        # Check tool usage
        assert "## Tool Usage" in section
        assert "Read: 10" in section
        assert "Edit: 5" in section
        assert "Bash: 3" in section

        # Check files
        assert "## Files Accessed" in section
        assert "### Modified" in section
        assert "/path/to/edit.py" in section
        assert "### Created" in section
        assert "/path/to/new.py" in section
        assert "### Read" in section
        assert "/path/to/file1.py" in section

        # Check bash commands
        assert "## Bash Commands" in section
        assert "`pytest`" in section
        assert "`ls -la`" in section

        # Check errors
        assert "## Errors" in section
        assert "1 error(s) detected" in section
        assert "Something went wrong" in section

    def test_format_structural_section_empty_data(self) -> None:
        """Handles empty structural data."""
        data = {
            "metadata": {
                "session_id": "unknown",
                "command": "unknown",
                "timestamp": "unknown",
                "worktree": "unknown",
                "git_branch": "unknown",
            },
            "tool_counts": {},
            "files": {"read": [], "modified": [], "created": []},
            "bash_commands": [],
            "error_count": 0,
            "errors": [],
        }

        section = _format_structural_section(data)

        assert "No tool calls recorded." in section
        assert "No bash commands recorded." in section
        assert "No errors detected." in section

    def test_format_structural_section_truncates_long_commands(self) -> None:
        """Truncates long bash commands."""
        long_command = "x" * 200
        data = {
            "metadata": {
                "session_id": "abc",
                "command": "code",
                "timestamp": "now",
                "worktree": "/tmp",
                "git_branch": "main",
            },
            "tool_counts": {},
            "files": {"read": [], "modified": [], "created": []},
            "bash_commands": [long_command],
            "error_count": 0,
            "errors": [],
        }

        section = _format_structural_section(data)

        # Command should be truncated
        assert "..." in section
        assert len(long_command) > 100  # Original is long
        # The formatted output shouldn't contain the full command

    def test_format_structural_section_limits_read_files(self) -> None:
        """Limits read files list to 20."""
        many_files = [f"/path/to/file{i}.py" for i in range(30)]
        data = {
            "metadata": {
                "session_id": "abc",
                "command": "code",
                "timestamp": "now",
                "worktree": "/tmp",
                "git_branch": "main",
            },
            "tool_counts": {},
            "files": {"read": many_files, "modified": [], "created": []},
            "bash_commands": [],
            "error_count": 0,
            "errors": [],
        }

        section = _format_structural_section(data)

        # Should indicate there are more files
        assert "10 more" in section


class TestNeedsRegeneration:
    """Tests for needs_regeneration function."""

    def test_needs_regeneration_no_summary(self, tmp_path: Path) -> None:
        """Returns True when summary doesn't exist."""
        trace_path = tmp_path / "code_trace.md"
        summary_path = tmp_path / "code_trace_summary.md"
        trace_path.write_text("content")

        assert needs_regeneration(trace_path, summary_path) is True

    def test_needs_regeneration_summary_newer(self, tmp_path: Path) -> None:
        """Returns False when summary is newer than trace."""
        trace_path = tmp_path / "code_trace.md"
        summary_path = tmp_path / "code_trace_summary.md"

        trace_path.write_text("old content")
        # Ensure some time passes
        import time
        time.sleep(0.1)
        summary_path.write_text("new summary")

        assert needs_regeneration(trace_path, summary_path) is False

    def test_needs_regeneration_trace_newer(self, tmp_path: Path) -> None:
        """Returns True when trace is newer than summary."""
        trace_path = tmp_path / "code_trace.md"
        summary_path = tmp_path / "code_trace_summary.md"

        summary_path.write_text("old summary")
        # Ensure some time passes
        import time
        time.sleep(0.1)
        trace_path.write_text("new content")

        assert needs_regeneration(trace_path, summary_path) is True


class TestLoadSummarizationPrompt:
    """Tests for _load_summarization_prompt function."""

    def test_prompt_file_exists(self) -> None:
        """Summarization prompt file exists and is loadable."""
        from lw_coder.trace_summarizer import _load_summarization_prompt

        prompt = _load_summarization_prompt()

        # Should contain key sections
        assert len(prompt) > 100
        assert "Task Intent" in prompt or "intent" in prompt.lower()
        assert "Subagent" in prompt
        assert "Feedback" in prompt
