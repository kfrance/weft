"""Utilities for capturing and applying AI-generated patches.

This module provides functionality for:
- Capturing all changes made by the AI during SDK sessions as a git patch
- Saving patches to the session directory
- Applying patches to temporary worktrees during evaluation
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


class PatchError(Exception):
    """Base exception for patch operations."""


class PatchCaptureError(PatchError):
    """Raised when patch capture fails due to git command errors."""


class EmptyPatchError(PatchError):
    """Raised when SDK session produces no changes (empty patch)."""


class PatchApplicationError(PatchError):
    """Raised when patch fails to apply to a worktree."""


def capture_ai_patch(worktree_path: Path) -> str:
    """Capture all changes in a worktree as a git patch.

    This function:
    1. Stages all changes (including new files) with `git add -A`
    2. Generates a unified diff with `git diff --cached`
    3. Restores worktree to unstaged state with `git reset` (in finally block)

    Args:
        worktree_path: Path to the worktree containing AI changes.

    Returns:
        The patch content as a string.

    Raises:
        EmptyPatchError: If the AI made no changes (empty patch).
        PatchCaptureError: If git commands fail.
    """
    worktree_str = str(worktree_path)

    try:
        # Stage all changes including new files, modifications, and deletions
        result = subprocess.run(
            ["git", "-C", worktree_str, "add", "-A"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug("Staged all changes in worktree")

        # Generate the patch from staged changes
        result = subprocess.run(
            ["git", "-C", worktree_str, "diff", "--cached"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        patch_content = result.stdout

        if not patch_content.strip():
            raise EmptyPatchError(
                "SDK session produced no changes. Cannot proceed without AI modifications."
            )

        logger.debug("Captured patch (%d bytes)", len(patch_content))
        return patch_content

    except subprocess.CalledProcessError as exc:
        raise PatchCaptureError(
            f"Git command failed during patch capture: {exc.stderr}"
        ) from exc

    finally:
        # Always unstage changes to restore worktree state
        try:
            subprocess.run(
                ["git", "-C", worktree_str, "reset"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            logger.debug("Reset worktree to unstaged state")
        except subprocess.CalledProcessError as reset_exc:
            logger.warning("Failed to reset worktree after patch capture: %s", reset_exc.stderr)


def save_patch(patch_content: str, output_path: Path) -> Path:
    """Save patch content to a file.

    Args:
        patch_content: The patch content as a string.
        output_path: Path where the patch should be saved.

    Returns:
        The output path (for logging/chaining).

    Raises:
        PatchCaptureError: If writing the file fails.
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(patch_content, encoding="utf-8")
        logger.debug("Saved patch to %s", output_path)
        return output_path
    except OSError as exc:
        raise PatchCaptureError(f"Failed to save patch to {output_path}: {exc}") from exc


def apply_patch(patch_path: Path, worktree_path: Path) -> None:
    """Apply a patch to a worktree.

    Args:
        patch_path: Path to the patch file.
        worktree_path: Path to the worktree where the patch should be applied.

    Raises:
        PatchApplicationError: If patch application fails (conflicts, malformed patch, etc.).
    """
    if not patch_path.exists():
        raise PatchApplicationError(f"Patch file not found: {patch_path}")

    worktree_str = str(worktree_path)
    patch_str = str(patch_path)

    try:
        subprocess.run(
            ["git", "-C", worktree_str, "apply", patch_str],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.debug("Applied patch to %s", worktree_path)
    except subprocess.CalledProcessError as exc:
        raise PatchApplicationError(
            f"Failed to apply patch to {worktree_path}: {exc.stderr}"
        ) from exc
