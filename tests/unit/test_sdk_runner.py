"""Unit tests for SDK runner module.

These tests verify internal logic using mocks and make no external API calls.
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


def test_no_proxy_restored_on_sdk_error(tmp_path: Path, monkeypatch):
    """NO_PROXY should be restored even when SDK session raises exception.

    This test verifies the finally block guarantees cleanup even on errors.
    We mock ClaudeSDKClient to raise an exception quickly, while still
    exercising the real NO_PROXY setup/teardown code path in run_sdk_session.
    """
    # Set NO_PROXY to a custom value before test
    original_value = "custom_error_test_value"
    os.environ["NO_PROXY"] = original_value

    # Create minimal sdk_settings.json
    settings_path = tmp_path / "sdk_settings.json"
    settings_path.write_text('{"sandbox": {"enabled": true}}')

    # Mock ClaudeSDKClient to raise an exception immediately
    # This tests the finally block without waiting for real SDK timeout
    class MockSDKClient:
        def __init__(self, options):
            pass

        async def __aenter__(self):
            raise ConnectionError("Simulated SDK connection failure")

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(
        "lw_coder.sdk_runner.ClaudeSDKClient",
        MockSDKClient
    )

    try:
        # Attempt SDK session that should fail due to mocked exception
        with pytest.raises(SDKRunnerError, match="SDK session failed"):
            asyncio.run(run_sdk_session(
                worktree_path=tmp_path,
                prompt_content="This should fail due to mocked SDK error.",
                model="haiku",
                sdk_settings_path=settings_path,
            ))

        # Verify NO_PROXY was still restored despite the error
        assert os.environ.get("NO_PROXY") == original_value
    finally:
        # Cleanup: restore environment
        if "NO_PROXY" in os.environ:
            del os.environ["NO_PROXY"]
