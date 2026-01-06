"""Implementation of the recover-plan command for restoring backed-up plans.

This command provides listing and recovery of plan files from git backup references.
Supports both active backups (refs/plan-backups/) and abandoned plans (refs/plan-abandoned/).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .logging_config import get_logger
from .plan_backup import (
    BackupExistsError,
    BackupNotFoundError,
    PlanBackupError,
    backup_exists_in_namespace,
    list_abandoned_plans,
    list_backups,
    move_abandoned_to_backup,
    recover_backup,
)
from .repo_utils import RepoUtilsError, find_repo_root

logger = get_logger(__name__)


class RecoverCommandError(Exception):
    """Raised when recover command operations fail."""


def run_recover_command(
    plan_id: str | None,
    force: bool = False,
    show_abandoned: bool = False,
    show_all: bool = False,
) -> int:
    """Execute the recover-plan command.

    Args:
        plan_id: Optional plan identifier to recover. If None, lists all backups.
        force: If True, overwrite existing plan files during recovery.
        show_abandoned: If True, show only abandoned plans (from refs/plan-abandoned/).
        show_all: If True, show both active backups and abandoned plans.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    try:
        # Find repository root
        repo_root = find_repo_root()
        logger.debug("Repository root: %s", repo_root)

        # If no plan_id provided, list all backups
        if plan_id is None:
            return _list_backups(repo_root, show_abandoned, show_all)

        # Strip status suffix from tab completion if present
        # e.g., "my-plan (exists)" -> "my-plan"
        plan_id = _strip_status_suffix(plan_id)

        # Recover the specified plan
        return _recover_plan(repo_root, plan_id, force, show_abandoned)

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
    if plan_id.endswith(" (abandoned)"):
        return plan_id[:-len(" (abandoned)")]
    return plan_id


def _list_backups(repo_root: Path, show_abandoned: bool, show_all: bool) -> int:
    """List all backed-up plans with metadata.

    Args:
        repo_root: Repository root directory.
        show_abandoned: If True, show only abandoned plans.
        show_all: If True, show both active and abandoned plans.

    Returns:
        Exit code (0 for success).
    """
    try:
        # Determine which backups to show
        active_backups = []
        abandoned_backups = []

        if show_all:
            active_backups = list_backups(repo_root)
            abandoned_backups = list_abandoned_plans(repo_root)
        elif show_abandoned:
            abandoned_backups = list_abandoned_plans(repo_root)
        else:
            active_backups = list_backups(repo_root)

        total_count = len(active_backups) + len(abandoned_backups)

        if total_count == 0:
            if show_abandoned:
                print("No abandoned plans found.")
                print("\nPlans are moved to abandoned when you run 'weft abandon'.")
            elif show_all:
                print("No backed-up or abandoned plans found.")
            else:
                print("No backed-up plans found.")
                print("\nBackups are created automatically when you run 'weft plan'")
                print("and deleted when you run 'weft finalize'.")
            return 0

        # Display header
        if show_all:
            print(f"Found {len(active_backups)} backed-up plan(s) and {len(abandoned_backups)} abandoned plan(s):\n")
        elif show_abandoned:
            print(f"Found {len(abandoned_backups)} abandoned plan(s):\n")
        else:
            print(f"Found {len(active_backups)} backed-up plan(s):\n")

        # Calculate column widths
        all_backups = active_backups + abandoned_backups
        id_width = max(len(plan_id) for plan_id, _, _ in all_backups) if all_backups else 7
        id_width = max(id_width, len("Plan ID"))

        # Header
        if show_all:
            print(f"{'Plan ID':<{id_width}}  {'Backup Date':<20}  {'Status':<10}  {'Type'}")
            print("-" * (id_width + 20 + 10 + 12 + 6))
        else:
            print(f"{'Plan ID':<{id_width}}  {'Backup Date':<20}  {'Status'}")
            print("-" * (id_width + 20 + 10 + 4))

        # Display active backups
        if active_backups and (show_all or not show_abandoned):
            for plan_id, timestamp, file_exists in active_backups:
                date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                status = "exists" if file_exists else "missing"
                if show_all:
                    print(f"{plan_id:<{id_width}}  {date_str:<20}  {status:<10}  active")
                else:
                    print(f"{plan_id:<{id_width}}  {date_str:<20}  {status}")

        # Display abandoned backups
        if abandoned_backups:
            for plan_id, timestamp, file_exists in abandoned_backups:
                date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
                status = "exists" if file_exists else "missing"
                if show_all:
                    print(f"{plan_id:<{id_width}}  {date_str:<20}  {status:<10}  abandoned")
                else:
                    print(f"{plan_id:<{id_width}}  {date_str:<20}  {status}")
                # Show abandonment reason if available (only when not showing all)
                if not show_all:
                    reason = parse_abandoned_log(repo_root, plan_id)
                    if reason:
                        # Indent reason lines for readability
                        reason_preview = reason.split("\n")[0][:60]
                        if len(reason) > 60 or "\n" in reason:
                            reason_preview += "..."
                        print(f"{'':>{id_width}}  Reason: {reason_preview}")

        # Display help text
        if show_abandoned:
            print("\nUse 'weft recover-plan --abandoned <plan_id>' to restore an abandoned plan.")
        elif show_all:
            print("\nUse 'weft recover-plan <plan_id>' for active backups.")
            print("Use 'weft recover-plan --abandoned <plan_id>' for abandoned plans.")
        else:
            print("\nUse 'weft recover-plan <plan_id>' to restore a plan.")

        return 0

    except PlanBackupError as exc:
        raise RecoverCommandError(f"Failed to list backups: {exc}") from exc


