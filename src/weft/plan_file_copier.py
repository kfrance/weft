"""File copying utilities for preserving plan output files from temporary worktrees.

This module provides functions to track and copy plan files generated during
plan command execution from a temporary worktree to the main repository,
resolving naming conflicts using Chrome-style numbering.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Set

from .logging_config import get_logger

logger = get_logger(__name__)


class PlanFileCopyError(Exception):
    """Raised when plan file copy operations fail critically."""


def get_existing_files(tasks_dir: Path) -> Set[str]:
    """Capture the names of files existing in the tasks directory before execution.

    Args:
        tasks_dir: Path to the .weft/tasks directory.

    Returns:
        Set of filenames that exist in the directory.
    """
    if not tasks_dir.exists():
        return set()

    existing = set()
    try:
        for file_path in tasks_dir.iterdir():
            if file_path.is_file():
                existing.add(file_path.name)
    except OSError as exc:
        logger.warning("Failed to read existing files from %s: %s", tasks_dir, exc)

    return existing


def find_new_files(tasks_dir: Path, existing_files: Set[str]) -> list[Path]:
    """Identify newly created files in the tasks directory.

    Args:
        tasks_dir: Path to the .weft/tasks directory.
        existing_files: Set of filenames that existed before execution.

    Returns:
        List of Path objects for newly created files.
    """
    if not tasks_dir.exists():
        return []

    new_files = []
    try:
        for file_path in tasks_dir.iterdir():
            if file_path.is_file() and file_path.name not in existing_files:
                new_files.append(file_path)
    except OSError as exc:
        logger.warning("Failed to read new files from %s: %s", tasks_dir, exc)

    return new_files


def generate_unique_filename(target_dir: Path, filename: str) -> str:
    """Generate a unique filename using Chrome-style numbering for conflicts.

    For example:
    - "my-plan.md" -> "my-plan (1).md"
    - "my-plan (1).md" -> "my-plan (2).md"

    Args:
        target_dir: Directory where the file will be placed.
        filename: Original filename to check for conflicts.

    Returns:
        Unique filename to use. If no conflict, returns original filename.
    """
    target_path = target_dir / filename

    # If no conflict, return the original filename
    if not target_path.exists():
        return filename

    # Split filename into stem and suffix
    # For "my-plan.md" -> stem="my-plan", suffix=".md"
    # For "my-plan (1).md" -> stem="my-plan (1)", suffix=".md"
    parts = filename.rsplit(".", 1)
    if len(parts) == 2:
        stem, ext = parts
        ext = f".{ext}"
    else:
        stem = filename
        ext = ""

    # Find the highest existing number in the format "stem (N)"
    highest_num = 0
    pattern = re.escape(stem) + r" \((\d+)\)" + re.escape(ext)

    try:
        for existing_file in target_dir.iterdir():
            if existing_file.is_file():
                match = re.fullmatch(pattern, existing_file.name)
                if match:
                    num = int(match.group(1))
                    highest_num = max(highest_num, num)
    except OSError:
        pass

    # Generate next number
    next_num = highest_num + 1
    return f"{stem} ({next_num}){ext}"


def copy_plan_files(
    source_dir: Path, dest_dir: Path, existing_files: Set[str]
) -> Dict[str, str]:
    """Copy newly created plan files from source to destination with conflict resolution.

    Args:
        source_dir: Source directory (worktree's .weft/tasks/).
        dest_dir: Destination directory (main repo's .weft/tasks/).
        existing_files: Set of filenames that existed before execution.

    Returns:
        Dictionary mapping original filenames to final filenames.

    Raises:
        PlanFileCopyError: If destination directory doesn't exist or has permission issues.
    """
    # Ensure destination directory exists
    if not dest_dir.exists():
        raise PlanFileCopyError(f"Destination directory does not exist: {dest_dir}")

    if not dest_dir.is_dir():
        raise PlanFileCopyError(f"Destination path is not a directory: {dest_dir}")

    file_mapping = {}

    # Find and copy new files
    new_files = find_new_files(source_dir, existing_files)

    for source_file in new_files:
        try:
            # Determine target filename
            target_filename = generate_unique_filename(dest_dir, source_file.name)
            target_path = dest_dir / target_filename

            # Copy the file
            target_path.write_bytes(source_file.read_bytes())

            # Record the mapping
            file_mapping[source_file.name] = target_filename

            # Log the copy operation
            if target_filename == source_file.name:
                logger.info(
                    "Saved plan to .weft/tasks/%s", target_filename
                )
            else:
                logger.info(
                    "Saved plan to .weft/tasks/%s (original name %s already existed)",
                    target_filename,
                    source_file.name,
                )

        except (OSError, IOError) as exc:
            logger.warning(
                "Failed to copy plan file %s: %s",
                source_file.name,
                exc,
            )

    return file_mapping
