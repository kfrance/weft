"""Training data loader for DSPy prompt optimization.

This module provides functions to discover and load training samples
from the .lw_coder/training_data/ directory for use in prompt training.

Supports lazy generation of compressed trace summaries via trace_summarizer.
When loading training samples, this module prioritizes code_trace_summary.md
over full code_trace.md files to reduce context size for prompt optimization.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .training_types import TrainingSample

logger = get_logger(__name__)


class TrainingDataLoadError(Exception):
    """Raised when training data loading fails."""

    pass


def _get_or_create_summary(
    sample_dir: Path,
    model: Optional[str] = None,
) -> str:
    """Get trace summary, generating it if needed.

    Handles lazy generation of trace summaries:
    1. If code_trace_summary.md exists and is newer than code_trace.md: use it
    2. If code_trace.md exists but no summary (or stale): generate summary
    3. If neither exists: return empty string

    Args:
        sample_dir: Path to the training sample directory
        model: OpenRouter model for summarization. If None, skips generation.

    Returns:
        Trace summary content, or empty string if no trace available

    Raises:
        TrainingDataLoadError: If summarization fails (when model provided)
    """
    # Lazy import to avoid circular dependency and loading DSPy unnecessarily
    from .trace_summarizer import (
        TraceSummarizationError,
        create_trace_summary,
        needs_regeneration,
    )

    trace_path = sample_dir / "code_trace.md"
    summary_path = sample_dir / "code_trace_summary.md"

    # Check if summary exists and is up to date
    if summary_path.exists():
        if not trace_path.exists():
            # Summary exists but no trace - use summary
            try:
                return summary_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Failed to read trace summary: %s", exc)
                return ""

        # Both exist - check if regeneration is needed
        if not needs_regeneration(trace_path, summary_path):
            # Summary is up to date
            logger.debug("Using existing trace summary for %s", sample_dir.name)
            try:
                return summary_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Failed to read trace summary: %s", exc)
                # Fall through to regenerate

    # Need to generate summary (or use full trace if no model)
    if not trace_path.exists():
        return ""

    if model is None:
        # No model provided - fall back to full trace
        logger.debug("No model provided, using full trace for %s", sample_dir.name)
        try:
            return trace_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read trace file: %s", exc)
            return ""

    # Generate summary
    logger.info("Generating trace summary for %s", sample_dir.name)
    try:
        summary_path = create_trace_summary(trace_path, model)
        return summary_path.read_text(encoding="utf-8")
    except TraceSummarizationError as exc:
        raise TrainingDataLoadError(
            f"Failed to generate trace summary for {sample_dir.name}: {exc}"
        ) from exc
    except OSError as exc:
        raise TrainingDataLoadError(
            f"Failed to read generated summary for {sample_dir.name}: {exc}"
        ) from exc


def discover_training_samples(repo_root: Path) -> list[str]:
    """Discover available training sample plan_ids.

    Args:
        repo_root: Repository root directory

    Returns:
        List of plan_ids that have training data directories

    Raises:
        TrainingDataLoadError: If training_data directory doesn't exist
    """
    training_data_dir = repo_root / ".lw_coder" / "training_data"

    if not training_data_dir.exists():
        raise TrainingDataLoadError(
            f"Training data directory not found: {training_data_dir}"
        )

    # Find all subdirectories (each is a plan_id)
    plan_ids = []
    for item in training_data_dir.iterdir():
        if item.is_dir():
            plan_ids.append(item.name)

    logger.debug("Discovered %d training sample(s)", len(plan_ids))
    return sorted(plan_ids)


def _format_judge_results(training_sample_dir: Path) -> str:
    """Format judge results into a readable string.

    Args:
        training_sample_dir: Path to the training sample directory

    Returns:
        Formatted string with all judge results
    """
    judge_files = list(training_sample_dir.glob("judge_*.json"))
    if not judge_files:
        return "No judge results available."

    results = []
    for judge_file in sorted(judge_files):
        try:
            with open(judge_file, "r", encoding="utf-8") as f:
                judge_data = json.load(f)

            judge_name = judge_data.get("judge_name", judge_file.stem)
            score = judge_data.get("score", "N/A")
            weight = judge_data.get("weight", "N/A")
            feedback = judge_data.get("feedback", "No feedback provided.")

            results.append(
                f"## Judge: {judge_name}\n"
                f"Score: {score} (weight: {weight})\n\n"
                f"{feedback}"
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read judge file %s: %s", judge_file, exc)
            continue

    return "\n\n---\n\n".join(results) if results else "Failed to parse judge results."


def load_training_sample(
    repo_root: Path,
    plan_id: str,
    model: Optional[str] = None,
) -> TrainingSample:
    """Load a complete training sample by plan_id.

    Args:
        repo_root: Repository root directory
        plan_id: Identifier for the training sample
        model: OpenRouter model for trace summarization (from train --model).
               If provided, enables lazy summary generation.

    Returns:
        TrainingSample with all loaded data

    Raises:
        TrainingDataLoadError: If required files are missing, cannot be read,
                               or if summarization fails when model is provided
    """
    training_sample_dir = repo_root / ".lw_coder" / "training_data" / plan_id

    if not training_sample_dir.exists():
        raise TrainingDataLoadError(
            f"Training sample directory not found: {training_sample_dir}"
        )

    # Required files
    required_files = {
        "human_feedback.md": "human_feedback",
        "test_results_after.json": "test_results_after",
    }

    # Optional files (excluding code_trace which is handled separately)
    optional_files = {
        "plan.md": "plan_content",
        "test_results_before.json": "test_results_before",
    }

    data: dict[str, str] = {"plan_id": plan_id}

    # Load required files
    for filename, field in required_files.items():
        filepath = training_sample_dir / filename
        if not filepath.exists():
            raise TrainingDataLoadError(
                f"Required file missing for {plan_id}: {filename}"
            )
        try:
            data[field] = filepath.read_text(encoding="utf-8")
        except OSError as exc:
            raise TrainingDataLoadError(
                f"Failed to read {filename} for {plan_id}: {exc}"
            ) from exc

    # Load optional files
    for filename, field in optional_files.items():
        filepath = training_sample_dir / filename
        if filepath.exists():
            try:
                data[field] = filepath.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Failed to read optional file %s: %s", filename, exc)
                data[field] = ""
        else:
            data[field] = ""

    # Load code trace with summary support
    # Prioritizes code_trace_summary.md over full trace
    data["code_trace"] = _get_or_create_summary(training_sample_dir, model)

    # Check for at least one judge result
    judge_files = list(training_sample_dir.glob("judge_*.json"))
    if not judge_files:
        raise TrainingDataLoadError(
            f"No judge results found for {plan_id}. "
            f"Expected judge_*.json files in {training_sample_dir}"
        )

    # Format judge results
    data["judge_results"] = _format_judge_results(training_sample_dir)

    logger.debug("Loaded training sample: %s", plan_id)
    return TrainingSample(**data)


def load_training_batch(
    repo_root: Path,
    batch_size: int = 3,
    model: Optional[str] = None,
) -> list[TrainingSample]:
    """Load a batch of training samples.

    Args:
        repo_root: Repository root directory
        batch_size: Maximum number of samples to load (default: 3)
        model: OpenRouter model for trace summarization (from train --model).
               If provided, enables lazy summary generation.

    Returns:
        List of TrainingSample objects

    Raises:
        TrainingDataLoadError: If no training samples are available
    """
    plan_ids = discover_training_samples(repo_root)

    if not plan_ids:
        raise TrainingDataLoadError(
            "No training samples found. Run 'lw_coder eval' first to generate training data."
        )

    # Limit to batch_size
    selected_ids = plan_ids[:batch_size]
    logger.info(
        "Loading %d training sample(s) from %d available",
        len(selected_ids),
        len(plan_ids),
    )

    samples = []
    for plan_id in selected_ids:
        try:
            sample = load_training_sample(repo_root, plan_id, model=model)
            samples.append(sample)
        except TrainingDataLoadError as exc:
            logger.warning("Skipping sample %s: %s", plan_id, exc)
            continue

    if not samples:
        raise TrainingDataLoadError(
            "Failed to load any training samples. Check training data integrity."
        )

    return samples


def delete_trace_summaries(repo_root: Path) -> int:
    """Delete all existing trace summaries for regeneration.

    Args:
        repo_root: Repository root directory

    Returns:
        Number of summaries deleted
    """
    training_data_dir = repo_root / ".lw_coder" / "training_data"

    if not training_data_dir.exists():
        return 0

    deleted = 0
    for sample_dir in training_data_dir.iterdir():
        if not sample_dir.is_dir():
            continue

        summary_path = sample_dir / "code_trace_summary.md"
        if summary_path.exists():
            try:
                summary_path.unlink()
                logger.debug("Deleted summary: %s", summary_path)
                deleted += 1
            except OSError as exc:
                logger.warning("Failed to delete summary %s: %s", summary_path, exc)

    if deleted > 0:
        logger.info("Deleted %d trace summar%s", deleted, "y" if deleted == 1 else "ies")

    return deleted
