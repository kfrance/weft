"""Candidate prompt writer for saving generated prompt sets.

This module provides functions to write candidate prompt sets generated
by the train command to the .weft/prompts/candidates/ directory.
"""

from __future__ import annotations

import re
from pathlib import Path

from .logging_config import get_logger
from .training_types import CandidatePrompts

logger = get_logger(__name__)


class CandidateWriteError(Exception):
    """Raised when writing candidate prompts fails."""

    pass


def get_next_candidate_number(
    repo_root: Path,
    tool: str = "claude-code-cli",
    model: str = "sonnet",
) -> int:
    """Get the next sequential candidate number.

    Args:
        repo_root: Repository root directory
        tool: Tool name (default: claude-code-cli)
        model: Model variant (default: sonnet)

    Returns:
        Next candidate number (1 if no candidates exist)
    """
    candidates_dir = repo_root / ".weft" / "prompts" / "candidates" / tool / model

    if not candidates_dir.exists():
        return 1

    # Find existing candidate directories
    pattern = re.compile(r"^candidate-(\d{3})$")
    max_num = 0

    for item in candidates_dir.iterdir():
        if item.is_dir():
            match = pattern.match(item.name)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)

    return max_num + 1


def write_candidate(
    repo_root: Path,
    tool: str,
    model: str,
    candidate: CandidatePrompts,
) -> Path:
    """Write a candidate prompt set and return the directory path.

    Creates .weft/prompts/candidates/<tool>/<model>/candidate-NNN/
    with main.md and subagent .md files.

    Args:
        repo_root: Repository root directory
        tool: Tool name
        model: Model variant
        candidate: CandidatePrompts object to write

    Returns:
        Path to the created candidate directory

    Raises:
        CandidateWriteError: If writing fails
    """
    # Get next candidate number
    candidate_num = get_next_candidate_number(repo_root, tool, model)
    candidate_name = f"candidate-{candidate_num:03d}"

    # Create candidate directory
    candidate_dir = (
        repo_root / ".weft" / "prompts" / "candidates" / tool / model / candidate_name
    )

    try:
        candidate_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise CandidateWriteError(
            f"Candidate directory already exists: {candidate_dir}"
        )
    except OSError as exc:
        raise CandidateWriteError(
            f"Failed to create candidate directory: {exc}"
        ) from exc

    logger.info("Creating candidate prompts at: %s", candidate_dir)

    # Write main.md
    main_path = candidate_dir / "main.md"
    try:
        main_path.write_text(candidate.main_prompt, encoding="utf-8")
        logger.debug("Wrote main prompt: %s", main_path)
    except OSError as exc:
        raise CandidateWriteError(f"Failed to write main prompt: {exc}") from exc

    # Write subagent files
    reserved_names = {"main", "analysis"}
    for subagent in candidate.subagents:
        # Check for reserved filename collision
        if subagent.name.lower() in reserved_names:
            logger.warning(
                "Skipping subagent '%s' - conflicts with reserved filename",
                subagent.name
            )
            continue

        # Sanitize name for filename (remove path separators and special chars)
        safe_name = re.sub(r"[/\\<>:\"|?*]", "-", subagent.name)
        filename = f"{safe_name}.md"
        subagent_path = candidate_dir / filename

        try:
            subagent_path.write_text(subagent.prompt, encoding="utf-8")
            logger.debug("Wrote subagent prompt: %s", subagent_path)
        except OSError as exc:
            raise CandidateWriteError(
                f"Failed to write subagent {subagent.name}: {exc}"
            ) from exc

    # Write analysis summary as separate file for reference
    analysis_path = candidate_dir / "ANALYSIS.md"
    try:
        analysis_content = f"# Candidate {candidate_name} Analysis\n\n{candidate.analysis_summary}"
        analysis_path.write_text(analysis_content, encoding="utf-8")
        logger.debug("Wrote analysis summary: %s", analysis_path)
    except OSError as exc:
        logger.warning("Failed to write analysis summary: %s", exc)
        # Non-fatal - continue without analysis file

    logger.info(
        "Candidate %s created with %d subagent(s)",
        candidate_name,
        len(candidate.subagents),
    )

    return candidate_dir
