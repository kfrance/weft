"""Judge command implementation.

Runs LLM judges against git changes in a worktree for quick feedback
during the coding phase, independent of the full eval pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .git_context import GitContextError, gather_git_context
from .judge_executor import JudgeExecutionError, JudgeResult, get_cache_dir, get_openrouter_api_key
from .judge_loader import JudgeLoaderError, discover_judges
from .judge_orchestrator import JudgeOrchestrationError, execute_judges_parallel
from .logging_config import get_logger
from .plan_resolver import PlanResolver
from .repo_utils import RepoUtilsError, find_repo_root
from .worktree_utils import WorktreeError, validate_worktree_exists

logger = get_logger(__name__)


def format_stdout(results: list[JudgeResult]) -> str:
    """Format judge results for stdout output.

    Args:
        results: List of JudgeResult objects

    Returns:
        Formatted string matching spec format:
        ```
        Judge Results:

        code-reuse (score: 0.85, weight: 0.4)
          The implementation properly reuses the existing validation
          utilities rather than reimplementing them...

        plan-compliance (score: 0.92, weight: 0.6)
          The changes align well with the plan requirements...

        Weighted average: 0.89
        ```
    """
    lines = ["Judge Results:", ""]

    for result in results:
        # Header line with score and weight
        lines.append(f"{result.judge_name} (score: {result.score:.2f}, weight: {result.weight})")

        # Indent feedback
        feedback_lines = result.feedback.strip().split("\n")
        for line in feedback_lines:
            lines.append(f"  {line}")

        lines.append("")  # Blank line between judges

    # Calculate weighted average
    total_weight = sum(r.weight for r in results)
    if total_weight > 0:
        weighted_avg = sum(r.score * r.weight for r in results) / total_weight
        lines.append(f"Weighted average: {weighted_avg:.2f}")

    return "\n".join(lines)


def format_markdown(results: list[JudgeResult], plan_id: str) -> str:
    """Format judge results as markdown for file output.

    Args:
        results: List of JudgeResult objects
        plan_id: Plan identifier

    Returns:
        Markdown formatted string
    """
    lines = [f"# Judge Results for {plan_id}", ""]

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Judge | Score | Weight |")
    lines.append("|-------|-------|--------|")

    for result in results:
        lines.append(f"| {result.judge_name} | {result.score:.2f} | {result.weight} |")

    # Calculate weighted average
    total_weight = sum(r.weight for r in results)
    if total_weight > 0:
        weighted_avg = sum(r.score * r.weight for r in results) / total_weight
        lines.append("")
        lines.append(f"**Weighted Average**: {weighted_avg:.2f}")

    lines.append("")

    # Detailed feedback for each judge
    lines.append("## Detailed Feedback")
    lines.append("")

    for result in results:
        lines.append(f"### {result.judge_name}")
        lines.append("")
        lines.append(f"**Score**: {result.score:.2f} / 1.00  ")
        lines.append(f"**Weight**: {result.weight}")
        lines.append("")
        lines.append(result.feedback.strip())
        lines.append("")

    return "\n".join(lines)


def run_judge_command(plan_id: str, output_dir: Optional[str] = None) -> int:
    """Run the judge command for quick feedback on code changes.

    Executes all judges against git changes in a worktree and displays
    results to stdout. Optionally saves results as markdown to a directory.

    Args:
        plan_id: Plan ID to evaluate
        output_dir: Optional directory path to save markdown results

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        # Find repo root
        try:
            repo_root = find_repo_root()
        except RepoUtilsError as exc:
            logger.error("Not in a git repository: %s", exc)
            return 1

        # Extract actual plan_id from path if provided
        if "/" in plan_id:
            actual_plan_id = Path(plan_id).stem
        else:
            actual_plan_id = plan_id

        # Validate worktree exists
        try:
            worktree_path = validate_worktree_exists(repo_root, actual_plan_id)
        except WorktreeError as exc:
            logger.error("%s", exc)
            return 1

        logger.info("Running judges for plan: %s", actual_plan_id)
        logger.info("Worktree: %s", worktree_path)

        # Resolve plan file (validates it exists)
        try:
            _plan_path = PlanResolver.resolve(plan_id)
        except FileNotFoundError as exc:
            logger.error("Plan not found: %s", exc)
            return 1

        # Discover judges from repo root
        judges_dir = repo_root / ".weft" / "judges"
        try:
            discovered_judges = discover_judges(judges_dir)
        except JudgeLoaderError as exc:
            logger.error("Failed to load judges: %s", exc)
            return 1

        if not discovered_judges:
            logger.error("No judges found in %s", judges_dir)
            return 1

        logger.info("Loaded %d judge(s)", len(discovered_judges))

        # Gather git context
        try:
            plan_content, git_changes = gather_git_context(worktree_path, plan_id=actual_plan_id)
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

        # Execute judges in parallel
        try:
            judge_results = execute_judges_parallel(
                judges=discovered_judges,
                plan_content=plan_content,
                git_changes=git_changes,
                api_key=api_key,
                cache_dir=cache_dir,
            )
        except JudgeOrchestrationError as exc:
            logger.error("Judge execution failed: %s", exc)
            return 1

        # Format and display results to stdout
        output = format_stdout(judge_results)
        print(output)

        # Save markdown if output directory specified
        if output_dir:
            output_path = Path(output_dir)
            try:
                output_path.mkdir(parents=True, exist_ok=True)
                md_file = output_path / f"judge-results-{actual_plan_id}.md"
                md_content = format_markdown(judge_results, actual_plan_id)
                md_file.write_text(md_content, encoding="utf-8")
                logger.info("Results saved to: %s", md_file)
            except (OSError, PermissionError) as exc:
                logger.error("Failed to save results to %s: %s", output_dir, exc)
                return 1

        return 0

    except Exception as exc:
        logger.error("Unexpected error during judge execution: %s", exc)
        logger.debug("Exception details:", exc_info=True)
        return 1
