"""Fingerprint computation for prompts and eval configurations.

Provides deterministic fingerprints for:
- Prompt sets (main prompt + subagents) used during coding sessions
- Judge configurations used during evaluation

Fingerprints are SHA256 hashes truncated to 8 characters for readability.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .judge_loader import JudgeConfig
    from .training_types import PromptSnapshot, SubagentDefinition


def compute_prompt_fingerprint(
    main_prompt: str,
    subagents: list["SubagentDefinition"],
) -> str:
    """Compute a deterministic fingerprint for a prompt set.

    The fingerprint is computed by:
    1. Sorting subagents by name for deterministic ordering
    2. Concatenating main prompt and all subagent prompts with their names
    3. Computing SHA256 hash and returning first 8 characters

    Args:
        main_prompt: The main system prompt content
        subagents: List of subagent definitions

    Returns:
        8-character hexadecimal fingerprint
    """
    # Sort subagents by name for deterministic ordering
    sorted_subagents = sorted(subagents, key=lambda s: s.name)

    # Build content string
    parts = [main_prompt]
    for subagent in sorted_subagents:
        parts.append(f"\n---SUBAGENT:{subagent.name}---\n")
        parts.append(subagent.prompt)

    content = "".join(parts)

    # Compute SHA256 hash
    hash_obj = hashlib.sha256(content.encode("utf-8"))
    return hash_obj.hexdigest()[:8]


def compute_prompt_fingerprint_from_snapshot(snapshot: "PromptSnapshot") -> str:
    """Compute fingerprint from a PromptSnapshot object.

    Convenience wrapper around compute_prompt_fingerprint.

    Args:
        snapshot: PromptSnapshot containing main prompt and subagents

    Returns:
        8-character hexadecimal fingerprint
    """
    return compute_prompt_fingerprint(snapshot.main_prompt, snapshot.subagents)


def compute_eval_fingerprint(judges: list["JudgeConfig"]) -> str:
    """Compute a deterministic fingerprint for a judge configuration.

    The fingerprint is computed by:
    1. Sorting judges by name for deterministic ordering
    2. Concatenating judge name, weight, and instructions for each judge
    3. Computing SHA256 hash and returning first 8 characters

    Args:
        judges: List of judge definitions (JudgeConfig objects from judge_loader)

    Returns:
        8-character hexadecimal fingerprint
    """
    # Sort judges by name for deterministic ordering
    sorted_judges = sorted(judges, key=lambda j: j.name)

    # Build content string
    parts = []
    for judge in sorted_judges:
        parts.append(f"---JUDGE:{judge.name}---\n")
        parts.append(f"weight:{judge.weight}\n")
        # JudgeConfig uses 'instructions' attribute, not 'prompt'
        parts.append(judge.instructions)
        parts.append("\n")

    content = "".join(parts)

    # Compute SHA256 hash
    hash_obj = hashlib.sha256(content.encode("utf-8"))
    return hash_obj.hexdigest()[:8]