def _recover_plan(repo_root: Path, plan_id: str, force: bool, from_abandoned: bool) -> int:
    """Recover a specific plan from backup.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier to recover.
        force: If True, overwrite existing file.
        from_abandoned: If True, recover from abandoned namespace.

    Returns:
        Exit code (0 for success).
    """
    try:
        # Determine which namespace to use
        if from_abandoned:
            namespace = "plan-abandoned"
            # Check if it exists in abandoned namespace
            if not backup_exists_in_namespace(repo_root, plan_id, namespace):
                logger.error("No abandoned plan found for '%s'", plan_id)
                print(f"\nNo abandoned plan found for '{plan_id}'.")
                print("Tip: Use 'weft recover-plan --abandoned' to list available abandoned plans.")
                return 1
        else:
            namespace = "plan-backups"
            # Check both namespaces and provide helpful message
            if not backup_exists_in_namespace(repo_root, plan_id, namespace):
                # Check if it exists in abandoned namespace
                if backup_exists_in_namespace(repo_root, plan_id, "plan-abandoned"):
                    logger.error(
                        "Plan '%s' not found in active backups, but exists in abandoned plans",
                        plan_id,
                    )
                    print(f"\nPlan '{plan_id}' not found in active backups.")
                    print("It exists in abandoned plans. Use --abandoned flag to recover it:")
                    print(f"  weft recover-plan --abandoned {plan_id}")
                    return 1

        # Recover the plan file
        recovered_path = recover_backup(repo_root, plan_id, force, namespace)
        logger.info("Successfully recovered plan '%s'", plan_id)

        # If recovering from abandoned, move ref back to active namespace
        if from_abandoned:
            try:
                move_abandoned_to_backup(repo_root, plan_id)
                logger.info("Moved plan reference back to active backups")
            except PlanBackupError as exc:
                logger.warning("Failed to move reference back to active namespace: %s", exc)
                print(f"Warning: Plan file recovered, but failed to move reference: {exc}")

        print(f"Successfully recovered plan to: {recovered_path}")
        print(f"\nYou can now continue working with: weft code {plan_id}")
        return 0

    except BackupNotFoundError as exc:
        logger.error("%s", exc)
        if from_abandoned:
            print("\nTip: Use 'weft recover-plan --abandoned' to list available abandoned plans.")
        else:
            print("\nTip: Use 'weft recover-plan' to list available backups.")
        return 1

    except BackupExistsError as exc:
        logger.error("%s", exc)
        print("\nTip: Use --force to overwrite the existing file.")
        return 1

    except PlanBackupError as exc:
        raise RecoverCommandError(f"Failed to recover plan '{plan_id}': {exc}") from exc


def parse_abandoned_log(repo_root: Path, plan_id: str) -> str | None:
    """Parse the abandoned-plans.log file to find reason for a specific plan.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.

    Returns:
        Abandonment reason if found, None otherwise.
    """
    log_file = repo_root / ".weft" / "abandoned-plans.log"

    if not log_file.exists():
        return None

    try:
        content = log_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Find the entry for this plan_id
        in_entry = False
        reason_lines = []

        for line in lines:
            if line.startswith("## ") and plan_id in line:
                in_entry = True
                continue
            elif line.startswith("## ") and in_entry:
                # Found next entry, stop
                break
            elif in_entry and line.strip():
                reason_lines.append(line)

        if reason_lines:
            return "\n".join(reason_lines)
        return None

    except OSError:
        return None
