"""DSPy-based judge execution framework.

Executes judges using DSPy with dynamically loaded instructions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import dspy

from .home_env import HomeEnvError, load_home_env
from .judge_loader import JudgeConfig
from .logging_config import get_logger

logger = get_logger(__name__)


class JudgeExecutionError(Exception):
    """Raised when judge execution fails."""

    pass


@dataclass
class JudgeResult:
    """Result from executing a judge.

    Attributes:
        judge_name: Name of the judge that produced this result
        score: Score from 0.0 to 1.0
        feedback: Detailed feedback and recommendations
        weight: Weight of this judge for weighted scoring
    """

    judge_name: str
    score: float
    feedback: str
    weight: float


class JudgeSignatureBase(dspy.Signature):
    """Base signature for judge evaluation.

    This base signature only defines input/output fields.
    Instructions are added dynamically via .with_instructions()
    """

    plan_content: str = dspy.InputField(desc="Full plan.md file content")
    git_changes: str = dspy.InputField(
        desc="Git diff, status, and changed file contents"
    )
    score: float = dspy.OutputField(desc="Score from 0.0 to 1.0")
    feedback: str = dspy.OutputField(desc="Detailed feedback and recommendations")


def configure_dspy_cache(cache_dir: Path) -> None:
    """Configure DSPy to use the specified cache directory.

    Args:
        cache_dir: Directory for disk cache

    Note:
        This configures DSPy's global cache settings. Must be called before
        any LM operations to ensure cache is used.
    """
    # Ensure cache directory exists
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Configure DSPy cache to use the specified directory
    dspy.configure_cache(
        enable_disk_cache=True,
        enable_memory_cache=True,
        disk_cache_dir=str(cache_dir),
    )

    logger.debug("Configured DSPy cache at %s", cache_dir)


def create_lm(model: str, api_key: str, cache_dir: Path) -> dspy.LM:
    """Create a DSPy LM instance for OpenRouter.

    Args:
        model: OpenRouter model tag (e.g., "x-ai/grok-4.1-fast")
        api_key: OpenRouter API key
        cache_dir: Directory for disk cache

    Returns:
        Configured DSPy LM instance

    Raises:
        JudgeExecutionError: If LM creation fails
    """
    try:
        # Configure DSPy cache to use the specified directory
        configure_dspy_cache(cache_dir)

        # Create LM with OpenRouter via LiteLLM
        lm = dspy.LM(f"openrouter/{model}", api_key=api_key, max_tokens=64000)

        logger.debug("Created DSPy LM with model %s", model)
        return lm
    except Exception as e:
        raise JudgeExecutionError(f"Failed to create DSPy LM: {e}") from e


def execute_judge(
    judge: JudgeConfig, plan_content: str, git_changes: str, api_key: str, cache_dir: Path
) -> JudgeResult:
    """Execute a single judge using DSPy.

    Uses dspy.context() for thread-safe LM configuration. This allows
    multiple judges to run in parallel threads without conflicting.

    Args:
        judge: Judge configuration with instructions and model
        plan_content: Full plan.md file content
        git_changes: Git diff, status, and changed file contents
        api_key: OpenRouter API key
        cache_dir: Directory for disk cache

    Returns:
        JudgeResult with score and feedback

    Raises:
        JudgeExecutionError: If judge execution fails
    """
    logger.info("Executing judge '%s' with model %s", judge.name, judge.model)

    try:
        # Create LM for this judge's model
        lm = create_lm(judge.model, api_key, cache_dir)

        # Create signature with loaded instructions
        JudgeSignature = JudgeSignatureBase.with_instructions(judge.instructions)

        # Create predictor and execute with thread-local LM context
        # Using dspy.context() instead of dspy.configure() for thread safety
        predictor = dspy.Predict(JudgeSignature)
        with dspy.context(lm=lm):
            result = predictor(plan_content=plan_content, git_changes=git_changes)

        # Extract score and feedback
        score = float(result.score)
        feedback = str(result.feedback)

        # Validate score range
        if not (0.0 <= score <= 1.0):
            raise JudgeExecutionError(
                f"Judge '{judge.name}' returned invalid score {score} "
                "(must be between 0.0 and 1.0)"
            )

        logger.info("Judge '%s' completed: score=%.2f", judge.name, score)

        return JudgeResult(
            judge_name=judge.name,
            score=score,
            feedback=feedback,
            weight=judge.weight,
        )

    except Exception as e:
        raise JudgeExecutionError(
            f"Failed to execute judge '{judge.name}': {e}"
        ) from e


def get_openrouter_api_key() -> str:
    """Get OpenRouter API key from environment.

    Returns:
        OpenRouter API key

    Raises:
        JudgeExecutionError: If API key is not found
    """
    try:
        # Load home environment variables
        load_home_env()
    except HomeEnvError as e:
        raise JudgeExecutionError(f"Failed to load environment: {e}") from e

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise JudgeExecutionError(
            "OPENROUTER_API_KEY not found in environment. "
            "Add it to ~/.weft/.env"
        )

    return api_key


def get_cache_dir() -> Path:
    """Get DSPy cache directory.

    Always returns the global cache directory at ~/.weft/dspy_cache/.
    The SDK sandbox is configured to grant write access to this directory,
    allowing DSPy to write cache entries directly without rsync.

    Returns:
        Path to global cache directory
    """
    return Path.home() / ".weft" / "dspy_cache"
