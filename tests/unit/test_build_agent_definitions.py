"""Unit tests for _build_agent_definitions helper function.

These tests verify the helper function that creates AgentDefinition objects
for SDK execution from the prompts dictionary.
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from weft.code_command import _build_agent_definitions, AGENT_DESCRIPTIONS


class TestBuildAgentDefinitions:
    """Unit tests for the _build_agent_definitions helper function."""

    def test_builds_correct_agents(self):
        """Verify _build_agent_definitions creates correct AgentDefinition objects."""
        prompts = {
            "code_review_auditor": "Review the code for quality issues.",
            "plan_alignment_checker": "Check if implementation matches the plan.",
        }
        model = "sonnet"

        agents = _build_agent_definitions(prompts, model)

        # Verify both agents are created
        assert "code-review-auditor" in agents
        assert "plan-alignment-checker" in agents

        # Verify code-review-auditor
        code_review = agents["code-review-auditor"]
        assert isinstance(code_review, AgentDefinition)
        assert code_review.description == AGENT_DESCRIPTIONS["code-review-auditor"]
        assert code_review.prompt == "Review the code for quality issues."
        assert code_review.model == "sonnet"

        # Verify plan-alignment-checker
        plan_alignment = agents["plan-alignment-checker"]
        assert isinstance(plan_alignment, AgentDefinition)
        assert plan_alignment.description == AGENT_DESCRIPTIONS["plan-alignment-checker"]
        assert plan_alignment.prompt == "Check if implementation matches the plan."
        assert plan_alignment.model == "sonnet"

    def test_uses_provided_model(self):
        """Verify agent definitions use the model passed to the function."""
        prompts = {
            "code_review_auditor": "Review prompt",
            "plan_alignment_checker": "Alignment prompt",
        }

        # Test with different models
        for model in ["sonnet", "opus", "haiku"]:
            agents = _build_agent_definitions(prompts, model)
            assert agents["code-review-auditor"].model == model
            assert agents["plan-alignment-checker"].model == model

    def test_returns_dict_type(self):
        """Verify return type is dict[str, AgentDefinition]."""
        prompts = {
            "code_review_auditor": "Review prompt",
            "plan_alignment_checker": "Alignment prompt",
        }

        agents = _build_agent_definitions(prompts, "sonnet")

        assert isinstance(agents, dict)
        assert len(agents) == 2
        for name, agent in agents.items():
            assert isinstance(name, str)
            assert isinstance(agent, AgentDefinition)
