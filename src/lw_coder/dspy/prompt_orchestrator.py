"""Orchestrates DSPy-based prompt generation for coding tasks.

This module coordinates configuration loading, environment setup,
DSPy initialization, and prompt artifact generation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import dspy
from dotenv import load_dotenv

from ..config_loader import load_code_config
from ..logging_config import get_logger
from ..plan_validator import PlanMetadata
from .code_prompt_signature import CodePromptSignature

logger = get_logger(__name__)


@dataclass
class PromptArtifacts:
    """Paths to generated prompt files.

    Attributes:
        main_prompt_path: Path to the main coding agent prompt
        review_prompt_path: Path to the code review auditor prompt
        alignment_prompt_path: Path to the plan alignment checker prompt
    """

    main_prompt_path: Path
    review_prompt_path: Path
    alignment_prompt_path: Path


def _initialize_dspy_cache() -> Path:
    """Initialize DSPy disk cache directory.

    Returns:
        Path to the cache directory

    Creates the cache directory at ~/.lw_coder/dspy_cache if it doesn't exist.
    """
    cache_dir = Path.home() / ".lw_coder" / "dspy_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("DSPy cache directory initialized at %s", cache_dir)
    return cache_dir


def _setup_dspy(cache_dir: Path) -> None:
    """Configure DSPy with caching and LLM settings.

    Args:
        cache_dir: Path to the cache directory for DSPy responses
    """
    # Enable disk caching for DSPy
    # Note: DSPy caching is configured via environment or settings
    # For now we just ensure the directory exists; actual cache config
    # happens when DSPy modules are used
    dspy.configure(cache={"type": "disk", "path": str(cache_dir)})
    logger.debug("DSPy configured with disk cache at %s", cache_dir)


def _write_prompt_file(path: Path, content: str) -> None:
    """Write prompt content to file with proper formatting.

    Args:
        path: Path to write the prompt file
        content: Prompt content to write

    Ensures:
    - Parent directories are created
    - Content is trimmed of leading/trailing whitespace
    - File ends with a newline
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Trim whitespace and ensure newline termination
    trimmed_content = content.strip()
    if trimmed_content and not trimmed_content.endswith("\n"):
        trimmed_content += "\n"

    path.write_text(trimmed_content, encoding="utf-8")
    logger.debug("Wrote prompt file: %s (%d bytes)", path, len(trimmed_content))


def generate_code_prompts(
    plan_metadata: PlanMetadata,
    run_dir: Path,
) -> PromptArtifacts:
    """Generate coding prompts from plan metadata and write to run directory.

    This function:
    1. Loads configuration from .lw_coder/config.toml
    2. Loads environment variables from configured .env file
    3. Initializes DSPy with disk caching
    4. Generates three prompts (main, review, alignment) using DSPy or templates
    5. Writes prompts to expected locations in run_dir

    Args:
        plan_metadata: Validated plan metadata containing all plan information
        run_dir: Directory to write prompt artifacts (must exist or be creatable)

    Returns:
        PromptArtifacts containing paths to the three generated prompt files

    Raises:
        ConfigLoaderError: If configuration is invalid or missing
        OSError: If file operations fail
    """
    repo_root = plan_metadata.repo_root

    # Load configuration
    logger.debug("Loading configuration from %s", repo_root)
    config = load_code_config(repo_root)

    # Load environment variables from configured .env file
    logger.debug("Loading environment from %s", config.env_file)
    load_dotenv(config.env_file, override=False)

    # Initialize DSPy caching
    cache_dir = _initialize_dspy_cache()
    _setup_dspy(cache_dir)

    # Generate prompts using DSPy signature
    logger.info(
        "Generating prompts for plan '%s' (SHA: %s)",
        plan_metadata.plan_id,
        plan_metadata.git_sha[:8],
    )

    # Build complete plan text with metadata
    evaluation_notes_formatted = "\n".join(
        f"{i+1}. {note}" for i, note in enumerate(plan_metadata.evaluation_notes)
    )

    complete_plan_text = f"""# Plan Metadata
- Plan ID: {plan_metadata.plan_id}
- Git SHA: {plan_metadata.git_sha}
- Status: {plan_metadata.status}

## Evaluation Criteria
{evaluation_notes_formatted}

# Plan Content
{plan_metadata.plan_text}
"""

    # Use DSPy signature to generate prompts
    predictor = dspy.Predict(CodePromptSignature)

    result = predictor(
        plan_text=complete_plan_text,
    )

    # Validate that DSPy returned valid prompt data
    if not hasattr(result, "main_prompt") or not result.main_prompt:
        raise ValueError(
            "DSPy predictor failed to generate main_prompt. "
            "Check LLM configuration and ensure the model is accessible."
        )
    if not hasattr(result, "review_prompt") or not result.review_prompt:
        raise ValueError(
            "DSPy predictor failed to generate review_prompt. "
            "Check LLM configuration and ensure the model is accessible."
        )
    if not hasattr(result, "alignment_prompt") or not result.alignment_prompt:
        raise ValueError(
            "DSPy predictor failed to generate alignment_prompt. "
            "Check LLM configuration and ensure the model is accessible."
        )

    main_prompt = result.main_prompt
    review_prompt = result.review_prompt
    alignment_prompt = result.alignment_prompt

    logger.debug("Generated prompts using DSPy signature")

    # Define output paths
    main_prompt_path = run_dir / "prompts" / "main.md"
    review_prompt_path = run_dir / "droids" / "code-review-auditor.md"
    alignment_prompt_path = run_dir / "droids" / "plan-alignment-checker.md"

    # Write prompt files
    _write_prompt_file(main_prompt_path, main_prompt)
    _write_prompt_file(review_prompt_path, review_prompt)
    _write_prompt_file(alignment_prompt_path, alignment_prompt)

    logger.info("Prompt artifacts written to %s", run_dir)
    logger.info("  Main prompt: %s", main_prompt_path)
    logger.info("  Review prompt: %s", review_prompt_path)
    logger.info("  Alignment prompt: %s", alignment_prompt_path)

    return PromptArtifacts(
        main_prompt_path=main_prompt_path,
        review_prompt_path=review_prompt_path,
        alignment_prompt_path=alignment_prompt_path,
    )
