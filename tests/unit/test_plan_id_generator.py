"""Unit tests for plan_id_generator module.

These tests verify the plan_id generation logic using mocks.
They do not make any external API calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weft.plan_id_generator import (
    PlanIdGenerationError,
    PlanIdRequest,
    PlanIdResult,
    _clean_plan_id,
    _parse_numbered_list,
    _validate_plan_id,
    generate_plan_id,
    generate_plan_ids_batch,
)


class TestCleanPlanId:
    """Tests for _clean_plan_id function."""

    def test_strips_whitespace(self) -> None:
        """Verify whitespace is stripped."""
        assert _clean_plan_id("  my-plan  ") == "my-plan"

    def test_removes_double_quotes(self) -> None:
        """Verify double quotes are removed."""
        assert _clean_plan_id('"my-plan"') == "my-plan"

    def test_removes_single_quotes(self) -> None:
        """Verify single quotes are removed."""
        assert _clean_plan_id("'my-plan'") == "my-plan"

    def test_strips_whitespace_after_quote_removal(self) -> None:
        """Verify whitespace is stripped after quote removal."""
        assert _clean_plan_id('  "my-plan"  ') == "my-plan"

    def test_leaves_valid_id_unchanged(self) -> None:
        """Verify valid IDs are unchanged."""
        assert _clean_plan_id("my-plan-123") == "my-plan-123"


class TestValidatePlanId:
    """Tests for _validate_plan_id function."""

    def test_valid_simple_id(self) -> None:
        """Verify simple valid IDs pass."""
        _validate_plan_id("my-plan")  # Should not raise

    def test_valid_id_with_dots(self) -> None:
        """Verify IDs with dots pass."""
        _validate_plan_id("feature.auth")  # Should not raise

    def test_valid_id_with_underscores(self) -> None:
        """Verify IDs with underscores pass."""
        _validate_plan_id("my_plan_v2")  # Should not raise

    def test_valid_id_with_numbers(self) -> None:
        """Verify IDs with numbers pass."""
        _validate_plan_id("plan-123")  # Should not raise

    def test_invalid_too_short(self) -> None:
        """Verify IDs that are too short fail."""
        with pytest.raises(PlanIdGenerationError, match="does not match"):
            _validate_plan_id("ab")

    def test_invalid_too_long(self) -> None:
        """Verify IDs that are too long fail."""
        long_id = "a" * 101
        with pytest.raises(PlanIdGenerationError, match="does not match"):
            _validate_plan_id(long_id)

    def test_invalid_characters(self) -> None:
        """Verify IDs with invalid characters fail."""
        with pytest.raises(PlanIdGenerationError, match="does not match"):
            _validate_plan_id("my plan")  # space

        with pytest.raises(PlanIdGenerationError, match="does not match"):
            _validate_plan_id("my@plan")  # @ symbol


class TestParseNumberedList:
    """Tests for _parse_numbered_list function."""

    def test_parses_simple_numbered_list(self) -> None:
        """Verify simple numbered list parsing."""
        text = """1. plan-one
2. plan-two
3. plan-three"""
        result = _parse_numbered_list(text, 3)
        assert result == ["plan-one", "plan-two", "plan-three"]

    def test_parses_with_parentheses(self) -> None:
        """Verify parsing with parentheses format."""
        text = """1) plan-one
2) plan-two"""
        result = _parse_numbered_list(text, 2)
        assert result == ["plan-one", "plan-two"]

    def test_handles_extra_whitespace(self) -> None:
        """Verify extra whitespace is handled."""
        text = """
1.   plan-one
2.   plan-two

"""
        result = _parse_numbered_list(text, 2)
        assert result == ["plan-one", "plan-two"]

    def test_raises_on_count_mismatch(self) -> None:
        """Verify error on count mismatch."""
        text = """1. plan-one
