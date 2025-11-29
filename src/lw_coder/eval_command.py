"""Eval command implementation.

Evaluates code changes using LLM judges.
"""

from __future__ import annotations

from pathlib import Path

from .cache_sync import (
    check_rsync_available,
    get_global_cache_dir,
    get_worktree_cache_dir,
    sync_cache_from_worktree,
    sync_cache_to_worktree,
)
from .git_context import GitContextError, gather_git_context
from .judge_executor import JudgeExecutionError, get_cache_dir, get_openrouter_api_key
from .judge_loader import JudgeLoaderError, discover_judges
from .judge_orchestrator import JudgeOrchestrationError, execute_judges_parallel
from .logging_config import get_logger
from .plan_resolver import PlanResolver

logger = get_logger(__name__)


def format_judge_results(results: list, plan_id: str, worktree_path: Path) -> str:
    """Format judge results for console output.

    Args:
        results: List of JudgeResult objects
        plan_id: Plan ID being evaluated
        worktree_path: Path to the worktree

    Returns:
        Formatted string for console output
    """
    from .judge_executor import JudgeResult

    lines = []
    lines.append("=" * 80)
    lines.append(f"Evaluation Results for: {plan_id}")
    lines.append(f"Worktree: {worktree_path}")
    lines.append("=" * 80)
    lines.append("")

    # Display each judge's results
    for result in results:
        lines.append(f"Judge: {result.judge_name}")
        lines.append(f"Weight: {result.weight:.2f}")
        lines.append(f"Score: {result.score:.2f} / 1.00")
        lines.append("-" * 80)
        lines.append("Feedback:")
        lines.append(result.feedback)
        lines.append("=" * 80)
        lines.append("")

    # Calculate weighted score
    total_weight = sum(r.weight for r in results)
    if total_weight > 0:
        weighted_score = sum(r.score * r.weight for r in results) / total_weight
        lines.append(f"Overall Weighted Score: {weighted_score:.2f} / 1.00")
        lines.append("=" * 80)

    return "\n".join(lines)


def run_eval_command(plan_id: str) -> int:
    """Run the eval command to evaluate code changes.

    Args:
        plan_id: Plan ID to evaluate

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        # Resolve plan_id to plan file path
        try:
            plan_path = PlanResolver.resolve(plan_id)
        except FileNotFoundError as exc:
            logger.error("Plan not found: %s", exc)
            return 1

        # Determine worktree path from plan_id
        # Extract plan_id from path if it's a full path
        if "/" in plan_id:
            # Get basename without .md extension
            actual_plan_id = Path(plan_id).stem
        else:
            actual_plan_id = plan_id

        worktree_path = Path(f".lw_coder/worktrees/{actual_plan_id}")

        logger.info("Evaluating plan: %s", actual_plan_id)
        logger.info("Worktree: %s", worktree_path)

        # Check if worktree exists
        if not worktree_path.exists():
            logger.error(
                "Worktree not found: %s\n"
                "Run 'lw_coder code %s' first to create the worktree",
                worktree_path,
                actual_plan_id,
            )
            return 1

        # Sync cache to worktree before execution
        global_cache = get_global_cache_dir()
        worktree_cache = get_worktree_cache_dir(worktree_path)

        rsync_available = check_rsync_available()
        if not rsync_available:
            logger.warning(
                "rsync is not available. DSPy cache sync disabled. "
                "Install rsync to enable cache synchronization between worktrees."
            )
        else:
            logger.debug("Syncing DSPy cache to worktree...")
            sync_cache_to_worktree(global_cache, worktree_cache)

        # Discover judges
        judges_dir = Path(".lw_coder/judges")
        try:
            judges = discover_judges(judges_dir)
        except JudgeLoaderError as exc:
            logger.error("Failed to load judges: %s", exc)
            return 1

        logger.info("Loaded %d judge(s)", len(judges))

        # Gather git context
        try:
            plan_content, git_changes = gather_git_context(worktree_path)
        except GitContextError as exc:
            logger.error("Failed to gather git context: %s", exc)
            return 1

        logger.debug("Gathered plan content (%d chars)", len(plan_content))
        logger.debug("Gathered git changes (%d chars)", len(git_changes))

        # Get OpenRouter API key
        try:
            api_key = get_openrouter_api_key()
        except JudgeExecutionError as exc:
            logger.error("%s", exc)
            return 1

        # Get cache directory
        cache_dir = get_cache_dir()

        # Execute all judges in parallel
        try:
            results = execute_judges_parallel(
                judges=judges,
                plan_content=plan_content,
                git_changes=git_changes,
                api_key=api_key,
                cache_dir=cache_dir,
            )
        except JudgeOrchestrationError as exc:
            logger.error("Judge execution failed: %s", exc)
            return 1
        finally:
            # Sync cache from worktree back to global (even on failure)
            if rsync_available:
                logger.debug("Syncing DSPy cache from worktree back to global...")
                sync_cache_from_worktree(worktree_cache, global_cache)

        # Format and display results
        output = format_judge_results(results, actual_plan_id, worktree_path)
        print(output)

        logger.info("Evaluation completed successfully")
        return 0

    except Exception as exc:
        logger.error("Unexpected error during evaluation: %s", exc)
        logger.debug("Exception details:", exc_info=True)
        return 1
