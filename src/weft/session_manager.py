"""Session directory management for weft commands.

This module handles:
- Creating session directories for plan, code, and eval commands
- Organizing all artifacts by plan_id
- Pruning old session directories (30-day retention)

Directory structure:
.weft/sessions/<plan_id>/
├── plan/
│   └── trace.md                    # Plan session trace
├── code/                            # Code session
│   ├── trace.md
│   └── prompts/
└── eval/                            # Eval outputs
    ├── test_results_before.json
    ├── test_results_after.json
    ├── human_feedback.md
    ├── judge_<name>.json
    └── judge_<name>.md
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .logging_config import get_logger

logger = get_logger(__name__)

# Retention period for session directories (30 days)
SESSION_RETENTION_DAYS = 30

# Valid session types
SessionType = Literal["plan", "code", "eval"]


class SessionManagerError(Exception):
    """Raised when session directory operations fail."""

    pass


def create_session_directory(
    repo_root: Path, plan_id: str, session_type: SessionType
) -> Path:
    """Create session directory for plan, code, or eval.

    Creates a directory at .weft/sessions/<plan_id>/<session_type>/

    Args:
        repo_root: Repository root directory
        plan_id: Plan identifier
        session_type: One of 'plan', 'code', 'eval'

    Returns:
        Path to the created session directory

    Raises:
        SessionManagerError: If directory creation fails
    """
    if session_type not in ("plan", "code", "eval"):
        raise SessionManagerError(
            f"Invalid session type: {session_type}. Must be one of: plan, code, eval"
        )

    # Build session directory path: .weft/sessions/<plan_id>/<session_type>
    session_dir = repo_root / ".weft" / "sessions" / plan_id / session_type

    try:
        session_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SessionManagerError(
            f"Failed to create session directory {session_dir}: {e}"
        ) from e

    logger.info("Created session directory: %s", session_dir)
    return session_dir


def get_session_directory(
    repo_root: Path, plan_id: str, session_type: SessionType
) -> Path:
    """Get the path to a session directory (may not exist yet).

    Args:
        repo_root: Repository root directory
        plan_id: Plan identifier
        session_type: One of 'plan', 'code', 'eval'

    Returns:
        Path to the session directory
    """
    return repo_root / ".weft" / "sessions" / plan_id / session_type


def prune_old_sessions(
    repo_root: Path, active_session_dir: Path | None = None
) -> int:
    """Remove session directories older than retention period.

    Only prunes from .weft/sessions/, never from .weft/training_data/.

    Args:
        repo_root: Repository root directory
        active_session_dir: Currently active session directory (will not be deleted)

    Returns:
        Number of plan directories pruned (each plan dir may have multiple session types)

    Raises:
        SessionManagerError: If pruning encounters critical errors
    """
    sessions_base = repo_root / ".weft" / "sessions"

    if not sessions_base.exists():
        logger.debug("No sessions directory to prune")
        return 0

    # Calculate cutoff time
    cutoff_time = time.time() - (SESSION_RETENTION_DAYS * 24 * 60 * 60)
    pruned_count = 0
    errors = []

    # Iterate through plan directories
    for plan_dir in sessions_base.iterdir():
        if not plan_dir.is_dir():
            continue

        # Check directory age using modification time
        try:
            dir_mtime = plan_dir.stat().st_mtime

            # Skip if this is the active session's plan directory
            if active_session_dir:
                active_plan_dir = active_session_dir.parent
                if plan_dir.resolve() == active_plan_dir.resolve():
                    logger.debug("Skipping active session's plan directory: %s", plan_dir)
                    continue

            if dir_mtime < cutoff_time:
                # Directory is older than retention period
                logger.debug("Pruning old session directory: %s", plan_dir)
                shutil.rmtree(plan_dir)
                pruned_count += 1
        except OSError as e:
            error_msg = f"Failed to prune {plan_dir}: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)
            continue

    if pruned_count > 0:
        logger.info(
            "Pruned %d old session director%s",
            pruned_count,
            "y" if pruned_count == 1 else "ies",
        )

    # If we encountered errors but still made progress, that's acceptable
    # Only raise if ALL operations failed
    if errors and pruned_count == 0:
        raise SessionManagerError(f"Pruning failed: {'; '.join(errors)}")

    return pruned_count
