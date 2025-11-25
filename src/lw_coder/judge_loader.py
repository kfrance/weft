"""Judge file loader and parser for evaluation framework.

Loads judge configurations from markdown files with YAML frontmatter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .logging_config import get_logger

logger = get_logger(__name__)


class JudgeLoaderError(Exception):
    """Raised when a judge file cannot be loaded or parsed."""

    pass


@dataclass
class JudgeConfig:
    """Configuration for a single judge.

    Attributes:
        name: Judge name (derived from filename without .md extension)
        weight: Weight for weighted scoring (0.0 to 1.0)
        model: OpenRouter model tag (e.g., "x-ai/grok-4.1-fast")
        instructions: Judge instructions in markdown format
        file_path: Path to the judge file
    """

    name: str
    weight: float
    model: str
    instructions: str
    file_path: Path


def parse_judge_file(file_path: Path) -> JudgeConfig:
    """Parse a judge markdown file with YAML frontmatter.

    Args:
        file_path: Path to the judge markdown file

    Returns:
        JudgeConfig with parsed frontmatter and instructions

    Raises:
        JudgeLoaderError: If file is invalid or missing required fields
    """
    if not file_path.exists():
        raise JudgeLoaderError(f"Judge file not found: {file_path}")

    if not file_path.is_file():
        raise JudgeLoaderError(f"Judge path is not a file: {file_path}")

    try:
        content = file_path.read_text()
    except (PermissionError, OSError) as e:
        raise JudgeLoaderError(f"Cannot read judge file {file_path}: {e}") from e

    # Parse frontmatter and body
    # Match YAML frontmatter between --- delimiters at start of file
    frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(frontmatter_pattern, content, re.DOTALL)

    if not match:
        raise JudgeLoaderError(
            f"Invalid judge file format in {file_path}: "
            "Expected YAML frontmatter between --- delimiters"
        )

    frontmatter_text, instructions = match.groups()

    # Parse YAML frontmatter
    try:
        frontmatter: dict[str, Any] = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as e:
        raise JudgeLoaderError(
            f"Invalid YAML frontmatter in {file_path}: {e}"
        ) from e

    if not isinstance(frontmatter, dict):
        raise JudgeLoaderError(
            f"Invalid frontmatter in {file_path}: Expected a mapping/dict"
        )

    # Validate required fields
    if "weight" not in frontmatter:
        raise JudgeLoaderError(f"Missing required field 'weight' in {file_path}")

    if "model" not in frontmatter:
        raise JudgeLoaderError(f"Missing required field 'model' in {file_path}")

    # Validate weight type and range
    weight = frontmatter["weight"]
    if not isinstance(weight, (int, float)):
        raise JudgeLoaderError(
            f"Invalid 'weight' in {file_path}: Expected number, got {type(weight).__name__}"
        )

    weight = float(weight)
    if not (0.0 <= weight <= 1.0):
        raise JudgeLoaderError(
            f"Invalid 'weight' in {file_path}: Must be between 0.0 and 1.0, got {weight}"
        )

    # Validate model type
    model = frontmatter["model"]
    if not isinstance(model, str):
        raise JudgeLoaderError(
            f"Invalid 'model' in {file_path}: Expected string, got {type(model).__name__}"
        )

    if not model.strip():
        raise JudgeLoaderError(f"Invalid 'model' in {file_path}: Cannot be empty")

    # Extract judge name from filename
    name = file_path.stem  # Remove .md extension

    # Validate instructions not empty
    instructions = instructions.strip()
    if not instructions:
        raise JudgeLoaderError(
            f"Empty instructions in {file_path}: Judge must have instructions in body"
        )

    logger.debug(
        "Loaded judge '%s' from %s (weight=%.2f, model=%s)",
        name,
        file_path,
        weight,
        model,
    )

    return JudgeConfig(
        name=name,
        weight=weight,
        model=model,
        instructions=instructions,
        file_path=file_path,
    )


def discover_judges(judges_dir: Path) -> list[JudgeConfig]:
    """Discover and load all judge files from a directory.

    Args:
        judges_dir: Path to directory containing judge .md files

    Returns:
        List of JudgeConfig objects, sorted by name

    Raises:
        JudgeLoaderError: If judges directory doesn't exist or no judges found
    """
    if not judges_dir.exists():
        raise JudgeLoaderError(f"Judges directory not found: {judges_dir}")

    if not judges_dir.is_dir():
        raise JudgeLoaderError(f"Judges path is not a directory: {judges_dir}")

    # Find all .md files in the judges directory
    judge_files = sorted(judges_dir.glob("*.md"))

    if not judge_files:
        raise JudgeLoaderError(f"No judge files found in {judges_dir}")

    judges = []
    errors = []

    for file_path in judge_files:
        try:
            judge = parse_judge_file(file_path)
            judges.append(judge)
        except JudgeLoaderError as e:
            errors.append(str(e))

    # If any judges failed to load, report all errors
    if errors:
        error_msg = "Failed to load some judge files:\n" + "\n".join(errors)
        raise JudgeLoaderError(error_msg)

    logger.info("Discovered %d judge(s) in %s", len(judges), judges_dir)
    return judges
