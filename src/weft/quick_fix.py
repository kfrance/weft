"""Quick fix mode for simple code changes.

This module provides utilities to create plan files for simple fixes
without requiring the full interactive planning process.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .logging_config import get_logger
from .plan_validator import PLACEHOLDER_SHA
from .repo_utils import RepoUtilsError, find_repo_root
from .worktree_utils import WorktreeError, list_branches_matching_pattern

logger = get_logger(__name__)


class QuickFixError(Exception):
    """Raised when quick fix operations fail."""


def extract_quick_fix_counter(name: str, year: int, month: int) -> int | None:
    """Extract the counter from a quick-fix filename or branch name.

    Works for both file names (quick-fix-YYYY.MM-NNN.md) and branch names
    (quick-fix-YYYY.MM-NNN). Silently skips malformed names by returning None.

    Args:
        name: The filename or branch name to extract counter from.
        year: The year to match (e.g., 2026).
        month: The month to match (1-12).

    Returns:
        The extracted counter as an integer, or None if the name doesn't match
        the expected pattern for the given year/month or has invalid format.
    """
    # Pattern matches both "quick-fix-YYYY.MM-NNN" and "quick-fix-YYYY.MM-NNN.md"
    pattern = re.compile(rf"^quick-fix-{year:04d}\.{month:02d}-(\d{{3}})(?:\.md)?$")
    match = pattern.match(name)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def generate_quick_fix_id(tasks_dir: Path, repo_root: Path | None = None) -> str:
    """Generate a unique quick-fix plan ID.

    Generates IDs in the format: quick-fix-YYYY.MM-NNN where:
    - YYYY is the current year
    - MM is the current month (01-12)
    - NNN is a 3-digit counter (001-999) that resets monthly

    The next counter is determined by finding the maximum counter from both:
    - Existing task files in tasks_dir (quick-fix-YYYY.MM-NNN.md)
    - Existing git branches (both local and remote tracking branches)

    If counter would exceed 999, falls back to timestamp format:
    quick-fix-YYYY.MM.DD-HHMMSS

    Args:
        tasks_dir: Directory containing existing plan files.
        repo_root: Optional repository root for checking existing branches.
            When provided, both local and remote tracking branches are checked.
            When None (default), only file checking is performed (backward
            compatible behavior).

    Returns:
        Generated plan ID string.

    Raises:
        QuickFixError: If ID generation fails.

    Notes:
        - Remote branches are checked via local tracking refs (e.g.,
          origin/quick-fix-2026.02-001). If remote refs are stale, the check
          may miss recently created branches on the remote.
        - If git commands fail, a warning is logged and the function falls
          back to file-only checking (graceful degradation).
    """
    try:
        now = datetime.now()
        year = now.year
        month = now.month

        counters: list[int] = []

        # Find all matching files
        file_pattern = f"quick-fix-{year:04d}.{month:02d}-*.md"
        existing_files = list(tasks_dir.glob(file_pattern))

        # Extract counter numbers from filenames using shared helper
        for file_path in existing_files:
            counter = extract_quick_fix_counter(file_path.name, year, month)
            if counter is not None:
                counters.append(counter)

        # Check git branches if repo_root is provided
        if repo_root is not None:
            branch_pattern = f"quick-fix-{year:04d}.{month:02d}-*"
            try:
                branches = list_branches_matching_pattern(repo_root, branch_pattern)
                for branch_name in branches:
                    counter = extract_quick_fix_counter(branch_name, year, month)
                    if counter is not None:
                        counters.append(counter)
            except WorktreeError as exc:
                logger.warning(
                    "Failed to check git branches for existing quick-fix IDs, "
                    "falling back to file-only checking: %s",
                    exc,
                )

        # Determine next counter
        if not counters:
            next_counter = 1
        else:
            next_counter = max(counters) + 1

        # Check for overflow
        if next_counter > 999:
            # Fallback to timestamp format
            timestamp = now.strftime("%d-%H%M%S")
            plan_id = f"quick-fix-{year:04d}.{month:02d}.{timestamp}"
            logger.warning(
                "Quick-fix counter exceeded 999 for %04d.%02d, using timestamp format: %s",
                year,
                month,
                plan_id,
            )
        else:
            # Use counter format
            plan_id = f"quick-fix-{year:04d}.{month:02d}-{next_counter:03d}"
            logger.debug(
                "Generated quick-fix ID: %s (counter: %d)",
                plan_id,
                next_counter,
            )

        return plan_id

    except Exception as exc:
        raise QuickFixError(f"Failed to generate quick-fix ID: {exc}") from exc


def create_quick_fix_plan(text: str) -> Path:
    """Create a minimal plan file for a quick fix.

    Args:
        text: User-provided description of the fix.

    Returns:
        Path to the created plan file.

    Raises:
        QuickFixError: If plan creation fails or text is invalid.
    """
    # Validate text input
    if not isinstance(text, str):
        raise QuickFixError("Text must be a string")

    stripped_text = text.strip()
    if not stripped_text:
        raise QuickFixError("Text cannot be empty or whitespace-only")

    try:
        # Find repository root
        repo_root = find_repo_root()
        logger.debug("Repository root: %s", repo_root)
    except RepoUtilsError as exc:
        raise QuickFixError(f"Failed to find repository root: {exc}") from exc

    # Determine tasks directory
    tasks_dir = repo_root / ".weft" / "tasks"

    # Ensure tasks directory exists
    try:
        tasks_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, IOError) as exc:
        raise QuickFixError(f"Failed to create tasks directory: {exc}") from exc

    # Generate unique plan ID (pass repo_root to also check git branches)
    try:
        plan_id = generate_quick_fix_id(tasks_dir, repo_root=repo_root)
    except QuickFixError:
        raise

    # Create plan file path
    plan_path = tasks_dir / f"{plan_id}.md"

    # Check if file already exists (should be extremely rare)
    if plan_path.exists():
        raise QuickFixError(
            f"Plan file already exists: {plan_path}. "
            "This should not happen - please try again."
        )

    # Create YAML front matter
    # Note: git_sha must be quoted to ensure YAML treats it as a string, not an integer
    front_matter = f"""---
plan_id: {plan_id}
git_sha: "{PLACEHOLDER_SHA}"
status: draft
evaluation_notes: []
---

{text}
"""

    # Write plan file
    try:
        plan_path.write_text(front_matter, encoding="utf-8")
        logger.info("Created quick-fix plan: %s", plan_path)
    except (OSError, IOError) as exc:
        raise QuickFixError(f"Failed to write plan file: {exc}") from exc

    return plan_path
