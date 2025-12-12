"""Integration tests for SDK network access via NO_PROXY environment variable.

These tests verify that setting NO_PROXY="*" enables network access for SDK sessions
and that the environment variable is properly restored after session completion.
They make actual API calls to the Claude SDK.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from lw_coder.sdk_runner import (
    run_sdk_session,
    SDKRunnerError,
)


class TestSDKNetworkAccess:
    """Integration tests for SDK network access via NO_PROXY."""

    def test_sdk_network_succeeds_with_no_proxy(self, tmp_path: Path):
        """SDK session should succeed when WebFetch is used with NO_PROXY="*".

        This test validates the solution: with NO_PROXY="*", network tools
        like WebFetch work correctly during SDK execution.
        """
        # Create minimal sdk_settings.json
        settings_path = tmp_path / "sdk_settings.json"
        settings_path.write_text('{"sandbox": {"enabled": true}}')

        # The run_sdk_session function should set NO_PROXY="*" internally
        # This should succeed
        session_id = asyncio.run(run_sdk_session(
            worktree_path=tmp_path,
            prompt_content="Use the WebFetch tool to fetch https://example.com and tell me the title of the page.",
            model="haiku",
            sdk_settings_path=settings_path,
        ))

        # Verify we got a valid session ID
        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    def test_no_proxy_restored_after_successful_session(self, tmp_path: Path):
        """NO_PROXY should be restored to original value after successful session.

        This test verifies environment cleanup on the success path.
        """
        # Set NO_PROXY to a custom value before test
        original_value = "custom_test_value"
        os.environ["NO_PROXY"] = original_value

        # Create minimal sdk_settings.json
        settings_path = tmp_path / "sdk_settings.json"
        settings_path.write_text('{"sandbox": {"enabled": true}}')

        try:
            # Run successful SDK session
            session_id = asyncio.run(run_sdk_session(
                worktree_path=tmp_path,
                prompt_content="Say only 'hello' and nothing else.",
                model="haiku",
                sdk_settings_path=settings_path,
            ))

            # Verify session succeeded
            assert session_id is not None

            # Verify NO_PROXY was restored to original value
            assert os.environ.get("NO_PROXY") == original_value
        finally:
            # Cleanup: restore environment
            if "NO_PROXY" in os.environ:
                del os.environ["NO_PROXY"]

    def test_no_proxy_removed_if_not_originally_set(self, tmp_path: Path):
        """NO_PROXY should be removed if it wasn't set originally.

        This test verifies that we don't pollute the environment by leaving
        NO_PROXY set after the session if it wasn't set before.
        """
        # Ensure NO_PROXY is not set
        original_value = os.environ.pop("NO_PROXY", None)

        # Create minimal sdk_settings.json
        settings_path = tmp_path / "sdk_settings.json"
        settings_path.write_text('{"sandbox": {"enabled": true}}')

        try:
            # Run SDK session
            session_id = asyncio.run(run_sdk_session(
                worktree_path=tmp_path,
                prompt_content="Say only 'hello' and nothing else.",
                model="haiku",
                sdk_settings_path=settings_path,
            ))

            # Verify session succeeded
            assert session_id is not None

            # Verify NO_PROXY was removed (not just set to empty string)
            assert "NO_PROXY" not in os.environ
        finally:
            # Restore original value if it existed
            if original_value is not None:
                os.environ["NO_PROXY"] = original_value
