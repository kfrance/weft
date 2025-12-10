"""Training data export for DSPy prompt optimization.

This module creates permanent training data from evaluation results.
Training data is stored in .lw_coder/training_data/<plan_id>/ and is
expected to be committed to git.

Training data includes:
- plan.md - copy of the plan
- code_trace.md - trace from code session
- test_results_before.json / test_results_after.json - test execution results
- human_feedback.md - human feedback on the implementation
- judge_<name>.json / judge_<name>.md - per-judge results
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from .logging_config import get_logger

logger = get_logger(__name__)


class TrainingDataExportError(Exception):
    """Raised when training data export fails."""

    pass


def copy_plan_file(plan_id: str, repo_root: Path, staging_dir: Path) -> None:
    """Copy plan file to staging directory.

    Args:
        plan_id: Plan identifier
        repo_root: Repository root directory
        staging_dir: Staging directory for atomic commit

    Raises:
        TrainingDataExportError: If plan file not found or copy fails
    """
    source = repo_root / ".lw_coder" / "tasks" / f"{plan_id}.md"
    dest = staging_dir / "plan.md"

    if not source.exists():
        raise TrainingDataExportError(f"Plan file not found: {source}")

    try:
        shutil.copy2(source, dest)
        logger.debug("Copied plan file to staging")
    except OSError as exc:
        raise TrainingDataExportError(f"Failed to copy plan file: {exc}") from exc


def copy_code_trace(
    plan_id: str, repo_root: Path, staging_dir: Path
) -> Optional[str]:
    """Copy code trace to staging directory.

    Args:
        plan_id: Plan identifier
        repo_root: Repository root directory
        staging_dir: Staging directory for atomic commit

    Returns:
        Warning message if trace not found, None otherwise

    Raises:
        TrainingDataExportError: If copy fails (but not if file is missing)
    """
    source = repo_root / ".lw_coder" / "sessions" / plan_id / "code" / "trace.md"
    dest = staging_dir / "code_trace.md"

    if not source.exists():
        return "Code trace not found. Training example will be incomplete."

    try:
        shutil.copy2(source, dest)
        logger.debug("Copied code trace to staging")
        return None
    except OSError as exc:
        raise TrainingDataExportError(f"Failed to copy code trace: {exc}") from exc


def copy_test_results(plan_id: str, repo_root: Path, staging_dir: Path) -> None:
    """Copy test results to staging directory.

    Args:
        plan_id: Plan identifier
        repo_root: Repository root directory
        staging_dir: Staging directory for atomic commit

    Raises:
        TrainingDataExportError: If after-tests not found or copy fails
    """
    eval_dir = repo_root / ".lw_coder" / "sessions" / plan_id / "eval"

    # After tests are required
    after_source = eval_dir / "test_results_after.json"
    if not after_source.exists():
        raise TrainingDataExportError(
            f"After-test results not found: {after_source}"
        )

    try:
        shutil.copy2(after_source, staging_dir / "test_results_after.json")
        logger.debug("Copied after-test results to staging")
    except OSError as exc:
        raise TrainingDataExportError(
            f"Failed to copy after-test results: {exc}"
        ) from exc

    # Before tests are optional
    before_source = eval_dir / "test_results_before.json"
    if before_source.exists():
        try:
            shutil.copy2(before_source, staging_dir / "test_results_before.json")
            logger.debug("Copied before-test results to staging")
        except OSError as exc:
            logger.warning("Failed to copy before-test results: %s", exc)


def copy_judge_results(plan_id: str, repo_root: Path, staging_dir: Path) -> None:
    """Copy judge results to staging directory.

    Args:
        plan_id: Plan identifier
        repo_root: Repository root directory
        staging_dir: Staging directory for atomic commit

    Raises:
        TrainingDataExportError: If no judge results found or copy fails
    """
    eval_dir = repo_root / ".lw_coder" / "sessions" / plan_id / "eval"

    # Find all judge result files
    judge_json_files = list(eval_dir.glob("judge_*.json"))
    judge_md_files = list(eval_dir.glob("judge_*.md"))

    if not judge_json_files:
        raise TrainingDataExportError(
            f"No judge result files found in: {eval_dir}"
        )

    # Copy JSON files
    for source in judge_json_files:
        try:
            shutil.copy2(source, staging_dir / source.name)
            logger.debug("Copied %s to staging", source.name)
        except OSError as exc:
            raise TrainingDataExportError(
                f"Failed to copy {source.name}: {exc}"
            ) from exc

    # Copy markdown files
    for source in judge_md_files:
        try:
            shutil.copy2(source, staging_dir / source.name)
            logger.debug("Copied %s to staging", source.name)
        except OSError as exc:
            raise TrainingDataExportError(
                f"Failed to copy {source.name}: {exc}"
            ) from exc


def copy_human_feedback(plan_id: str, repo_root: Path, staging_dir: Path) -> None:
    """Copy human feedback to staging directory.

    Args:
        plan_id: Plan identifier
        repo_root: Repository root directory
        staging_dir: Staging directory for atomic commit

    Raises:
        TrainingDataExportError: If feedback not found or copy fails
    """
    source = (
        repo_root / ".lw_coder" / "sessions" / plan_id / "eval" / "human_feedback.md"
    )
    dest = staging_dir / "human_feedback.md"

    if not source.exists():
        raise TrainingDataExportError(f"Human feedback not found: {source}")

    try:
        shutil.copy2(source, dest)
        logger.debug("Copied human feedback to staging")
    except OSError as exc:
        raise TrainingDataExportError(
            f"Failed to copy human feedback: {exc}"
        ) from exc


def validate_training_data(training_data_dir: Path) -> list[str]:
    """Validate that training data directory has required files.

    Args:
        training_data_dir: Path to training data directory

    Returns:
        List of warning messages (empty if all files present)
    """
    warnings = []

    required_files = [
        ("plan.md", True),
        ("code_trace.md", False),  # Optional, warn if missing
        ("test_results_after.json", True),
        ("test_results_before.json", False),  # Optional
        ("human_feedback.md", True),
    ]

    for filename, is_required in required_files:
        filepath = training_data_dir / filename
        if not filepath.exists():
            if is_required:
                warnings.append(f"Missing required file: {filename}")
            else:
                warnings.append(f"Missing optional file: {filename}")

    # Check for at least one judge file
    judge_files = list(training_data_dir.glob("judge_*.json"))
    if not judge_files:
        warnings.append("Missing required files: judge results (judge_*.json)")

    return warnings


def create_training_data(plan_id: str, repo_root: Path) -> Path:
    """Create permanent training data from evaluation results.

    Uses staging directory pattern for atomic operations:
    1. Collect all artifacts in temp directory
    2. Only copy to training_data/ if all steps succeed
    3. If any step fails, clean up temp directory and raise

    Args:
        plan_id: Plan identifier
        repo_root: Repository root directory

    Returns:
        Path to created training data directory

    Raises:
        TrainingDataExportError: If any required file is missing or copy fails
    """
    training_data_dir = repo_root / ".lw_coder" / "training_data" / plan_id

    # Check if training data already exists
    if training_data_dir.exists():
        logger.info("Training data already exists for %s", plan_id)
        return training_data_dir

    logger.info("Creating training data for %s...", plan_id)

    # Use staging directory for atomic commit
    with tempfile.TemporaryDirectory() as staging:
        staging_path = Path(staging)

        # Copy all files to staging
        copy_plan_file(plan_id, repo_root, staging_path)

        # Code trace is optional - warn if missing and ask user to confirm
        warning = copy_code_trace(plan_id, repo_root, staging_path)
        if warning:
            logger.warning(warning)
            response = input("Continue without code trace? (y/n): ").strip().lower()
            if response != "y":
                raise TrainingDataExportError(
                    "Training data creation cancelled by user (missing code trace)"
                )

        copy_test_results(plan_id, repo_root, staging_path)
        copy_judge_results(plan_id, repo_root, staging_path)
        copy_human_feedback(plan_id, repo_root, staging_path)

        # Validate staging directory
        validation_warnings = validate_training_data(staging_path)
        for warn in validation_warnings:
            if "required" in warn.lower():
                raise TrainingDataExportError(warn)
            logger.warning(warn)

        # Atomic commit: copy staging to training_data
        try:
            training_data_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staging_path, training_data_dir)
            logger.info("Training data created at: %s", training_data_dir)
        except OSError as exc:
            raise TrainingDataExportError(
                f"Failed to create training data directory: {exc}"
            ) from exc

    return training_data_dir
