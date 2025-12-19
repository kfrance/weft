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

logger = get_logger(__name__)


class QuickFixError(Exception):
    """Raised when quick fix operations fail."""


def generate_quick_fix_id(tasks_dir: Path) -> str:
    """Generate a unique quick-fix plan ID.

    Generates IDs in the format: quick-fix-YYYY.MM-NNN where:
    - YYYY is the current year
    - MM is the current month (01-12)
    - NNN is a 3-digit counter (001-999) that resets monthly

    If counter would exceed 999, falls back to timestamp format:
    quick-fix-YYYY.MM.DD-HHMMSS

    Args:
        tasks_dir: Directory containing existing plan files.

    Returns:
        Generated plan ID string.

    Raises:
        QuickFixError: If ID generation fails.
    """
    try:
        now = datetime.now()
        year = now.year
        month = now.month

        # Pattern for current month's quick-fix files
        pattern = f"quick-fix-{year:04d}.{month:02d}-*.md"

        # Find all matching files
        existing_files = list(tasks_dir.glob(pattern))

        # Extract counter numbers from filenames
        counter_pattern = re.compile(rf"quick-fix-{year:04d}\.{month:02d}-(\d{{3}})\.md$")
        counters = []

        for file_path in existing_files:
            match = counter_pattern.match(file_path.name)
            if match:
                try:
                    counter = int(match.group(1))
                    counters.append(counter)
                except ValueError:
                    # Skip files with invalid counter format
                    continue

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

    # Generate unique plan ID
    try:
        plan_id = generate_quick_fix_id(tasks_dir)
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
