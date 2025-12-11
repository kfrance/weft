"""Tests for training_data_exporter module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lw_coder.training_data_exporter import (
    TrainingDataExportError,
    copy_code_trace,
    copy_human_feedback,
    copy_judge_results,
    copy_plan_file,
    copy_test_results,
    create_training_data,
    validate_training_data,
)


class TestCopyPlanFile:
    """Tests for copy_plan_file function."""

    def test_copies_plan_file_to_staging(self, tmp_path: Path) -> None:
        """Copies plan file to staging directory."""
        # Create plan file
        tasks_dir = tmp_path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)
        plan_file = tasks_dir / "test-plan.md"
        plan_file.write_text("# Test Plan\n\nThis is the plan.")

        staging = tmp_path / "staging"
        staging.mkdir()

        copy_plan_file("test-plan", tmp_path, staging)

        copied = staging / "plan.md"
        assert copied.exists()
        assert "Test Plan" in copied.read_text()

    def test_raises_when_plan_not_found(self, tmp_path: Path) -> None:
        """Raises TrainingDataExportError when plan file doesn't exist."""
        staging = tmp_path / "staging"
        staging.mkdir()

        with pytest.raises(TrainingDataExportError, match="Plan file not found"):
            copy_plan_file("missing-plan", tmp_path, staging)


class TestCopyCodeTrace:
    """Tests for copy_code_trace function."""

    def test_copies_trace_to_staging(self, tmp_path: Path) -> None:
        """Copies code trace to staging directory."""
        # Create trace file
        code_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "code"
        code_dir.mkdir(parents=True)
        trace_file = code_dir / "trace.md"
        trace_file.write_text("# Code Trace\n\nThis is the trace.")

        staging = tmp_path / "staging"
        staging.mkdir()

        warning = copy_code_trace("test-plan", tmp_path, staging)

        assert warning is None
        copied = staging / "code_trace.md"
        assert copied.exists()
        assert "Code Trace" in copied.read_text()

    def test_returns_warning_when_trace_missing(self, tmp_path: Path) -> None:
        """Returns warning message when trace file doesn't exist."""
        staging = tmp_path / "staging"
        staging.mkdir()

        warning = copy_code_trace("test-plan", tmp_path, staging)

        assert warning is not None
        assert "not found" in warning.lower()


class TestCopyTestResults:
    """Tests for copy_test_results function."""

    def test_copies_after_tests(self, tmp_path: Path) -> None:
        """Copies after-test results to staging."""
        # Create eval directory with test results
        eval_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)

        after_results = {"command": "pytest", "exit_code": 0, "total_tests": 10}
        (eval_dir / "test_results_after.json").write_text(json.dumps(after_results))

        staging = tmp_path / "staging"
        staging.mkdir()

        copy_test_results("test-plan", tmp_path, staging)

        copied = staging / "test_results_after.json"
        assert copied.exists()
        assert json.loads(copied.read_text())["total_tests"] == 10

    def test_copies_before_tests_when_available(self, tmp_path: Path) -> None:
        """Copies before-test results when they exist."""
        eval_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)

        after_results = {"command": "pytest", "exit_code": 0, "total_tests": 10}
        before_results = {"command": "pytest", "exit_code": 1, "total_tests": 10}
        (eval_dir / "test_results_after.json").write_text(json.dumps(after_results))
        (eval_dir / "test_results_before.json").write_text(json.dumps(before_results))

        staging = tmp_path / "staging"
        staging.mkdir()

        copy_test_results("test-plan", tmp_path, staging)

        assert (staging / "test_results_after.json").exists()
        assert (staging / "test_results_before.json").exists()

    def test_raises_when_after_tests_missing(self, tmp_path: Path) -> None:
        """Raises TrainingDataExportError when after-test results missing."""
        eval_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)

        staging = tmp_path / "staging"
        staging.mkdir()

        with pytest.raises(TrainingDataExportError, match="After-test results not found"):
            copy_test_results("test-plan", tmp_path, staging)


class TestCopyJudgeResults:
    """Tests for copy_judge_results function."""

    def test_copies_all_judge_files(self, tmp_path: Path) -> None:
        """Copies all judge JSON and markdown files."""
        eval_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)

        # Create judge files
        (eval_dir / "judge_code-reuse.json").write_text('{"score": 0.85}')
        (eval_dir / "judge_code-reuse.md").write_text("# Code Reuse\n\nScore: 0.85")
        (eval_dir / "judge_plan-compliance.json").write_text('{"score": 0.90}')
        (eval_dir / "judge_plan-compliance.md").write_text("# Plan Compliance\n\nScore: 0.90")

        staging = tmp_path / "staging"
        staging.mkdir()

        copy_judge_results("test-plan", tmp_path, staging)

        assert (staging / "judge_code-reuse.json").exists()
        assert (staging / "judge_code-reuse.md").exists()
        assert (staging / "judge_plan-compliance.json").exists()
        assert (staging / "judge_plan-compliance.md").exists()

    def test_raises_when_no_judge_files(self, tmp_path: Path) -> None:
        """Raises TrainingDataExportError when no judge files exist."""
        eval_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)

        staging = tmp_path / "staging"
        staging.mkdir()

        with pytest.raises(TrainingDataExportError, match="No judge result files found"):
            copy_judge_results("test-plan", tmp_path, staging)


