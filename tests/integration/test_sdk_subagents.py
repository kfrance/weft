"""Integration tests for SDK subagent availability.

These tests verify that subagents (code-review-auditor, plan-alignment-checker)
are properly available during SDK execution via programmatic registration.

Background:
The Claude Agent SDK does not discover filesystem-based agents in .claude/agents/
directories. This was identified through testing where agents written to filesystem
would fail with "agent not available" errors during SDK execution.

Solution:
Agents are registered programmatically via the `agents` parameter in ClaudeAgentOptions.
Filesystem agents are still created for CLI resume sessions which DO discover them.
Both are built from the same prompts dictionary to ensure synchronization.
"""

from __future__ import annotations

import pytest

from claude_agent_sdk import AgentDefinition


class TestSDKProgrammaticAgents:
    """Integration tests for programmatic agent registration in SDK.

    These tests verify that agents passed via the `agents` parameter
    are properly available during SDK execution.

    Note: These are real SDK integration tests that make API calls.
    They are skipped by default (require --run-integration flag or similar).
    """

    def test_sdk_accepts_agents_parameter(self, tmp_path):
        """Verify SDK session can be started with programmatic agents.

        This is a smoke test to verify the agents parameter is accepted
        by the SDK. It does not test agent invocation (that would require
        a more complex prompt that triggers agent usage).
        """
        from lw_coder.sdk_runner import run_sdk_session_sync

        # Create minimal sdk_settings.json
        settings_path = tmp_path / "sdk_settings.json"
        settings_path.write_text('{"sandbox": {"enabled": true}}')

        # Create programmatic agent definitions
        agents = {
            "test-agent": AgentDefinition(
                description="A test agent",
                prompt="You are a test agent. Simply respond with 'test agent responding'.",
                model="haiku",
            ),
        }

        # Run SDK session with agents parameter
        # Just verify it doesn't error - agent invocation is a separate concern
        session_id = run_sdk_session_sync(
            worktree_path=tmp_path,
            prompt_content="Say only the word 'hello' and nothing else.",
            model="haiku",
            sdk_settings_path=settings_path,
            agents=agents,
        )

        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    def test_sdk_session_without_agents_also_works(self, tmp_path):
        """Verify SDK session works without agents (backward compatibility)."""
        from lw_coder.sdk_runner import run_sdk_session_sync

        # Create minimal sdk_settings.json
        settings_path = tmp_path / "sdk_settings.json"
        settings_path.write_text('{"sandbox": {"enabled": true}}')

        # Run SDK session without agents parameter (should still work)
        session_id = run_sdk_session_sync(
            worktree_path=tmp_path,
            prompt_content="Say only the word 'hello' and nothing else.",
            model="haiku",
            sdk_settings_path=settings_path,
            # agents parameter omitted
        )

        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0
