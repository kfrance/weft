"""Pre-execution setup commands for the code command.

This module provides functionality to run arbitrary setup commands on the host
system before the sandboxed `weft code` session begins. This allows preparation
of the execution environment (starting services, configuring system resources, etc.)
that cannot be done from within the sandbox.

Security Model:
    Setup commands are configured in the repository's .weft/config.toml file.
    These commands are developer-controlled within their own repository - similar to
    npm scripts, Makefiles, or git hooks. The user explicitly invokes `weft code`
    in their repository, opting into the repository's configured setup commands.
    See docs/THREAT_MODEL.md for detailed security rationale.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .logging_config import get_logger
from .worktree.file_sync import load_repo_config, FileSyncError

if TYPE_CHECKING:
    from typing import Any

logger = get_logger(__name__)


class SetupCommandError(Exception):
    """Base exception for setup command errors."""


class SetupConfigError(SetupCommandError):
    """Exception for configuration validation errors."""


class SetupExecutionError(SetupCommandError):
    """Exception for command execution failures."""


@dataclass
class SetupCommand:
    """Configuration for a single setup command.

    Attributes:
        name: Descriptive name for the command.
        command: Shell command to execute.
        working_dir: Optional working directory relative to repo root.
        continue_on_failure: If True, don't abort on command failure.
    """

    name: str
    command: str
    working_dir: str | None = None
    continue_on_failure: bool = False


def _validate_setup_command(
    cmd_config: dict[str, Any], index: int
) -> SetupCommand:
    """Validate and parse a single [[code.setup]] entry.

    Args:
        cmd_config: Dictionary containing command configuration.
        index: Index of this command in the config list (for error messages).

    Returns:
        Validated SetupCommand instance.

    Raises:
        SetupConfigError: If the configuration is invalid.
    """
    # Validate no unknown keys
    valid_keys = {"name", "command", "working_dir", "continue_on_failure"}
    unknown_keys = set(cmd_config.keys()) - valid_keys
    if unknown_keys:
        raise SetupConfigError(
            f"[[code.setup]] entry {index}: Unknown keys: {', '.join(sorted(unknown_keys))}. "
            f"Valid keys: {', '.join(sorted(valid_keys))}"
        )

    # Validate required 'name' field
    name = cmd_config.get("name")
    if name is None:
        raise SetupConfigError(
            f"[[code.setup]] entry {index}: Missing required 'name' field"
        )
    if not isinstance(name, str):
        raise SetupConfigError(
            f"[[code.setup]] entry {index}: 'name' must be a string, got {type(name).__name__}"
        )
    if not name.strip():
        raise SetupConfigError(
            f"[[code.setup]] entry {index}: 'name' cannot be empty or whitespace-only"
        )

    # Validate required 'command' field
    command = cmd_config.get("command")
    if command is None:
        raise SetupConfigError(
            f"[[code.setup]] entry {index}: Missing required 'command' field"
        )
    if not isinstance(command, str):
        raise SetupConfigError(
            f"[[code.setup]] entry {index}: 'command' must be a string, got {type(command).__name__}"
        )
    if not command.strip():
        raise SetupConfigError(
            f"[[code.setup]] entry {index}: 'command' cannot be empty or whitespace-only"
        )

    # Validate optional 'working_dir' field
    working_dir = cmd_config.get("working_dir")
    if working_dir is not None:
        if not isinstance(working_dir, str):
            raise SetupConfigError(
                f"[[code.setup]] entry {index}: 'working_dir' must be a string, got {type(working_dir).__name__}"
            )

    # Validate optional 'continue_on_failure' field
    continue_on_failure = cmd_config.get("continue_on_failure", False)
    if not isinstance(continue_on_failure, bool):
        raise SetupConfigError(
            f"[[code.setup]] entry {index}: 'continue_on_failure' must be a boolean, "
            f"got {type(continue_on_failure).__name__}"
        )

    return SetupCommand(
        name=name,
        command=command,
        working_dir=working_dir,
        continue_on_failure=continue_on_failure,
    )


def load_setup_commands(repo_root: Path) -> list[SetupCommand]:
    """Load setup commands from .weft/config.toml in the repository.

    Parses the [[code.setup]] sections and validates each entry.

    Args:
        repo_root: Path to the repository root.

    Returns:
        List of validated SetupCommand instances, or empty list if none configured.

    Raises:
        SetupConfigError: If configuration is invalid.
        SetupCommandError: If configuration file cannot be read.
    """
    try:
        config = load_repo_config(repo_root)
    except FileSyncError as exc:
        raise SetupCommandError(f"Failed to load repository config: {exc}") from exc

    if not config:
        logger.debug("No repo config found, no setup commands")
        return []

    # Get the code section
    code_section = config.get("code")
    if code_section is None:
        logger.debug("No [code] section in config, no setup commands")
        return []

    if not isinstance(code_section, dict):
        raise SetupConfigError(
            "[code] section must be a table"
        )

    # Get the setup list
    setup_list = code_section.get("setup")
    if setup_list is None:
        logger.debug("No [[code.setup]] entries in config")
        return []

    if not isinstance(setup_list, list):
        raise SetupConfigError(
            "[code.setup] must be an array of tables (use [[code.setup]])"
        )

    # Validate and parse each entry
    commands = []
    for index, cmd_config in enumerate(setup_list):
        if not isinstance(cmd_config, dict):
            raise SetupConfigError(
                f"[[code.setup]] entry {index}: Must be a table, got {type(cmd_config).__name__}"
            )
        command = _validate_setup_command(cmd_config, index)
        commands.append(command)

    logger.debug("Loaded %d setup commands from config", len(commands))
    return commands


def _resolve_working_dir(
    working_dir: str | None, repo_root: Path
) -> Path:
    """Resolve and validate working directory.

    Args:
        working_dir: Optional relative path from config.
        repo_root: Repository root directory.

    Returns:
        Resolved absolute path to working directory.

    Raises:
        SetupExecutionError: If working directory is invalid.
    """
    if working_dir is None:
        return repo_root

    # Reject absolute paths explicitly for clearer error message
    if working_dir.startswith('/'):
        raise SetupExecutionError(
            f"Working directory must be a relative path, got absolute path: {working_dir}"
        )

    # Resolve relative to repo root
    resolved = (repo_root / working_dir).resolve()

    # Validate directory exists
    if not resolved.exists():
        raise SetupExecutionError(
            f"Working directory does not exist: {working_dir}"
        )

    if not resolved.is_dir():
        raise SetupExecutionError(
            f"Working directory is not a directory: {working_dir}"
        )

    # Validate within repository (prevent escaping via .. or symlinks)
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        raise SetupExecutionError(
            f"Working directory escapes repository root: {working_dir}"
        )

    return resolved


def run_setup_commands(
    commands: list[SetupCommand],
    repo_root: Path,
    worktree_path: Path,
    plan_id: str,
    plan_path: Path,
) -> None:
    """Execute setup commands sequentially on the host.

    Commands inherit the current shell environment with additional WEFT_*
    variables injected. Commands run from repo_root by default, with
    optional per-command working_dir override.

    Args:
        commands: List of SetupCommand instances to execute.
        repo_root: Absolute path to repository root.
        worktree_path: Absolute path to created worktree.
        plan_id: Identifier of the current plan.
        plan_path: Path to the plan file.

    Raises:
        SetupExecutionError: If a command fails and continue_on_failure is False.
    """
    if not commands:
        return

    # Build environment with WEFT_* variables injected
    # These override any existing env vars with the same names
    env = os.environ.copy()
    env["WEFT_REPO_ROOT"] = str(repo_root.resolve())
    env["WEFT_WORKTREE_PATH"] = str(worktree_path.resolve())
    env["WEFT_PLAN_ID"] = plan_id
    env["WEFT_PLAN_PATH"] = str(plan_path.resolve())

    logger.info("Running %d setup command(s)...", len(commands))

    for cmd in commands:
        # Log at info level with name only (not full command for security)
        logger.info("Running setup command: %s", cmd.name)
        logger.debug("Command details: %s", cmd.command)

        # Resolve working directory
        try:
            cwd = _resolve_working_dir(cmd.working_dir, repo_root)
        except SetupExecutionError as exc:
            if cmd.continue_on_failure:
                logger.warning(
                    "Setup command '%s' working directory error (continuing): %s",
                    cmd.name,
                    exc,
                )
                continue
            raise

        # Execute command with shell=True for shell features
        # This is developer-controlled code from their repo config (see security model)
        try:
            result = subprocess.run(
                cmd.command,
                shell=True,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            if cmd.continue_on_failure:
                logger.warning(
                    "Setup command '%s' execution error (continuing): %s",
                    cmd.name,
                    exc,
                )
                continue
            raise SetupExecutionError(
                f"Setup command '{cmd.name}' failed to execute: {exc}"
            ) from exc

        if result.returncode != 0:
            # Build detailed error message with captured output
            error_details = [
                f"Setup command '{cmd.name}' failed with exit code {result.returncode}",
            ]
            if cmd.working_dir:
                error_details.append(f"Working directory: {cmd.working_dir}")

            if result.stdout:
                error_details.append(f"stdout:\n{result.stdout}")
            if result.stderr:
                error_details.append(f"stderr:\n{result.stderr}")

            error_message = "\n".join(error_details)

            if cmd.continue_on_failure:
                logger.warning("%s (continuing due to continue_on_failure=true)", error_message)
                continue

            raise SetupExecutionError(error_message)

        logger.debug("Setup command '%s' completed successfully", cmd.name)

    logger.info("All setup commands completed")
