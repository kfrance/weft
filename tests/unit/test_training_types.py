"""Tests for training_types module."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from weft.training_types import (
    CandidatePrompts,
    CurrentPrompts,
    SubagentDefinition,
    TrainingSample,
)


class TestTrainingSample:
    """Tests for TrainingSample model."""

    def test_training_sample_validation(self) -> None:
        """TrainingSample validates required fields."""
        sample = TrainingSample(
            plan_id="test-plan",
            plan_content="# Test Plan\n\nObjectives...",
            code_trace="Tool calls...",
            human_feedback="Agent performed well.",
            judge_results="## Judge: code-reuse\nScore: 0.9",
            test_results_before='{"passed": 10, "failed": 0}',
            test_results_after='{"passed": 11, "failed": 0}',
        )
        assert sample.plan_id == "test-plan"
        assert sample.plan_content == "# Test Plan\n\nObjectives..."
        assert sample.human_feedback == "Agent performed well."

    def test_training_sample_optional_fields_default(self) -> None:
        """TrainingSample allows optional fields to be empty."""
        sample = TrainingSample(
            plan_id="test-plan",
            plan_content="# Plan",
            human_feedback="Feedback",
            judge_results="Results",
            test_results_after='{"passed": 10}',
        )
        # Optional fields should default to empty string
        assert sample.code_trace == ""
        assert sample.test_results_before == ""

    def test_training_sample_missing_required_field(self) -> None:
        """TrainingSample raises error for missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            TrainingSample(
                plan_id="test-plan",
                plan_content="# Plan",
                # Missing human_feedback
                judge_results="Results",
                test_results_after='{"passed": 10}',
            )
        assert "human_feedback" in str(exc_info.value)


class TestSubagentDefinition:
    """Tests for SubagentDefinition model."""

    def test_subagent_definition_validation(self) -> None:
        """SubagentDefinition validates name/description/prompt."""
        subagent = SubagentDefinition(
            name="code-review-auditor",
            description="Reviews code for quality issues",
            prompt="You are a code review expert...",
        )
        assert subagent.name == "code-review-auditor"
        assert subagent.description == "Reviews code for quality issues"
        assert subagent.prompt == "You are a code review expert..."

    def test_subagent_definition_empty_name_fails(self) -> None:
        """SubagentDefinition rejects empty name."""
        with pytest.raises(ValidationError) as exc_info:
            SubagentDefinition(
                name="",
                description="Description",
                prompt="Prompt content",
            )
        assert "name" in str(exc_info.value)

    def test_subagent_definition_empty_description_fails(self) -> None:
        """SubagentDefinition rejects empty description."""
        with pytest.raises(ValidationError) as exc_info:
            SubagentDefinition(
                name="test-agent",
                description="",
                prompt="Prompt content",
            )
        assert "description" in str(exc_info.value)

    def test_subagent_definition_empty_prompt_fails(self) -> None:
        """SubagentDefinition rejects empty prompt."""
        with pytest.raises(ValidationError) as exc_info:
            SubagentDefinition(
                name="test-agent",
                description="Description",
                prompt="",
            )
        assert "prompt" in str(exc_info.value)


class TestCurrentPrompts:
    """Tests for CurrentPrompts model."""

    def test_current_prompts_with_subagents(self) -> None:
        """CurrentPrompts accepts list of subagents."""
        subagent = SubagentDefinition(
            name="code-review-auditor",
            description="Reviews code",
            prompt="Review prompt...",
        )
        prompts = CurrentPrompts(
            main_prompt="Main system prompt...",
            subagents=[subagent],
        )
        assert prompts.main_prompt == "Main system prompt..."
        assert len(prompts.subagents) == 1
        assert prompts.subagents[0].name == "code-review-auditor"

    def test_current_prompts_empty_subagents(self) -> None:
        """CurrentPrompts accepts empty subagents list."""
        prompts = CurrentPrompts(
            main_prompt="Main system prompt...",
            subagents=[],
        )
        assert prompts.main_prompt == "Main system prompt..."
        assert prompts.subagents == []

    def test_current_prompts_default_subagents(self) -> None:
        """CurrentPrompts defaults to empty subagents list."""
        prompts = CurrentPrompts(main_prompt="Main system prompt...")
        assert prompts.subagents == []


class TestCandidatePrompts:
    """Tests for CandidatePrompts model."""

    def test_candidate_prompts_subagent_list(self) -> None:
        """CandidatePrompts accepts list of subagents."""
        subagents = [
            SubagentDefinition(
                name="code-review-auditor",
                description="Reviews code",
                prompt="Review prompt...",
            ),
            SubagentDefinition(
                name="test-validator",
                description="Validates tests",
                prompt="Test prompt...",
            ),
        ]
        candidate = CandidatePrompts(
            main_prompt="Improved main prompt...",
            subagents=subagents,
            analysis_summary="Made improvements to X and Y.",
        )
        assert candidate.main_prompt == "Improved main prompt..."
        assert len(candidate.subagents) == 2
        assert candidate.subagents[0].name == "code-review-auditor"
        assert candidate.subagents[1].name == "test-validator"
        assert candidate.analysis_summary == "Made improvements to X and Y."

    def test_candidate_prompts_empty_subagents(self) -> None:
        """CandidatePrompts accepts empty subagents list."""
        candidate = CandidatePrompts(
            main_prompt="Main prompt...",
            subagents=[],
            analysis_summary="No subagents needed.",
        )
        assert candidate.subagents == []

    def test_candidate_prompts_missing_analysis_fails(self) -> None:
        """CandidatePrompts requires analysis_summary."""
        with pytest.raises(ValidationError) as exc_info:
            CandidatePrompts(
                main_prompt="Main prompt...",
                subagents=[],
                # Missing analysis_summary
            )
        assert "analysis_summary" in str(exc_info.value)
