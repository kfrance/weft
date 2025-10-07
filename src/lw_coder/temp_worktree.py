"""Utilities for managing temporary detached HEAD worktrees."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


class TempWorktreeError(Exception):
    """Raised when temporary worktree operations fail."""


def create_temp_worktree(repo_root: Path) -> Path:
    """Create a temporary detached HEAD worktree.

    Args:
        repo_root: The root directory of the Git repository.

    Returns:
        Path to the created temporary worktree.

    Raises:
        TempWorktreeError: If worktree creation fails.
    """
    import uuid

    # Validate repo_root is safe and resolve to absolute path
    try:
        repo_root = repo_root.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise TempWorktreeError(
            f"Invalid repository root: {exc}"
        ) from exc

    # Add UUID to prevent race conditions
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_id = uuid.uuid4().hex[:8]
    worktree_path = repo_root / ".lw_coder" / "worktrees" / f"temp-{timestamp}-{unique_id}"

    # Validate worktree_path is within expected directory
    try:
        expected_parent = (repo_root / ".lw_coder" / "worktrees").resolve()
        worktree_path.resolve().relative_to(expected_parent)
    except ValueError as exc:
        raise TempWorktreeError(
            f"Worktree path would escape expected directory: {worktree_path}"
        ) from exc

    # Create parent directory if needed
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug("Creating temporary worktree at %s", worktree_path)

    try:
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "add", "--detach", str(worktree_path), "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise TempWorktreeError(
            f"Failed to create temporary worktree at {worktree_path}: {exc.stderr}"
        ) from exc

    logger.info("Created temporary worktree at %s", worktree_path)
    return worktree_path


def remove_temp_worktree(repo_root: Path, worktree_path: Path) -> None:
    """Remove a temporary worktree.

    Args:
        repo_root: The root directory of the Git repository.
        worktree_path: Path to the worktree to remove.

    Raises:
        TempWorktreeError: If worktree removal fails.
    """
    if not worktree_path.exists():
        logger.debug("Worktree %s does not exist, skipping removal", worktree_path)
        return

    logger.debug("Removing temporary worktree at %s", worktree_path)

    try:
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "remove", str(worktree_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info("Removed temporary worktree at %s", worktree_path)
    except subprocess.CalledProcessError as exc:
        # If regular removal fails, try with --force
        # This is expected for worktrees with modified files
        logger.warning(
            "Regular worktree removal failed (this is expected for modified worktrees): %s",
            exc.stderr.strip()
        )
        logger.debug("Attempting force removal of worktree at %s", worktree_path)
        try:
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree_path)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            logger.info("Forcefully removed temporary worktree at %s", worktree_path)
        except subprocess.CalledProcessError as force_exc:
            raise TempWorktreeError(
                f"Failed to remove temporary worktree at {worktree_path}: {force_exc.stderr}"
            ) from force_exc
