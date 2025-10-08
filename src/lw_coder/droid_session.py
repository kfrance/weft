"""Shared utilities for managing droid sessions in Docker containers.

This module provides:
- Git worktree .git pointer patching for Docker mounts
- Docker command construction with all required mounts
- lw_coder source directory discovery
"""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


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


def create_container_passwd_file(uid: int, gid: int, username: str = "droiduser") -> Path:
    """Create a minimal /etc/passwd file for the container user.

    Args:
        uid: User ID for the container user.
        gid: Group ID for the container user.
        username: Username for the container user (default: "droiduser").

    Returns:
        Path to the created passwd file.
    """
    # Create a minimal passwd file with the host user's UID
    # Format: username:x:uid:gid:gecos:home:shell
    passwd_content = f"{username}:x:{uid}:{gid}:Container User:/home/{username}:/bin/bash\n"

    # Create temporary file that won't be auto-deleted
    fd, passwd_path = tempfile.mkstemp(prefix="container_passwd_", suffix=".txt", text=True)
    try:
        with open(fd, 'w') as f:
            f.write(passwd_content)
    except Exception:
        # Clean up on error
        Path(passwd_path).unlink(missing_ok=True)
        raise

    return Path(passwd_path)


def create_container_group_file(gid: int, groupname: str = "droiduser") -> Path:
    """Create a minimal /etc/group file for the container group.

    Args:
        gid: Group ID for the container group.
        groupname: Group name for the container group (default: "droiduser").

    Returns:
        Path to the created group file.
    """
    # Create a minimal group file with the host user's GID
    # Format: groupname:x:gid:
    group_content = f"{groupname}:x:{gid}:\n"

    # Create temporary file that won't be auto-deleted
    fd, group_path = tempfile.mkstemp(prefix="container_group_", suffix=".txt", text=True)
    try:
        with open(fd, 'w') as f:
            f.write(group_content)
    except Exception:
        # Clean up on error
        Path(group_path).unlink(missing_ok=True)
        raise

    return Path(group_path)


@dataclass
class DroidSessionConfig:
    """Configuration for a droid session in Docker.

    Attributes:
        worktree_path: Path to the Git worktree to mount.
        repo_git_dir: Path to the repository's .git directory.
        tasks_dir: Path to the .lw_coder/tasks directory.
        droids_dir: Path to the droids directory.
        auth_file: Path to the Factory auth.json file.
        settings_file: Path to the container settings.json file.
        prompt_file: Path to the file containing the prompt.
        image_tag: Docker image tag to use.
        worktree_name: Name of the worktree (extracted from .git file).
        command: Command string to run inside the container.
        container_uid: UID to run the container as.
        container_gid: GID to run the container as.
        container_home: HOME directory path inside the container.
        host_factory_dir: Path to the host's .factory directory.
        passwd_file: Path to the temporary passwd file for the container.
        group_file: Path to the temporary group file for the container.
    """

    worktree_path: Path
    repo_git_dir: Path
    tasks_dir: Path
    droids_dir: Path
    auth_file: Path
    settings_file: Path
    prompt_file: Path
    image_tag: str
    worktree_name: str
    command: str
    container_uid: int
    container_gid: int
    container_home: str
    host_factory_dir: Path
    passwd_file: Path
    group_file: Path


@contextmanager
def patched_worktree_gitdir(
    worktree: Path, repo_git_dir: Path
) -> Iterator[str]:
    """Context manager that patches a worktree's .git file to point to container path.

    The worktree's .git file is rewritten to point to /repo-git/worktrees/<name>
    for the duration of the context, then restored to its original contents.

    Args:
        worktree: Path to the worktree directory.
        repo_git_dir: Path to the repository's .git directory (for validation).

    Yields:
        The worktree name extracted from the original .git file.

    Raises:
        RuntimeError: If the .git file cannot be read or does not contain a gitdir pointer.
    """
    worktree_git_file = worktree / ".git"
    if not worktree_git_file.exists():
        raise RuntimeError(
            f"Worktree .git file not found at {worktree_git_file}"
        )

    # Read the current gitdir path
    original_gitdir = worktree_git_file.read_text().strip()
    if not original_gitdir.startswith("gitdir:"):
        raise RuntimeError(
            f"Worktree .git file does not contain a gitdir pointer: {original_gitdir}"
        )

    # Extract worktree name (e.g., "temp-20251007_142615_613903-6f72d984")
    # The original format is like: "gitdir: /path/to/repo/.git/worktrees/<name>"
    gitdir_path = original_gitdir.split(":", 1)[1].strip()
    worktree_name = Path(gitdir_path).name

    # Write new gitdir pointing to container path
    container_gitdir = f"gitdir: /repo-git/worktrees/{worktree_name}\n"
    try:
        worktree_git_file.write_text(container_gitdir)
        yield worktree_name
    finally:
        # Restore original contents
        worktree_git_file.write_text(original_gitdir)


def build_docker_command(config: DroidSessionConfig) -> list[str]:
    """Build the Docker command to run droid with the given configuration.

    This function constructs the full docker run command with all required
    mounts and settings. It also ensures the tasks directory and host factory
    directory exist, and validates that required source files/directories exist.

    Args:
        config: Configuration object with all paths and settings.

    Returns:
        List of command arguments for subprocess.run.

    Raises:
        RuntimeError: If required source files or directories don't exist.
    """
    # Ensure tasks directory exists
    config.tasks_dir.mkdir(parents=True, exist_ok=True)

    # Ensure host factory directory exists
    config.host_factory_dir.mkdir(parents=True, exist_ok=True)

    # Validate that required source files/directories exist for Docker mounts
    if not config.droids_dir.exists():
        raise RuntimeError(f"Droids directory not found: {config.droids_dir}")
    if not config.settings_file.exists():
        raise RuntimeError(f"Settings file not found: {config.settings_file}")
    if not config.prompt_file.exists():
        raise RuntimeError(f"Prompt file not found: {config.prompt_file}")
    if not config.passwd_file.exists():
        raise RuntimeError(f"Passwd file not found: {config.passwd_file}")
    if not config.group_file.exists():
        raise RuntimeError(f"Group file not found: {config.group_file}")

    cmd = [
        "docker", "run", "-it", "--rm",
        "--security-opt=no-new-privileges",
        "--user", f"{config.container_uid}:{config.container_gid}",
        "-e", f"HOME={config.container_home}",
        "-v", f"{config.worktree_path}:/workspace",
        "-v", f"{config.repo_git_dir}:/repo-git:ro",
        "-v", f"{config.tasks_dir}:/output",
        "-v", f"{config.host_factory_dir}:{config.container_home}/.factory",
        "-v", f"{config.droids_dir}:{config.container_home}/.factory/droids:ro",
        "-v", f"{config.settings_file}:{config.container_home}/.factory/settings.json:ro",
        "-v", f"{config.prompt_file}:/tmp/prompt.txt:ro",
        "-v", f"{config.passwd_file}:/etc/passwd:ro",
        "-v", f"{config.group_file}:/etc/group:ro",
        "-w", "/workspace",
        config.image_tag,
        "bash", "-c", config.command,
    ]

    return cmd
