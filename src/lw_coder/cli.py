"""Command-line interface for lw_coder."""

from __future__ import annotations

import sys
from typing import Sequence

from docopt import docopt

from .code_command import run_code_command
from .logging_config import configure_logging
from .plan_command import run_plan_command

_USAGE = """\
Usage:
  lw_coder plan [<plan_path>] [--text <description>] [--tool <tool_name>] [--debug]
  lw_coder code <plan_path> [--model <model>] [--debug]
  lw_coder (-h | --help)

Options:
  -h --help              Show this screen.
  --text <description>   Inline plan idea text.
  --tool <tool_name>     Coding tool to use [default: claude-code].
  --model <model>        Model variant for Claude Code CLI [default: sonnet].
  --debug                Enable debug-level logging.
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``lw_coder`` CLI."""

    parsed = docopt(_USAGE, argv=argv)
    debug = parsed["--debug"]
    is_plan_command = parsed["plan"]

    # Configure logging before any other operations
    configure_logging(debug=debug)

    if is_plan_command:
        # Plan command: interactive plan development with Claude Code CLI or Droid
        plan_path = parsed["<plan_path>"]
        text_input = parsed["--text"]
        tool = parsed["--tool"]
        return run_plan_command(plan_path, text_input, tool)

    # Code command: validate plan and prepare worktree
    plan_path = parsed["<plan_path>"]
    model = parsed["--model"]
    return run_code_command(plan_path, model=model)


if __name__ == "__main__":  # pragma: no cover - exercised by manual invocation
    sys.exit(main())
