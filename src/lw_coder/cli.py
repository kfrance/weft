"""Command-line interface for lw_coder."""

from __future__ import annotations

import sys
from typing import Sequence

from docopt import docopt

from .logging_config import configure_logging, get_logger
from .plan_validator import PlanValidationError, load_plan_metadata
from .worktree_utils import WorktreeError, ensure_worktree

_USAGE = """\
Usage:
  lw_coder plan <plan_path> [--debug]
  lw_coder code <plan_path> [--debug]
  lw_coder (-h | --help)

Options:
  -h --help     Show this screen.
  --debug       Enable debug-level logging.
"""

logger = get_logger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``lw_coder`` CLI."""

    parsed = docopt(_USAGE, argv=argv)
    plan_path = parsed["<plan_path>"]
    debug = parsed["--debug"]
    is_plan_command = parsed["plan"]
    is_code_command = parsed["code"]

    # Configure logging before any other operations
    configure_logging(debug=debug)

    try:
        metadata = load_plan_metadata(plan_path)
    except PlanValidationError as exc:
        logger.error("Plan validation failed: %s", exc)
        return 1

    logger.info("Plan validation succeeded for %s", metadata.plan_path)

    # Both plan and code commands prepare the worktree
    if is_plan_command or is_code_command:
        try:
            worktree_path = ensure_worktree(metadata)
            logger.info("Worktree prepared at: %s", worktree_path)
        except WorktreeError as exc:
            logger.error("Worktree preparation failed: %s", exc)
            return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by manual invocation
    sys.exit(main())
