"""Eval command implementation.

Evaluates code changes using LLM judges, runs tests before/after via Claude
Code SDK, collects human feedback, and creates training data for DSPy
prompt optimization.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Optional

from .cache_sync import (
    check_rsync_available,
    get_global_cache_dir,
    get_worktree_cache_dir,
    sync_cache_from_worktree,
    sync_cache_to_worktree,
)
from .feedback_collector import FeedbackCollectionError, collect_human_feedback
from .fingerprint import compute_eval_fingerprint
from .git_context import GitContextError, gather_git_context
from .hooks import trigger_hook
from .judge_executor import JudgeExecutionError, JudgeResult, get_cache_dir, get_openrouter_api_key
from .judge_loader import JudgeLoaderError, discover_judges
from .judge_orchestrator import JudgeOrchestrationError, execute_judges_parallel
from .logging_config import get_logger
from .plan_resolver import PlanResolver
from .session_manager import SessionManagerError, create_session_directory
from .test_runner import TestRunnerError, run_after_tests, run_before_tests
from .training_data_exporter import TrainingDataExportError, create_training_data

logger = get_logger(__name__)


def format_judge_markdown(result: JudgeResult) -> str:
    """Format a judge result as human-readable markdown.

    Args:
        result: JudgeResult object

    Returns:
        Formatted markdown string
    """
    return f"""# Judge: {result.judge_name}

**Weight**: {result.weight:.2f}
**Score**: {result.score:.2f} / 1.00

## Feedback

