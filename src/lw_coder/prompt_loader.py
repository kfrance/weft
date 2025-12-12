"""Load optimized prompts from disk for Claude Code CLI and other tools.

This module provides functionality to load pre-optimized prompts from the
project's .lw_coder directory, replacing the dynamic DSPy-based prompt generation.

Directory structure:
- New location: .lw_coder/prompts/active/<tool>/<model>/
- Old location (legacy): .lw_coder/optimized_prompts/<tool>/<model>/

Migration happens automatically when loading from old location.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .logging_config import get_logger
from .training_types import CurrentPrompts, SubagentDefinition

logger = get_logger(__name__)


class PromptLoadingError(Exception):
    """Raised when prompt loading fails."""


def _migrate_prompts_if_needed(repo_root: Path) -> bool:
    """Migrate prompts from old location to new location.

    Args:
        repo_root: Repository root directory

    Returns:
        True if migration occurred, False otherwise
    """
    old_location = repo_root / ".lw_coder" / "optimized_prompts"
    new_location = repo_root / ".lw_coder" / "prompts" / "active"

    # No migration needed if old location doesn't exist
    if not old_location.exists():
        return False

    # No migration needed if new location already exists
    if new_location.exists():
        return False

    logger.info("Migrating prompts from %s to %s", old_location, new_location)

    try:
        # Create new location parent
        new_location.parent.mkdir(parents=True, exist_ok=True)

        # Copy contents to new location
        shutil.copytree(old_location, new_location)
        logger.info("Copied prompts to new location")

        # Delete old location
        shutil.rmtree(old_location)
        logger.info("Removed old prompts directory")

        return True
    except OSError as exc:
        logger.warning("Migration failed, falling back to old location: %s", exc)
        return False


def _get_prompts_base(repo_root: Path, tool: str, model: str) -> Path:
    """Get the prompts base directory, handling migration.

    Args:
        repo_root: Repository root directory
        tool: Tool name
        model: Model variant

    Returns:
        Path to the prompts directory
    """
    # Try migration first
    _migrate_prompts_if_needed(repo_root)

    # Check new location first
    new_location = repo_root / ".lw_coder" / "prompts" / "active" / tool / model
    if new_location.exists():
        return new_location

    # Fall back to old location
    old_location = repo_root / ".lw_coder" / "optimized_prompts" / tool / model
    if old_location.exists():
        return old_location

    # Return new location as default (will fail with appropriate error later)
    return new_location


def load_prompts(
    repo_root: Path | str,
    tool: str = "claude-code-cli",
    model: str = "sonnet",
) -> dict[str, str]:
    """Load optimized prompts for a given tool and model from the project directory.

    Checks new location (prompts/active/) first, then falls back to old location
    (optimized_prompts/) with automatic migration.

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

    # Get prompts base directory (handles migration)
    prompts_base = _get_prompts_base(repo_root, tool, model)

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
                f"Expected at .lw_coder/prompts/active/{tool}/{model}/{file_path.name}"
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


def load_current_prompts_for_training(
    repo_root: Path,
    tool: str = "claude-code-cli",
    model: str = "sonnet",
) -> CurrentPrompts:
    """Load current prompts as CurrentPrompts object for training.

    Loads main.md and discovers all subagent .md files in the directory.

    Args:
        repo_root: Repository root directory
        tool: Tool name (default: claude-code-cli)
        model: Model variant (default: sonnet)

    Returns:
        CurrentPrompts object with main prompt and all subagents

    Raises:
        PromptLoadingError: If prompts cannot be loaded
    """
    # Get prompts base directory
    prompts_base = _get_prompts_base(repo_root, tool, model)

    if not prompts_base.exists():
        raise PromptLoadingError(
            f"Prompts directory not found: {prompts_base}. "
            f"Run 'lw_coder init' to install prompts."
        )

    # Load main prompt
    main_prompt_path = prompts_base / "main.md"
    if not main_prompt_path.exists():
        raise PromptLoadingError(f"Main prompt not found: {main_prompt_path}")

    try:
        main_prompt = main_prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptLoadingError(f"Failed to read main prompt: {exc}") from exc

    # Discover all subagent files (all .md files except main.md)
    subagents = []
    for md_file in prompts_base.glob("*.md"):
        if md_file.name == "main.md":
            continue

        try:
            content = md_file.read_text(encoding="utf-8")
            # Extract name from filename (kebab-case)
            name = md_file.stem  # e.g., "code-review-auditor"

            subagents.append(SubagentDefinition(
                name=name,
                description=f"Subagent: {name.replace('-', ' ').title()}",
                prompt=content,
            ))
            logger.debug("Loaded subagent: %s", name)
        except OSError as exc:
            logger.warning("Failed to read subagent file %s: %s", md_file, exc)
            continue

    logger.info(
        "Loaded current prompts for training: 1 main + %d subagents",
        len(subagents),
    )

    return CurrentPrompts(
        main_prompt=main_prompt,
        subagents=subagents,
    )
