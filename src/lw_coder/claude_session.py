"""Claude session abstraction layer for SDK interactions.

This module provides a reusable abstraction around run_sdk_session_sync()
for all Claude Code SDK interactions including:
- Test execution (headless)
- Feedback collection (interactive)
- Refactored code command patterns

The abstraction handles common patterns like:
- Running SDK sessions in worktrees
- Output file validation
- Launching interactive CLI sessions after SDK
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Optional

from claude_agent_sdk import AgentDefinition

from .logging_config import get_logger
from .sdk_runner import SDKRunnerError, run_sdk_session_sync

logger = get_logger(__name__)


class ClaudeSessionError(Exception):
    """Raised when Claude session operations fail."""

    pass


def run_headless_session(
    worktree_path: Path,
    prompt: str,
    model: str,
    expected_output: Path,
    sdk_settings_path: Path,
    agents: dict[str, AgentDefinition] | None = None,
) -> Path:
    """Run headless Claude Code session via SDK.

    Executes prompt, waits for completion, validates output file exists.
    Use for: test execution, non-interactive tasks.

    Args:
        worktree_path: Path to worktree for session execution
        prompt: Prompt content for Claude Code
        model: Model to use (sonnet, opus, haiku)
        expected_output: File that should be created by session
        sdk_settings_path: Path to SDK settings.json
        agents: Optional dict of agent definitions for programmatic registration

    Returns:
        Path to output file

    Raises:
        ClaudeSessionError: If session fails or output missing
    """
    logger.info("Running headless SDK session...")
    logger.debug("Worktree: %s", worktree_path)
    logger.debug("Model: %s", model)
    logger.debug("Expected output: %s", expected_output)

    try:
        session_id = run_sdk_session_sync(
            worktree_path=worktree_path,
            prompt_content=prompt,
            model=model,
            sdk_settings_path=sdk_settings_path,
            agents=agents,
        )
        logger.info("Headless SDK session completed. Session ID: %s", session_id)
    except SDKRunnerError as exc:
        raise ClaudeSessionError(f"SDK session failed: {exc}") from exc

    if not expected_output.exists():
        raise ClaudeSessionError(
            f"Expected output file not created: {expected_output}. "
            f"The Claude session completed but did not produce the expected file."
        )

    logger.info("Output file validated: %s", expected_output)
    return expected_output


def run_interactive_session(
    worktree_path: Path,
    prompt: str,
    model: str,
    sdk_settings_path: Path,
    expected_output: Optional[Path] = None,
    agents: dict[str, AgentDefinition] | None = None,
) -> tuple[str, Optional[Path]]:
    """Run SDK session then launch CLI for user interaction.

    Runs headless SDK first (for logging/tracing), then launches
    interactive CLI for user to continue working.
    Use for: feedback collection, interactive editing tasks.

    Args:
        worktree_path: Path to worktree for session execution
        prompt: Initial prompt content for Claude Code
        model: Model to use (sonnet, opus, haiku)
        sdk_settings_path: Path to SDK settings.json
        expected_output: Optional file that should be created by session.
                        If None, no output validation is performed.
        agents: Optional dict of agent definitions for programmatic registration

    Returns:
        Tuple of (session_id, output_path). output_path is None if expected_output
        was None or if the file wasn't created.

    Raises:
        ClaudeSessionError: If SDK session fails or CLI launch fails.
        Does NOT raise if expected_output doesn't exist (user may have cancelled).
    """
    logger.info("Running interactive SDK session...")
    logger.debug("Worktree: %s", worktree_path)
    logger.debug("Model: %s", model)
    if expected_output:
        logger.debug("Expected output: %s", expected_output)

    # Run SDK first (for logging/tracing)
    try:
        session_id = run_sdk_session_sync(
            worktree_path=worktree_path,
            prompt_content=prompt,
            model=model,
            sdk_settings_path=sdk_settings_path,
            agents=agents,
        )
        logger.info("Initial SDK session completed. Session ID: %s", session_id)
    except SDKRunnerError as exc:
        raise ClaudeSessionError(f"SDK session failed: {exc}") from exc

    # Launch CLI for interactive user session
    command = f"claude -r {shlex.quote(session_id)} --model {shlex.quote(model)}"
    logger.info("Launching interactive CLI session...")
    logger.debug("CLI command: %s", command)

    try:
        subprocess.run(
            shlex.split(command),
            cwd=worktree_path,
            check=False,  # Don't raise on non-zero exit (user may cancel)
        )
    except Exception as exc:
        raise ClaudeSessionError(f"Failed to launch CLI session: {exc}") from exc

    # Check for expected output if provided
    output_path = None
    if expected_output and expected_output.exists():
        output_path = expected_output
        logger.info("Output file validated: %s", expected_output)
    elif expected_output:
        logger.warning(
            "Expected output file not created: %s. "
            "User may have cancelled the session.",
            expected_output,
        )

    return session_id, output_path


def run_sdk_only_session(
    worktree_path: Path,
    prompt: str,
    model: str,
    sdk_settings_path: Path,
    agents: dict[str, AgentDefinition] | None = None,
) -> str:
    """Run SDK session without any output validation or CLI follow-up.

    This is a thin wrapper around run_sdk_session_sync() that converts
    SDKRunnerError to ClaudeSessionError for consistent error handling.

    Use for: tasks where you need the session_id but don't expect a specific
    output file, or when you want to handle CLI resume separately.

    Args:
        worktree_path: Path to worktree for session execution
        prompt: Prompt content for Claude Code
        model: Model to use (sonnet, opus, haiku)
        sdk_settings_path: Path to SDK settings.json
        agents: Optional dict of agent definitions for programmatic registration

    Returns:
        Session ID from the SDK session

    Raises:
        ClaudeSessionError: If SDK session fails
    """
    logger.info("Running SDK-only session...")
    logger.debug("Worktree: %s", worktree_path)
    logger.debug("Model: %s", model)

    try:
        session_id = run_sdk_session_sync(
            worktree_path=worktree_path,
            prompt_content=prompt,
            model=model,
            sdk_settings_path=sdk_settings_path,
            agents=agents,
        )
        logger.info("SDK session completed. Session ID: %s", session_id)
        return session_id
    except SDKRunnerError as exc:
        raise ClaudeSessionError(f"SDK session failed: {exc}") from exc
