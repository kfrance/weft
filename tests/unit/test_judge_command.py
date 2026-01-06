"""Tests for judge command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


from weft.judge_command import (
    format_markdown,
    format_stdout,
    run_judge_command,
)
from weft.judge_executor import JudgeResult


# =============================================================================
# Formatting Tests
# =============================================================================


class TestFormatStdout:
    """Tests for format_stdout function."""

    def test_single_judge_output(self) -> None:
        """Test stdout formatting with a single judge result."""
        results = [
            JudgeResult(
                judge_name="code-reuse",
                score=0.85,
                feedback="Good code reuse patterns observed.",
                weight=0.4,
            )
        ]

        output = format_stdout(results)

        assert "Judge Results:" in output
        assert "code-reuse (score: 0.85, weight: 0.4)" in output
        assert "Good code reuse patterns observed." in output
        assert "Weighted average: 0.85" in output

    def test_multiple_judges_output(self) -> None:
        """Test stdout formatting with multiple judge results."""
        results = [
            JudgeResult(
                judge_name="code-reuse",
                score=0.85,
                feedback="The implementation properly reuses the existing validation\nutilities rather than reimplementing them.",
                weight=0.4,
            ),
            JudgeResult(
                judge_name="plan-compliance",
                score=0.92,
                feedback="The changes align well with the plan requirements.",
                weight=0.6,
            ),
        ]

        output = format_stdout(results)

        assert "Judge Results:" in output
        assert "code-reuse (score: 0.85, weight: 0.4)" in output
        assert "plan-compliance (score: 0.92, weight: 0.6)" in output
        assert "The implementation properly reuses" in output
        assert "The changes align well" in output
        # Weighted average: (0.85*0.4 + 0.92*0.6) / (0.4 + 0.6) = 0.892
        assert "Weighted average: 0.89" in output

    def test_multiline_feedback_indented(self) -> None:
        """Test that multiline feedback is properly indented."""
        results = [
            JudgeResult(
                judge_name="test-judge",
                score=0.75,
                feedback="Line one\nLine two\nLine three",
                weight=1.0,
            )
        ]

        output = format_stdout(results)

        # Each feedback line should be indented with 2 spaces
        assert "  Line one" in output
        assert "  Line two" in output
        assert "  Line three" in output

    def test_weighted_average_calculation(self) -> None:
        """Test weighted average calculation with different weights."""
        results = [
            JudgeResult(
                judge_name="judge-1",
                score=1.0,
                feedback="Perfect score",
                weight=0.5,
            ),
            JudgeResult(
                judge_name="judge-2",
                score=0.0,
                feedback="Zero score",
                weight=0.5,
            ),
        ]

        output = format_stdout(results)

        # Weighted average: (1.0*0.5 + 0.0*0.5) / (0.5 + 0.5) = 0.5
        assert "Weighted average: 0.50" in output

    def test_empty_results_list(self) -> None:
        """Test stdout formatting with empty results list."""
        results: list[JudgeResult] = []

        output = format_stdout(results)

        # Should have header but no weighted average (no division by zero)
        assert "Judge Results:" in output
        assert "Weighted average" not in output


class TestFormatMarkdown:
    """Tests for format_markdown function."""

    def test_markdown_header(self) -> None:
        """Test markdown output includes proper header with plan ID."""
        results = [
            JudgeResult(
                judge_name="test-judge",
                score=0.85,
                feedback="Test feedback.",
                weight=0.5,
            )
        ]

        output = format_markdown(results, "my-test-plan")

        assert "# Judge Results for my-test-plan" in output

    def test_markdown_summary_table(self) -> None:
        """Test markdown output includes summary table."""
        results = [
            JudgeResult(
                judge_name="code-reuse",
                score=0.85,
                feedback="Test feedback.",
                weight=0.4,
            ),
            JudgeResult(
                judge_name="plan-compliance",
                score=0.92,
                feedback="Test feedback.",
                weight=0.6,
            ),
        ]

        output = format_markdown(results, "test-plan")

        assert "## Summary" in output
        assert "| Judge | Score | Weight |" in output
        assert "| code-reuse | 0.85 | 0.4 |" in output
        assert "| plan-compliance | 0.92 | 0.6 |" in output

    def test_markdown_weighted_average(self) -> None:
        """Test markdown includes weighted average."""
        results = [
            JudgeResult(
                judge_name="judge-1",
                score=0.8,
                feedback="Feedback 1",
                weight=0.5,
            ),
            JudgeResult(
                judge_name="judge-2",
                score=0.6,
                feedback="Feedback 2",
                weight=0.5,
            ),
        ]

        output = format_markdown(results, "test-plan")

        # Weighted average: (0.8*0.5 + 0.6*0.5) / (0.5 + 0.5) = 0.7
        assert "**Weighted Average**: 0.70" in output

    def test_markdown_detailed_feedback(self) -> None:
        """Test markdown includes detailed feedback section."""
        results = [
            JudgeResult(
                judge_name="test-judge",
                score=0.85,
                feedback="Detailed feedback content here.",
                weight=0.5,
            )
        ]

        output = format_markdown(results, "test-plan")

        assert "## Detailed Feedback" in output
        assert "### test-judge" in output
        assert "**Score**: 0.85 / 1.00" in output
        assert "**Weight**: 0.5" in output
        assert "Detailed feedback content here." in output

    def test_markdown_empty_results_list(self) -> None:
        """Test markdown formatting with empty results list."""
        results: list[JudgeResult] = []

        output = format_markdown(results, "test-plan")

        # Should have header and structure but no weighted average
        assert "# Judge Results for test-plan" in output
        assert "## Summary" in output
        assert "**Weighted Average**" not in output


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestJudgeCommandErrors:
    """Tests for judge command error handling."""

    def test_not_in_git_repo(self, tmp_path: Path, monkeypatch) -> None:
        """Test error when not in a git repository."""
        # Create a non-git directory
        monkeypatch.chdir(tmp_path)

        exit_code = run_judge_command("test-plan")

        assert exit_code == 1

    def test_plan_not_found(self, tmp_path: Path, monkeypatch) -> None:
        """Test error when plan file doesn't exist."""
        monkeypatch.chdir(tmp_path)

        # Mock find_repo_root to succeed
        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            # Mock validate_worktree_exists to succeed
            worktree_path = tmp_path / ".weft" / "worktrees" / "nonexistent-plan"
            worktree_path.mkdir(parents=True)
            with patch("weft.judge_command.validate_worktree_exists", return_value=worktree_path):
                exit_code = run_judge_command("nonexistent-plan")

        assert exit_code == 1

    def test_worktree_not_found(self, tmp_path: Path, monkeypatch) -> None:
        """Test error when worktree doesn't exist."""
        monkeypatch.chdir(tmp_path)

        from weft.worktree_utils import WorktreeError

        # Mock find_repo_root to succeed
        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            # Mock validate_worktree_exists to raise WorktreeError
            with patch(
                "weft.judge_command.validate_worktree_exists",
                side_effect=WorktreeError("Worktree not found"),
            ):
                exit_code = run_judge_command("missing-worktree")

        assert exit_code == 1

    def test_no_judges_found_exception(self, tmp_path: Path, monkeypatch) -> None:
        """Test error when discover_judges raises JudgeLoaderError."""
        monkeypatch.chdir(tmp_path)

        from weft.judge_loader import JudgeLoaderError

        # Mock dependencies up to discover_judges
        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            worktree_path = tmp_path / ".weft" / "worktrees" / "test-plan"
            worktree_path.mkdir(parents=True)
            with patch("weft.judge_command.validate_worktree_exists", return_value=worktree_path):
                with patch("weft.judge_command.PlanResolver.resolve", return_value=tmp_path / "plan.md"):
                    with patch(
                        "weft.judge_command.discover_judges",
                        side_effect=JudgeLoaderError("No judge files found"),
                    ):
                        exit_code = run_judge_command("test-plan")

        assert exit_code == 1

    def test_no_judges_found_empty_list(self, tmp_path: Path, monkeypatch) -> None:
        """Test error when discover_judges returns empty list."""
        monkeypatch.chdir(tmp_path)

        # Mock dependencies up to discover_judges
        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            worktree_path = tmp_path / ".weft" / "worktrees" / "test-plan"
            worktree_path.mkdir(parents=True)
            with patch("weft.judge_command.validate_worktree_exists", return_value=worktree_path):
                with patch("weft.judge_command.PlanResolver.resolve", return_value=tmp_path / "plan.md"):
                    # Return empty list instead of exception
                    with patch("weft.judge_command.discover_judges", return_value=[]):
                        exit_code = run_judge_command("test-plan")

        assert exit_code == 1

    def test_judge_execution_failure(self, tmp_path: Path, monkeypatch) -> None:
        """Test error when judge execution fails."""
        monkeypatch.chdir(tmp_path)

        from weft.judge_loader import JudgeConfig
        from weft.judge_orchestrator import JudgeOrchestrationError

        mock_judge = JudgeConfig(
            name="test-judge",
            weight=0.5,
            model="test-model",
            instructions="Test instructions",
            file_path=tmp_path / "judge.md",
        )

        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            worktree_path = tmp_path / ".weft" / "worktrees" / "test-plan"
            worktree_path.mkdir(parents=True)
            with patch("weft.judge_command.validate_worktree_exists", return_value=worktree_path):
                with patch("weft.judge_command.PlanResolver.resolve", return_value=tmp_path / "plan.md"):
                    with patch("weft.judge_command.discover_judges", return_value=[mock_judge]):
                        with patch("weft.judge_command.gather_git_context", return_value=("plan", "changes")):
                            with patch("weft.judge_command.get_openrouter_api_key", return_value="test-key"):
                                with patch("weft.judge_command.get_cache_dir", return_value=tmp_path / "cache"):
                                    with patch(
                                        "weft.judge_command.execute_judges_parallel",
                                        side_effect=JudgeOrchestrationError("Judge failed"),
                                    ):
                                        exit_code = run_judge_command("test-plan")

        assert exit_code == 1

    def test_api_key_not_found(self, tmp_path: Path, monkeypatch) -> None:
        """Test error when API key is not found."""
        monkeypatch.chdir(tmp_path)

        from weft.judge_executor import JudgeExecutionError
        from weft.judge_loader import JudgeConfig

        mock_judge = JudgeConfig(
            name="test-judge",
            weight=0.5,
            model="test-model",
            instructions="Test instructions",
            file_path=tmp_path / "judge.md",
        )

        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            worktree_path = tmp_path / ".weft" / "worktrees" / "test-plan"
            worktree_path.mkdir(parents=True)
            with patch("weft.judge_command.validate_worktree_exists", return_value=worktree_path):
                with patch("weft.judge_command.PlanResolver.resolve", return_value=tmp_path / "plan.md"):
                    with patch("weft.judge_command.discover_judges", return_value=[mock_judge]):
                        with patch("weft.judge_command.gather_git_context", return_value=("plan", "changes")):
                            with patch(
                                "weft.judge_command.get_openrouter_api_key",
                                side_effect=JudgeExecutionError("OPENROUTER_API_KEY not found"),
                            ):
                                exit_code = run_judge_command("test-plan")

        assert exit_code == 1

    def test_git_context_error(self, tmp_path: Path, monkeypatch) -> None:
        """Test error when git context gathering fails."""
        monkeypatch.chdir(tmp_path)

        from weft.git_context import GitContextError
        from weft.judge_loader import JudgeConfig

        mock_judge = JudgeConfig(
            name="test-judge",
            weight=0.5,
            model="test-model",
            instructions="Test instructions",
            file_path=tmp_path / "judge.md",
        )

        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            worktree_path = tmp_path / ".weft" / "worktrees" / "test-plan"
            worktree_path.mkdir(parents=True)
            with patch("weft.judge_command.validate_worktree_exists", return_value=worktree_path):
                with patch("weft.judge_command.PlanResolver.resolve", return_value=tmp_path / "plan.md"):
                    with patch("weft.judge_command.discover_judges", return_value=[mock_judge]):
                        with patch(
                            "weft.judge_command.gather_git_context",
                            side_effect=GitContextError("Git command failed"),
                        ):
                            exit_code = run_judge_command("test-plan")

        assert exit_code == 1


