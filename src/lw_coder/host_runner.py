"""Utilities for running commands directly on the host environment.

This module replaces Docker-based execution with direct host execution,
supporting Linux environments with appropriate warnings for unsupported platforms.

Provides:
- OS detection and validation
- Direct command execution on host
- Environment variable setup for droid CLI
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .logging_config import get_logger

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
            f"⚠️  WARNING: lw_coder currently only supports Linux.\n"
            f"   Detected OS: {os_name.upper()}\n"
            f"   This command may not work correctly on {os_name}.\n"
            f"   For the best experience, use lw_coder on a Linux system.\n"
            f"   See https://github.com/anthropics/claude-code/issues for platform support updates."
        )
        logger.warning(warning_msg)
        print(warning_msg, file=sys.stderr)


def get_lw_coder_src_dir() -> Path:
    """Get the lw_coder source directory (where prompts and droids are located).

    Returns:
        Path to the lw_coder source directory.

    Raises:
        RuntimeError: If the source directory cannot be determined.
    """
    # The source directory is where this module is located
    src_dir = Path(__file__).resolve().parent
    if not src_dir.exists():
        raise RuntimeError(
            f"lw_coder source directory not found at {src_dir}. "
            "Ensure the package is properly installed."
        )
    return src_dir


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
        tasks_dir: Path to the .lw_coder/tasks directory.
        droids_dir: Path to the droids directory.
        auth_file: Path to the Factory auth.json file.
        settings_file: Path to the settings.json file.
        command: Command string to run on the host.
        host_factory_dir: Path to the host's .factory directory.
        env_vars: Optional dictionary of environment variables to pass.
    """

    worktree_path: Path
    repo_git_dir: Path
    tasks_dir: Path
    droids_dir: Path
    auth_file: Path
    settings_file: Path
    command: str
    host_factory_dir: Path
    env_vars: dict[str, str] | None = None


def host_runner_config(
    worktree_path: Path,
    repo_git_dir: Path,
    tasks_dir: Path,
    droids_dir: Path,
    auth_file: Path,
    settings_file: Path,
    command: str,
    host_factory_dir: Path,
    env_vars: dict[str, str] | None = None,
) -> HostRunnerConfig:
    """Factory function that creates a HostRunnerConfig.

    Args:
        worktree_path: Path to the Git worktree to use.
        repo_git_dir: Path to the repository's .git directory.
        tasks_dir: Path to the .lw_coder/tasks directory.
        droids_dir: Path to the droids directory.
        auth_file: Path to the Factory auth.json file.
        settings_file: Path to the settings.json file.
        command: Command string to run on the host.
        host_factory_dir: Path to the host's .factory directory.
        env_vars: Optional dictionary of environment variables to pass.

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
        droids_dir=droids_dir,
        auth_file=auth_file,
        settings_file=settings_file,
        command=command,
        host_factory_dir=host_factory_dir,
        env_vars=env_vars,
    )


def build_host_command(config: HostRunnerConfig) -> tuple[list[str], dict[str, str]]:
    """Build the host command and environment variables to run droid.

    Args:
        config: Configuration object with all paths and settings.

    Returns:
        Tuple of (command_list, environment_dict) for subprocess.run.

    Raises:
        RuntimeError: If required files or directories don't exist.
    """
    # Ensure tasks directory exists
    config.tasks_dir.mkdir(parents=True, exist_ok=True)

    # Ensure host factory directory exists
    config.host_factory_dir.mkdir(parents=True, exist_ok=True)

    # Validate that required files/directories exist
    _validate_path_exists(config.droids_dir, "Droids directory")
    if not config.auth_file.exists():
        raise RuntimeError(
            f"Auth file not found: {config.auth_file}\n"
            f"Factory authentication is required to run droid commands."
        )
    _validate_path_exists(config.settings_file, "Settings file")

    # Build environment for the command
    env = os.environ.copy()

    # Add custom environment variables if provided
    if config.env_vars:
        env.update(config.env_vars)

    # Set up Factory environment for droid CLI
    # The droid CLI looks for auth.json and settings.json in ~/.factory
    env["FACTORY_HOME"] = str(config.host_factory_dir)

    # Build the command - just run it with bash -c on the host
    cmd = ["bash", "-c", config.command]

    return cmd, env
