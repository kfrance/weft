"""Orchestrates DSPy-based prompt generation for coding tasks.

This module coordinates configuration loading, environment setup,
DSPy initialization, and prompt artifact generation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import dspy

from ..home_env import load_home_env
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

    Raises:
        ValueError: If OPENROUTER_API_KEY is not set in environment

    Note:
        If DSPy is already configured (e.g., in tests), this function skips
        reconfiguration to preserve the existing setup.
    """
    # Check if DSPy is already configured (has an LM set)
    if dspy.settings.lm is not None:
        logger.debug("DSPy already configured, skipping setup")
        return

    # Get OpenRouter API key from environment
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable must be set. "
            "Add it to your .env file or export it in your shell."
        )

    # Configure DSPy with OpenRouter LLM and disk caching
    lm = dspy.LM("openrouter/x-ai/grok-3-mini", api_key=api_key, max_tokens=64000)
    dspy.configure(lm=lm, cache={"type": "disk", "path": str(cache_dir)})
    logger.debug("DSPy configured with OpenRouter LLM (max_tokens=64000) and disk cache at %s", cache_dir)


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


def _write_droid_file(path: Path, name: str, content: str) -> None:
    """Write droid configuration file with YAML frontmatter.

    Args:
        path: Path to write the droid configuration file
        name: Name of the droid (lowercase with hyphens)
        content: Prompt content for the droid

    Creates a droid configuration file with YAML frontmatter containing
    the droid metadata (name, model, tools) followed by the prompt content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Trim prompt content
    trimmed_content = content.strip()

    # Build droid configuration with YAML frontmatter
    droid_config = f"""---
name: {name}
model: inherit
tools: all
---

{trimmed_content}
"""

    path.write_text(droid_config, encoding="utf-8")
    logger.debug("Wrote droid config file: %s (%d bytes)", path, len(droid_config))


def generate_code_prompts(
    plan_metadata: PlanMetadata,
    run_dir: Path,
) -> PromptArtifacts:
    """Generate coding prompts from plan metadata and write to run directory.

    This function:
    1. Loads environment variables from ~/.lw_coder/.env
    2. Initializes DSPy with disk caching
    3. Generates three prompts (main, review, alignment) using DSPy
    4. Writes prompts to expected locations in run_dir

    Args:
        plan_metadata: Validated plan metadata containing all plan information
        run_dir: Directory to write prompt artifacts (must exist or be creatable)

    Returns:
        PromptArtifacts containing paths to the three generated prompt files

    Raises:
        HomeEnvError: If ~/.lw_coder/.env is missing or unreadable
        OSError: If file operations fail
    """
    # Load environment variables from home-level .env
    logger.debug("Loading environment from ~/.lw_coder/.env")
    load_home_env()

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
    _write_droid_file(review_prompt_path, "code-review-auditor", review_prompt)
    _write_droid_file(alignment_prompt_path, "plan-alignment-checker", alignment_prompt)

    logger.info("Prompt artifacts written to %s", run_dir)
    logger.info("  Main prompt: %s", main_prompt_path)
    logger.info("  Review prompt: %s", review_prompt_path)
    logger.info("  Alignment prompt: %s", alignment_prompt_path)

    return PromptArtifacts(
        main_prompt_path=main_prompt_path,
        review_prompt_path=review_prompt_path,
        alignment_prompt_path=alignment_prompt_path,
    )
