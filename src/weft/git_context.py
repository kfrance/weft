"""Git context gathering for evaluation.

Gathers plan content and git changes from a worktree for judge evaluation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


class GitContextError(Exception):
    """Raised when git context gathering fails."""

    pass


def gather_git_context(worktree_path: Path, plan_id: str | None = None) -> tuple[str, str]:
    """Gather evaluation context from a worktree.

    Reads the plan.md file and collects git changes including:
    - Git status output
    - Git diff output (all changes)
    - Full contents of changed files

    Args:
        worktree_path: Path to the worktree directory
        plan_id: Optional plan ID for fallback lookup in .weft/tasks/

    Returns:
        Tuple of (plan_content, git_changes) where:
        - plan_content: Full text of plan.md file
        - git_changes: Combined git status, diff, and file contents

    Raises:
        GitContextError: If worktree doesn't exist, plan.md not found,
                        or git operations fail
    """
    if not worktree_path.exists():
        raise GitContextError(f"Worktree not found: {worktree_path}")

    if not worktree_path.is_dir():
        raise GitContextError(f"Worktree path is not a directory: {worktree_path}")

    # Read plan content - try worktree first, then fall back to tasks directory
    plan_file = worktree_path / "plan.md"
    plan_content = None

    if plan_file.exists():
        try:
            plan_content = plan_file.read_text()
            logger.debug("Read plan.md from worktree: %s", plan_file)
        except (PermissionError, OSError) as e:
            raise GitContextError(f"Cannot read plan.md: {e}") from e
    elif plan_id:
        # Fall back to .weft/tasks/<plan_id>.md in repo root
        # Worktree path is .weft/worktrees/<plan_id>, so repo root is 3 levels up
        repo_root = worktree_path.parent.parent.parent
        tasks_plan_file = repo_root / ".weft" / "tasks" / f"{plan_id}.md"
        if tasks_plan_file.exists():
            try:
                plan_content = tasks_plan_file.read_text()
                logger.debug("Read plan from tasks directory: %s", tasks_plan_file)
            except (PermissionError, OSError) as e:
                raise GitContextError(f"Cannot read plan from tasks: {e}") from e

    if plan_content is None:
        raise GitContextError(f"plan.md not found in worktree: {plan_file}")

    # Gather git changes
    try:
        git_changes = _gather_git_changes(worktree_path)
    except subprocess.CalledProcessError as e:
        raise GitContextError(f"Git command failed: {e}") from e
    except Exception as e:
        raise GitContextError(f"Failed to gather git changes: {e}") from e

    return plan_content, git_changes


def _gather_git_changes(worktree_path: Path) -> str:
    """Gather git changes from worktree.

    Args:
        worktree_path: Path to worktree directory

    Returns:
        Combined string with git status, diff, and changed file contents

    Raises:
        subprocess.CalledProcessError: If git commands fail
    """
    sections = []

    # Get git status
    status_result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        check=True,
    )
    status_output = status_result.stdout.strip()

    if status_output:
        sections.append("=== Git Status ===\n" + status_output)
        logger.debug("Captured git status with %d lines", len(status_output.splitlines()))
    else:
        sections.append("=== Git Status ===\n(no changes)")
        logger.debug("No changes in git status")

    # Get git diff for all changes (staged and unstaged)
    diff_result = subprocess.run(
        ["git", "diff", "HEAD"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
        check=True,
    )
    diff_output = diff_result.stdout.strip()

    if diff_output:
        sections.append("\n=== Git Diff ===\n" + diff_output)
        logger.debug("Captured git diff with %d lines", len(diff_output.splitlines()))
    else:
        sections.append("\n=== Git Diff ===\n(no changes)")
        logger.debug("No changes in git diff")

    # Get list of changed files from git status
    if status_output:
        changed_files = _parse_changed_files(status_output, worktree_path)
        if changed_files:
            sections.append("\n=== Changed File Contents ===")
            for file_path in changed_files:
                try:
                    content = file_path.read_text()
                    relative_path = file_path.relative_to(worktree_path)
                    sections.append(f"\n--- {relative_path} ---\n{content}")
                    logger.debug("Read changed file: %s", relative_path)
                except (PermissionError, OSError, UnicodeDecodeError) as e:
                    # Skip files that can't be read (binary, permissions, etc.)
                    relative_path = file_path.relative_to(worktree_path)
                    sections.append(f"\n--- {relative_path} ---\n(unable to read: {e})")
                    logger.warning("Could not read file %s: %s", relative_path, e)

    return "\n".join(sections)


def _parse_changed_files(status_output: str, worktree_path: Path) -> list[Path]:
    """Parse changed file paths from git status output.

    Args:
        status_output: Output from git status --porcelain
        worktree_path: Path to worktree directory

    Returns:
        List of absolute paths to changed files that exist
    """
    changed_files = []

    for line in status_output.splitlines():
        if not line.strip():
            continue

        # Git status --porcelain format: XY filename
        # XY is two-character status code, followed by space, then filename
        # Handle renamed files: "R  old -> new"
        if " -> " in line:
            # For renames, take the new filename
            parts = line.split(" -> ")
            filename = parts[1].strip()
        else:
            # Regular file: skip first 3 characters (XY + space)
            filename = line[3:].strip()

        file_path = worktree_path / filename
        if file_path.exists() and file_path.is_file():
            changed_files.append(file_path)

    return changed_files
