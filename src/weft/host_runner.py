"""Utilities for running commands directly on the host environment.

This module replaces Docker-based execution with direct host execution,
supporting Linux environments with appropriate warnings for unsupported platforms.

Provides:
- OS detection and validation
- Direct command execution on host with bwrap sandbox isolation
- Environment variable setup for droid CLI

Sandbox: Commands are wrapped with bwrap (bubblewrap) for filesystem isolation.
The sandbox configuration is loaded from the repository's .weft/config.toml.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from .logging_config import get_logger
from .sandbox import SandboxConfig, build_bwrap_command

logger = get_logger(__name__)


def get_os_name() -> str:
    """Get the operating system name.

    Returns:
        "linux", "darwin" (macOS), "windows", or the result of platform.system().lower()
    """
    return platform.system().lower()


def is_supported_os() -> bool:
    """Check if the current OS is supported (Linux).

    Returns:
        True if OS is Linux, False otherwise
    """
    return get_os_name() == "linux"


def check_os_support() -> None:
    """Check if current OS is supported and warn if not.

    Logs a warning and prints to stderr if the current OS is not Linux.
    Does not raise exceptions.
    """
    if not is_supported_os():
        os_name = get_os_name()
        warning_msg = (
            f"⚠️  WARNING: weft currently only supports Linux.\n"
            f"   Detected OS: {os_name.upper()}\n"
            f"   This command may not work correctly on {os_name}.\n"
            f"   For the best experience, use weft on a Linux system.\n"
            f"   See https://github.com/anthropics/claude-code/issues for platform support updates."
        )
        logger.warning(warning_msg)
        print(warning_msg, file=sys.stderr)


# Re-export from paths module for backwards compatibility
from .paths import get_weft_src_dir


def _validate_path_exists(path: Path, name: str) -> None:
    """Validate that a required path exists.

    Args:
        path: Path to validate.
        name: Human-readable name of the resource for error messages.

    Raises:
        RuntimeError: If the path does not exist.
    """
    if not path.exists():
        raise RuntimeError(f"{name} not found: {path}")


@dataclass
class HostRunnerConfig:
    """Configuration for running a command on the host.

    Attributes:
        worktree_path: Path to the Git worktree to use.
        repo_git_dir: Path to the repository's .git directory.
        tasks_dir: Path to the .weft/tasks directory.
        command: Command string to run on the host.
        host_factory_dir: Path to the host's .factory directory.
        env_vars: Optional dictionary of environment variables to pass.
        auth_file: Optional path to the Factory auth.json file (deprecated, kept for backward compatibility).
        sandbox_config: Optional sandbox configuration for bwrap isolation.
    """

    worktree_path: Path
    repo_git_dir: Path
    tasks_dir: Path
    command: str
    host_factory_dir: Path
    env_vars: dict[str, str] | None = None
    auth_file: Path | None = None
    sandbox_config: SandboxConfig | None = None


def host_runner_config(
    worktree_path: Path,
    repo_git_dir: Path,
    tasks_dir: Path,
    command: str,
    host_factory_dir: Path,
    env_vars: dict[str, str] | None = None,
    auth_file: Path | None = None,
    sandbox_config: SandboxConfig | None = None,
) -> HostRunnerConfig:
    """Factory function that creates a HostRunnerConfig.

    Args:
        worktree_path: Path to the Git worktree to use.
        repo_git_dir: Path to the repository's .git directory.
        tasks_dir: Path to the .weft/tasks directory.
        command: Command string to run on the host.
        host_factory_dir: Path to the host's .factory directory.
        env_vars: Optional dictionary of environment variables to pass.
        auth_file: Optional path to the Factory auth.json file (deprecated, kept for backward compatibility).
        sandbox_config: Optional sandbox configuration for bwrap isolation.

    Returns:
        HostRunnerConfig with all fields populated.

    Example:
        config = host_runner_config(...)
        cmd, env = build_host_command(config)
        subprocess.run(cmd, env=env)
    """
    return HostRunnerConfig(
        worktree_path=worktree_path,
        repo_git_dir=repo_git_dir,
        tasks_dir=tasks_dir,
        command=command,
        host_factory_dir=host_factory_dir,
        env_vars=env_vars,
        auth_file=auth_file,
        sandbox_config=sandbox_config,
    )


def build_host_command(config: HostRunnerConfig) -> tuple[list[str], dict[str, str]]:
    """Build the host command and environment variables to run the executor.

    Wraps the command with bwrap for filesystem isolation if sandbox_config
    is provided. The sandbox provides:
    - Read-only access to system paths (/usr, /lib, /bin, /etc)
    - Read-write access to the worktree and configured paths
    - Network sharing (required for API calls)

    Args:
        config: Configuration object with all paths and settings.

    Returns:
        Tuple of (command_list, environment_dict) for subprocess.run.
    """
    # Ensure tasks directory exists
    config.tasks_dir.mkdir(parents=True, exist_ok=True)

    # Ensure host factory directory exists
    config.host_factory_dir.mkdir(parents=True, exist_ok=True)

    # Build environment for the command
    env = os.environ.copy()

    # Add executor-specific environment variables if provided
    if config.env_vars:
        env.update(config.env_vars)

    # Use default sandbox config if none provided
    sandbox_config = config.sandbox_config or SandboxConfig()

    # Build the command wrapped with bwrap for filesystem isolation
    cmd = build_bwrap_command(
        command=config.command,
        config=sandbox_config,
        worktree_path=config.worktree_path,
        repo_git_dir=config.repo_git_dir,
    )

    logger.debug("Built bwrap command with %d args", len(cmd))

    return cmd, env
