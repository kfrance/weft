"""Integration tests for SDK session execution.

These tests verify the SDK runner module works correctly with real SDK calls.
They make actual API calls to the Claude SDK.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path


from weft.sdk_runner import (
    run_sdk_session,
)
from weft.trace_capture import (
    capture_session_trace,
)


class TestRealSDKSession:
    """Real integration tests that make actual SDK calls."""

    def test_real_sdk_session_returns_session_id(self, tmp_path: Path):
        """Real SDK session should return a valid session_id."""
        # Create minimal sdk_settings.json
        settings_path = tmp_path / "sdk_settings.json"
        settings_path.write_text('{"sandbox": {"enabled": true}}')

        session_id = asyncio.run(run_sdk_session(
            worktree_path=tmp_path,
            prompt_content="Say only the word 'hello' and nothing else.",
            model="haiku",  # Cheapest/fastest
            sdk_settings_path=settings_path,
        ))

        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    def test_trace_capture_from_sdk_session(self, tmp_path: Path):
        """Verify trace capture works with real SDK session.

        This test validates the full integration:
        1. Run SDK session and get session_id
        2. Capture trace using the session_id
        3. Verify trace file contains expected content
        """
        # Create minimal sdk_settings.json
        settings_path = tmp_path / "sdk_settings.json"
        settings_path.write_text('{"sandbox": {"enabled": true}}')

        # Create run directory for trace output
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        # Record execution timing
        execution_start = time.time()

        # Run SDK session
        session_id = asyncio.run(run_sdk_session(
            worktree_path=tmp_path,
            prompt_content="Say only the word 'hello' and nothing else.",
            model="haiku",
            sdk_settings_path=settings_path,
        ))

        execution_end = time.time()

        # Capture trace using the session_id
        trace_file = capture_session_trace(
            worktree_path=tmp_path,
            command="code",
            run_dir=run_dir,
            execution_start=execution_start,
            execution_end=execution_end,
            session_id=session_id,
        )

        # Verify trace was captured
        assert trace_file is not None, "Trace capture should return a file path"
        assert trace_file.exists(), "Trace file should exist"

        # Read and validate trace content
        trace_content = trace_file.read_text(encoding="utf-8")

        # Verify expected sections exist
        assert "# Conversation Trace" in trace_content
        assert "## Session Metadata" in trace_content
        assert f"**Session ID**: {session_id}" in trace_content
        assert "## Main Conversation" in trace_content

        # Verify our prompt appears in the trace
        assert "hello" in trace_content.lower()