class TestCopyHumanFeedback:
    """Tests for copy_human_feedback function."""

    def test_copies_feedback_to_staging(self, tmp_path: Path) -> None:
        """Copies human feedback to staging directory."""
        eval_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "human_feedback.md").write_text("# Feedback\n\nGreat work!")

        staging = tmp_path / "staging"
        staging.mkdir()

        copy_human_feedback("test-plan", tmp_path, staging)

        copied = staging / "human_feedback.md"
        assert copied.exists()
        assert "Great work!" in copied.read_text()

    def test_raises_when_feedback_missing(self, tmp_path: Path) -> None:
        """Raises TrainingDataExportError when feedback file doesn't exist."""
        staging = tmp_path / "staging"
        staging.mkdir()

        with pytest.raises(TrainingDataExportError, match="Human feedback not found"):
            copy_human_feedback("test-plan", tmp_path, staging)


class TestValidateTrainingData:
    """Tests for validate_training_data function."""

    def test_returns_empty_list_when_valid(self, tmp_path: Path) -> None:
        """Returns empty list when all required files exist."""
        # Create all required files
        (tmp_path / "plan.md").write_text("# Plan")
        (tmp_path / "code_trace.md").write_text("# Trace")
        (tmp_path / "test_results_after.json").write_text("{}")
        (tmp_path / "test_results_before.json").write_text("{}")
        (tmp_path / "human_feedback.md").write_text("# Feedback")
        (tmp_path / "judge_test.json").write_text("{}")

        warnings = validate_training_data(tmp_path)

        # Filter to only required warnings (not optional warnings)
        required_warnings = [w for w in warnings if "required" in w.lower()]
        assert required_warnings == []

    def test_warns_on_missing_optional_files(self, tmp_path: Path) -> None:
        """Returns warnings for missing optional files."""
        # Create only required files
        (tmp_path / "plan.md").write_text("# Plan")
        (tmp_path / "test_results_after.json").write_text("{}")
        (tmp_path / "human_feedback.md").write_text("# Feedback")
        (tmp_path / "judge_test.json").write_text("{}")
        # Missing: code_trace.md, test_results_before.json

        warnings = validate_training_data(tmp_path)

        optional_warnings = [w for w in warnings if "optional" in w.lower()]
        assert len(optional_warnings) >= 1

    def test_warns_on_missing_required_files(self, tmp_path: Path) -> None:
        """Returns warnings for missing required files."""
        # Create only some files
        (tmp_path / "plan.md").write_text("# Plan")
        # Missing: test_results_after.json, human_feedback.md, judge files

        warnings = validate_training_data(tmp_path)

        required_warnings = [w for w in warnings if "required" in w.lower()]
        assert len(required_warnings) >= 1

    def test_warns_when_no_judge_files(self, tmp_path: Path) -> None:
        """Returns warning when no judge result files exist."""
        (tmp_path / "plan.md").write_text("# Plan")
        (tmp_path / "test_results_after.json").write_text("{}")
        (tmp_path / "human_feedback.md").write_text("# Feedback")
        # No judge_*.json files

        warnings = validate_training_data(tmp_path)

        judge_warnings = [w for w in warnings if "judge" in w.lower()]
        assert len(judge_warnings) >= 1


