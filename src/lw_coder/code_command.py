"""Implementation of the code command for plan validation and worktree preparation.

This module provides the core business logic for the `lw_coder code` command,
separating it from CLI argument parsing and dispatch.
"""

from __future__ import annotations

from pathlib import Path

from .logging_config import get_logger
from .plan_validator import PlanValidationError, load_plan_metadata
from .worktree_utils import WorktreeError, ensure_worktree

logger = get_logger(__name__)


def run_code_command(plan_path: Path | str) -> int:
    """Execute the code command: validate plan and prepare worktree.

    This function:
    1. Resolves the plan path and loads plan metadata.
    2. Returns exit code 1 if validation raises PlanValidationError.
    3. Calls ensure_worktree on success and logs the resulting path.
    4. Returns exit code 0 on success.
    5. Catches WorktreeError and returns exit code 1.

    Args:
        plan_path: Path to the plan file (string or Path object).

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    # Resolve plan path
    if isinstance(plan_path, str):
        plan_path = Path(plan_path)

    # Load and validate plan metadata
    try:
        metadata = load_plan_metadata(plan_path)
    except PlanValidationError as exc:
        logger.error("Plan validation failed: %s", exc)
        return 1

    logger.info("Plan validation succeeded for %s", metadata.plan_path)

    # Prepare worktree
    try:
        worktree_path = ensure_worktree(metadata)
        logger.info("Worktree prepared at: %s", worktree_path)
    except WorktreeError as exc:
        logger.error("Worktree preparation failed: %s", exc)
        return 1

    return 0
