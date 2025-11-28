"""Unit tests for trace capture component integration.

Despite the name, these tests use mocks and make no external API calls.
The 'integration' refers to component integration (testing how trace_capture
works with mock JSONL files), not external API integration.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from lw_coder.trace_capture import (
    TraceCaptureError,
    capture_session_trace,
    find_project_folder,
    create_plan_trace_directory,
    prune_old_plan_traces,
)


def create_mock_jsonl_file(file_path: Path, cwd: str, session_id: str, messages: list[dict]):
    """Helper to create a mock JSONL file."""
    with file_path.open("w", encoding="utf-8") as f:
        for message in messages:
            message["cwd"] = cwd
            message["sessionId"] = session_id
            f.write(json.dumps(message) + "\n")


def test_capture_session_trace_with_mock_jsonl(tmp_path, monkeypatch):
    """End-to-end test with mock JSONL files in temp directory."""
    # Create mock Claude projects directory
    mock_projects = tmp_path / ".claude" / "projects"
    mock_projects.mkdir(parents=True)

    # Create mock worktree
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create mock project folder
    project_folder_name = "-" + str(worktree.resolve()).replace("/", "-")
    project_folder = mock_projects / project_folder_name
    project_folder.mkdir()

    # Create mock JSONL file with conversation
    session_id = "test-session-123"
    messages = [
        {
            "type": "user",
            "timestamp": "2025-01-01T00:00:00Z",
            "isSidechain": False,
            "gitBranch": "main",
            "message": {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
        },
        {
            "type": "assistant",
            "timestamp": "2025-01-01T00:00:01Z",
            "isSidechain": False,
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Hi there"}],
            },
        },
        {
            "type": "file-history-snapshot",
            "messageId": "snapshot-1",
            "snapshot": {},
        },
    ]

    jsonl_file = project_folder / f"{session_id}.jsonl"
    create_mock_jsonl_file(jsonl_file, str(worktree.resolve()), session_id, messages)

    # Set modification time to match execution window
    current_time = time.time()
    jsonl_file.touch()

    # Create run directory
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # Patch Path.home() to return tmp_path
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Capture trace
    trace_file = capture_session_trace(
        worktree_path=worktree,
        command="code",
        run_dir=run_dir,
        execution_start=current_time - 1,
        execution_end=current_time + 1,
    )

    # Verify trace file was created
    assert trace_file is not None
    assert trace_file.exists()
    assert trace_file.name == "trace.md"

    # Verify content
    content = trace_file.read_text()
    assert "# Conversation Trace" in content
    assert session_id in content
    assert "Hello" in content
    assert "Hi there" in content
    # File history snapshot should be removed
    assert "file-history-snapshot" not in content


def test_trace_file_contains_metadata(tmp_path, monkeypatch):
    """Trace file header should have session_id, timestamp, etc."""
    # Create mock Claude projects directory
    mock_projects = tmp_path / ".claude" / "projects"
    mock_projects.mkdir(parents=True)

    # Create mock worktree
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create mock project folder
    project_folder_name = "-" + str(worktree.resolve()).replace("/", "-")
    project_folder = mock_projects / project_folder_name
    project_folder.mkdir()

    # Create mock JSONL file
    session_id = "metadata-test-session"
    messages = [
        {
            "type": "user",
            "timestamp": "2025-01-01T12:00:00Z",
            "isSidechain": False,
            "gitBranch": "feature-branch",
            "message": {"content": [{"type": "text", "text": "test"}]},
        }
    ]

    jsonl_file = project_folder / f"{session_id}.jsonl"
    create_mock_jsonl_file(jsonl_file, str(worktree.resolve()), session_id, messages)

    current_time = time.time()
    jsonl_file.touch()

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Capture trace
    trace_file = capture_session_trace(
        worktree_path=worktree,
        command="plan",
        run_dir=run_dir,
        execution_start=current_time - 1,
        execution_end=current_time + 1,
    )

    assert trace_file is not None
    content = trace_file.read_text()

    # Check metadata fields
    assert "## Session Metadata" in content
    assert f"**Session ID**: {session_id}" in content
    assert "**Command**: plan" in content
    assert "**Timestamp**:" in content
    assert f"**Worktree**: {worktree}" in content
    assert "**Git Branch**: feature-branch" in content


def test_trace_file_hierarchical_structure(tmp_path, monkeypatch):
    """Main section + subagent sections should be present."""
    # Create mock Claude projects directory
    mock_projects = tmp_path / ".claude" / "projects"
    mock_projects.mkdir(parents=True)

    # Create mock worktree
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create mock project folder
    project_folder_name = "-" + str(worktree.resolve()).replace("/", "-")
    project_folder = mock_projects / project_folder_name
    project_folder.mkdir()

    # Create main conversation file
    session_id = "hierarchical-test"
    main_messages = [
        {
            "type": "user",
            "timestamp": "2025-01-01T00:00:00Z",
            "isSidechain": False,
            "gitBranch": "main",
            "message": {"content": [{"type": "text", "text": "Main conversation"}]},
        }
    ]

    main_file = project_folder / f"{session_id}.jsonl"
    create_mock_jsonl_file(
        main_file, str(worktree.resolve()), session_id, main_messages
    )

    # Create subagent conversation file
    subagent_messages = [
        {
            "type": "user",
            "timestamp": "2025-01-01T00:00:01Z",
            "isSidechain": True,
            "agentId": "abc123",
            "gitBranch": "main",
            "message": {"content": [{"type": "text", "text": "Subagent message"}]},
        }
    ]

    subagent_file = project_folder / "agent-abc123.jsonl"
    create_mock_jsonl_file(
        subagent_file, str(worktree.resolve()), session_id, subagent_messages
    )

    current_time = time.time()
    main_file.touch()
    subagent_file.touch()

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Capture trace
    trace_file = capture_session_trace(
        worktree_path=worktree,
        command="code",
        run_dir=run_dir,
        execution_start=current_time - 1,
        execution_end=current_time + 1,
    )

    assert trace_file is not None
    content = trace_file.read_text()

    # Check hierarchical structure
    assert "## Main Conversation" in content
    assert "## Subagent: agent-abc123" in content
    assert "Main conversation" in content
    assert "Subagent message" in content


def test_error_on_file_discovery_failure(tmp_path, monkeypatch):
    """Should return None when no matching files found."""
    # Create empty Claude projects directory
    mock_projects = tmp_path / ".claude" / "projects"
    mock_projects.mkdir(parents=True)

    # Create mock worktree
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Attempt to capture trace (should return None, not raise)
    result = capture_session_trace(
        worktree_path=worktree,
        command="code",
        run_dir=run_dir,
        execution_start=time.time() - 10,
        execution_end=time.time(),
    )

    assert result is None


def test_error_on_format_mismatch(tmp_path, monkeypatch):
    """Should handle JSONL format errors gracefully."""
    # Create mock Claude projects directory
    mock_projects = tmp_path / ".claude" / "projects"
    mock_projects.mkdir(parents=True)

    # Create mock worktree
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create mock project folder
    project_folder_name = "-" + str(worktree.resolve()).replace("/", "-")
    project_folder = mock_projects / project_folder_name
    project_folder.mkdir()

    # Create malformed JSONL file
    jsonl_file = project_folder / "session.jsonl"
    jsonl_file.write_text("not valid json\n{also not valid}\n")

    current_time = time.time()
    jsonl_file.touch()

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Should handle gracefully and return None
    result = capture_session_trace(
        worktree_path=worktree,
        command="code",
        run_dir=run_dir,
        execution_start=current_time - 1,
        execution_end=current_time + 1,
    )

    assert result is None


def test_project_folder_discovery(tmp_path, monkeypatch):
    """Test find_project_folder() with mock ~/.claude/projects/ structure."""
    # Create mock Claude projects directory
    mock_projects = tmp_path / ".claude" / "projects"
    mock_projects.mkdir(parents=True)

    # Create mock worktree
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create mock project folder
    project_folder_name = "-" + str(worktree.resolve()).replace("/", "-")
    project_folder = mock_projects / project_folder_name
    project_folder.mkdir()

    # Create a JSONL file with recent modification time
    jsonl_file = project_folder / "session.jsonl"
    jsonl_file.write_text('{"test": "data"}\n')
    current_time = time.time()
    jsonl_file.touch()

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Test discovery within time window
    result = find_project_folder(
        worktree, (current_time - 5, current_time + 5)
    )

    assert result is not None
    assert result == project_folder


def test_project_folder_discovery_time_window(tmp_path, monkeypatch):
    """Test that find_project_folder respects time window."""
    # Create mock Claude projects directory
    mock_projects = tmp_path / ".claude" / "projects"
    mock_projects.mkdir(parents=True)

    # Create mock worktree
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create mock project folder
    project_folder_name = "-" + str(worktree.resolve()).replace("/", "-")
    project_folder = mock_projects / project_folder_name
    project_folder.mkdir()

    # Create a JSONL file with old modification time
    jsonl_file = project_folder / "session.jsonl"
    jsonl_file.write_text('{"test": "data"}\n')

    # Set file modification time to 1 hour ago using os.utime
    import os
    old_time = time.time() - 3600  # 1 hour ago
    os.utime(jsonl_file, (old_time, old_time))

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Test discovery outside time window (should return None)
    result = find_project_folder(
        worktree, (time.time() - 5, time.time() + 5)
    )

    # Since file is old, should not find it
    assert result is None


def test_create_plan_trace_directory(tmp_path):
    """Test creating timestamped plan trace directory."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    trace_dir = create_plan_trace_directory(repo_root)

    # Verify directory was created
    assert trace_dir.exists()
    assert trace_dir.is_dir()
    assert str(trace_dir).startswith(str(repo_root / ".lw_coder" / "plan-traces"))


