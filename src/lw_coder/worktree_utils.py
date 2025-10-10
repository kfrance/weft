"""Utilities for managing Git worktrees for plan execution."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .logging_config import get_logger
from .plan_validator import PlanMetadata

logger = get_logger(__name__)


class WorktreeError(Exception):
    """Raised when worktree operations fail."""


def get_branch_name_from_plan_id(plan_id: str) -> str:
    """Derive the Git branch name from the plan ID.

    Args:
        plan_id: The plan identifier.

    Returns:
        Branch name in the format "lw/task/<plan_id>".
    """
    return f"lw/task/{plan_id}"


def get_worktree_path(repo_root: Path, plan_id: str) -> Path:
    """Compute the worktree path for a given plan.

    Args:
        repo_root: The root directory of the Git repository.
        plan_id: The plan identifier.

    Returns:
        Path to the worktree directory (.lw_coder/worktrees/<plan_id>).

    Raises:
        WorktreeError: If plan_id contains path traversal sequences or would escape the repository.
    """
    # Validate plan_id doesn't contain path traversal sequences
    if ".." in plan_id:
        raise WorktreeError(
            f"Invalid plan_id contains path traversal sequence: {plan_id}"
        )

    worktree_path = repo_root / ".lw_coder" / "worktrees" / plan_id

    # Ensure resolved path is within repo_root/.lw_coder/worktrees
    # Use resolve() to handle any symbolic links or relative components
    try:
        expected_parent = (repo_root / ".lw_coder" / "worktrees").resolve()
        resolved_path = worktree_path.resolve()
        resolved_path.relative_to(expected_parent)
    except ValueError as exc:
        raise WorktreeError(
            f"Worktree path escapes repository worktrees directory: {worktree_path}"
        ) from exc

    return worktree_path


def is_git_worktree(path: Path, repo_root: Path) -> bool:
    """Check if a directory is a registered Git worktree.

    Args:
        path: Directory path to check.
        repo_root: The root directory of the Git repository.

    Returns:
        True if the path is a registered worktree, False otherwise.
    """
    if not path.exists():
        return False

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.debug("Failed to list worktrees: %s", exc.stderr)
        return False

    # Parse worktree list output to find matching path
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            worktree_path = Path(line[9:]).resolve()
            if worktree_path == path.resolve():
                return True

    return False


def get_branch_worktree(repo_root: Path, branch_name: str) -> Path | None:
    """Find the worktree path for a given branch, if any.

    Args:
        repo_root: The root directory of the Git repository.
        branch_name: The branch name to search for.

    Returns:
        Path to the worktree if the branch is checked out in a worktree, None otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "list", "--porcelain"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.debug("Failed to list worktrees: %s", exc.stderr)
        return None

    # Parse porcelain output: worktree path followed by branch line
    lines = result.stdout.splitlines()
    current_worktree = None
    for line in lines:
        if line.startswith("worktree "):
            current_worktree = Path(line[9:])
        elif line.startswith("branch "):
            branch = line[7:]
            # Handle both refs/heads/branch and branch formats
            if branch == f"refs/heads/{branch_name}" or branch == branch_name:
                return current_worktree

    return None


def get_branch_tip(repo_root: Path, branch_name: str) -> str | None:
    """Get the commit SHA at the tip of a branch.

    Args:
        repo_root: The root directory of the Git repository.
        branch_name: The branch name.

    Returns:
        Commit SHA if the branch exists, None otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", branch_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def branch_exists(repo_root: Path, branch_name: str) -> bool:
    """Check if a branch exists in the repository.

    Args:
        repo_root: The root directory of the Git repository.
        branch_name: The branch name to check.

    Returns:
        True if the branch exists, False otherwise.
    """
    return get_branch_tip(repo_root, branch_name) is not None


def ensure_worktree(metadata: PlanMetadata) -> Path:
    """Ensure a Git worktree exists for the given plan metadata.

    This function:
    1. Computes the worktree path from plan_id
    2. Derives the branch name from plan_id
    3. Checks if the path exists and validates it's a worktree
    4. Creates the branch from git_sha if needed
    5. Creates the worktree if it doesn't exist
    6. Validates the branch tip matches git_sha

    Args:
        metadata: Validated plan metadata.

    Returns:
        Path to the worktree directory.

    Raises:
        WorktreeError: If worktree setup fails.
    """
    repo_root = metadata.repo_root
    plan_id = metadata.plan_id
    git_sha = metadata.git_sha

    worktree_path = get_worktree_path(repo_root, plan_id)
    branch_name = get_branch_name_from_plan_id(plan_id)

    logger.debug("Ensuring worktree at %s for branch %s", worktree_path, branch_name)

    # Create parent directories if needed
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if path exists and is not a worktree
    if worktree_path.exists() and not is_git_worktree(worktree_path, repo_root):
        raise WorktreeError(
            f"Directory {worktree_path} exists but is not a registered Git worktree. "
            f"Please remove it or use a different plan_id."
        )

    # Check if branch is already checked out in a different worktree
    existing_worktree = get_branch_worktree(repo_root, branch_name)
    if existing_worktree and existing_worktree.resolve() != worktree_path.resolve():
        raise WorktreeError(
            f"Branch '{branch_name}' is already checked out in worktree at {existing_worktree}. "
            f"Cannot create worktree at {worktree_path}."
        )

    # If worktree already exists, validate branch tip
    if worktree_path.exists():
        current_tip = get_branch_tip(repo_root, branch_name)
        if current_tip and current_tip != git_sha:
            raise WorktreeError(
                f"Branch '{branch_name}' exists at {current_tip[:8]} but plan requires {git_sha[:8]}. "
                f"Cannot proceed with mismatched branch tip."
            )
        logger.info("Worktree already exists at %s", worktree_path)
        return worktree_path

    # Create branch if it doesn't exist
    if not branch_exists(repo_root, branch_name):
        logger.debug("Creating branch %s from %s", branch_name, git_sha)
        try:
            subprocess.run(
                ["git", "-C", str(repo_root), "branch", branch_name, git_sha],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise WorktreeError(
                f"Failed to create branch '{branch_name}' from {git_sha}: {exc.stderr}"
            ) from exc
    else:
        # Branch exists, validate tip matches
        current_tip = get_branch_tip(repo_root, branch_name)
        if current_tip != git_sha:
            raise WorktreeError(
                f"Branch '{branch_name}' exists at {current_tip[:8]} but plan requires {git_sha[:8]}. "
                f"Cannot proceed with mismatched branch tip."
            )

    # Create worktree
    logger.debug("Creating worktree at %s", worktree_path)
    try:
        subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "add", str(worktree_path), branch_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise WorktreeError(
            f"Failed to create worktree at {worktree_path}: {exc.stderr}"
        ) from exc

    logger.info("Created worktree at %s", worktree_path)
    return worktree_path
