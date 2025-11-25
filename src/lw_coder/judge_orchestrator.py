"""Parallel judge execution orchestrator.

Executes multiple judges concurrently and collects results.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

from .judge_executor import JudgeExecutionError, JudgeResult, execute_judge
from .judge_loader import JudgeConfig
from .logging_config import get_logger

logger = get_logger(__name__)


class JudgeOrchestrationError(Exception):
    """Raised when judge orchestration fails."""

    pass


def execute_judges_parallel(
    judges: list[JudgeConfig],
    plan_content: str,
    git_changes: str,
    api_key: str,
    cache_dir: Path,
    max_workers: int | None = None,
) -> list[JudgeResult]:
    """Execute all judges in parallel.

    Uses ThreadPoolExecutor for concurrent execution. Fails fast on first error.

    Args:
        judges: List of judge configurations to execute
        plan_content: Full plan.md file content
        git_changes: Git diff, status, and changed file contents
        api_key: OpenRouter API key
        cache_dir: Directory for disk cache
        max_workers: Maximum number of concurrent workers (None = default)

    Returns:
        List of JudgeResult objects from all judges

    Raises:
        JudgeOrchestrationError: If any judge fails to execute
    """
    if not judges:
        raise JudgeOrchestrationError("No judges to execute")

    logger.info("Executing %d judge(s) in parallel", len(judges))

    results: list[JudgeResult] = []
    errors: list[str] = []

    # Use ThreadPoolExecutor for parallel execution
    # DSPy operations are I/O bound (API calls), so threads work well
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all judge executions
        future_to_judge = {
            executor.submit(
                execute_judge,
                judge,
                plan_content,
                git_changes,
                api_key,
                cache_dir,
            ): judge
            for judge in judges
        }

        # Collect results as they complete
        # Using as_completed() allows us to fail fast on first error
        for future in concurrent.futures.as_completed(future_to_judge):
            judge = future_to_judge[future]
            try:
                result = future.result()
                results.append(result)
                logger.debug("Judge '%s' completed successfully", judge.name)
            except JudgeExecutionError as e:
                # Fail fast: cancel remaining futures and raise error
                error_msg = f"Judge '{judge.name}' failed: {e}"
                logger.error(error_msg)

                # Cancel all pending futures before raising
                for future in future_to_judge.keys():
                    if not future.done():
                        future.cancel()

                raise JudgeOrchestrationError(error_msg) from e
            except Exception as e:
                # Unexpected error: also fail fast
                error_msg = f"Unexpected error executing judge '{judge.name}': {e}"
                logger.error(error_msg)

                # Cancel all pending futures before raising
                for future in future_to_judge.keys():
                    if not future.done():
                        future.cancel()

                raise JudgeOrchestrationError(error_msg) from e

    # Sort results by judge name for consistent output
    results.sort(key=lambda r: r.judge_name)

    logger.info("All %d judge(s) completed successfully", len(results))
    return results
