"""Shared utilities for managing droid sessions in Docker containers.

This module provides:
- Git worktree .git pointer patching for Docker mounts
- Docker command construction with all required mounts
- lw_coder source directory discovery
"""

from __future__ import annotations

import os
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

    This file is mounted read-only over /etc/passwd in the container. Currently creates
    only the container user entry, which works for the lw_coder_droid image that has
    git and other tools pre-installed.

    NOTE: If you need to run package installers (apt-get, yum) inside the container,
    you'll need to add system accounts (root:x:0:0, _apt:x:42:65534, etc.) to this
    file, otherwise apt-get will fail with exit code 100 due to missing _apt user.
    See docs/historical/docker_test_debugging.md for the debugging journey.

    Args:
        uid: User ID for the container user.
        gid: Group ID for the container user.
        username: Username for the container user (default: "droiduser").

    Returns:
        Path to the created passwd file.

    Note:
        Caller is responsible for cleaning up the temporary file after use.
        The file is created in the system temp directory and will persist
        until explicitly deleted or system reboot.
    """
    # Create a minimal passwd file with the host user's UID
    # Format: username:x:uid:gid:gecos:home:shell
    passwd_content = f"{username}:x:{uid}:{gid}:Container User:/home/{username}:/bin/bash\n"

    # Create temporary file that won't be auto-deleted
    # mkstemp returns an open file descriptor which we must properly handle
    fd, passwd_path = tempfile.mkstemp(prefix="container_passwd_", suffix=".txt", text=True)
    try:
        # Write using the file descriptor returned by mkstemp to avoid fd leak
        os.write(fd, passwd_content.encode())
        os.close(fd)
    except Exception:
        # Ensure fd is closed on error to prevent fd leak
        try:
            os.close(fd)
        except OSError:
            pass  # fd might already be closed
        # Clean up temp file
        Path(passwd_path).unlink(missing_ok=True)
        raise

    return Path(passwd_path)


def create_container_group_file(gid: int, groupname: str = "droiduser") -> Path:
    """Create a minimal /etc/group file for the container group.

    This file is mounted read-only over /etc/group in the container. Currently creates
    only the container group entry, which works for the lw_coder_droid image.

    NOTE: If you need to run package installers inside the container, you may need to
    add system groups (root:x:0:, daemon:x:1:, _apt:x:42:, etc.) to support privilege
    dropping during package installation. See docs/historical/docker_test_debugging.md.

    Args:
        gid: Group ID for the container group.
        groupname: Group name for the container group (default: "droiduser").

    Returns:
        Path to the created group file.

    Note:
        Caller is responsible for cleaning up the temporary file after use.
        The file is created in the system temp directory and will persist
        until explicitly deleted or system reboot.
    """
    # Create a minimal group file with the host user's GID
    # Format: groupname:x:gid:
    group_content = f"{groupname}:x:{gid}:\n"

    # Create temporary file that won't be auto-deleted
    # mkstemp returns an open file descriptor which we must properly handle
    fd, group_path = tempfile.mkstemp(prefix="container_group_", suffix=".txt", text=True)
    try:
        # Write using the file descriptor returned by mkstemp to avoid fd leak
        os.write(fd, group_content.encode())
        os.close(fd)
    except Exception:
        # Ensure fd is closed on error to prevent fd leak
        try:
            os.close(fd)
        except OSError:
            pass  # fd might already be closed
        # Clean up temp file
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
        env_vars: Optional dictionary of environment variables to pass to container.
        extra_docker_args: Optional list of additional docker arguments.
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
    env_vars: dict[str, str] | None = None
    extra_docker_args: list[str] | None = None


@contextmanager
def droid_session_config(
    worktree_path: Path,
    repo_git_dir: Path,
    tasks_dir: Path,
    droids_dir: Path,
    auth_file: Path,
    settings_file: Path,
    prompt_file: Path,
    image_tag: str,
    worktree_name: str,
    command: str,
    container_uid: int,
    container_gid: int,
    container_home: str,
    host_factory_dir: Path,
    container_username: str = "droiduser",
    container_groupname: str = "droiduser",
    env_vars: dict[str, str] | None = None,
    extra_docker_args: list[str] | None = None,
) -> Iterator[DroidSessionConfig]:
    """Context manager that creates a DroidSessionConfig with automatic temp file cleanup.

    This manages the lifecycle of temporary passwd/group files, creating them on entry
    and cleaning them up on exit. This prevents callers from having to manage temp file
    cleanup manually, which is error-prone.

    Args:
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
        container_username: Username for container user (default: "droiduser").
        container_groupname: Group name for container group (default: "droiduser").
        env_vars: Optional dictionary of environment variables to pass to container.
        extra_docker_args: Optional list of additional docker arguments.

    Yields:
        DroidSessionConfig with all fields populated including temp files.

    Example:
        with droid_session_config(...) as config:
            cmd = build_docker_command(config)
            subprocess.run(cmd)
        # Temp files automatically cleaned up here
    """
    passwd_file = create_container_passwd_file(
        uid=container_uid, gid=container_gid, username=container_username
    )
    group_file = create_container_group_file(
        gid=container_gid, groupname=container_groupname
    )

    try:
        yield DroidSessionConfig(
            worktree_path=worktree_path,
            repo_git_dir=repo_git_dir,
            tasks_dir=tasks_dir,
            droids_dir=droids_dir,
            auth_file=auth_file,
            settings_file=settings_file,
            prompt_file=prompt_file,
            image_tag=image_tag,
            worktree_name=worktree_name,
            command=command,
            container_uid=container_uid,
            container_gid=container_gid,
            container_home=container_home,
            host_factory_dir=host_factory_dir,
            passwd_file=passwd_file,
            group_file=group_file,
            env_vars=env_vars,
            extra_docker_args=extra_docker_args,
        )
    finally:
        # Clean up temp files
        passwd_file.unlink(missing_ok=True)
        group_file.unlink(missing_ok=True)


@contextmanager
def patched_worktree_gitdir(
    worktree: Path, repo_git_dir: Path
) -> Iterator[str]:
    """Context manager that patches a worktree's .git file to point to container path.

    Git worktrees use BIDIRECTIONAL pointers that must stay in sync:
    - Forward pointer: worktree/.git file → points to .git/worktrees/<name>
    - Reverse pointer: .git/worktrees/<name>/gitdir → points back to worktree/.git

    When mounting worktrees in Docker, paths change (host /home/... → container /workspace).
    Git validates pointer consistency, so BOTH must be patched to container paths.

    Original formatting including newlines is preserved on restoration. During patching,
    whitespace around "gitdir:" may be normalized to standard format (single space after colon).
    Git's parser is whitespace-tolerant, but newlines must be preserved to avoid
    "fatal: not a git repository" errors.

    This is why tests/test_git_in_docker.py exists: to validate the full chain
    (worktree + pointer patching + Docker + git commands) works end-to-end.

    Args:
        worktree: Path to the worktree directory.
        repo_git_dir: Path to the repository's .git directory (for validation).

    Yields:
        The worktree name extracted from the original .git file.

    Raises:
        RuntimeError: If the .git file cannot be read or does not contain a gitdir pointer.
    """
    # Validate repo_git_dir
    if not repo_git_dir.exists() or not repo_git_dir.is_dir():
        raise RuntimeError(
            f"Invalid repo_git_dir: {repo_git_dir}. "
            f"Must be the repository's .git directory."
        )
    if not (repo_git_dir / "worktrees").exists():
        raise RuntimeError(
            f"Repository has no worktrees directory: {repo_git_dir / 'worktrees'}. "
            f"Ensure the repository has worktrees configured."
        )

    worktree_git_file = worktree / ".git"
    if not worktree_git_file.exists():
        raise RuntimeError(
            f"Worktree .git file not found at {worktree_git_file}"
        )

    # Read the current gitdir path (preserve exact formatting for restoration)
    original_gitdir = worktree_git_file.read_text()
    if not original_gitdir.strip().startswith("gitdir:"):
        raise RuntimeError(
            f"Worktree .git file does not contain a gitdir pointer: {original_gitdir.strip()}"
        )

    # Extract worktree name (e.g., "temp-20251007_142615_613903-6f72d984")
    # The original format is like: "gitdir: /path/to/repo/.git/worktrees/<name>"
    # Strip only for parsing, not for storage
    gitdir_path = original_gitdir.strip().split(":", 1)[1].strip()
    worktree_name = Path(gitdir_path).name

    # Validate worktree metadata directory exists
    worktree_metadata_dir = repo_git_dir / "worktrees" / worktree_name
    if not worktree_metadata_dir.exists():
        raise RuntimeError(
            f"Worktree metadata directory not found: {worktree_metadata_dir}\n"
            f"The worktree at {worktree} may be corrupted. "
            f"Run 'git worktree prune' to clean up broken worktrees."
        )

    # Patch the reverse pointer in the worktree metadata
    worktree_metadata_gitdir_file = worktree_metadata_dir / "gitdir"
    original_reverse_gitdir = None
    reverse_pointer_existed = worktree_metadata_gitdir_file.exists()
    if reverse_pointer_existed:
        original_reverse_gitdir = worktree_metadata_gitdir_file.read_text()

    # Write new gitdir pointing to container path
    container_gitdir = f"gitdir: /repo-git/worktrees/{worktree_name}\n"
    container_reverse_gitdir = "/workspace/.git\n"

    try:
        worktree_git_file.write_text(container_gitdir)
        worktree_metadata_gitdir_file.write_text(container_reverse_gitdir)
        yield worktree_name
    finally:
        # Restore original contents
        worktree_git_file.write_text(original_gitdir)
        if reverse_pointer_existed:
            worktree_metadata_gitdir_file.write_text(original_reverse_gitdir)
        else:
            # If reverse pointer didn't exist originally, remove it
            worktree_metadata_gitdir_file.unlink(missing_ok=True)


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
    if not config.auth_file.exists():
        raise RuntimeError(
            f"Auth file not found: {config.auth_file}\n"
            f"Docker will auto-create this path as a directory if missing, "
            f"causing authentication to fail silently in the container. "
            f"Ensure the auth file exists before launching the Docker session."
        )
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
    ]

    # Add environment variables if provided
    if config.env_vars:
        for key, value in config.env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

    # Add volume mounts
    cmd.extend([
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
    ])

    # Add extra Docker arguments if provided
    if config.extra_docker_args:
        cmd.extend(config.extra_docker_args)

    # Add image and command
    cmd.extend([
        config.image_tag,
        "bash", "-c", config.command,
    ])

    return cmd
