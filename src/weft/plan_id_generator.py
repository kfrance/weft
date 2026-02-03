"""DSPy-based plan_id generation for collision resolution.

Generates new unique plan_ids based on plan content using an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import dspy

from .judge_executor import create_lm
from .logging_config import get_logger
from .plan_validator import _PLAN_ID_PATTERN

logger = get_logger(__name__)


class PlanIdGenerationError(Exception):
    """Raised when plan_id generation fails."""

    pass


@dataclass
class PlanIdRequest:
    """Request for generating a new plan_id.

    Attributes:
        plan_content: The markdown body of the plan.
        file_path: Path to the plan file (for reference in logs).
    """

    plan_content: str
    file_path: Path


@dataclass
class PlanIdResult:
    """Result of plan_id generation.

    Attributes:
        file_path: Path to the plan file.
        new_plan_id: The newly generated plan_id.
    """

    file_path: Path
    new_plan_id: str


class PlanIdSignature(dspy.Signature):
    """Generate a unique plan_id based on plan content.

    You are tasked with generating a unique, descriptive plan_id for a software
    development plan. The plan_id should:
    - Be 3-100 characters long
    - Use only alphanumeric characters, dots (.), underscores (_), and hyphens (-)
    - Be descriptive of the plan's purpose
    - Be concise but meaningful
    - NOT match any of the plan_ids listed to avoid

    Analyze the plan content and generate a suitable plan_id.
    """

    plan_content: str = dspy.InputField(desc="The markdown body of the plan")
    plan_ids_to_avoid: str = dspy.InputField(
        desc="Comma-separated list of plan_ids that must NOT be used"
    )
    plan_id: str = dspy.OutputField(
        desc="New unique plan_id (3-100 chars, alphanumeric/._- only)"
    )


class BatchPlanIdSignature(dspy.Signature):
    """Generate unique plan_ids for multiple plans at once.

    You are tasked with generating unique, descriptive plan_ids for multiple
    software development plans. Each plan_id should:
    - Be 3-100 characters long
    - Use only alphanumeric characters, dots (.), underscores (_), and hyphens (-)
    - Be descriptive of the plan's purpose
    - Be concise but meaningful
    - NOT match any of the plan_ids listed to avoid
    - Be unique from each other

    The input is a numbered list of plan contents. Return a numbered list of
    corresponding plan_ids in the same order.
    """

    plans_content: str = dspy.InputField(
        desc="Numbered list of plan contents, each separated by '---PLAN---'"
    )
    plan_ids_to_avoid: str = dspy.InputField(
        desc="Comma-separated list of plan_ids that must NOT be used"
    )
    plan_ids: str = dspy.OutputField(
        desc="Numbered list of new unique plan_ids, one per line in format 'N. plan-id'"
    )


def generate_plan_id(
    request: PlanIdRequest,
    plan_ids_to_avoid: set[str],
    api_key: str,
    cache_dir: Path,
) -> PlanIdResult:
    """Generate a single new plan_id based on plan content.

    Args:
        request: The plan content and file path.
        plan_ids_to_avoid: Set of plan_ids that must not be used.
        api_key: OpenRouter API key.
        cache_dir: Directory for DSPy cache.

    Returns:
        PlanIdResult with the new plan_id.

    Raises:
        PlanIdGenerationError: If generation fails.
    """
    results = generate_plan_ids_batch(
        [request], plan_ids_to_avoid, api_key, cache_dir
    )
    return results[0]


def generate_plan_ids_batch(
    requests: list[PlanIdRequest],
    plan_ids_to_avoid: set[str],
    api_key: str,
    cache_dir: Path,
) -> list[PlanIdResult]:
    """Generate new plan_ids for multiple plans in a single LLM call.

    Args:
        requests: List of plan content and file paths.
        plan_ids_to_avoid: Set of plan_ids that must not be used.
        api_key: OpenRouter API key.
        cache_dir: Directory for DSPy cache.

    Returns:
        List of PlanIdResult with new plan_ids, in same order as requests.

    Raises:
        PlanIdGenerationError: If generation fails.
    """
    if not requests:
        return []

    logger.info(
        "Generating %d new plan_id(s), avoiding %d existing IDs",
        len(requests),
        len(plan_ids_to_avoid),
    )

    try:
        # Create LM with grok-4.1-fast model
        lm = create_lm("x-ai/grok-4.1-fast", api_key, cache_dir)

        # Format the avoid list
        avoid_str = ", ".join(sorted(plan_ids_to_avoid)) if plan_ids_to_avoid else "none"

        if len(requests) == 1:
            # Single plan - use simpler signature
            return _generate_single(requests[0], avoid_str, lm)
        else:
            # Multiple plans - use batch signature
            return _generate_batch(requests, avoid_str, lm)

    except Exception as e:
        raise PlanIdGenerationError(f"Failed to generate plan_ids: {e}") from e


def _generate_single(
    request: PlanIdRequest,
    avoid_str: str,
    lm: dspy.LM,
) -> list[PlanIdResult]:
    """Generate a single plan_id using the single-plan signature."""
    predictor = dspy.Predict(PlanIdSignature)

    with dspy.context(lm=lm):
        result = predictor(
            plan_content=request.plan_content,
            plan_ids_to_avoid=avoid_str,
        )

    plan_id = _clean_plan_id(result.plan_id)
    _validate_plan_id(plan_id)

    logger.debug(
        "Generated plan_id '%s' for %s",
        plan_id,
        request.file_path.name,
    )

    return [PlanIdResult(file_path=request.file_path, new_plan_id=plan_id)]


def _generate_batch(
    requests: list[PlanIdRequest],
    avoid_str: str,
    lm: dspy.LM,
) -> list[PlanIdResult]:
    """Generate multiple plan_ids using the batch signature."""
    # Format plans as numbered list
    plans_content = "\n---PLAN---\n".join(
        f"{i + 1}. {req.plan_content}" for i, req in enumerate(requests)
    )

    predictor = dspy.Predict(BatchPlanIdSignature)

    with dspy.context(lm=lm):
        result = predictor(
            plans_content=plans_content,
            plan_ids_to_avoid=avoid_str,
        )

    # Parse the numbered list of plan_ids
    plan_ids = _parse_numbered_list(result.plan_ids, len(requests))

    results = []
    for i, (request, plan_id) in enumerate(zip(requests, plan_ids)):
        clean_id = _clean_plan_id(plan_id)
        _validate_plan_id(clean_id)

        logger.debug(
            "Generated plan_id '%s' for %s",
            clean_id,
            request.file_path.name,
        )

        results.append(PlanIdResult(file_path=request.file_path, new_plan_id=clean_id))

    return results


def _clean_plan_id(plan_id: str) -> str:
    """Clean a plan_id by stripping whitespace and quotes."""
    cleaned = plan_id.strip()
    # Remove surrounding quotes if present
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1]
    return cleaned.strip()


def _validate_plan_id(plan_id: str) -> None:
    """Validate that a plan_id matches the required pattern.

    Uses the same pattern as plan_validator.py for consistency.

    Raises:
        PlanIdGenerationError: If plan_id is invalid.
    """
    if not _PLAN_ID_PATTERN.fullmatch(plan_id):
        raise PlanIdGenerationError(
            f"Generated plan_id '{plan_id}' does not match required pattern "
            f"{_PLAN_ID_PATTERN.pattern}"
        )


def _parse_numbered_list(text: str, expected_count: int) -> list[str]:
    """Parse a numbered list of plan_ids.

    Expected format:
    1. plan-id-one
    2. plan-id-two

    Args:
        text: The numbered list text.
        expected_count: Number of plan_ids expected.

    Returns:
        List of plan_ids in order.

    Raises:
        PlanIdGenerationError: If parsing fails or count doesn't match.
    """
    import re

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    plan_ids = []

    # Pattern to match "N. plan-id" or "N) plan-id"
    pattern = re.compile(r"^\d+[.)]\s*(.+)$")

    for line in lines:
        match = pattern.match(line)
        if match:
            plan_ids.append(match.group(1))
        elif not line[0].isdigit():
            # If line doesn't start with a number, it might be a continuation
            # or just the plan_id itself
            plan_ids.append(line)

    if len(plan_ids) != expected_count:
        raise PlanIdGenerationError(
            f"Expected {expected_count} plan_ids but got {len(plan_ids)} "
            f"from response: {text!r}"
        )

    return plan_ids
