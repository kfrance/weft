"""SDK runner for Claude Agent SDK session execution.

This module provides the SDK integration for the `weft code` command,
running the initial prompt via the Claude Agent SDK and capturing the
session ID for subsequent CLI resume.

Uses ClaudeSDKClient for stateful, bidirectional conversation that maintains
session context. This allows the CLI to resume the same conversation using
the captured session_id.

Note: The session_id API is stable and core to the SDK, though documentation
may be light at this time.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    ResultMessage,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from .logging_config import get_logger

logger = get_logger(__name__)

# Pattern to match 'git' as a standalone word (same as referenced in plan)
GIT_COMMAND_PATTERN = re.compile(r'\bgit\b')


class SDKRunnerError(Exception):
    """Raised when SDK session execution fails."""


async def _can_use_tool_callback(
    tool_name: str,
    input_data: dict[str, Any],
    context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    """Callback to inspect and control tool usage.

    Blocks git commands to prevent unintended commits during SDK session.
    Git operations should be performed after CLI resume.

    Args:
        tool_name: Name of the tool being invoked.
        input_data: Tool input parameters.
        context: Permission context for the tool call.

    Returns:
        PermissionResultAllow or PermissionResultDeny.
    """
    # Block git commands
    if tool_name == "Bash":
        command = input_data.get("command", "")
        if GIT_COMMAND_PATTERN.search(command):
            logger.debug("Blocking git command in SDK session: %s", command[:100])
            return PermissionResultDeny(message="Git commands are not allowed during SDK session")

    return PermissionResultAllow()


async def run_sdk_session(
    worktree_path: Path,
    prompt_content: str,
    model: str,
    sdk_settings_path: Path,
    agents: dict[str, AgentDefinition] | None = None,
) -> str:
    """Run SDK session and capture session ID.

    Uses ClaudeSDKClient to execute a query while maintaining session state.
    The session ID can be used to resume the conversation via CLI with
    `claude -r <session_id>`.

    Args:
        worktree_path: Path to the worktree directory where the session runs.
        prompt_content: The main prompt content to execute.
        model: Model variant to use (e.g., "sonnet", "opus", "haiku").
        sdk_settings_path: Path to the SDK settings JSON file.
        agents: Optional dict of agent definitions for programmatic registration.
                If None, agents are only available via filesystem discovery.
                Note: SDK does not discover filesystem agents in .claude/agents/,
                so programmatic registration is required for SDK execution.

    Returns:
        Session ID from the ResultMessage.

    Raises:
        SDKRunnerError: If the session fails or session ID cannot be captured.
    """
    logger.info("Starting SDK session with model '%s' in %s", model, worktree_path)
    logger.debug("SDK settings: %s", sdk_settings_path)

    # Save original NO_PROXY value for restoration after SDK session
    # NO_PROXY is documented at https://code.claude.com/docs/en/settings
    # Setting NO_PROXY="*" bypasses proxy for all network requests, enabling
    # tools like WebFetch to function correctly during SDK execution
    original_no_proxy = os.environ.get("NO_PROXY")

    # Set NO_PROXY="*" to enable network access for SDK session
    os.environ["NO_PROXY"] = "*"
    logger.debug("Set NO_PROXY='*' for SDK session network access")

    # Build options for the SDK client
    # NOTE: agents parameter provides programmatic agent registration since
    # SDK does not discover filesystem agents in .claude/agents/ directories.
    options = ClaudeAgentOptions(
        cwd=worktree_path,
        model=model,
        settings=str(sdk_settings_path),
        permission_mode="default",
        can_use_tool=_can_use_tool_callback,
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
                    # Print assistant messages to terminal
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text)
                        elif isinstance(block, ToolUseBlock):
                            desc = block.input.get("description", "")
                            if desc:
                                print(f"{block.name}: {desc}")
                            else:
                                print(block.name)

    except SDKRunnerError:
        # Re-raise our own errors
        raise
    except Exception as exc:
        raise SDKRunnerError(f"SDK session failed: {exc}") from exc
    finally:
        # Restore original NO_PROXY value to ensure environment is not polluted
        # This guarantees cleanup even if SDK session raises exceptions
        if original_no_proxy is None:
            # NO_PROXY was not set originally, remove it
            os.environ.pop("NO_PROXY", None)
            logger.debug("Restored NO_PROXY to original value (unset)")
        else:
            # Restore to original value
            os.environ["NO_PROXY"] = original_no_proxy
            logger.debug("Restored NO_PROXY to original value: %s", original_no_proxy)

    if not session_id:
        raise SDKRunnerError("Failed to capture session ID from SDK session")

    return session_id


def run_sdk_session_sync(
    worktree_path: Path,
    prompt_content: str,
    model: str,
    sdk_settings_path: Path,
    agents: dict[str, AgentDefinition] | None = None,
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
