"""Command-line interface for lw_coder."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

import argcomplete

# Note: Command modules (code_command, finalize_command, plan_command, recover_command)
# are lazy-loaded inside their respective dispatch blocks to avoid importing heavy
# dependencies (executors, sdk_runner, worktree_utils, etc.) during tab completion.
# This significantly improves tab completion performance.
from .completion.completers import complete_backup_plans, complete_models, complete_plan_files, complete_tools
from .completion_install import run_completion_install
from .init_command import run_init_command
from .logging_config import configure_logging, get_logger
from .param_validation import ParameterValidationError, validate_tool_model_compatibility
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
    plan_parser.add_argument(
        "--no-hooks",
        dest="no_hooks",
        action="store_true",
        help="Disable execution of configured hooks",
    )

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
    code_parser.add_argument(
        "--no-hooks",
        dest="no_hooks",
        action="store_true",
        help="Disable execution of configured hooks",
    )

    # Init command
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize lw_coder in current git repository",
    )
    init_parser.add_argument(
        "--force",
        dest="force",
        action="store_true",
        help="Reinitialize even if .lw_coder already exists",
    )
    init_parser.add_argument(
        "--yes",
        dest="yes",
        action="store_true",
        help="Skip interactive prompts (for CI/CD automation)",
    )

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

    # Recover-plan command
    recover_parser = subparsers.add_parser(
        "recover-plan",
        help="List or recover backed-up plans",
    )
    recover_plan_id_arg = recover_parser.add_argument(
        "plan_id",
        nargs="?",
        help="Plan ID to recover (omit to list all backups)",
    )
    recover_plan_id_arg.completer = complete_backup_plans
    recover_parser.add_argument(
        "--force",
        dest="force",
        action="store_true",
        help="Overwrite existing plan file if it exists",
    )
    recover_parser.add_argument(
        "--abandoned",
        dest="abandoned",
        action="store_true",
        help="Show only abandoned plans (from refs/plan-abandoned/)",
    )
    recover_parser.add_argument(
        "--all",
        dest="all",
        action="store_true",
        help="Show both active backups and abandoned plans",
    )

    # Abandon command
    abandon_parser = subparsers.add_parser(
        "abandon",
        help="Abandon a plan by cleaning up worktree, branch, and plan file",
    )
    abandon_plan_path_arg = abandon_parser.add_argument(
        "plan_path",
        help="Path to plan file or plan ID",
    )
    abandon_plan_path_arg.completer = complete_plan_files
    abandon_parser.add_argument(
        "--reason",
        dest="reason",
        help="Reason for abandoning the plan",
    )
    abandon_parser.add_argument(
        "--yes",
        dest="yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

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

    # Eval command
    eval_parser = subparsers.add_parser(
        "eval",
        help="Evaluate code changes using LLM judges",
    )
    eval_plan_id_arg = eval_parser.add_argument(
        "plan_id",
        help="Plan ID to evaluate",
    )
    eval_plan_id_arg.completer = complete_plan_files

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

    # Init command
    if args.command == "init":
        return run_init_command(force=args.force, yes=args.yes)

    # Plan command
    if args.command == "plan":
        # Lazy import to avoid loading heavy dependencies during tab completion
        from .plan_command import run_plan_command

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
        no_hooks = args.no_hooks
        return run_plan_command(plan_path, text_input, tool, no_hooks=no_hooks)

    # Finalize command
    if args.command == "finalize":
        # Lazy import to avoid loading heavy dependencies during tab completion
        from .finalize_command import run_finalize_command

        # Resolve plan_path (could be ID or path)
        try:
            plan_path = PlanResolver.resolve(args.plan_path)
        except FileNotFoundError as exc:
            logger.error("%s", exc)
            return 1
        tool = args.tool
        return run_finalize_command(plan_path, tool=tool)

    # Recover-plan command
    if args.command == "recover-plan":
        # Lazy import to avoid loading heavy dependencies during tab completion
        from .recover_command import run_recover_command

        plan_id = args.plan_id
        force = args.force
        show_abandoned = args.abandoned
        show_all = args.all
        return run_recover_command(plan_id, force, show_abandoned, show_all)

    # Abandon command
    if args.command == "abandon":
        # Lazy import to avoid loading heavy dependencies during tab completion
        from .abandon_command import run_abandon_command

        # Resolve plan_path (could be ID or path)
        try:
            plan_path = PlanResolver.resolve(args.plan_path)
        except FileNotFoundError:
            # Plan file may not exist, but other artifacts might
            # Pass the input directly for abandon to handle
            plan_path = args.plan_path

        reason = args.reason
        skip_confirmation = args.yes
        return run_abandon_command(plan_path, reason=reason, skip_confirmation=skip_confirmation)

    # Completion command
    if args.command == "completion":
        if args.completion_command == "install":
            return run_completion_install()
        else:
            # No sub-command specified, show help
            parser.parse_args(["completion", "--help"])
            return 1

    # Eval command
    if args.command == "eval":
        # Lazy import to avoid loading dspy (2+ seconds) during tab completion
        from .eval_command import run_eval_command

        plan_id = args.plan_id
        return run_eval_command(plan_id)

    # Code command
    if args.command == "code":
        # Lazy import to avoid loading heavy dependencies during tab completion
        from .code_command import run_code_command

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

        no_hooks = args.no_hooks
        return run_code_command(plan_path, tool=tool, model=model, no_hooks=no_hooks)

    # Should not reach here
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - exercised by manual invocation
    sys.exit(main())
