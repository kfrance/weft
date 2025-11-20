"""Command-line interface for lw_coder."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

import argcomplete

from .code_command import run_code_command
from .completion.completers import complete_models, complete_plan_files, complete_tools
from .completion_install import run_completion_install
from .finalize_command import run_finalize_command
from .logging_config import configure_logging, get_logger
from .param_validation import ParameterValidationError, validate_tool_model_compatibility
from .plan_command import run_plan_command
from .plan_resolver import PlanResolver

logger = get_logger(__name__)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for lw_coder CLI.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="lw_coder",
        description="AI coding platform with self-optimizing multi-agent assistants",
    )

    # Global options
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug-level logging",
    )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Plan command
    plan_parser = subparsers.add_parser(
        "plan",
        help="Interactive plan development with Claude Code CLI or Droid",
    )
    plan_path_arg = plan_parser.add_argument(
        "plan_path",
        nargs="?",
        help="Path to markdown file with plan idea (optional)",
    )
    plan_path_arg.completer = complete_plan_files
    plan_parser.add_argument(
        "--text",
        dest="text",
        help="Inline plan idea text",
    )
    plan_tool_arg = plan_parser.add_argument(
        "--tool",
        dest="tool",
        default="claude-code",
        help="Coding tool to use (default: claude-code)",
    )
    plan_tool_arg.completer = complete_tools

    # Code command
    code_parser = subparsers.add_parser(
        "code",
        help="Validate plan and prepare worktree",
    )
    code_plan_path_arg = code_parser.add_argument(
        "plan_path",
        nargs="?",
        help="Path to plan file or plan ID",
    )
    code_plan_path_arg.completer = complete_plan_files
    code_parser.add_argument(
        "--text",
        dest="text",
        help="Inline text for quick fix (mutually exclusive with plan_path)",
    )
    code_tool_arg = code_parser.add_argument(
        "--tool",
        dest="tool",
        default="claude-code",
        help="Coding tool to use (default: claude-code)",
    )
    code_tool_arg.completer = complete_tools
    code_model_arg = code_parser.add_argument(
        "--model",
        dest="model",
        default="sonnet",
        help="Model variant for Claude Code CLI (default: sonnet)",
    )
    code_model_arg.completer = complete_models

    # Finalize command
    finalize_parser = subparsers.add_parser(
        "finalize",
        help="Commit, rebase, and merge completed plan",
    )
    finalize_plan_path_arg = finalize_parser.add_argument(
        "plan_path",
        help="Path to plan file or plan ID",
    )
    finalize_plan_path_arg.completer = complete_plan_files
    finalize_tool_arg = finalize_parser.add_argument(
        "--tool",
        dest="tool",
        default="claude-code",
        help="Coding tool to use (default: claude-code)",
    )
    finalize_tool_arg.completer = complete_tools

    # Completion command
    completion_parser = subparsers.add_parser(
        "completion",
        help="Manage bash tab completion",
    )
    completion_subparsers = completion_parser.add_subparsers(
        dest="completion_command",
        help="Completion sub-command",
    )
    completion_subparsers.add_parser(
        "install",
        help="Install bash completion for lw_coder",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``lw_coder`` CLI."""

    parser = create_parser()

    # Enable argcomplete for bash tab completion
    # argcomplete is a required dependency in pyproject.toml
    argcomplete.autocomplete(parser)

    # Parse arguments
    args = parser.parse_args(argv)

    # Configure logging before any other operations
    configure_logging(debug=args.debug)

    # Handle no command case
    if not args.command:
        parser.print_help()
        return 0

    # Plan command
    if args.command == "plan":
        # Resolve plan_path if provided (could be ID or path)
        if args.plan_path:
            try:
                plan_path = PlanResolver.resolve(args.plan_path)
            except FileNotFoundError:
                # For plan command, if file doesn't exist yet, just pass through
                # (user might be creating a new plan)
                logger.info(
                    "Plan file not found for '%s', treating as new plan creation",
                    args.plan_path
                )
                plan_path = args.plan_path
        else:
            plan_path = None
        text_input = args.text
        tool = args.tool
        return run_plan_command(plan_path, text_input, tool)

    # Finalize command
    if args.command == "finalize":
        # Resolve plan_path (could be ID or path)
        try:
            plan_path = PlanResolver.resolve(args.plan_path)
        except FileNotFoundError as exc:
            logger.error("%s", exc)
            return 1
        tool = args.tool
        return run_finalize_command(plan_path, tool=tool)

    # Completion command
    if args.command == "completion":
        if args.completion_command == "install":
            return run_completion_install()
        else:
            # No sub-command specified, show help
            parser.parse_args(["completion", "--help"])
            return 1

    # Code command
    if args.command == "code":
        # Check for mutual exclusivity of plan_path and --text
        if args.plan_path and args.text is not None:
            logger.error("Cannot specify both plan_path and --text. They are mutually exclusive.")
            return 1

        # Check that at least one is provided
        if not args.plan_path and args.text is None:
            logger.error("Must specify either plan_path or --text")
            return 1

        # Handle --text flag: create quick-fix plan
        if args.text is not None:
            from .quick_fix import QuickFixError, create_quick_fix_plan

            try:
                plan_path = create_quick_fix_plan(args.text)
                logger.info("Created quick-fix plan: %s", plan_path)
            except QuickFixError as exc:
                logger.error("Failed to create quick-fix plan: %s", exc)
                return 1
        else:
            # Resolve plan_path (could be ID or path)
            try:
                plan_path = PlanResolver.resolve(args.plan_path)
            except FileNotFoundError as exc:
                logger.error("%s", exc)
                return 1

        tool = args.tool

        # Check if model was explicitly provided in command line
        # argv is None means called from main(), use sys.argv[1:]
        actual_argv = argv if argv is not None else sys.argv[1:]
        model_explicitly_provided = "--model" in actual_argv

        # Get the model value - either explicit or default
        model = args.model

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

    # Should not reach here
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - exercised by manual invocation
    sys.exit(main())