class TestCreateTrainingData:
    """Tests for create_training_data function."""

    def test_creates_training_data_directory(self, tmp_path: Path) -> None:
        """Creates training data directory with all files."""
        # Set up source files
        tasks_dir = tmp_path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "test-plan.md").write_text("# Plan")

        code_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "code"
        code_dir.mkdir(parents=True)
        (code_dir / "trace.md").write_text("# Trace")

        eval_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "test_results_after.json").write_text('{"exit_code": 0}')
        (eval_dir / "judge_test.json").write_text('{"score": 0.85}')
        (eval_dir / "judge_test.md").write_text("# Judge")
        (eval_dir / "human_feedback.md").write_text("# Feedback")

        result = create_training_data("test-plan", tmp_path)

        assert result.exists()
        assert (result / "plan.md").exists()
        assert (result / "code_trace.md").exists()
        assert (result / "test_results_after.json").exists()
        assert (result / "judge_test.json").exists()
        assert (result / "human_feedback.md").exists()

    def test_skips_when_already_exists(self, tmp_path: Path) -> None:
        """Returns existing directory when training data already exists."""
        training_dir = tmp_path / ".lw_coder" / "training_data" / "test-plan"
        training_dir.mkdir(parents=True)
        (training_dir / "plan.md").write_text("# Existing")

        result = create_training_data("test-plan", tmp_path)

        assert result == training_dir
        assert "Existing" in (result / "plan.md").read_text()

    def test_atomic_operation_on_failure(self, tmp_path: Path, monkeypatch) -> None:
        """Does not create training_data directory if any copy fails."""
        # Set up only plan file (missing everything else)
        tasks_dir = tmp_path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "test-plan.md").write_text("# Plan")

        training_dir = tmp_path / ".lw_coder" / "training_data" / "test-plan"

        # Mock input to continue past missing code trace prompt
        monkeypatch.setattr("builtins.input", lambda _: "y")

        with pytest.raises(TrainingDataExportError):
            create_training_data("test-plan", tmp_path)

        # Training data directory should not exist
        assert not training_dir.exists()

    def test_warns_on_missing_code_trace(self, tmp_path: Path, monkeypatch) -> None:
        """Warns but continues when code trace is missing."""
        # Set up required files except code trace
        tasks_dir = tmp_path / ".lw_coder" / "tasks"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "test-plan.md").write_text("# Plan")

        eval_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "test_results_after.json").write_text('{"exit_code": 0}')
        (eval_dir / "judge_test.json").write_text('{"score": 0.85}')
        (eval_dir / "human_feedback.md").write_text("# Feedback")
        # No code trace

        # Mock input to continue past missing code trace prompt
        monkeypatch.setattr("builtins.input", lambda _: "y")

        result = create_training_data("test-plan", tmp_path)

        # Should still create training data
        assert result.exists()
        assert (result / "plan.md").exists()
        # But code_trace.md should not exist
        assert not (result / "code_trace.md").exists()


class TestPruningBehavior:
    """Tests to verify training_data is never pruned."""

    def test_training_data_not_in_sessions(self, tmp_path: Path) -> None:
        """Training data is stored separately from sessions (which get pruned)."""
        # Create both training_data and sessions
        training_dir = tmp_path / ".lw_coder" / "training_data" / "test-plan"
        training_dir.mkdir(parents=True)

        sessions_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan"
        sessions_dir.mkdir(parents=True)

        # Get the relative paths within .lw_coder to verify structure
        lw_coder_base = tmp_path / ".lw_coder"
        training_relative = training_dir.relative_to(lw_coder_base)
        sessions_relative = sessions_dir.relative_to(lw_coder_base)

        # Training data should be under training_data/, not sessions/
        assert str(training_relative).startswith("training_data")
        assert not str(training_relative).startswith("sessions")

        # Sessions should be under sessions/, not training_data/
        assert str(sessions_relative).startswith("sessions")
        assert not str(sessions_relative).startswith("training_data")

    def test_prune_old_sessions_preserves_training_data(self, tmp_path: Path) -> None:
        """Verify prune_old_sessions deletes sessions but never touches training_data."""
        import os
        import time

        from lw_coder.session_manager import SESSION_RETENTION_DAYS, prune_old_sessions

        # Create old session directory (will be pruned)
        old_plan_dir = tmp_path / ".lw_coder" / "sessions" / "test-plan"
        old_session_dir = old_plan_dir / "code"
        old_session_dir.mkdir(parents=True)
        (old_session_dir / "trace.md").write_text("# Old trace")

        # Set plan directory mtime to be older than retention period
        # (prune_old_sessions checks the plan_dir mtime, not subdirectory mtime)
        old_timestamp = time.time() - (SESSION_RETENTION_DAYS + 1) * 24 * 60 * 60
        os.utime(old_plan_dir, (old_timestamp, old_timestamp))

        # Create training_data directory (must NEVER be pruned)
        training_dir = tmp_path / ".lw_coder" / "training_data" / "test-plan"
        training_dir.mkdir(parents=True)
        (training_dir / "plan.md").write_text("# Training data plan")
        (training_dir / "code_trace.md").write_text("# Training data trace")

        # Also set training_data to be "old" to verify it's never touched
        os.utime(training_dir, (old_timestamp, old_timestamp))

        # Run pruning
        pruned_count = prune_old_sessions(tmp_path)

        # Verify old session was pruned
        assert pruned_count >= 1
        assert not old_plan_dir.exists()

        # Verify training_data is COMPLETELY UNTOUCHED
        assert training_dir.exists()
        assert (training_dir / "plan.md").exists()
        assert (training_dir / "code_trace.md").exists()
        assert "Training data plan" in (training_dir / "plan.md").read_text()
