"""Run directory management for code command.

This module handles:
- Creating timestamped run directories
- Copying droid definitions (excluding plan-only droids)
- Pruning old run directories (30-day retention)
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from .host_runner import get_lw_coder_src_dir
from .logging_config import get_logger

logger = get_logger(__name__)

# Retention period for run directories (30 days)
RUN_RETENTION_DAYS = 30


class RunManagerError(Exception):
    """Raised when run directory operations fail."""

    pass


def create_run_directory(repo_root: Path, plan_id: str) -> Path:
    """Create a timestamped run directory for the given plan.

    Args:
        repo_root: Repository root directory
        plan_id: Plan identifier (used as subdirectory name)

    Returns:
        Path to the created run directory

    Raises:
        RunManagerError: If directory creation fails
    """
    # Create timestamp: YYYYMMDD_HHMMSS
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Build run directory path: .lw_coder/runs/<plan_id>/<timestamp>
    run_dir = repo_root / ".lw_coder" / "runs" / plan_id / timestamp

    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        # If directory exists (rare race condition), append microseconds
        timestamp_with_micro = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        run_dir = repo_root / ".lw_coder" / "runs" / plan_id / timestamp_with_micro
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except OSError as e:
            raise RunManagerError(
                f"Failed to create run directory {run_dir}: {e}"
            ) from e
    except OSError as e:
        raise RunManagerError(
            f"Failed to create run directory {run_dir}: {e}"
        ) from e

    logger.info("Created run directory: %s", run_dir)
    return run_dir


def copy_coding_droids(run_dir: Path) -> Path:
    """Copy coding droid definitions to the run directory.

    Copies droids from src/lw_coder/droids/ but excludes the plan/ subdirectory
    since those droids are plan-specific.

    Args:
        run_dir: Run directory where droids should be copied

    Returns:
        Path to the droids directory in the run directory

    Raises:
        RunManagerError: If copying fails
    """
    # Get source droids directory from lw_coder package
    src_dir = get_lw_coder_src_dir()
    source_droids_dir = src_dir / "droids"

    if not source_droids_dir.exists():
        raise RunManagerError(
            f"Source droids directory not found: {source_droids_dir}"
        )

    # Create destination droids directory
    dest_droids_dir = run_dir / "droids"
    dest_droids_dir.mkdir(parents=True, exist_ok=True)

    # Copy all .md files except those in plan/ subdirectory
    copied_count = 0
    for source_file in source_droids_dir.rglob("*.md"):
        # Skip files in plan/ subdirectory
        try:
            relative_path = source_file.relative_to(source_droids_dir)
            if relative_path.parts[0] == "plan":
                logger.debug("Skipping plan-specific droid: %s", source_file.name)
                continue
        except (ValueError, IndexError):
            continue

        # Copy file, preserving relative directory structure
        dest_file = dest_droids_dir / relative_path
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, dest_file)
        copied_count += 1
        logger.debug("Copied droid: %s", relative_path)

    logger.info("Copied %d coding droid(s) to %s", copied_count, dest_droids_dir)
    return dest_droids_dir


def prune_old_runs(repo_root: Path, active_run_dir: Path | None = None) -> int:
    """Remove run directories older than retention period.

    Args:
        repo_root: Repository root directory
        active_run_dir: Currently active run directory (will not be deleted)

    Returns:
        Number of directories pruned

    Raises:
        RunManagerError: If pruning encounters critical errors
    """
    runs_base = repo_root / ".lw_coder" / "runs"

    if not runs_base.exists():
        logger.debug("No runs directory to prune")
        return 0

    # Calculate cutoff time
    cutoff_time = time.time() - (RUN_RETENTION_DAYS * 24 * 60 * 60)
    pruned_count = 0
    errors = []

    # Iterate through plan directories
    for plan_dir in runs_base.iterdir():
        if not plan_dir.is_dir():
            continue

        # Iterate through timestamp directories
        for timestamp_dir in plan_dir.iterdir():
            if not timestamp_dir.is_dir():
                continue

            # Skip active run directory
            if active_run_dir and timestamp_dir.resolve() == active_run_dir.resolve():
                logger.debug("Skipping active run directory: %s", timestamp_dir)
                continue

            # Check directory age using modification time
            try:
                dir_mtime = timestamp_dir.stat().st_mtime
                if dir_mtime < cutoff_time:
                    # Directory is older than retention period
                    logger.debug("Pruning old run directory: %s", timestamp_dir)
                    shutil.rmtree(timestamp_dir)
                    pruned_count += 1
            except OSError as e:
                error_msg = f"Failed to prune {timestamp_dir}: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)
                continue

        # Remove empty plan directories
        try:
            if plan_dir.is_dir() and not any(plan_dir.iterdir()):
                plan_dir.rmdir()
                logger.debug("Removed empty plan directory: %s", plan_dir)
        except OSError as e:
            # Non-critical: just log and continue
            logger.debug("Could not remove plan directory %s: %s", plan_dir, e)

    if pruned_count > 0:
        logger.info("Pruned %d old run director%s", pruned_count, "y" if pruned_count == 1 else "ies")

    # If we encountered errors but still made progress, that's acceptable
    # Only raise if ALL operations failed
    if errors and pruned_count == 0:
        raise RunManagerError(
            f"Pruning failed: {'; '.join(errors)}"
        )

    return pruned_count
