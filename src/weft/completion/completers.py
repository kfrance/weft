"""Completer functions for argcomplete integration.

This module provides completion functions for CLI arguments:
- Plan files (both IDs and full paths)
- Tool names (dynamically from ExecutorRegistry)
- Model names (dynamically from ClaudeCodeExecutor)
"""

from __future__ import annotations

from pathlib import Path

from ..executors import ClaudeCodeExecutor, ExecutorRegistry
from ..logging_config import get_logger
from .cache import get_active_plans

logger = get_logger(__name__)


def complete_plan_files(prefix: str, parsed_args, **kwargs) -> list[str]:
    """Complete plan file paths and plan IDs.

    Provides completions for:
    1. Plan IDs (e.g., "fix-" -> ["fix-subagent", "fix-bug"])
    2. Full paths (e.g., ".weft/tasks/fix-" -> [".weft/tasks/fix-subagent.md"])

    Only returns plans with status != "done".

    Args:
        prefix: Current input prefix being completed.
        parsed_args: Parsed arguments from argparse (unused).
        **kwargs: Additional argcomplete arguments (unused).

    Returns:
        List of completion candidates.
    """
    try:
        # Get active plan IDs from cache
        plan_ids = get_active_plans()

        completions = []

        # If prefix contains path separator, complete as path
        if "/" in prefix or "\\" in prefix:
            # Try to complete full paths
            try:
                from ..repo_utils import find_repo_root
                import os

                repo_root = find_repo_root()
                tasks_dir = repo_root / ".weft" / "tasks"

                # Add full path completions - need to handle both absolute and relative paths
                for plan_id in plan_ids:
                    # Generate both absolute and relative paths
                    full_path_abs = str(tasks_dir / f"{plan_id}.md")

                    # Try relative path from repo root
                    try:
                        full_path_rel = str((tasks_dir / f"{plan_id}.md").relative_to(repo_root))
                    except ValueError:
                        full_path_rel = full_path_abs

                    # Check both absolute and relative paths
                    if full_path_abs.startswith(prefix):
                        completions.append(full_path_abs)
                    elif full_path_rel.startswith(prefix):
                        completions.append(full_path_rel)

            except Exception:
                pass  # Fallback to ID-only completion

        # Always add plan ID completions
        for plan_id in plan_ids:
            if plan_id.startswith(prefix):
                completions.append(plan_id)

        return completions

    except Exception as exc:
        logger.debug("Error in complete_plan_files: %s", exc)
        return []


def complete_tools(prefix: str, parsed_args, **kwargs) -> list[str]:
    """Complete tool names from ExecutorRegistry.

    Args:
        prefix: Current input prefix being completed.
        parsed_args: Parsed arguments from argparse (unused).
        **kwargs: Additional argcomplete arguments (unused).

    Returns:
        List of available tool names.
    """
    try:
        tools = ExecutorRegistry.list_executors()
        return [tool for tool in tools if tool.startswith(prefix)]
    except Exception as exc:
        logger.debug("Error in complete_tools: %s", exc)
        return []


def complete_models(prefix: str, parsed_args, **kwargs) -> list[str]:
    """Complete model names for Claude Code CLI.

    Suppresses completions if --tool droid is specified (left-to-right parsing).

    Args:
        prefix: Current input prefix being completed.
        parsed_args: Parsed arguments from argparse.
        **kwargs: Additional argcomplete arguments (unused).

    Returns:
        List of available model names, or empty list if tool is droid.
    """
    try:
        # Check if tool is droid (suppress model completions)
        tool = getattr(parsed_args, "tool", None)
        if tool == "droid":
            return []

        # Return valid models from ClaudeCodeExecutor
        models = list(ClaudeCodeExecutor.VALID_MODELS)
        return [model for model in models if model.startswith(prefix)]

    except Exception as exc:
        logger.debug("Error in complete_models: %s", exc)
        return []


def complete_backup_plans(prefix: str, parsed_args, **kwargs) -> list[str]:
    """Complete backup plan IDs with status indicators.

    Provides completions for plan IDs from backup references in the format:
    - "plan-id (exists)" for plans with existing files
    - "plan-id (missing)" for plans without existing files
    - "plan-id (abandoned)" for abandoned plans (when --abandoned flag is set)

    Args:
        prefix: Current input prefix being completed.
        parsed_args: Parsed arguments from argparse.
        **kwargs: Additional argcomplete arguments (unused).

    Returns:
        List of backup plan IDs with status indicators.
    """
    try:
        from ..plan_backup import list_abandoned_plans, list_backups
        from ..repo_utils import find_repo_root

        repo_root = find_repo_root()

        # Check if --abandoned flag is set
        show_abandoned = getattr(parsed_args, "abandoned", False)

        completions = []

        if show_abandoned:
            # Show only abandoned plans
            abandoned = list_abandoned_plans(repo_root)
            for plan_id, timestamp, file_exists in abandoned:
                completion = f"{plan_id} (abandoned)"
                if completion.startswith(prefix):
                    completions.append(completion)
        else:
            # Show only active backups
            backups = list_backups(repo_root)
            for plan_id, timestamp, file_exists in backups:
                status = "exists" if file_exists else "missing"
                completion = f"{plan_id} ({status})"
                if completion.startswith(prefix):
                    completions.append(completion)

        return completions

    except Exception as exc:
        logger.debug("Error in complete_backup_plans: %s", exc)
        return []
