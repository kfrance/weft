"""Load optimized prompts from disk for Claude Code CLI and other tools.

This module provides functionality to load pre-optimized prompts from the
project's .lw_coder directory, replacing the dynamic DSPy-based prompt generation.
"""

from __future__ import annotations

from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


class PromptLoadingError(Exception):
    """Raised when prompt loading fails."""


def load_prompts(
    repo_root: Path | str,
    tool: str = "claude-code-cli",
    model: str = "sonnet",
) -> dict[str, str]:
    """Load optimized prompts for a given tool and model from the project directory.

    Args:
        repo_root: Path to the project root directory where .lw_coder/ exists.
        tool: Name of the tool (default: "claude-code-cli").
        model: Model variant (default: "sonnet"). Valid options: "sonnet", "opus", "haiku".

    Returns:
        Dictionary with keys:
        - "main_prompt": Main system prompt for Claude Code CLI
        - "code_review_auditor": Prompt for code review auditor sub-agent
        - "plan_alignment_checker": Prompt for plan alignment checker sub-agent

    Raises:
        PromptLoadingError: If any prompt file is missing or cannot be read.
    """
    # Convert to Path if string
    if isinstance(repo_root, str):
        repo_root = Path(repo_root)

    # Validate model parameter
    valid_models = {"sonnet", "opus", "haiku"}
    if model not in valid_models:
        raise PromptLoadingError(
            f"Invalid model '{model}'. Valid options: {', '.join(sorted(valid_models))}"
        )

    # Construct prompt directory path (project-relative)
    prompts_base = repo_root / ".lw_coder" / "optimized_prompts" / tool / model

    # Define prompt file paths
    prompt_files = {
        "main_prompt": prompts_base / "main.md",
        "code_review_auditor": prompts_base / "code-review-auditor.md",
        "plan_alignment_checker": prompts_base / "plan-alignment-checker.md",
    }

    # Load all prompts
    prompts = {}
    for key, file_path in prompt_files.items():
        if not file_path.exists():
            raise PromptLoadingError(
                f"Prompt file not found: {file_path}. "
                f"Expected at ~/.lw_coder/optimized_prompts/{tool}/{model}/{file_path.name}"
            )

        try:
            content = file_path.read_text(encoding="utf-8")
            # Validate that prompt content is not empty
            if not content.strip():
                raise PromptLoadingError(
                    f"Prompt file is empty: {file_path}. "
                    f"Prompt files must contain non-empty content."
                )
            prompts[key] = content
            logger.debug("Loaded prompt: %s", file_path)
        except (OSError, IOError) as exc:
            raise PromptLoadingError(f"Failed to read prompt file {file_path}: {exc}") from exc

    logger.info(
        "Loaded prompts for %s/%s (%d prompts total)", tool, model, len(prompts)
    )
    return prompts