{result.feedback}
"""


def format_judge_results(results: list, plan_id: str, worktree_path: Path) -> str:
    """Format judge results for console output.

    Args:
        results: List of JudgeResult objects
        plan_id: Plan ID being evaluated
        worktree_path: Path to the worktree

    Returns:
        Formatted string for console output
    """
    lines = []
    lines.append("=" * 80)
    lines.append(f"Evaluation Results for: {plan_id}")
    lines.append(f"Worktree: {worktree_path}")
    lines.append("=" * 80)
    lines.append("")

    # Display each judge's results (scores only, not full feedback)
    for result in results:
        lines.append(f"  {result.judge_name}: {result.score:.2f}/1.00 (weight: {result.weight:.2f})")

    lines.append("")

    # Calculate weighted score
    total_weight = sum(r.weight for r in results)
    if total_weight > 0:
        weighted_score = sum(r.score * r.weight for r in results) / total_weight
        lines.append(f"Overall Weighted Score: {weighted_score:.2f} / 1.00")
        lines.append("=" * 80)

    return "\n".join(lines)


def save_judge_results(
    results: list[JudgeResult],
    eval_dir: Path,
) -> None:
    """Save per-judge results to JSON and markdown files.

    Args:
        results: List of JudgeResult objects
        eval_dir: Directory where judge files should be saved
    """
    eval_dir.mkdir(parents=True, exist_ok=True)

    for result in results:
        # Save JSON
        json_path = eval_dir / f"judge_{result.judge_name}.json"
        json_data = {
            "judge_name": result.judge_name,
            "weight": result.weight,
            "score": result.score,
            "feedback": result.feedback,
        }
        json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
        logger.debug("Saved judge JSON: %s", json_path)

        # Save markdown
        md_path = eval_dir / f"judge_{result.judge_name}.md"
        md_content = format_judge_markdown(result)
        md_path.write_text(md_content, encoding="utf-8")
        logger.debug("Saved judge markdown: %s", md_path)


def run_eval_command(
    plan_id: str,
    model: str = "sonnet",
    force: bool = False,
    no_hooks: bool = False,
) -> int:
    """Run the eval command to evaluate code changes.

    Orchestrates:
    1. Run LLM judges (skip if already done unless --force)
    2. Run before tests via Claude Code SDK (skip if already done unless --force)
    3. Run after tests via Claude Code SDK (skip if already done unless --force)
    4. Collect human feedback (skip if already done unless --force)
    5. Create training data (skip if already exists unless --force)

    Args:
        plan_id: Plan ID to evaluate
        model: Model to use for Claude Code SDK (default: sonnet)
        force: If True, re-run all steps and overwrite existing results
        no_hooks: If True, disable execution of configured hooks

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

        # Get repo root (assume we're in the repo)
        repo_root = Path.cwd()
        worktree_path = repo_root / ".weft" / "worktrees" / actual_plan_id

        logger.info("Evaluating plan: %s", actual_plan_id)
        logger.info("Worktree: %s", worktree_path)

        # Check if worktree exists
        if not worktree_path.exists():
            logger.error(
                "Worktree not found: %s\n"
                "Run 'weft code %s' first to create the worktree",
                worktree_path,
                actual_plan_id,
            )
            return 1

        # Create eval session directory
        try:
            eval_dir = create_session_directory(repo_root, actual_plan_id, "eval")
        except SessionManagerError as exc:
            logger.error("Failed to create eval session directory: %s", exc)
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

        # =====================================================================
        # Step 1: Run judges
        # =====================================================================
        logger.info("Running judges...")

        # Discover judges
        judges_dir = Path(".weft/judges")
        try:
            discovered_judges = discover_judges(judges_dir)
        except JudgeLoaderError as exc:
            logger.error("Failed to load judges: %s", exc)
            return 1

        if not discovered_judges:
            logger.error("No judges found in %s", judges_dir)
            return 1

        logger.info("Loaded %d judge(s)", len(discovered_judges))

        # Compute eval fingerprint from discovered judges
        eval_fingerprint = compute_eval_fingerprint(discovered_judges)
        logger.debug("Eval fingerprint: %s", eval_fingerprint)

        # Check which judge outputs already exist
        discovered_names = {j.name for j in discovered_judges}
        existing_outputs = {
            p.stem.replace("judge_", "") for p in eval_dir.glob("judge_*.json")
        }

        # Delete outputs for removed judges
        for stale_name in existing_outputs - discovered_names:
            stale_json = eval_dir / f"judge_{stale_name}.json"
            stale_md = eval_dir / f"judge_{stale_name}.md"
            stale_json.unlink(missing_ok=True)
            stale_md.unlink(missing_ok=True)
            logger.info("Removed stale judge output: %s", stale_name)

        # Determine which judges need to run
        if force:
            judges_to_run = discovered_judges
        else:
            judges_to_run = [j for j in discovered_judges if j.name not in existing_outputs]

        judge_results: list[JudgeResult] = []

        if not judges_to_run:
            logger.info("Skipping judges (already run, use --force to re-run)")
            # Load existing results
            for judge in discovered_judges:
                json_path = eval_dir / f"judge_{judge.name}.json"
                if json_path.exists():
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                    judge_results.append(
                        JudgeResult(
                            judge_name=data["judge_name"],
                            score=data["score"],
                            feedback=data["feedback"],
                            weight=data["weight"],
                        )
                    )
        else:
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

            # Execute judges
            try:
                judge_results = execute_judges_parallel(
                    judges=judges_to_run,
                    plan_content=plan_content,
                    git_changes=git_changes,
                    api_key=api_key,
                    cache_dir=cache_dir,
                )
            except JudgeOrchestrationError as exc:
                logger.error("Judge execution failed: %s", exc)
                return 1

            # Save judge results
            save_judge_results(judge_results, eval_dir)

            # If we only ran some judges, load the rest
            if len(judges_to_run) < len(discovered_judges):
                for judge in discovered_judges:
                    if judge.name not in {r.judge_name for r in judge_results}:
                        json_path = eval_dir / f"judge_{judge.name}.json"
                        if json_path.exists():
                            data = json.loads(json_path.read_text(encoding="utf-8"))
                            judge_results.append(
                                JudgeResult(
                                    judge_name=data["judge_name"],
                                    score=data["score"],
                                    feedback=data["feedback"],
                                    weight=data["weight"],
                                )
                            )

        # Display judge scores
        for result in judge_results:
            logger.info("  %s: %.2f/1.00", result.judge_name, result.score)

        # =====================================================================
        # Step 2: Run before tests
        # =====================================================================
        logger.info("Running before tests...")

        test_results_before: Optional[dict] = None
        before_results_path = eval_dir / "test_results_before.json"

        if before_results_path.exists() and not force:
            logger.info("Skipping before-tests (already run, use --force to re-run)")
            test_results_before = json.loads(before_results_path.read_text(encoding="utf-8"))
        else:
            try:
                test_results_before = run_before_tests(
                    plan_path=plan_path,
                    plan_id=actual_plan_id,
                    repo_root=repo_root,
                    output_dir=eval_dir,
                    model=model,
                )
                if test_results_before:
                    logger.info(
                        "Before: %d/%d passed",
                        test_results_before.get("passed_tests", 0),
                        test_results_before.get("total_tests", 0),
                    )
                else:
                    logger.info("Before tests skipped (no valid git_sha)")
            except TestRunnerError as exc:
                logger.warning("Before tests failed: %s", exc)
                # Continue - before tests are optional

        # =====================================================================
        # Step 3: Run after tests
        # =====================================================================
        logger.info("Running after tests...")

        test_results_after: Optional[dict] = None
        after_results_path = eval_dir / "test_results_after.json"

        if after_results_path.exists() and not force:
            logger.info("Skipping after-tests (already run, use --force to re-run)")
            test_results_after = json.loads(after_results_path.read_text(encoding="utf-8"))
        else:
            try:
                test_results_after = run_after_tests(
                    plan_path=plan_path,
                    plan_id=actual_plan_id,
                    repo_root=repo_root,
                    output_dir=eval_dir,
                    model=model,
                )
                logger.info(
                    "After: %d/%d passed",
                    test_results_after.get("passed_tests", 0),
                    test_results_after.get("total_tests", 0),
                )
            except TestRunnerError as exc:
                logger.error("After tests failed: %s", exc)
                return 1

        # =====================================================================
        # Step 4: Collect human feedback
        # =====================================================================
        logger.info("Collecting feedback...")

        feedback_path = eval_dir / "human_feedback.md"

        if feedback_path.exists() and not force:
            logger.info("Skipping feedback collection (already done, use --force to re-provide)")
        else:
            try:
                # Convert JudgeResult objects to dicts for feedback prompt
                judge_dicts = [
                    {
                        "judge_name": r.judge_name,
                        "score": r.score,
                        "weight": r.weight,
                        "feedback": r.feedback,
                    }
                    for r in judge_results
                ]

                result_path = collect_human_feedback(
                    plan_id=actual_plan_id,
                    repo_root=repo_root,
                    output_dir=eval_dir,
                    model=model,
                    judge_results=judge_dicts,
                    test_results_before=test_results_before,
                    test_results_after=test_results_after,
                )
                if result_path:
                    logger.info("Feedback collected successfully")
                else:
                    logger.warning("Feedback collection was cancelled by user")
                    # Don't fail - user may want to provide feedback later
            except FeedbackCollectionError as exc:
                logger.error("Feedback collection failed: %s", exc)
                return 1

        # =====================================================================
        # Step 5: Create training data
        # =====================================================================
        logger.info("Creating training data...")

        training_data_dir = repo_root / ".weft" / "training_data" / actual_plan_id

        # Check if training data needs to be created or updated
        should_create = False
        code_session_dir = repo_root / ".weft" / "sessions" / actual_plan_id / "code"
        if not training_data_dir.exists():
            should_create = True
        elif force:
            should_create = True
        else:
            # Check if code_trace.md is missing from training data but now available
            trace_in_training = training_data_dir / "code_trace.md"
            trace_in_session = code_session_dir / "trace.md"
            if not trace_in_training.exists() and trace_in_session.exists():
                logger.info("Code trace now available - updating training data...")
                should_create = True

        if not should_create:
            logger.info("Skipping training data creation (already exists, use --force to recreate)")
        else:
            # Check if feedback was collected
            if not feedback_path.exists():
                logger.warning(
                    "Training data creation skipped: human feedback not collected. "
                    "Run eval again with --force to provide feedback."
                )
            else:
                try:
                    if training_data_dir.exists():
                        shutil.rmtree(training_data_dir)
                    create_training_data(actual_plan_id, repo_root, eval_fingerprint)
                    logger.info("Training data created at: %s", training_data_dir)

                    # Trigger eval_complete hook after successful training data creation
                    # Note: trigger_hook handles exceptions internally, but we add
                    # defense-in-depth to ensure hook failures never fail eval
                    if not no_hooks:
                        try:
                            trigger_hook(
                                "eval_complete",
                                {
                                    "training_data_dir": training_data_dir,
                                    "worktree_path": worktree_path,
                                    "plan_path": plan_path,
                                    "plan_id": actual_plan_id,
                                    "repo_root": repo_root,
                                },
                            )
                        except Exception as hook_exc:
                            logger.warning("eval_complete hook failed: %s", hook_exc)
                except TrainingDataExportError as exc:
                    logger.error("Training data creation failed: %s", exc)
                    return 1

        # Sync cache from worktree back to global
        if rsync_available:
            logger.debug("Syncing DSPy cache from worktree back to global...")
            sync_cache_from_worktree(worktree_cache, global_cache)

        # Format and display summary
        output = format_judge_results(judge_results, actual_plan_id, worktree_path)
        print(output)

        logger.info("Evaluation completed successfully")
        return 0

    except Exception as exc:
        logger.error("Unexpected error during evaluation: %s", exc)
        logger.debug("Exception details:", exc_info=True)
        return 1
