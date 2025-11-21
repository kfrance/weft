"""Implementation of the recover-plan command for restoring backed-up plans.

This command provides listing and recovery of plan files from git backup references.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .logging_config import get_logger
from .plan_backup import (
    BackupExistsError,
    BackupNotFoundError,
    PlanBackupError,
    list_backups,
    recover_backup,
)
from .repo_utils import RepoUtilsError, find_repo_root

logger = get_logger(__name__)


class RecoverCommandError(Exception):
    """Raised when recover command operations fail."""


def run_recover_command(plan_id: str | None, force: bool = False) -> int:
    """Execute the recover-plan command.

    Args:
        plan_id: Optional plan identifier to recover. If None, lists all backups.
        force: If True, overwrite existing plan files during recovery.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    try:
        # Find repository root
        repo_root = find_repo_root()
        logger.debug("Repository root: %s", repo_root)

        # If no plan_id provided, list all backups
        if plan_id is None:
            return _list_backups(repo_root)

        # Strip status suffix from tab completion if present
        # e.g., "my-plan (exists)" -> "my-plan"
        plan_id = _strip_status_suffix(plan_id)

        # Recover the specified plan
        return _recover_plan(repo_root, plan_id, force)

    except (RepoUtilsError, RecoverCommandError) as exc:
        logger.error("%s", exc)
        return 1


def _strip_status_suffix(plan_id: str) -> str:
    """Strip status suffix from plan_id if present.

    Tab completion provides plan IDs in the format "plan-id (exists)" or
    "plan-id (missing)". This function removes the suffix.

    Args:
        plan_id: Plan identifier potentially with status suffix.

    Returns:
        Clean plan identifier without suffix.
    """
    plan_id = plan_id.strip()
    if plan_id.endswith(" (exists)"):
        return plan_id[:-len(" (exists)")]
    if plan_id.endswith(" (missing)"):
        return plan_id[:-len(" (missing)")]
    return plan_id


def _list_backups(repo_root: Path) -> int:
    """List all backed-up plans with metadata.

    Args:
        repo_root: Repository root directory.

    Returns:
        Exit code (0 for success).
    """
    try:
        backups = list_backups(repo_root)

        if not backups:
            print("No backed-up plans found.")
            print("\nBackups are created automatically when you run 'lw_coder plan'")
            print("and deleted when you run 'lw_coder finalize'.")
            return 0

        print(f"Found {len(backups)} backed-up plan(s):\n")

        # Display backups in a table format
        # Column widths
        id_width = max(len(plan_id) for plan_id, _, _ in backups)
        id_width = max(id_width, len("Plan ID"))

        # Header
        print(f"{'Plan ID':<{id_width}}  {'Backup Date':<20}  {'Status'}")
        print("-" * (id_width + 20 + 10 + 4))

        # Rows
        for plan_id, timestamp, file_exists in backups:
            # Format timestamp
            date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

            # Status indicator
            status = "exists" if file_exists else "missing"

            print(f"{plan_id:<{id_width}}  {date_str:<20}  {status}")

        print(f"\nUse 'lw_coder recover-plan <plan_id>' to restore a plan.")

        return 0

    except PlanBackupError as exc:
        raise RecoverCommandError(f"Failed to list backups: {exc}") from exc


def _recover_plan(repo_root: Path, plan_id: str, force: bool) -> int:
    """Recover a specific plan from backup.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier to recover.
        force: If True, overwrite existing file.

    Returns:
        Exit code (0 for success).
    """
    try:
        recovered_path = recover_backup(repo_root, plan_id, force)
        logger.info("Successfully recovered plan '%s'", plan_id)
        print(f"Successfully recovered plan to: {recovered_path}")
        print(f"\nYou can now continue working with: lw_coder code {plan_id}")
        return 0

    except BackupNotFoundError as exc:
        logger.error("%s", exc)
        print(f"\nTip: Use 'lw_coder recover-plan' to list available backups.")
        return 1

    except BackupExistsError as exc:
        logger.error("%s", exc)
        print(f"\nTip: Use --force to overwrite the existing file.")
        return 1

    except PlanBackupError as exc:
        raise RecoverCommandError(f"Failed to recover plan '{plan_id}': {exc}") from exc
