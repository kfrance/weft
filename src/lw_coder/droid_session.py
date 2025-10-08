"""Shared utilities for managing droid sessions in Docker containers.

This module provides:
- Git worktree .git pointer patching for Docker mounts
- Docker command construction with all required mounts
- lw_coder source directory discovery
"""

from __future__ import annotations

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
    mounts and settings. It also ensures the tasks directory exists.

    Args:
        config: Configuration object with all paths and settings.

    Returns:
        List of command arguments for subprocess.run.
    """
    # Ensure tasks directory exists
    config.tasks_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "docker", "run", "-it", "--rm",
        "--security-opt=no-new-privileges",
        "-v", f"{config.worktree_path}:/workspace",
        "-v", f"{config.repo_git_dir}:/repo-git:ro",
        "-v", f"{config.tasks_dir}:/output",
        "-v", f"{config.droids_dir}:/home/droiduser/.factory/droids:ro",
        "-v", f"{config.auth_file}:/home/droiduser/.factory/auth.json:ro",
        "-v", f"{config.settings_file}:/home/droiduser/.factory/settings.json:ro",
        "-v", f"{config.prompt_file}:/tmp/prompt.txt:ro",
        "-w", "/workspace",
        config.image_tag,
        "bash", "-c", config.command,
    ]

    return cmd
