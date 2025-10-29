"""Command-line interface for lw_coder."""

from __future__ import annotations

import sys
from typing import Sequence

from docopt import docopt

from .code_command import run_code_command
from .logging_config import configure_logging, get_logger
from .param_validation import ParameterValidationError, validate_tool_model_compatibility
from .plan_command import run_plan_command

logger = get_logger(__name__)

_USAGE = """\
Usage:
  lw_coder plan [<plan_path>] [--text <description>] [--tool <tool_name>] [--debug]
  lw_coder code <plan_path> [--tool <tool_name>] [--model <model>] [--debug]
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
    tool = parsed["--tool"]

    # Check if model was explicitly provided in command line
    # argv is None means called from main(), use sys.argv[1:]
    actual_argv = argv if argv is not None else sys.argv[1:]
    model_explicitly_provided = "--model" in actual_argv

    # Get the model value - either explicit or default
    model = parsed["--model"]

    # Validate tool/model parameter compatibility
    # Only validate model with droid if it was explicitly provided
    if tool == "droid" and model_explicitly_provided:
        logger.error("The --model parameter cannot be used with --tool droid. "
                     "Droid does not support model selection.")
        return 1

    # For droid, ignore the model parameter entirely
    if tool == "droid":
        model = None

    # Validate other combinations
    try:
        validate_tool_model_compatibility(tool, model)
    except ParameterValidationError as exc:
        logger.error("%s", exc)
        return 1

    return run_code_command(plan_path, tool=tool, model=model)


if __name__ == "__main__":  # pragma: no cover - exercised by manual invocation
    sys.exit(main())
