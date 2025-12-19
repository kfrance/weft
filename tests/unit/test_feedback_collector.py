"""Tests for feedback_collector module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from weft.feedback_collector import (
    FeedbackCollectionError,
    build_feedback_prompt,
    collect_human_feedback,
)


class TestBuildFeedbackPrompt:
    """Tests for build_feedback_prompt function."""

    def test_includes_plan_id(self) -> None:
        """Prompt includes the plan_id."""
        prompt = build_feedback_prompt(
            plan_id="my-test-plan",
            judge_results=[],
        )

        assert "my-test-plan" in prompt

    def test_includes_judge_results(self) -> None:
        """Prompt includes formatted judge results."""
        judge_results = [
            {"judge_name": "code-reuse", "score": 0.85, "weight": 0.5, "feedback": "Good code reuse."},
            {"judge_name": "plan-compliance", "score": 0.90, "weight": 0.5, "feedback": "Plan followed well."},
        ]

        prompt = build_feedback_prompt(
            plan_id="test-plan",
            judge_results=judge_results,
        )

        assert "code-reuse" in prompt
        assert "plan-compliance" in prompt
        assert "0.85" in prompt
        assert "0.90" in prompt
        assert "Good code reuse." in prompt
        assert "Plan followed well." in prompt

    def test_calculates_weighted_score(self) -> None:
        """Prompt includes calculated weighted score."""
        judge_results = [
            {"judge_name": "judge-1", "score": 0.80, "weight": 0.5, "feedback": ""},
            {"judge_name": "judge-2", "score": 0.60, "weight": 0.5, "feedback": ""},
        ]

        prompt = build_feedback_prompt(
            plan_id="test-plan",
            judge_results=judge_results,
        )

        # Weighted score: (0.80 * 0.5 + 0.60 * 0.5) / (0.5 + 0.5) = 0.70
        assert "0.70" in prompt

    def test_includes_test_results_when_provided(self) -> None:
        """Prompt includes test results when provided."""
        test_before = {
            "total_tests": 100,
            "passed_tests": 95,
            "failed_tests": 5,
            "exit_code": 1,
        }
        test_after = {
            "total_tests": 100,
            "passed_tests": 100,
            "failed_tests": 0,
            "exit_code": 0,
        }

        prompt = build_feedback_prompt(
            plan_id="test-plan",
            judge_results=[],
            test_results_before=test_before,
            test_results_after=test_after,
        )

        assert "Before Implementation" in prompt
        assert "After Implementation" in prompt
        assert "95/100 passed" in prompt
        assert "100/100 passed" in prompt

    def test_handles_missing_test_results(self) -> None:
        """Prompt handles missing test results gracefully."""
        prompt = build_feedback_prompt(
            plan_id="test-plan",
            judge_results=[],
            test_results_before=None,
            test_results_after=None,
        )

        assert "Not available" in prompt

    def test_includes_instructions_for_feedback(self) -> None:
        """Prompt includes instructions for feedback collection."""
        prompt = build_feedback_prompt(
            plan_id="test-plan",
            judge_results=[],
        )

        assert "human_feedback.md" in prompt
        assert "compose feedback" in prompt.lower() or "compose" in prompt.lower()


class TestCollectHumanFeedback:
    """Tests for collect_human_feedback function."""

    def test_raises_when_sdk_settings_missing(self, tmp_path: Path) -> None:
        """Raises FeedbackCollectionError when SDK settings missing."""
        with patch("weft.feedback_collector.get_weft_src_dir") as mock_src:
            mock_src.return_value = tmp_path  # No sdk_settings.json

            with pytest.raises(FeedbackCollectionError, match="SDK settings file not found"):
                collect_human_feedback(
                    plan_id="test-plan",
                    repo_root=tmp_path,
                    output_dir=tmp_path,
                    model="haiku",
                    judge_results=[],
                )

    def test_raises_when_worktree_missing(self, tmp_path: Path) -> None:
        """Raises FeedbackCollectionError when worktree doesn't exist."""
        # Create SDK settings
        (tmp_path / "sdk_settings.json").write_text("{}")

        with patch("weft.feedback_collector.get_weft_src_dir") as mock_src:
            mock_src.return_value = tmp_path

            with pytest.raises(FeedbackCollectionError, match="Worktree not found"):
                collect_human_feedback(
                    plan_id="test-plan",
                    repo_root=tmp_path,
                    output_dir=tmp_path,
                    model="haiku",
                    judge_results=[],
                )

    def test_returns_none_when_user_cancels(self, tmp_path: Path) -> None:
        """Returns None when user cancels without creating feedback file."""
        # Create SDK settings and worktree
        (tmp_path / "sdk_settings.json").write_text("{}")
        worktree = tmp_path / ".weft" / "worktrees" / "test-plan"
        worktree.mkdir(parents=True)

        with patch("weft.feedback_collector.get_weft_src_dir") as mock_src:
            mock_src.return_value = tmp_path

            with patch("weft.feedback_collector.run_interactive_session") as mock_session:
                # Simulate user cancelling without creating file
                mock_session.return_value = ("session-123", None)

                result = collect_human_feedback(
                    plan_id="test-plan",
                    repo_root=tmp_path,
                    output_dir=tmp_path,
                    model="haiku",
                    judge_results=[],
                )

        assert result is None

    def test_copies_feedback_to_output_dir(self, tmp_path: Path) -> None:
        """Copies feedback file to output directory when created."""
        # Create SDK settings and worktree
        (tmp_path / "sdk_settings.json").write_text("{}")
        worktree = tmp_path / ".weft" / "worktrees" / "test-plan"
        worktree.mkdir(parents=True)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create the feedback file in worktree
        feedback_file = worktree / "human_feedback.md"
        feedback_file.write_text("# My Feedback\n\nThis is great!")

        with patch("weft.feedback_collector.get_weft_src_dir") as mock_src:
            mock_src.return_value = tmp_path

            with patch("weft.feedback_collector.run_interactive_session") as mock_session:
                mock_session.return_value = ("session-123", feedback_file)

                result = collect_human_feedback(
                    plan_id="test-plan",
                    repo_root=tmp_path,
                    output_dir=output_dir,
                    model="haiku",
                    judge_results=[],
                )

        assert result is not None
        assert result == output_dir / "human_feedback.md"
        assert result.exists()
        assert "My Feedback" in result.read_text()

    def test_raises_on_session_error(self, tmp_path: Path) -> None:
        """Raises FeedbackCollectionError when session fails."""
        # Create SDK settings and worktree
        (tmp_path / "sdk_settings.json").write_text("{}")
        worktree = tmp_path / ".weft" / "worktrees" / "test-plan"
        worktree.mkdir(parents=True)

        from weft.claude_session import ClaudeSessionError

        with patch("weft.feedback_collector.get_weft_src_dir") as mock_src:
            mock_src.return_value = tmp_path

            with patch("weft.feedback_collector.run_interactive_session") as mock_session:
                mock_session.side_effect = ClaudeSessionError("Session failed")

                with pytest.raises(FeedbackCollectionError, match="Feedback collection failed"):
                    collect_human_feedback(
                        plan_id="test-plan",
                        repo_root=tmp_path,
                        output_dir=tmp_path,
                        model="haiku",
                        judge_results=[],
                    )

    def test_cleans_up_worktree_copy(self, tmp_path: Path) -> None:
        """Removes feedback file from worktree after copying."""
        # Create SDK settings and worktree
        (tmp_path / "sdk_settings.json").write_text("{}")
        worktree = tmp_path / ".weft" / "worktrees" / "test-plan"
        worktree.mkdir(parents=True)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Create the feedback file in worktree
        feedback_file = worktree / "human_feedback.md"
        feedback_file.write_text("# Feedback")

        with patch("weft.feedback_collector.get_weft_src_dir") as mock_src:
            mock_src.return_value = tmp_path

            with patch("weft.feedback_collector.run_interactive_session") as mock_session:
                mock_session.return_value = ("session-123", feedback_file)

                collect_human_feedback(
                    plan_id="test-plan",
                    repo_root=tmp_path,
                    output_dir=output_dir,
                    model="haiku",
                    judge_results=[],
                )

        # Worktree copy should be removed
        assert not feedback_file.exists()
