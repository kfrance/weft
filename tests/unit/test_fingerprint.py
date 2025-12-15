"""Tests for fingerprint module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from lw_coder.fingerprint import (
    compute_eval_fingerprint,
    compute_prompt_fingerprint,
    compute_prompt_fingerprint_from_snapshot,
)
from lw_coder.training_types import PromptSnapshot, SubagentDefinition


class TestComputePromptFingerprint:
    """Tests for compute_prompt_fingerprint function."""

    def test_compute_prompt_fingerprint_deterministic(self) -> None:
        """Same inputs produce same fingerprint."""
        main_prompt = "Main prompt content"
        subagents = [
            SubagentDefinition(
                name="test-agent",
                description="Test agent",
                prompt="Test prompt"
            )
        ]

        fingerprint1 = compute_prompt_fingerprint(main_prompt, subagents)
        fingerprint2 = compute_prompt_fingerprint(main_prompt, subagents)

        assert fingerprint1 == fingerprint2
        assert len(fingerprint1) == 8  # 8-character fingerprint

    def test_compute_prompt_fingerprint_changes_with_content(self) -> None:
        """Different content produces different fingerprint."""
        main_prompt1 = "Main prompt content version 1"
        main_prompt2 = "Main prompt content version 2"
        subagents = [
            SubagentDefinition(
                name="test-agent",
                description="Test agent",
                prompt="Test prompt"
            )
        ]

        fingerprint1 = compute_prompt_fingerprint(main_prompt1, subagents)
        fingerprint2 = compute_prompt_fingerprint(main_prompt2, subagents)

        assert fingerprint1 != fingerprint2

    def test_compute_prompt_fingerprint_subagent_order_independent(self) -> None:
        """Subagents sorted by name before hashing (order doesn't matter)."""
        main_prompt = "Main prompt content"

        # Create subagents in different orders
        subagents_order1 = [
            SubagentDefinition(name="alpha-agent", description="Alpha", prompt="Alpha prompt"),
            SubagentDefinition(name="beta-agent", description="Beta", prompt="Beta prompt"),
        ]
        subagents_order2 = [
            SubagentDefinition(name="beta-agent", description="Beta", prompt="Beta prompt"),
            SubagentDefinition(name="alpha-agent", description="Alpha", prompt="Alpha prompt"),
        ]

        fingerprint1 = compute_prompt_fingerprint(main_prompt, subagents_order1)
        fingerprint2 = compute_prompt_fingerprint(main_prompt, subagents_order2)

        assert fingerprint1 == fingerprint2

    def test_compute_prompt_fingerprint_empty_subagents(self) -> None:
        """Works with no subagents."""
        main_prompt = "Main prompt only"

        fingerprint = compute_prompt_fingerprint(main_prompt, [])

        assert len(fingerprint) == 8
        # Verify it's deterministic
        assert fingerprint == compute_prompt_fingerprint(main_prompt, [])

    def test_compute_prompt_fingerprint_from_snapshot(self) -> None:
        """Works with PromptSnapshot object."""
        snapshot = PromptSnapshot(
            main_prompt="Main prompt",
            subagents=[
                SubagentDefinition(name="test", description="Test", prompt="Test prompt")
            ]
        )

        fingerprint = compute_prompt_fingerprint_from_snapshot(snapshot)
        expected = compute_prompt_fingerprint(snapshot.main_prompt, snapshot.subagents)

        assert fingerprint == expected


# Mock JudgeConfig for testing
@dataclass
class MockJudgeConfig:
    """Mock JudgeConfig for testing."""
    name: str
    weight: float
    instructions: str
    model: str = "test-model"
    file_path: Path = Path("test.md")


class TestComputeEvalFingerprint:
    """Tests for compute_eval_fingerprint function."""

    def test_compute_eval_fingerprint_deterministic(self) -> None:
        """Same judges produce same fingerprint."""
        judges = [
            MockJudgeConfig(
                name="test-judge",
                weight=1.0,
                instructions="Judge instructions"
            )
        ]

        fingerprint1 = compute_eval_fingerprint(judges)
        fingerprint2 = compute_eval_fingerprint(judges)

        assert fingerprint1 == fingerprint2
        assert len(fingerprint1) == 8

    def test_compute_eval_fingerprint_changes_with_judges(self) -> None:
        """Different judges produce different fingerprint."""
        judges1 = [
            MockJudgeConfig(name="judge-a", weight=1.0, instructions="Instructions A")
        ]
        judges2 = [
            MockJudgeConfig(name="judge-b", weight=1.0, instructions="Instructions B")
        ]

        fingerprint1 = compute_eval_fingerprint(judges1)
        fingerprint2 = compute_eval_fingerprint(judges2)

        assert fingerprint1 != fingerprint2

    def test_compute_eval_fingerprint_judge_order_independent(self) -> None:
        """Judges sorted by name before hashing (order doesn't matter)."""
        judges_order1 = [
            MockJudgeConfig(name="alpha-judge", weight=0.5, instructions="Alpha"),
            MockJudgeConfig(name="beta-judge", weight=0.5, instructions="Beta"),
        ]
        judges_order2 = [
            MockJudgeConfig(name="beta-judge", weight=0.5, instructions="Beta"),
            MockJudgeConfig(name="alpha-judge", weight=0.5, instructions="Alpha"),
        ]

        fingerprint1 = compute_eval_fingerprint(judges_order1)
        fingerprint2 = compute_eval_fingerprint(judges_order2)

        assert fingerprint1 == fingerprint2

    def test_compute_eval_fingerprint_weight_matters(self) -> None:
        """Different weights produce different fingerprints."""
        judges1 = [
            MockJudgeConfig(name="test-judge", weight=0.5, instructions="Instructions")
        ]
        judges2 = [
            MockJudgeConfig(name="test-judge", weight=1.0, instructions="Instructions")
        ]

        fingerprint1 = compute_eval_fingerprint(judges1)
        fingerprint2 = compute_eval_fingerprint(judges2)

        assert fingerprint1 != fingerprint2

    def test_compute_eval_fingerprint_empty_judges(self) -> None:
        """Works with no judges (edge case)."""
        fingerprint = compute_eval_fingerprint([])

        assert len(fingerprint) == 8
        # Verify it's deterministic
        assert fingerprint == compute_eval_fingerprint([])
