"""Train command for generating improved prompt candidates.

This module orchestrates the training workflow:
1. Load training data from eval command results
2. Load current active prompts
3. Run DSPy prompt trainer to generate candidates
4. Save candidates to prompts/candidates/
"""

from __future__ import annotations


from .candidate_writer import CandidateWriteError, write_candidate
from .judge_executor import get_cache_dir
from .logging_config import get_logger
from .prompt_loader import PromptLoadingError, load_current_prompts_for_training
from .prompt_trainer import PromptTrainerError, run_prompt_trainer
from .repo_utils import RepoUtilsError, find_repo_root
from .training_data_loader import (
    TrainingDataLoadError,
    delete_trace_summaries,
    load_training_batch,
)

logger = get_logger(__name__)


class TrainCommandError(Exception):
    """Raised when the train command fails."""

    pass


def _validate_parameters(variant: str, batch_size: int, max_subagents: int) -> None:
    """Validate command parameters.

    Args:
        variant: Prompt variant (sonnet, opus, haiku)
        batch_size: Number of training samples per batch
        max_subagents: Maximum subagents to generate

    Raises:
        TrainCommandError: If parameters are invalid
    """
    valid_variants = {"sonnet", "opus", "haiku"}
    if variant not in valid_variants:
        raise TrainCommandError(
            f"Invalid variant: '{variant}'. Valid options: {', '.join(sorted(valid_variants))}"
        )

    if batch_size < 1:
        raise TrainCommandError(
            f"Invalid batch_size: {batch_size}. Must be at least 1."
        )
    if batch_size > 10:
        raise TrainCommandError(
            f"Invalid batch_size: {batch_size}. Maximum is 10 to limit context size."
        )

    if max_subagents < 1:
        raise TrainCommandError(
            f"Invalid max_subagents: {max_subagents}. Must be at least 1."
        )
    if max_subagents > 10:
        raise TrainCommandError(
            f"Invalid max_subagents: {max_subagents}. Maximum is 10."
        )


def run_train_command(
    variant: str,
    batch_size: int = 3,
    max_subagents: int = 5,
    model: str = "x-ai/grok-4.1-fast",
    regenerate_summaries: bool = False,
) -> int:
    """Run the train command to generate a candidate prompt set.

    Args:
        variant: Prompt variant to train (sonnet, opus, haiku)
        batch_size: Number of training samples per batch (default: 3)
        max_subagents: Maximum subagents to generate (default: 5)
        model: OpenRouter model tag for DSPy calls (default: x-ai/grok-4.1-fast)
        regenerate_summaries: Delete existing trace summaries before loading (default: False)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        # Validate parameters
        _validate_parameters(variant, batch_size, max_subagents)

        # Find repo root
        try:
            repo_root = find_repo_root()
        except RepoUtilsError as exc:
            logger.error("Failed to find repository root: %s", exc)
            return 1

        logger.info("Starting prompt training...")
        logger.info("  Variant: %s", variant)
        logger.info("  Batch size: %d", batch_size)
        logger.info("  Max subagents: %d", max_subagents)
        logger.info("  Model: %s", model)

        # Delete existing summaries if requested
        if regenerate_summaries:
            logger.info("Regenerating trace summaries...")
            deleted = delete_trace_summaries(repo_root)
            logger.info("  Deleted %d existing summar%s", deleted, "y" if deleted == 1 else "ies")

        # Load training batch with trace summarization
        logger.info("Loading training data...")
        try:
            training_samples = load_training_batch(repo_root, batch_size, model=model)
        except TrainingDataLoadError as exc:
            logger.error("Failed to load training data: %s", exc)
            return 1

        logger.info("Loaded %d training sample(s)", len(training_samples))
        for sample in training_samples:
            logger.info("  - %s", sample.plan_id)

        # Load current prompts for the specified variant
        logger.info("Loading current prompts...")
        try:
            current_prompts = load_current_prompts_for_training(
                repo_root, tool="claude-code-cli", model=variant
            )
        except PromptLoadingError as exc:
            logger.error("Failed to load current prompts: %s", exc)
            return 1

        logger.info(
            "Loaded current prompts: 1 main + %d subagent(s)",
            len(current_prompts.subagents),
        )

        # Get cache directory
        cache_dir = get_cache_dir()
        logger.debug("Using cache directory: %s", cache_dir)

        # Run prompt trainer
        logger.info("Running DSPy prompt trainer...")
        try:
            candidate, token_usage = run_prompt_trainer(
                training_samples=training_samples,
                current_prompts=current_prompts,
                max_subagents=max_subagents,
                model=model,
                cache_dir=cache_dir,
            )
        except PromptTrainerError as exc:
            logger.error("Prompt training failed: %s", exc)
            return 1

        # Write candidate to the variant directory
        logger.info("Writing candidate prompts...")
        try:
            candidate_dir = write_candidate(
                repo_root=repo_root,
                tool="claude-code-cli",
                model=variant,
                candidate=candidate,
            )
        except CandidateWriteError as exc:
            logger.error("Failed to write candidate: %s", exc)
            return 1

        # Report results
        print()
        print("=" * 72)
        print("Training Complete")
        print("=" * 72)
        print()
        print(f"Candidate saved to: {candidate_dir}")
        print(f"Generated {len(candidate.subagents)} subagent(s):")
        for subagent in candidate.subagents:
            print(f"  - {subagent.name}")
        print()
        print("Token Usage:")
        print(f"  Input tokens:     {token_usage['input_tokens']:,}")
        print(f"  Output tokens:    {token_usage['output_tokens']:,}")
        print(f"  Reasoning tokens: {token_usage.get('reasoning_tokens', 0):,}")
        print(f"  Total tokens:     {token_usage['total_tokens']:,}")
        print()
        print("Analysis Summary:")
        print("-" * 72)
        # Print first 500 chars of analysis summary
        summary = candidate.analysis_summary
        if len(summary) > 500:
            print(summary[:500] + "...")
            print(f"(Full analysis in {candidate_dir}/ANALYSIS.md)")
        else:
            print(summary)
        print("-" * 72)
        print()
        print("Next steps:")
        print("  1. Review the generated prompts in the candidate directory")
        print("  2. Test the candidate prompts manually")
        print("  3. If satisfactory, copy to prompts/active/ to use")
        print()

        return 0

    except TrainCommandError as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Training cancelled by user.")
        return 1
    except Exception as exc:
        logger.exception("Unexpected error during training: %s", exc)
        return 1
