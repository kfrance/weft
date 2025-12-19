"""Unit tests for trace_capture module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from weft.trace_capture import (
    truncate_content,
    filter_and_clean_messages,
    clean_tool_results,
    generate_markdown,
    parse_jsonl_file,
    match_session_files,
)


def test_truncate_content_under_limit():
    """Content under 200 chars should return unchanged."""
    content = "Short content"
    result = truncate_content(content)
    assert result == content


def test_truncate_content_over_limit():
    """Content over 200 chars should truncate to first 50 + last 150."""
    content = "x" * 300
    result = truncate_content(content)
    assert result.startswith("x" * 50)
    assert result.endswith("x" * 150)
    assert "[... 100 chars truncated ...]" in result


def test_truncate_content_exact_limit():
    """Content at exactly 200 chars should return unchanged."""
    content = "x" * 200
    result = truncate_content(content)
    assert result == content


def test_filter_removes_file_snapshots():
    """File history snapshots should be removed from message list."""
    messages = [
        {"type": "file-history-snapshot", "messageId": "123"},
        {"type": "user", "message": {"content": "test"}},
        {"type": "file-history-snapshot", "messageId": "456"},
    ]
    result = filter_and_clean_messages(messages)
    assert len(result["main"]) == 1
    assert result["main"][0]["type"] == "user"


def test_filter_preserves_other_messages():
    """Non-snapshot messages should be preserved."""
    messages = [
        {"type": "user", "message": {"content": "test"}, "isSidechain": False},
        {"type": "assistant", "message": {"content": "response"}, "isSidechain": False},
    ]
    result = filter_and_clean_messages(messages)
    assert len(result["main"]) == 2


def test_filter_groups_subagents():
    """Messages should be grouped by agent ID."""
    messages = [
        {"type": "user", "message": {"content": "main"}, "isSidechain": False},
        {
            "type": "user",
            "message": {"content": "subagent"},
            "isSidechain": True,
            "agentId": "abc123",
        },
        {
            "type": "assistant",
            "message": {"content": "subagent response"},
            "isSidechain": True,
            "agentId": "abc123",
        },
    ]
    result = filter_and_clean_messages(messages)
    assert len(result["main"]) == 1
    assert len(result["abc123"]) == 2


def test_clean_tool_results_truncates():
    """Tool results over 200 chars should be truncated."""
    messages = [
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "123",
                        "content": "x" * 300,
                    }
                ]
            },
        }
    ]
    result = clean_tool_results(messages)
    tool_result = result[0]["message"]["content"][0]["content"]
    assert len(tool_result) < 300
    assert "[... 100 chars truncated ...]" in tool_result


def test_clean_tool_results_preserves_small():
    """Small tool results should be kept as-is."""
    small_content = "Short result"
    messages = [
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "123",
                        "content": small_content,
                    }
                ]
            },
        }
    ]
    result = clean_tool_results(messages)
    tool_result = result[0]["message"]["content"][0]["content"]
    assert tool_result == small_content


def test_markdown_generation_basic():
    """Basic markdown output should have correct structure."""
    grouped_messages = {
        "main": [
            {
                "type": "user",
                "timestamp": "2025-01-01T00:00:00Z",
                "message": {"content": [{"type": "text", "text": "Hello"}]},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T00:00:01Z",
                "message": {"content": [{"type": "text", "text": "Hi there"}]},
            },
        ]
    }
    metadata = {
        "session_id": "test-session",
        "command": "code",
        "timestamp": "2025-01-01T00:00:00",
        "worktree": "/tmp/test",
        "git_branch": "main",
    }

    result = generate_markdown(grouped_messages, metadata)

    assert "# Conversation Trace" in result
    assert "## Session Metadata" in result
    assert "test-session" in result
    assert "## Main Conversation" in result
    assert "Hello" in result
    assert "Hi there" in result


def test_markdown_generation_with_subagents():
    """Subagent sections should be created correctly."""
    grouped_messages = {
        "main": [
            {
                "type": "user",
                "timestamp": "2025-01-01T00:00:00Z",
                "message": {"content": [{"type": "text", "text": "Main message"}]},
            }
        ],
        "abc123": [
            {
                "type": "user",
                "timestamp": "2025-01-01T00:00:01Z",
                "message": {"content": [{"type": "text", "text": "Subagent message"}]},
            }
        ],
    }
    metadata = {
        "session_id": "test-session",
        "command": "code",
        "timestamp": "2025-01-01T00:00:00",
        "worktree": "/tmp/test",
        "git_branch": "main",
    }

    result = generate_markdown(grouped_messages, metadata)

    assert "## Main Conversation" in result
    assert "## Subagent: agent-abc123" in result
    assert "Main message" in result
    assert "Subagent message" in result


def test_markdown_generation_preserves_thinking_blocks():
    """Thinking blocks should be included in output."""
    grouped_messages = {
        "main": [
            {
                "type": "assistant",
                "timestamp": "2025-01-01T00:00:00Z",
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "Let me think..."},
                        {"type": "text", "text": "Here's my answer"},
                    ]
                },
            }
        ]
    }
    metadata = {
        "session_id": "test-session",
        "command": "code",
        "timestamp": "2025-01-01T00:00:00",
        "worktree": "/tmp/test",
        "git_branch": "main",
    }

    result = generate_markdown(grouped_messages, metadata)

    assert "**Thinking:**" in result
    assert "Let me think..." in result
    assert "Here's my answer" in result


def test_parse_jsonl_handles_invalid_lines(tmp_path):
    """Invalid JSON lines should be skipped with warning."""
    jsonl_file = tmp_path / "test.jsonl"
    jsonl_file.write_text(
        '{"type": "user", "message": {"content": "valid"}}\n'
        'invalid json line\n'
        '{"type": "assistant", "message": {"content": "also valid"}}\n'
    )

    result = parse_jsonl_file(jsonl_file)

    # Should skip the invalid line but keep the valid ones
    assert len(result) == 2
    assert result[0]["type"] == "user"
    assert result[1]["type"] == "assistant"


def test_match_session_finds_correct_cwd(tmp_path):
    """Session matching by cwd field should work."""
    jsonl_file = tmp_path / "session.jsonl"
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Write a JSONL file with matching cwd
    data = {
        "type": "user",
        "cwd": str(worktree_path.resolve()),
        "sessionId": "test-session-123",
        "message": {"content": "test"},
    }
    jsonl_file.write_text(json.dumps(data) + "\n")

    result = match_session_files([jsonl_file], worktree_path)

    assert result == "test-session-123"


def test_match_session_returns_none_on_no_match(tmp_path):
    """Should return None when no matching cwd is found."""
    jsonl_file = tmp_path / "session.jsonl"
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Write a JSONL file with non-matching cwd
    data = {
        "type": "user",
        "cwd": "/different/path",
        "sessionId": "test-session-123",
        "message": {"content": "test"},
    }
    jsonl_file.write_text(json.dumps(data) + "\n")

    result = match_session_files([jsonl_file], worktree_path)

    assert result is None


def test_markdown_generation_includes_tool_calls():
    """Tool calls should be formatted with JSON parameters."""
    grouped_messages = {
        "main": [
            {
                "type": "assistant",
                "timestamp": "2025-01-01T00:00:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "id": "tool123",
                            "input": {"file_path": "/tmp/test.txt"},
                        }
                    ]
                },
            }
        ]
    }
    metadata = {
        "session_id": "test-session",
        "command": "code",
        "timestamp": "2025-01-01T00:00:00",
        "worktree": "/tmp/test",
        "git_branch": "main",
    }

    result = generate_markdown(grouped_messages, metadata)

    assert "**Tool: Read**" in result
    assert "file_path" in result
    assert "/tmp/test.txt" in result


def test_clean_tool_results_handles_non_string_content():
    """Clean tool results should handle non-string content."""
    messages = [
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "123",
                        "content": {"some": "object"},  # Non-string content
                    }
                ]
            },
        }
    ]
    # Should not raise an error
    result = clean_tool_results(messages)
    assert len(result) == 1