def test_create_plan_trace_directory_race_condition(tmp_path):
    """Test handling of race condition when directory exists."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    # Create first directory
    trace_dir1 = create_plan_trace_directory(repo_root)

    # The second call might create a directory with microseconds appended
    # This is implementation-dependent based on timing
    trace_dir2 = create_plan_trace_directory(repo_root)

    # Both should exist
    assert trace_dir1.exists()
    assert trace_dir2.exists()


def test_prune_old_plan_traces(tmp_path):
    """Test pruning old plan trace directories."""
    import os

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    traces_base = repo_root / ".lw_coder" / "plan-traces"
    traces_base.mkdir(parents=True)

    # Create old trace directory
    old_trace = traces_base / "20200101_000000"
    old_trace.mkdir()
    old_file = old_trace / "trace.md"
    old_file.write_text("old trace")

    # Set modification time to be old (40 days ago)
    old_time = time.time() - (40 * 24 * 60 * 60)
    os.utime(old_trace, (old_time, old_time))

    # Create recent trace directory
    recent_trace = traces_base / "20251110_120000"
    recent_trace.mkdir()
    recent_file = recent_trace / "trace.md"
    recent_file.write_text("recent trace")

    # Run pruning
    pruned_count = prune_old_plan_traces(repo_root)

    # Old trace should be deleted
    assert not old_trace.exists()
    # Recent trace should remain
    assert recent_trace.exists()
    # Should have pruned at least the old one
    assert pruned_count >= 1
