"""SDK runner for Claude Agent SDK session execution.

This module provides the SDK integration for the `weft code` command,
running the initial prompt via the Claude Agent SDK and capturing the
session ID for subsequent CLI resume.

Uses ClaudeSDKClient for stateful, bidirectional conversation that maintains
session context. This allows the CLI to resume the same conversation using
the captured session_id.

Note: The session_id API is stable and core to the SDK, though documentation
may be light at this time.

Sandbox: SDK sessions use command-level blocking via the can_use_tool callback,
which checks commands against patterns in .weft/config.toml [sandbox].disallowed_commands.
Claude Code's internal sandbox is disabled (sandbox.enabled = false in sdk_settings.json).
Note: The SDK API does not support wrapping the entire process in bwrap; filesystem
isolation via bwrap is only applied to CLI resume sessions (see host_runner.py).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    ResultMessage,
    AssistantMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from .logging_config import get_logger
from .output import print_assistant_message
from .sandbox import SandboxConfig, matches_disallowed_command

logger = get_logger(__name__)


class SDKRunnerError(Exception):
    """Raised when SDK session execution fails."""


def _create_can_use_tool_callback(
    sandbox_config: SandboxConfig,
):
    """Create a callback to inspect and control tool usage.

    Args:
        sandbox_config: Sandbox configuration with disallowed command patterns.

    Returns:
        Async callback function for can_use_tool.
    """
    async def _can_use_tool_callback(
        tool_name: str,
        input_data: dict[str, Any],
        context: ToolPermissionContext
    ) -> PermissionResultAllow | PermissionResultDeny:
        """Callback to inspect and control tool usage.

        Blocks commands that match disallowed patterns from sandbox config.

        Args:
            tool_name: Name of the tool being invoked.
            input_data: Tool input parameters.
            context: Permission context for the tool call.

        Returns:
            PermissionResultAllow or PermissionResultDeny.
        """
        # Check Bash commands against disallowed patterns
        if tool_name == "Bash":
            command = input_data.get("command", "")
            is_blocked, pattern = matches_disallowed_command(command, sandbox_config)
            if is_blocked:
                logger.debug(
                    "Blocking command matching pattern '%s': %s",
                    pattern,
                    command[:100],
                )
                return PermissionResultDeny(
                    message=f"Command blocked by sandbox config (matches pattern: {pattern})"
                )

        return PermissionResultAllow()

    return _can_use_tool_callback


async def run_sdk_session(
    worktree_path: Path,
    prompt_content: str,
    model: str,
    sdk_settings_path: Path,
    agents: dict[str, AgentDefinition] | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> str:
    """Run SDK session and capture session ID.

    Uses ClaudeSDKClient to execute a query while maintaining session state.
    The session ID can be used to resume the conversation via CLI with
    `claude -r <session_id>`.

    Note: Filesystem isolation is provided by weft's external bwrap sandbox,
    not Claude Code's internal sandbox (which is disabled). Command blocking
    is handled via the can_use_tool callback using patterns from sandbox_config.

    Args:
        worktree_path: Path to the worktree directory where the session runs.
        prompt_content: The main prompt content to execute.
        model: Model variant to use (e.g., "sonnet", "opus", "haiku").
        sdk_settings_path: Path to the SDK settings JSON file.
        agents: Optional dict of agent definitions for programmatic registration.
                If None, agents are only available via filesystem discovery.
                Note: SDK does not discover filesystem agents in .claude/agents/,
                so programmatic registration is required for SDK execution.
        sandbox_config: Optional sandbox configuration for command blocking.
                       If None, no commands are blocked.

    Returns:
        Session ID from the ResultMessage.

    Raises:
        SDKRunnerError: If the session fails or session ID cannot be captured.
    """
    logger.info("Starting SDK session with model '%s' in %s", model, worktree_path)
    logger.debug("SDK settings: %s", sdk_settings_path)

    # Use empty config if none provided
    effective_config = sandbox_config or SandboxConfig()

    # Build options for the SDK client
    # NOTE: agents parameter provides programmatic agent registration since
    # SDK does not discover filesystem agents in .claude/agents/ directories.
    # permission_mode="acceptEdits" auto-accepts Edit/Write tool calls.
    # Filesystem isolation is handled by weft's external bwrap sandbox.
    options = ClaudeAgentOptions(
        cwd=worktree_path,
        model=model,
        settings=str(sdk_settings_path),
        permission_mode="acceptEdits",
        can_use_tool=_create_can_use_tool_callback(effective_config),
        agents=agents,
    )

    session_id: str | None = None

    try:
        async with ClaudeSDKClient(options=options) as client:
            # Send the query
            await client.query(prompt_content)

            # Receive all messages until ResultMessage
            async for message in client.receive_response():
                if isinstance(message, ResultMessage):
                    session_id = message.session_id
                    logger.info(
                        "SDK session completed: session_id=%s, turns=%d, cost=$%.4f",
                        session_id,
                        message.num_turns,
                        message.total_cost_usd or 0.0,
                    )
                    if message.is_error:
                        raise SDKRunnerError(
                            f"SDK session completed with error: {message.result}"
                        )
                elif isinstance(message, AssistantMessage):
                    # Print assistant messages with styled formatting
                    print_assistant_message(message)

    except SDKRunnerError:
        # Re-raise our own errors
        raise
    except Exception as exc:
        raise SDKRunnerError(f"SDK session failed: {exc}") from exc

    if not session_id:
        raise SDKRunnerError("Failed to capture session ID from SDK session")

    return session_id


def run_sdk_session_sync(
    worktree_path: Path,
    prompt_content: str,
    model: str,
    sdk_settings_path: Path,
    agents: dict[str, AgentDefinition] | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> str:
    """Synchronous wrapper for run_sdk_session.

    Provides a blocking interface for calling the async SDK session runner.

    Args:
        worktree_path: Path to the worktree directory where the session runs.
        prompt_content: The main prompt content to execute.
        model: Model variant to use (e.g., "sonnet", "opus", "haiku").
        sdk_settings_path: Path to the SDK settings JSON file.
        agents: Optional dict of agent definitions for programmatic registration.
                If None, agents are only available via filesystem discovery.
                Note: SDK does not discover filesystem agents in .claude/agents/,
                so programmatic registration is required for SDK execution.
        sandbox_config: Optional sandbox configuration for command blocking.
                       If None, no commands are blocked.

    Returns:
        Session ID from the ResultMessage.

    Raises:
        SDKRunnerError: If the session fails or session ID cannot be captured.
    """
    return asyncio.run(
        run_sdk_session(
            worktree_path=worktree_path,
            prompt_content=prompt_content,
            model=model,
            sdk_settings_path=sdk_settings_path,
            agents=agents,
            sandbox_config=sandbox_config,
        )
    )


if __name__ == "__main__":
    """Entry point for manual testing: python -m weft.sdk_runner"""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Run an SDK session and capture session ID"
    )
    parser.add_argument(
        "worktree_path",
        type=Path,
        help="Path to the worktree directory",
    )
    parser.add_argument(
        "prompt",
        type=str,
        help="Prompt text to send to the SDK",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="sonnet",
        help="Model variant (default: sonnet)",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        required=True,
        help="Path to SDK settings JSON file",
    )

    args = parser.parse_args()

    try:
        session_id = run_sdk_session_sync(
            worktree_path=args.worktree_path,
            prompt_content=args.prompt,
            model=args.model,
            sdk_settings_path=args.settings,
        )
        print(f"Session ID: {session_id}")
        sys.exit(0)
    except SDKRunnerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
