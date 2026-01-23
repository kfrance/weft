"""Weft sandbox module for bwrap-based filesystem isolation.

This module provides a custom sandbox implementation using bubblewrap (bwrap)
that provides consistent filesystem isolation for both Claude Code SDK sessions
and Droid executors.

Key features:
- Wraps executor commands with bwrap for filesystem isolation
- Configurable read-only, write-only, and read-write path mounts
- Supports ~ home directory expansion in configured paths
- Blocks specific commands via --disallowed-tools for Claude Code CLI
- Error detection for path collisions (same path in multiple lists)

Configuration is loaded from the repository's .weft/config.toml [sandbox] section.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logging_config import get_logger

# Try to import tomllib (Python 3.11+) or tomli (fallback)
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found]

logger = get_logger(__name__)


def find_claude_install_dir() -> str | None:
    """Find the Claude Code installation directory.

    Locates the 'claude' command, resolves symlinks, and returns the
    directory containing the actual executable. This allows mounting
    Claude Code regardless of installation location.

    Returns:
        Path to the directory containing Claude Code, or None if not found.
    """
    claude_path = shutil.which("claude")
    if not claude_path:
        logger.debug("Claude command not found in PATH")
        return None

    # Resolve symlinks to find the actual installation
    resolved = Path(claude_path).resolve()
    install_dir = str(resolved.parent)

    logger.debug(
        "Found Claude at %s, resolved to %s, install dir: %s",
        claude_path,
        resolved,
        install_dir,
    )

    return install_dir


class SandboxConfigError(Exception):
    """Raised when sandbox configuration is invalid."""


@dataclass
class SandboxConfig:
    """Configuration for the weft sandbox.

    Attributes:
        read_paths: Paths to mount as read-only (beyond automatic mounts).
        write_paths: Paths to mount as write-only (not implemented - reserved).
        read_write_paths: Paths to mount as read-write (beyond automatic mounts).
        disallowed_commands: Command patterns to block via --disallowed-tools.
            Patterns follow the format "command:pattern" e.g. "git add:*".
    """

    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    read_write_paths: list[str] = field(default_factory=list)
    disallowed_commands: list[str] = field(default_factory=list)


def expand_path(path: str) -> str:
    """Expand ~ and environment variables in a path.

    Args:
        path: Path string that may contain ~ or environment variables.

    Returns:
        Expanded absolute path string.
    """
    # Expand ~ to home directory
    expanded = os.path.expanduser(path)
    # Expand environment variables
    expanded = os.path.expandvars(expanded)
    return expanded


def validate_config(config: SandboxConfig) -> None:
    """Validate sandbox configuration for path collisions.

    Checks that no path appears in multiple lists (read_paths, write_paths,
    read_write_paths). Paths are compared after expansion.

    Args:
        config: SandboxConfig to validate.

    Raises:
        SandboxConfigError: If the same path appears in multiple lists.
    """
    # Expand all paths for comparison
    read_expanded = {expand_path(p) for p in config.read_paths}
    write_expanded = {expand_path(p) for p in config.write_paths}
    read_write_expanded = {expand_path(p) for p in config.read_write_paths}

    # Check for collisions
    read_write_collision = read_expanded & write_expanded
    read_rw_collision = read_expanded & read_write_expanded
    write_rw_collision = write_expanded & read_write_expanded

    collisions = []
    if read_write_collision:
        collisions.append(
            f"read_paths and write_paths: {read_write_collision}"
        )
    if read_rw_collision:
        collisions.append(
            f"read_paths and read_write_paths: {read_rw_collision}"
        )
    if write_rw_collision:
        collisions.append(
            f"write_paths and read_write_paths: {write_rw_collision}"
        )

    if collisions:
        raise SandboxConfigError(
            f"Path collision in sandbox config: {'; '.join(collisions)}"
        )


def load_sandbox_config(config_path: Path) -> SandboxConfig:
    """Load sandbox configuration from .weft/config.toml.

    Args:
        config_path: Path to the config.toml file.

    Returns:
        SandboxConfig with parsed settings, or defaults if section missing.

    Raises:
        SandboxConfigError: If TOML is invalid or path collisions detected.
    """
    if not config_path.exists():
        logger.debug("No config file at %s, using sandbox defaults", config_path)
        return SandboxConfig()

    try:
        content = config_path.read_bytes()
    except OSError as exc:
        raise SandboxConfigError(f"Failed to read config file: {exc}") from exc

    try:
        config_data = tomllib.loads(content.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SandboxConfigError(f"Invalid TOML in config file: {exc}") from exc

    sandbox_section = config_data.get("sandbox", {})
    if not isinstance(sandbox_section, dict):
        raise SandboxConfigError(
            f"[sandbox] section should be a table, got {type(sandbox_section).__name__}"
        )

    # Extract lists with type checking
    def get_string_list(data: dict[str, Any], key: str) -> list[str]:
        value = data.get(key, [])
        if not isinstance(value, list):
            raise SandboxConfigError(
                f"sandbox.{key} should be a list, got {type(value).__name__}"
            )
        for i, item in enumerate(value):
            if not isinstance(item, str):
                raise SandboxConfigError(
                    f"sandbox.{key}[{i}] should be a string, got {type(item).__name__}"
                )
        return value

    config = SandboxConfig(
        read_paths=get_string_list(sandbox_section, "read_paths"),
        write_paths=get_string_list(sandbox_section, "write_paths"),
        read_write_paths=get_string_list(sandbox_section, "read_write_paths"),
        disallowed_commands=get_string_list(sandbox_section, "disallowed_commands"),
    )

    # Validate for path collisions
    validate_config(config)

    # Warn if write_paths is configured (not implemented)
    if config.write_paths:
        logger.warning(
            "sandbox.write_paths is configured but not implemented. "
            "These paths will be ignored: %s. Use read_write_paths instead.",
            config.write_paths,
        )

    logger.debug(
        "Loaded sandbox config: %d read, %d write, %d read_write, %d disallowed",
        len(config.read_paths),
        len(config.write_paths),
        len(config.read_write_paths),
        len(config.disallowed_commands),
    )

    return config


def build_bwrap_command(
    command: str,
    config: SandboxConfig,
    worktree_path: Path,
    repo_git_dir: Path | None = None,
) -> list[str]:
    """Build a bwrap-wrapped command with sandbox isolation.

    Creates a bwrap command that:
    - Mounts system paths read-only (/usr, /lib, /lib64, /bin, /sbin, /etc)
    - Mounts /proc and /dev for process management
    - Creates a tmpfs at /tmp with /tmp/claude bind-mounted for temp files
    - Shares network access (required for API calls)
    - Mounts exact PATH directories read-only (not parent dirs, to avoid exposing credentials)
    - Mounts Claude Code installation directory read-only (dynamically located)
    - Mounts ~/.claude read-write (Claude config/sessions/todos)
    - Mounts ~/.claude.json read-write (global Claude config with onboarding state)
    - Mounts ~/.gitconfig read-only (git user identity and global settings)
    - Mounts XDG_RUNTIME_DIR read-write (D-Bus session bus for authentication)
    - Mounts the worktree path read-write
    - Mounts repo .git directory read-write (for git worktree operations)
    - Mounts configured paths from SandboxConfig
    - Passes through HOME, PATH, XDG_RUNTIME_DIR, and DBUS_SESSION_BUS_ADDRESS

    Args:
        command: The command string to wrap with bwrap.
        config: Sandbox configuration with additional mount paths.
        worktree_path: Path to the worktree (mounted read-write).
        repo_git_dir: Optional path to the repository's .git directory
            (mounted read-write for git worktree operations).

    Returns:
        List of command arguments starting with "bwrap".
    """
    home = str(Path.home())
    worktree = str(worktree_path.resolve())

    # Start building bwrap command
    bwrap_args = ["bwrap"]

    # System paths - read-only
    system_ro_paths = ["/usr", "/lib", "/lib64", "/bin", "/sbin", "/etc"]
    for path in system_ro_paths:
        if Path(path).exists():
            bwrap_args.extend(["--ro-bind", path, path])

    # Special mounts
    bwrap_args.extend(["--proc", "/proc"])
    bwrap_args.extend(["--dev", "/dev"])
    bwrap_args.extend(["--tmpfs", "/tmp"])

    # Mount /tmp/claude read-write for weft prompt files and other temp data
    # This overlays on top of the tmpfs, exposing the real /tmp/claude directory
    tmp_claude = Path("/tmp/claude")
    tmp_claude.mkdir(parents=True, exist_ok=True)
    bwrap_args.extend(["--bind", "/tmp/claude", "/tmp/claude"])

    # Network sharing (required for API calls)
    bwrap_args.append("--share-net")

    # Mount exact PATH directories read-only (not parent directories)
    # This avoids exposing credential files like ~/.cargo/credentials.toml
    user_path = os.environ.get("PATH", "")
    mounted_paths: set[str] = set()
    for path_entry in user_path.split(":"):
        if not path_entry or not Path(path_entry).exists():
            continue
        # Skip paths already covered by system mounts
        is_covered = any(
            path_entry == sys_path or path_entry.startswith(sys_path + "/")
            for sys_path in system_ro_paths
        )
        if is_covered:
            continue

        # Mount exact path only (not parent) to avoid credential exposure
        if path_entry not in mounted_paths:
            mounted_paths.add(path_entry)
            bwrap_args.extend(["--ro-bind", path_entry, path_entry])

    # Mount Claude Code installation directory (dynamically located)
    claude_install_dir = find_claude_install_dir()
    if claude_install_dir and claude_install_dir not in mounted_paths:
        # Check it's not already covered by system mounts
        is_system = any(
            claude_install_dir == sys_path or claude_install_dir.startswith(sys_path + "/")
            for sys_path in system_ro_paths
        )
        if not is_system:
            mounted_paths.add(claude_install_dir)
            bwrap_args.extend(["--ro-bind", claude_install_dir, claude_install_dir])

    # Claude-specific paths
    claude_dir = os.path.join(home, ".claude")
    claude_json = os.path.join(home, ".claude.json")

    # Ensure ~/.claude exists and mount read-write
    claude_path = Path(claude_dir)
    claude_path.mkdir(parents=True, exist_ok=True)
    # Also ensure ~/.claude/skills exists (Claude scans for it at startup)
    (claude_path / "skills").mkdir(parents=True, exist_ok=True)
    bwrap_args.extend(["--bind", claude_dir, claude_dir])

    # Mount ~/.claude.json read-write (global Claude config with onboarding state)
    if Path(claude_json).exists():
        bwrap_args.extend(["--bind", claude_json, claude_json])

    # Mount ~/.gitconfig read-only (git user identity and global settings)
    gitconfig = os.path.join(home, ".gitconfig")
    if Path(gitconfig).exists():
        bwrap_args.extend(["--ro-bind", gitconfig, gitconfig])

    # Mount XDG_RUNTIME_DIR for D-Bus session bus access (needed for authentication)
    xdg_runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime_dir and Path(xdg_runtime_dir).exists():
        bwrap_args.extend(["--bind", xdg_runtime_dir, xdg_runtime_dir])

    # Worktree path - read-write
    bwrap_args.extend(["--bind", worktree, worktree])

    # Repository .git directory - read-write (required for git worktree operations)
    if repo_git_dir and repo_git_dir.exists():
        git_dir_str = str(repo_git_dir.resolve())
        bwrap_args.extend(["--bind", git_dir_str, git_dir_str])

    # User-configured read-only paths
    for path in config.read_paths:
        expanded = expand_path(path)
        if Path(expanded).exists():
            bwrap_args.extend(["--ro-bind", expanded, expanded])
        else:
            logger.warning("Read path does not exist, skipping: %s", expanded)

    # User-configured read-write paths
    for path in config.read_write_paths:
        expanded = expand_path(path)
        # Create directory if it doesn't exist
        Path(expanded).mkdir(parents=True, exist_ok=True)
        bwrap_args.extend(["--bind", expanded, expanded])

    # Environment variables
    bwrap_args.extend(["--setenv", "HOME", home])
    # Pass through the user's actual PATH so all their tools are available
    bwrap_args.extend(["--setenv", "PATH", user_path])

    # Pass through XDG_RUNTIME_DIR and DBUS_SESSION_BUS_ADDRESS for D-Bus access
    if xdg_runtime_dir:
        bwrap_args.extend(["--setenv", "XDG_RUNTIME_DIR", xdg_runtime_dir])
    dbus_address = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if dbus_address:
        bwrap_args.extend(["--setenv", "DBUS_SESSION_BUS_ADDRESS", dbus_address])

    # Set working directory
    bwrap_args.extend(["--chdir", worktree])

    # Add separator and command
    bwrap_args.append("--")
    bwrap_args.extend(["bash", "-c", command])

    return bwrap_args


def get_disallowed_tools_args(config: SandboxConfig) -> list[str]:
    """Build --disallowed-tools arguments for Claude Code CLI.

    Converts disallowed_commands config patterns to the Claude Code CLI
    --disallowed-tools format. Each pattern like "git add:*" becomes
    "Bash(git add:*)" to block bash commands matching that pattern.

    Args:
        config: Sandbox configuration with disallowed_commands.

    Returns:
        List of CLI arguments, e.g. ["--disallowed-tools", "Bash(git add:*)", "Bash(git commit:*)"]
    """
    if not config.disallowed_commands:
        return []

    args = ["--disallowed-tools"]
    for pattern in config.disallowed_commands:
        # Wrap pattern in Bash() for CLI format
        args.append(f"Bash({pattern})")

    return args


def matches_disallowed_command(command: str, config: SandboxConfig) -> tuple[bool, str | None]:
    """Check if a command matches any disallowed command pattern.

    Used by the SDK can_use_tool callback to block commands.

    Args:
        command: The bash command to check.
        config: Sandbox configuration with disallowed_commands.

    Returns:
        Tuple of (is_blocked, matching_pattern). If blocked, matching_pattern
        is the pattern that matched. If not blocked, matching_pattern is None.
    """
    for pattern in config.disallowed_commands:
        # Pattern format is "prefix:*" where prefix must match start of command
        if pattern.endswith(":*"):
            prefix = pattern[:-2]  # Remove ":*"
            if command.startswith(prefix):
                return True, pattern
        elif command == pattern:
            # Exact match
            return True, pattern

    return False, None
