"""Cache synchronization utilities for DSPy cache in worktree environments.

Provides bidirectional rsync-based cache synchronization between
global ~/.lw_coder/dspy_cache/ and worktree-local cache directories.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


class CacheSyncError(Exception):
    """Raised when cache synchronization fails."""


def check_rsync_available() -> bool:
    """Check if rsync is available on the system.

    Returns:
        True if rsync is available, False otherwise.
    """
    try:
        subprocess.run(
            ["rsync", "--version"],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def sync_cache_to_worktree(
    source: Path,
    dest: Path,
) -> bool:
    """Sync global cache to worktree before command execution.

    Uses rsync -a --delete to mirror source to dest.
    Creates dest directory if it doesn't exist.

    Args:
        source: Source cache directory (e.g., ~/.lw_coder/dspy_cache)
        dest: Destination worktree cache directory

    Returns:
        True if sync succeeded, False if it failed or was skipped

    Note:
        Does not raise exceptions; logs warnings on failure.
        Command execution continues even if sync fails.
    """
    if not check_rsync_available():
        logger.warning(
            "rsync is not available. Cache sync disabled. "
            "Install rsync to enable DSPy cache synchronization."
        )
        return False

    if not source.exists():
        logger.debug("Source cache directory does not exist: %s", source)
        return True  # Nothing to sync, but not an error

    # Ensure destination directory exists
    dest.mkdir(parents=True, exist_ok=True)

    # Use rsync with trailing slashes to sync directory contents
    # -a: archive mode (preserves permissions, timestamps, etc.)
    # --delete: remove files in dest that don't exist in source
    try:
        result = subprocess.run(
            [
                "rsync",
                "-a",
                "--delete",
                f"{source}/",
                f"{dest}/",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            logger.warning(
                "Failed to sync cache to worktree: %s",
                result.stderr.strip() or f"rsync exited with code {result.returncode}",
            )
            return False

        logger.debug("Synced cache from %s to %s", source, dest)
        return True

    except Exception as exc:
        logger.warning("Cache sync to worktree failed: %s", exc)
        return False


def sync_cache_from_worktree(
    source: Path,
    dest: Path,
) -> bool:
    """Sync worktree cache back to global cache after execution.

    Uses rsync -a (no --delete) to preserve global cache entries.
    Only adds new entries, doesn't remove existing ones.

    Args:
        source: Source worktree cache directory
        dest: Destination global cache directory (e.g., ~/.lw_coder/dspy_cache)

    Returns:
        True if sync succeeded, False if it failed or was skipped

    Note:
        Does not raise exceptions; logs warnings on failure.
        Command execution continues even if sync fails.
    """
    if not check_rsync_available():
        logger.warning(
            "rsync is not available. Cache sync disabled. "
            "Install rsync to enable DSPy cache synchronization."
        )
        return False

    if not source.exists():
        logger.debug("Worktree cache directory does not exist: %s", source)
        return True  # Nothing to sync, but not an error

    # Ensure destination directory exists
    dest.mkdir(parents=True, exist_ok=True)

    # Use rsync without --delete to preserve existing files in dest
    # -a: archive mode (preserves permissions, timestamps, etc.)
    try:
        result = subprocess.run(
            [
                "rsync",
                "-a",
                f"{source}/",
                f"{dest}/",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            logger.warning(
                "Failed to sync cache from worktree: %s",
                result.stderr.strip() or f"rsync exited with code {result.returncode}",
            )
            return False

        logger.debug("Synced cache from %s to %s", source, dest)
        return True

    except Exception as exc:
        logger.warning("Cache sync from worktree failed: %s", exc)
        return False


def get_global_cache_dir() -> Path:
    """Get the global DSPy cache directory.

    Returns:
        Path to global cache directory (~/.lw_coder/dspy_cache)
    """
    return Path.home() / ".lw_coder" / "dspy_cache"


def get_worktree_cache_dir(worktree_path: Path) -> Path:
    """Get the worktree-local DSPy cache directory.

    Args:
        worktree_path: Path to the worktree root

    Returns:
        Path to worktree cache directory (worktree/.lw_coder/dspy_cache)
    """
    return worktree_path / ".lw_coder" / "dspy_cache"