2. plan-two"""
        with pytest.raises(PlanIdGenerationError, match="Expected 3 plan_ids but got 2"):
            _parse_numbered_list(text, 3)


class TestGeneratePlanIdBatch:
    """Tests for generate_plan_ids_batch function."""

    def test_empty_requests_returns_empty(self) -> None:
        """Verify empty request list returns empty result."""
        result = generate_plan_ids_batch([], set(), "fake-key", Path("/tmp"))
        assert result == []

    @patch("weft.plan_id_generator.create_lm")
    @patch("weft.plan_id_generator.dspy")
    def test_single_plan_uses_single_signature(
        self, mock_dspy: MagicMock, mock_create_lm: MagicMock, tmp_path: Path
    ) -> None:
        """Verify single plan uses PlanIdSignature."""
        # Setup mock
        mock_lm = MagicMock()
        mock_create_lm.return_value = mock_lm

        mock_predictor = MagicMock()
        mock_result = MagicMock()
        mock_result.plan_id = "new-plan-id"
        mock_predictor.return_value = mock_result
        mock_dspy.Predict.return_value = mock_predictor

        # Create request
        request = PlanIdRequest(
            plan_content="# My Plan\nThis is a plan.",
            file_path=tmp_path / "old-plan.md",
        )

        # Call
        results = generate_plan_ids_batch(
            [request], {"existing-id"}, "fake-key", tmp_path
        )

        # Verify
        assert len(results) == 1
        assert results[0].new_plan_id == "new-plan-id"
        assert results[0].file_path == tmp_path / "old-plan.md"

    @patch("weft.plan_id_generator.create_lm")
    @patch("weft.plan_id_generator.dspy")
    def test_multiple_plans_uses_batch_signature(
        self, mock_dspy: MagicMock, mock_create_lm: MagicMock, tmp_path: Path
    ) -> None:
        """Verify multiple plans use BatchPlanIdSignature."""
        # Setup mock
        mock_lm = MagicMock()
        mock_create_lm.return_value = mock_lm

        mock_predictor = MagicMock()
        mock_result = MagicMock()
        mock_result.plan_ids = """1. plan-one
