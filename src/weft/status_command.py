"""Status command for displaying plan pipeline dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import humanize
from tabulate import tabulate

from .completion.cache import PlanInfo, get_all_plans
from .logging_config import get_logger
from .repo_utils import RepoUtilsError, find_repo_root

logger = get_logger(__name__)

# Status order for pipeline sorting (draft -> ... -> abandoned)
STATUS_ORDER = {
    "draft": 0,
    "ready": 1,
    "coding": 2,
    "implemented": 3,
    "done": 4,
    "abandoned": 5,
}


def _get_status_order(status: str) -> int:
    """Return sort order for status values.

    Unknown statuses are sorted after 'done' but before 'abandoned'.

    Args:
        status: Status string from plan frontmatter.

    Returns:
        Sort order integer.
    """
    return STATUS_ORDER.get(status.lower(), 4)  # Unknown sorts with 'done'


def _get_pipeline_state(repo_root: Path, plan_id: str) -> dict[str, bool]:
    """Check existence of worktree/session/training directories.

    Args:
        repo_root: Repository root path.
        plan_id: Plan ID to check artifacts for.

    Returns:
        Dictionary with keys 'worktree', 'coded', 'eval', 'training'
        indicating whether each artifact exists.
    """
    weft_dir = repo_root / ".weft"

    return {
        "worktree": (weft_dir / "worktrees" / plan_id).exists(),
        "coded": (weft_dir / "sessions" / plan_id / "code").exists(),
        "eval": (weft_dir / "sessions" / plan_id / "eval").exists(),
        "training": (weft_dir / "training_data" / plan_id).exists(),
    }


def _format_relative_time(mtime: float) -> str:
    """Format modification time as relative time string.

    Args:
        mtime: Unix timestamp of file modification time.

    Returns:
        Human-readable relative time string (e.g., "2 days ago").
    """
    dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return humanize.naturaltime(dt)


def _format_check(exists: bool) -> str:
    """Format boolean as checkmark or dash.

    Args:
        exists: Whether the artifact exists.

    Returns:
        Checkmark symbol if exists, dash otherwise.
    """
    return "\u2713" if exists else "-"


def _format_table(plans: list[PlanInfo], repo_root: Path) -> str:
    """Format plan data as table using tabulate.

    Args:
        plans: List of PlanInfo objects.
        repo_root: Repository root path for artifact checking.

    Returns:
        Formatted table string.
    """
    headers = ["Plan ID", "Status", "Worktree", "Coded", "Eval", "Training", "Modified"]

    rows = []
    for plan in plans:
        state = _get_pipeline_state(repo_root, plan.plan_id)
        row = [
            plan.plan_id,
            plan.status or "(unknown)",
            _format_check(state["worktree"]),
            _format_check(state["coded"]),
            _format_check(state["eval"]),
            _format_check(state["training"]),
            _format_relative_time(plan.mtime),
        ]
        rows.append(row)

    return tabulate(rows, headers=headers, tablefmt="simple")


def run_status_command(
    status_filter: str | None = None,
    sort_field: str | None = None,
    reverse: bool = False,
    show_all: bool = False,
) -> int:
    """Display dashboard view of all plans and their pipeline state.

    Args:
        status_filter: Comma-separated list of statuses to filter by.
        sort_field: Field to sort by ('plan_id', 'status', 'modified').
        reverse: Whether to reverse the sort order.
        show_all: If True, show all plans including done. By default, done plans
            are hidden unless explicitly requested via --status filter.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    try:
        repo_root = find_repo_root()
    except RepoUtilsError as exc:
        logger.error("Failed to find repository root: %s", exc)
        return 1

    # Get all plans using the completion cache
    tasks_dir = repo_root / ".weft" / "tasks"
    plans = get_all_plans(tasks_dir)

    # Filter by status
    if status_filter:
        # Explicit filter: show exactly what was requested
        allowed_statuses = {s.strip().lower() for s in status_filter.split(",")}
        plans = [p for p in plans if p.status.lower() in allowed_statuses]
    elif not show_all:
        # Default: hide "done" plans unless --all is specified
        plans = [p for p in plans if p.status.lower() != "done"]

    # Sort plans
    if sort_field == "plan_id":
        plans = sorted(plans, key=lambda p: p.plan_id.lower(), reverse=reverse)
    elif sort_field == "modified":
        plans = sorted(plans, key=lambda p: p.mtime, reverse=not reverse)
    elif sort_field == "status":
        # Sort by status only (pipeline order)
        plans = sorted(
            plans,
            key=lambda p: _get_status_order(p.status),
            reverse=reverse,
        )
    else:
        # Default (None): sort by status (pipeline order), then by modified (newest first)
        plans = sorted(
            plans,
            key=lambda p: (_get_status_order(p.status), -p.mtime),
            reverse=reverse,
        )

    # Format and print table
    table = _format_table(plans, repo_root)
    print(table)

    return 0
