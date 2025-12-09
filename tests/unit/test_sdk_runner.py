"""Unit tests for SDK runner module.

These tests verify internal logic using mocks and make no external API calls.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from claude_agent_sdk import AgentDefinition, ResultMessage

from lw_coder.sdk_runner import (
    run_sdk_session,
    run_sdk_session_sync,
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


def test_agents_parameter_passed_to_options(tmp_path: Path, monkeypatch):
    """Verify agents parameter is passed to ClaudeAgentOptions.

    This test ensures the agents dict is correctly passed through to the SDK client.
    We mock ClaudeAgentOptions to capture the agents parameter.
    """
    # Create minimal sdk_settings.json
    settings_path = tmp_path / "sdk_settings.json"
    settings_path.write_text('{"sandbox": {"enabled": true}}')

    # Track what was passed to ClaudeAgentOptions
    captured_options = {}

    class MockAgentOptions:
        def __init__(self, **kwargs):
            captured_options.update(kwargs)

    # Create a mock ResultMessage that will pass the isinstance check
    mock_result = ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=50,
        is_error=False,
        num_turns=1,
        session_id="test-session-123",
        total_cost_usd=0.001,
        result="",
    )

    class MockSDKClient:
        def __init__(self, options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def query(self, prompt):
            pass

        async def receive_response(self):
            yield mock_result

    monkeypatch.setattr("lw_coder.sdk_runner.ClaudeAgentOptions", MockAgentOptions)
    monkeypatch.setattr("lw_coder.sdk_runner.ClaudeSDKClient", MockSDKClient)

    # Create test agents
    test_agents = {
        "test-agent": AgentDefinition(
            description="Test agent",
            prompt="Test prompt",
            model="haiku",
        ),
    }

    # Run session with agents
    session_id = run_sdk_session_sync(
        worktree_path=tmp_path,
        prompt_content="Test prompt",
        model="haiku",
        sdk_settings_path=settings_path,
        agents=test_agents,
    )

    # Verify agents were passed to options
    assert "agents" in captured_options
    assert captured_options["agents"] == test_agents
    assert session_id == "test-session-123"


def test_agents_parameter_optional(tmp_path: Path, monkeypatch):
    """Verify agents parameter is optional and defaults to None.

    This ensures backward compatibility - sessions can be run without agents.
    """
    # Create minimal sdk_settings.json
    settings_path = tmp_path / "sdk_settings.json"
    settings_path.write_text('{"sandbox": {"enabled": true}}')

    # Track what was passed to ClaudeAgentOptions
    captured_options = {}

    class MockAgentOptions:
        def __init__(self, **kwargs):
            captured_options.update(kwargs)

    # Create a mock ResultMessage that will pass the isinstance check
    mock_result = ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=50,
        is_error=False,
        num_turns=1,
        session_id="test-session-456",
        total_cost_usd=0.001,
        result="",
    )

    class MockSDKClient:
        def __init__(self, options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def query(self, prompt):
            pass

        async def receive_response(self):
            yield mock_result

    monkeypatch.setattr("lw_coder.sdk_runner.ClaudeAgentOptions", MockAgentOptions)
    monkeypatch.setattr("lw_coder.sdk_runner.ClaudeSDKClient", MockSDKClient)

    # Run session WITHOUT agents parameter
    session_id = run_sdk_session_sync(
        worktree_path=tmp_path,
        prompt_content="Test prompt",
        model="haiku",
        sdk_settings_path=settings_path,
        # agents parameter omitted
    )

    # Verify agents was passed as None
    assert "agents" in captured_options
    assert captured_options["agents"] is None
    assert session_id == "test-session-456"