2. plan-two"""
        mock_predictor.return_value = mock_result
        mock_dspy.Predict.return_value = mock_predictor

        # Create requests
        requests = [
            PlanIdRequest(
                plan_content="# Plan One",
                file_path=tmp_path / "plan1.md",
            ),
            PlanIdRequest(
                plan_content="# Plan Two",
                file_path=tmp_path / "plan2.md",
            ),
        ]

        # Call
        results = generate_plan_ids_batch(
            requests, {"existing-id"}, "fake-key", tmp_path
        )

        # Verify
        assert len(results) == 2
        assert results[0].new_plan_id == "plan-one"
        assert results[1].new_plan_id == "plan-two"

    @patch("weft.plan_id_generator.create_lm")
    @patch("weft.plan_id_generator.dspy")
    def test_avoid_list_formatted_correctly(
        self, mock_dspy: MagicMock, mock_create_lm: MagicMock, tmp_path: Path
    ) -> None:
        """Verify avoid list is formatted as comma-separated string."""
        # Setup mock
        mock_lm = MagicMock()
        mock_create_lm.return_value = mock_lm

        mock_predictor = MagicMock()
        mock_result = MagicMock()
        mock_result.plan_id = "new-id"
        mock_predictor.return_value = mock_result
        mock_dspy.Predict.return_value = mock_predictor

        # Create request with multiple IDs to avoid
        request = PlanIdRequest(
            plan_content="# My Plan",
            file_path=tmp_path / "plan.md",
        )

        # Call
        generate_plan_ids_batch(
            [request], {"id-z", "id-a", "id-m"}, "fake-key", tmp_path
        )

        # Verify predictor was called with sorted, comma-separated list
        predictor_call = mock_predictor.call_args
        assert "id-a, id-m, id-z" in predictor_call.kwargs.get("plan_ids_to_avoid", "")

    @patch("weft.plan_id_generator.create_lm")
    def test_raises_on_invalid_generated_id(
        self, mock_create_lm: MagicMock, tmp_path: Path
    ) -> None:
        """Verify error is raised for invalid generated plan_id."""
        # Setup mock to return invalid plan_id
        mock_lm = MagicMock()
        mock_create_lm.return_value = mock_lm

        # Create request
        request = PlanIdRequest(
            plan_content="# My Plan",
            file_path=tmp_path / "plan.md",
        )

        with patch("weft.plan_id_generator.dspy") as mock_dspy:
            mock_predictor = MagicMock()
            mock_result = MagicMock()
            mock_result.plan_id = "a"  # Too short
            mock_predictor.return_value = mock_result
            mock_dspy.Predict.return_value = mock_predictor

            with pytest.raises(PlanIdGenerationError, match="does not match"):
                generate_plan_ids_batch([request], set(), "fake-key", tmp_path)


class TestGeneratePlanId:
    """Tests for generate_plan_id function (single-plan convenience wrapper)."""

    @patch("weft.plan_id_generator.generate_plan_ids_batch")
    def test_delegates_to_batch(
        self, mock_batch: MagicMock, tmp_path: Path
    ) -> None:
        """Verify single-plan function delegates to batch."""
        mock_result = PlanIdResult(
            file_path=tmp_path / "plan.md",
            new_plan_id="new-id",
        )
        mock_batch.return_value = [mock_result]

        request = PlanIdRequest(
            plan_content="# My Plan",
            file_path=tmp_path / "plan.md",
        )

        result = generate_plan_id(request, {"avoid"}, "key", tmp_path)

        assert result == mock_result
        mock_batch.assert_called_once_with([request], {"avoid"}, "key", tmp_path)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @patch("weft.plan_id_generator.create_lm")
    @patch("weft.plan_id_generator.dspy")
    def test_handles_empty_plan_content(
        self, mock_dspy: MagicMock, mock_create_lm: MagicMock, tmp_path: Path
    ) -> None:
        """Verify empty plan content is handled."""
        mock_lm = MagicMock()
        mock_create_lm.return_value = mock_lm

        mock_predictor = MagicMock()
        mock_result = MagicMock()
        mock_result.plan_id = "empty-plan"
        mock_predictor.return_value = mock_result
        mock_dspy.Predict.return_value = mock_predictor

        request = PlanIdRequest(
            plan_content="",
            file_path=tmp_path / "empty.md",
        )

        results = generate_plan_ids_batch([request], set(), "key", tmp_path)
        assert len(results) == 1
        assert results[0].new_plan_id == "empty-plan"

    @patch("weft.plan_id_generator.create_lm")
    @patch("weft.plan_id_generator.dspy")
    def test_handles_very_long_plan_content(
        self, mock_dspy: MagicMock, mock_create_lm: MagicMock, tmp_path: Path
    ) -> None:
        """Verify very long plan content is handled."""
        mock_lm = MagicMock()
        mock_create_lm.return_value = mock_lm

        mock_predictor = MagicMock()
        mock_result = MagicMock()
        mock_result.plan_id = "long-plan"
        mock_predictor.return_value = mock_result
        mock_dspy.Predict.return_value = mock_predictor

        # Very long content
        long_content = "# Long Plan\n" + "x" * 100000

        request = PlanIdRequest(
            plan_content=long_content,
            file_path=tmp_path / "long.md",
        )

        results = generate_plan_ids_batch([request], set(), "key", tmp_path)
        assert len(results) == 1
        assert results[0].new_plan_id == "long-plan"

    @patch("weft.plan_id_generator.create_lm")
    def test_propagates_lm_creation_error(
        self, mock_create_lm: MagicMock, tmp_path: Path
    ) -> None:
        """Verify LM creation errors are propagated."""
        from weft.judge_executor import JudgeExecutionError

        mock_create_lm.side_effect = JudgeExecutionError("API key invalid")

        request = PlanIdRequest(
            plan_content="# My Plan",
            file_path=tmp_path / "plan.md",
        )

        with pytest.raises(PlanIdGenerationError, match="Failed to generate plan_ids"):
            generate_plan_ids_batch([request], set(), "bad-key", tmp_path)