# =============================================================================
# Successful Execution Tests
# =============================================================================


class TestJudgeCommandSuccess:
    """Tests for successful judge command execution."""

    def test_successful_execution_stdout(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Test successful execution outputs to stdout."""
        monkeypatch.chdir(tmp_path)

        from weft.judge_loader import JudgeConfig

        mock_judge = JudgeConfig(
            name="test-judge",
            weight=0.5,
            model="test-model",
            instructions="Test instructions",
            file_path=tmp_path / "judge.md",
        )

        mock_result = JudgeResult(
            judge_name="test-judge",
            score=0.85,
            feedback="Test feedback content.",
            weight=0.5,
        )

        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            worktree_path = tmp_path / ".weft" / "worktrees" / "test-plan"
            worktree_path.mkdir(parents=True)
            with patch("weft.judge_command.validate_worktree_exists", return_value=worktree_path):
                with patch("weft.judge_command.PlanResolver.resolve", return_value=tmp_path / "plan.md"):
                    with patch("weft.judge_command.discover_judges", return_value=[mock_judge]):
                        with patch("weft.judge_command.gather_git_context", return_value=("plan", "changes")):
                            with patch("weft.judge_command.get_openrouter_api_key", return_value="test-key"):
                                with patch("weft.judge_command.get_cache_dir", return_value=tmp_path / "cache"):
                                    with patch("weft.judge_command.execute_judges_parallel", return_value=[mock_result]):
                                        exit_code = run_judge_command("test-plan")

        assert exit_code == 0

        captured = capsys.readouterr()
        assert "Judge Results:" in captured.out
        assert "test-judge (score: 0.85, weight: 0.5)" in captured.out
        assert "Test feedback content." in captured.out
        assert "Weighted average: 0.85" in captured.out

    def test_successful_execution_with_output_dir(self, tmp_path: Path, monkeypatch) -> None:
        """Test successful execution saves markdown to output directory."""
        monkeypatch.chdir(tmp_path)

        from weft.judge_loader import JudgeConfig

        mock_judge = JudgeConfig(
            name="test-judge",
            weight=0.5,
            model="test-model",
            instructions="Test instructions",
            file_path=tmp_path / "judge.md",
        )

        mock_result = JudgeResult(
            judge_name="test-judge",
            score=0.85,
            feedback="Test feedback content.",
            weight=0.5,
        )

        output_dir = tmp_path / "output"

        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            worktree_path = tmp_path / ".weft" / "worktrees" / "test-plan"
            worktree_path.mkdir(parents=True)
            with patch("weft.judge_command.validate_worktree_exists", return_value=worktree_path):
                with patch("weft.judge_command.PlanResolver.resolve", return_value=tmp_path / "plan.md"):
                    with patch("weft.judge_command.discover_judges", return_value=[mock_judge]):
                        with patch("weft.judge_command.gather_git_context", return_value=("plan", "changes")):
                            with patch("weft.judge_command.get_openrouter_api_key", return_value="test-key"):
                                with patch("weft.judge_command.get_cache_dir", return_value=tmp_path / "cache"):
                                    with patch("weft.judge_command.execute_judges_parallel", return_value=[mock_result]):
                                        exit_code = run_judge_command("test-plan", output_dir=str(output_dir))

        assert exit_code == 0

        # Check markdown file was created
        md_file = output_dir / "judge-results-test-plan.md"
        assert md_file.exists()

        content = md_file.read_text()
        assert "# Judge Results for test-plan" in content
        assert "test-judge" in content
        assert "0.85" in content
        assert "Test feedback content." in content

    def test_plan_id_extraction_from_path(self, tmp_path: Path, monkeypatch, capsys) -> None:
        """Test that plan_id is properly extracted from full path."""
        monkeypatch.chdir(tmp_path)

        from weft.judge_loader import JudgeConfig

        mock_judge = JudgeConfig(
            name="test-judge",
            weight=0.5,
            model="test-model",
            instructions="Test instructions",
            file_path=tmp_path / "judge.md",
        )

        mock_result = JudgeResult(
            judge_name="test-judge",
            score=0.85,
            feedback="Test feedback.",
            weight=0.5,
        )

        with patch("weft.judge_command.find_repo_root", return_value=tmp_path):
            worktree_path = tmp_path / ".weft" / "worktrees" / "my-feature"
            worktree_path.mkdir(parents=True)
            with patch("weft.judge_command.validate_worktree_exists", return_value=worktree_path):
                with patch("weft.judge_command.PlanResolver.resolve", return_value=tmp_path / "plan.md"):
                    with patch("weft.judge_command.discover_judges", return_value=[mock_judge]):
                        with patch("weft.judge_command.gather_git_context", return_value=("plan", "changes")):
                            with patch("weft.judge_command.get_openrouter_api_key", return_value="test-key"):
                                with patch("weft.judge_command.get_cache_dir", return_value=tmp_path / "cache"):
                                    with patch("weft.judge_command.execute_judges_parallel", return_value=[mock_result]):
                                        # Pass full path instead of just plan ID
                                        exit_code = run_judge_command(".weft/tasks/my-feature.md")

        assert exit_code == 0
