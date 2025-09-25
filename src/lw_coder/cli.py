"""Command-line interface for lw_coder."""

from __future__ import annotations

import sys
from typing import Sequence

from docopt import docopt

from .plan_validator import PlanValidationError, load_plan_metadata

_USAGE = """\
Usage:
  lw_coder code <plan_path>
  lw_coder (-h | --help)

Options:
  -h --help     Show this screen.
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``lw_coder`` CLI."""

    parsed = docopt(_USAGE, argv=argv)
    plan_path = parsed["<plan_path>"]

    try:
        metadata = load_plan_metadata(plan_path)
    except PlanValidationError as exc:
        print(f"Plan validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Plan validation succeeded for {metadata.plan_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by manual invocation
    sys.exit(main())
