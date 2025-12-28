"""Tests for eval command."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weft.eval_command import (
    format_judge_markdown,
    format_judge_results,
    run_eval_command,
    save_judge_results,
)
from weft.judge_executor import JudgeResult


def test_format_judge_results() -> None:
    """Test formatting of judge results for console output."""
    results = [
        JudgeResult(
            judge_name="test-judge-1",
            score=0.85,
            feedback="Good code quality overall. Some minor issues.",
            weight=0.4,
        ),
        JudgeResult(
            judge_name="test-judge-2",
            score=0.92,
            feedback="Excellent plan compliance.",
            weight=0.6,
        ),
    ]

    plan_id = "test-plan"
    worktree_path = Path(".weft/worktrees/test-plan")

    output = format_judge_results(results, plan_id, worktree_path)

    # Console output shows scores but not full feedback (per plan)
    assert "test-plan" in output
    assert "test-judge-1" in output
    assert "test-judge-2" in output
    assert "0.85" in output
    assert "0.92" in output
    # Feedback is NOT in console output anymore (only in markdown files)
    assert "weight:" in output.lower()
    assert "Overall Weighted Score" in output


def test_format_judge_results_weighted_score() -> None:
    """Test weighted score calculation in formatted output."""
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

    plan_id = "test-plan"
    worktree_path = Path(".weft/worktrees/test-plan")

    output = format_judge_results(results, plan_id, worktree_path)

    # Weighted score should be (0.8 * 0.5 + 0.6 * 0.5) / (0.5 + 0.5) = 0.7
    assert "0.70" in output


def test_format_judge_markdown() -> None:
    """Test formatting of judge result as markdown."""
    result = JudgeResult(
        judge_name="test-judge",
        score=0.85,
        feedback="This is detailed feedback.",
        weight=0.5,
    )

    markdown = format_judge_markdown(result)

    assert "# Judge: test-judge" in markdown
    assert "**Weight**: 0.50" in markdown
    assert "**Score**: 0.85" in markdown
    assert "This is detailed feedback." in markdown


def test_save_judge_results(tmp_path: Path) -> None:
    """Test saving judge results to JSON and markdown files."""
    eval_dir = tmp_path / "eval"
    results = [
        JudgeResult(
            judge_name="test-judge",
            score=0.85,
            feedback="Test feedback content.",
            weight=0.5,
        )
    ]

    save_judge_results(results, eval_dir)

    # Check JSON file
    json_path = eval_dir / "judge_test-judge.json"
    assert json_path.exists()
    json_data = json.loads(json_path.read_text())
    assert json_data["judge_name"] == "test-judge"
    assert json_data["score"] == 0.85
    assert json_data["weight"] == 0.5
    assert json_data["feedback"] == "Test feedback content."

    # Check markdown file
    md_path = eval_dir / "judge_test-judge.md"
    assert md_path.exists()
    md_content = md_path.read_text()
    assert "# Judge: test-judge" in md_content
    assert "Test feedback content." in md_content


def test_run_eval_command_worktree_not_found(tmp_path: Path, monkeypatch) -> None:
    """Test eval command when worktree doesn't exist."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create a plan file
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    plan_file.write_text(
        """---
plan_id: test-plan
status: coding
---

# Test Plan
"""
    )

    # Don't create worktree
    exit_code = run_eval_command("test-plan")

    assert exit_code == 1


def test_run_eval_command_plan_not_found(tmp_path: Path, monkeypatch) -> None:
    """Test eval command with non-existent plan."""
    monkeypatch.chdir(tmp_path)

    exit_code = run_eval_command("nonexistent-plan")

    assert exit_code == 1


def test_run_eval_command_no_judges(tmp_path: Path, monkeypatch) -> None:
    """Test eval command when no judges are found."""
    monkeypatch.chdir(tmp_path)

    # Create plan file
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    plan_file.write_text(
        """---
plan_id: test-plan
status: coding
---

# Test Plan
"""
    )

    # Create worktree
    worktree_dir = tmp_path / ".weft" / "worktrees" / "test-plan"
    worktree_dir.mkdir(parents=True)

    # Initialize git repo in worktree
    subprocess.run(["git", "init"], cwd=worktree_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=worktree_dir,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=worktree_dir, check=True
    )

    # Create plan.md in worktree
    (worktree_dir / "plan.md").write_text("# Test Plan")
    subprocess.run(["git", "add", "plan.md"], cwd=worktree_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=worktree_dir,
        check=True,
        capture_output=True,
    )

    # Create empty judges directory
    judges_dir = tmp_path / ".weft" / "judges"
    judges_dir.mkdir(parents=True)

    exit_code = run_eval_command("test-plan")

    assert exit_code == 1


def test_run_eval_command_judges_only(tmp_path: Path, monkeypatch, capsys) -> None:
    """Test eval command runs judges successfully and saves results.

    This test mocks the test runner and feedback collector since those
    require actual Claude Code SDK interaction.
    """
    monkeypatch.chdir(tmp_path)

    # Initialize main git repo (required for PlanResolver)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
    )

    # Create plan file
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    plan_file.write_text(
        """---
plan_id: test-plan
status: coding
---

# Test Plan
"""
    )

    # Commit the plan file to satisfy PlanResolver
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add plan"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Create worktree
    worktree_dir = tmp_path / ".weft" / "worktrees" / "test-plan"
    worktree_dir.mkdir(parents=True)

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=worktree_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=worktree_dir,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=worktree_dir, check=True
    )

    # Create plan.md
    (worktree_dir / "plan.md").write_text("# Test Plan Content")
    subprocess.run(["git", "add", "plan.md"], cwd=worktree_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=worktree_dir,
        check=True,
        capture_output=True,
    )

    # Create judges directory and judge file
    judges_dir = tmp_path / ".weft" / "judges"
    judges_dir.mkdir(parents=True)
    judge_file = judges_dir / "test-judge.md"
    judge_file.write_text(
        """---
weight: 0.5
model: x-ai/grok-4.1-fast
---

Test judge instructions.
"""
    )

    # Mock the judge orchestrator to return test results
    mock_results = [
        JudgeResult(
            judge_name="test-judge",
            score=0.85,
            feedback="Test feedback",
            weight=0.5,
        )
    ]

    # Mock test runner and feedback collector to avoid SDK calls
    with patch("weft.eval_command.execute_judges_parallel", return_value=mock_results):
        with patch("weft.eval_command.get_openrouter_api_key", return_value="test_key"):
            with patch("weft.eval_command.run_before_tests", return_value=None):
                with patch("weft.eval_command.run_after_tests", return_value={
                    "command": "test",
                    "exit_code": 0,
                    "total_tests": 10,
                    "passed_tests": 10,
                    "failed_tests": 0,
                }):
                    with patch("weft.eval_command.collect_human_feedback", return_value=None):
                        exit_code = run_eval_command("test-plan")

    assert exit_code == 0

    # Check console output shows scores
    captured = capsys.readouterr()
    assert "test-plan" in captured.out
    assert "test-judge" in captured.out
    assert "0.85" in captured.out

    # Check judge result files were saved
    eval_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "eval"
    json_path = eval_dir / "judge_test-judge.json"
    md_path = eval_dir / "judge_test-judge.md"

    assert json_path.exists()
    assert md_path.exists()

    # Verify JSON content
    json_data = json.loads(json_path.read_text())
    assert json_data["judge_name"] == "test-judge"
    assert json_data["score"] == 0.85
    assert json_data["feedback"] == "Test feedback"


def _setup_eval_environment(tmp_path: Path) -> Path:
    """Set up a minimal eval test environment.

    Creates a git repo with a plan file, worktree, and judges directory.
    Shared by TestEvalCommandIdempotency and TestEvalCompleteHook.
    """
    # Initialize main git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
    )

    # Create plan file
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "test-plan.md"
    plan_file.write_text(
        """---
plan_id: test-plan
status: coding
---

# Test Plan
"""
    )

    # Commit the plan file
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add plan"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    # Create worktree
    worktree_dir = tmp_path / ".weft" / "worktrees" / "test-plan"
    worktree_dir.mkdir(parents=True)

    # Initialize git repo in worktree
    subprocess.run(["git", "init"], cwd=worktree_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=worktree_dir,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=worktree_dir, check=True
    )

    # Create plan.md and commit
    (worktree_dir / "plan.md").write_text("# Test Plan Content")
    subprocess.run(["git", "add", "plan.md"], cwd=worktree_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=worktree_dir,
        check=True,
        capture_output=True,
    )

    # Create judges directory with judge
    judges_dir = tmp_path / ".weft" / "judges"
    judges_dir.mkdir(parents=True)
    judge_file = judges_dir / "test-judge.md"
    judge_file.write_text(
        """---
weight: 0.5
model: x-ai/grok-4.1-fast
---

Test judge instructions.
"""
    )

    return tmp_path


class TestEvalCommandIdempotency:
    """Tests for eval command idempotency behavior."""

    def test_skips_judges_when_output_exists(self, tmp_path: Path, monkeypatch) -> None:
        """Judges are skipped when their output files already exist."""
        tmp_path = _setup_eval_environment(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Pre-create judge output file
        eval_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        judge_json = eval_dir / "judge_test-judge.json"
        judge_json.write_text(json.dumps({
            "judge_name": "test-judge",
            "score": 0.99,
            "weight": 0.5,
            "feedback": "Pre-existing result",
        }))

        # Mock execute_judges_parallel - should NOT be called
        mock_execute = MagicMock(return_value=[])

        with patch("weft.eval_command.execute_judges_parallel", mock_execute):
            with patch("weft.eval_command.get_openrouter_api_key", return_value="test_key"):
                with patch("weft.eval_command.run_before_tests", return_value=None):
                    with patch("weft.eval_command.run_after_tests", return_value={
                        "command": "test", "exit_code": 0, "total_tests": 1,
                        "passed_tests": 1, "failed_tests": 0,
                    }):
                        with patch("weft.eval_command.collect_human_feedback", return_value=None):
                            run_eval_command("test-plan")

        # execute_judges_parallel should not be called since output exists
        # (Or if called, it should be with empty list of judges to run)
        if mock_execute.called:
            call_args = mock_execute.call_args
            # If it was called, check that no judges were passed
            judges_arg = call_args[0][0] if call_args[0] else call_args[1].get("judges", [])
            assert len(judges_arg) == 0, "No judges should be run when output exists"

    def test_force_reruns_judges(self, tmp_path: Path, monkeypatch) -> None:
        """--force flag causes judges to re-run even when output exists."""
        tmp_path = _setup_eval_environment(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Pre-create judge output file
        eval_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        judge_json = eval_dir / "judge_test-judge.json"
        judge_json.write_text(json.dumps({
            "judge_name": "test-judge",
            "score": 0.50,  # Old score
            "weight": 0.5,
            "feedback": "Old result",
        }))

        # Mock to return new result
        new_result = JudgeResult(
            judge_name="test-judge",
            score=0.95,  # New score
            feedback="New result from force re-run",
            weight=0.5,
        )

        with patch("weft.eval_command.execute_judges_parallel", return_value=[new_result]):
            with patch("weft.eval_command.get_openrouter_api_key", return_value="test_key"):
                with patch("weft.eval_command.run_before_tests", return_value=None):
                    with patch("weft.eval_command.run_after_tests", return_value={
                        "command": "test", "exit_code": 0, "total_tests": 1,
                        "passed_tests": 1, "failed_tests": 0,
                    }):
                        with patch("weft.eval_command.collect_human_feedback", return_value=None):
                            run_eval_command("test-plan", force=True)

        # Verify new result was written
        json_data = json.loads(judge_json.read_text())
        assert json_data["score"] == 0.95, "Force should have overwritten the old result"

    def test_skips_tests_when_results_exist(self, tmp_path: Path, monkeypatch) -> None:
        """Test execution is skipped when result files already exist."""
        tmp_path = _setup_eval_environment(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Pre-create test result files
        eval_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "test_results_after.json").write_text(json.dumps({
            "command": "pytest", "exit_code": 0, "total_tests": 5,
            "passed_tests": 5, "failed_tests": 0,
        }))

        # Mock test runners - should NOT be called
        mock_after_tests = MagicMock()

        mock_results = [JudgeResult(
            judge_name="test-judge", score=0.85, feedback="Test", weight=0.5
        )]

        with patch("weft.eval_command.execute_judges_parallel", return_value=mock_results):
            with patch("weft.eval_command.get_openrouter_api_key", return_value="test_key"):
                with patch("weft.eval_command.run_before_tests", return_value=None):
                    with patch("weft.eval_command.run_after_tests", mock_after_tests):
                        with patch("weft.eval_command.collect_human_feedback", return_value=None):
                            run_eval_command("test-plan")

        # run_after_tests should not be called since result file exists
        mock_after_tests.assert_not_called()

    def test_skips_feedback_when_file_exists(self, tmp_path: Path, monkeypatch) -> None:
        """Feedback collection is skipped when human_feedback.md exists."""
        tmp_path = _setup_eval_environment(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Pre-create feedback file
        eval_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "human_feedback.md").write_text("# Existing Feedback\n\nPre-existing.")
        (eval_dir / "test_results_after.json").write_text(json.dumps({
            "command": "pytest", "exit_code": 0, "total_tests": 5,
            "passed_tests": 5, "failed_tests": 0,
        }))

        # Mock feedback collector - should NOT be called
        mock_feedback = MagicMock()

        mock_results = [JudgeResult(
            judge_name="test-judge", score=0.85, feedback="Test", weight=0.5
        )]

        with patch("weft.eval_command.execute_judges_parallel", return_value=mock_results):
            with patch("weft.eval_command.get_openrouter_api_key", return_value="test_key"):
                with patch("weft.eval_command.run_before_tests", return_value=None):
                    with patch("weft.eval_command.run_after_tests", return_value={
                        "command": "test", "exit_code": 0, "total_tests": 1,
                        "passed_tests": 1, "failed_tests": 0,
                    }):
                        with patch("weft.eval_command.collect_human_feedback", mock_feedback):
                            run_eval_command("test-plan")

        # collect_human_feedback should not be called since file exists
        mock_feedback.assert_not_called()


class TestEvalCompleteHook:
    """Tests for eval_complete hook trigger functionality."""

    def test_eval_command_triggers_hook_after_training_data_created(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Verify eval_complete hook is triggered with correct context after training data is created."""
        tmp_path = _setup_eval_environment(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Pre-create test results and feedback files (required for training data creation)
        eval_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "test_results_after.json").write_text(json.dumps({
            "command": "pytest", "exit_code": 0, "total_tests": 5,
            "passed_tests": 5, "failed_tests": 0,
        }))
        (eval_dir / "human_feedback.md").write_text("# Human Feedback\n\nGreat work!")

        mock_results = [JudgeResult(
            judge_name="test-judge", score=0.85, feedback="Test feedback", weight=0.5
        )]

        # Track trigger_hook calls
        hook_calls = []

        def mock_trigger_hook(hook_name: str, context: dict) -> None:
            hook_calls.append((hook_name, context.copy()))

        with patch("weft.eval_command.execute_judges_parallel", return_value=mock_results):
            with patch("weft.eval_command.get_openrouter_api_key", return_value="test_key"):
                with patch("weft.eval_command.run_before_tests", return_value=None):
                    with patch("weft.eval_command.run_after_tests", return_value={
                        "command": "test", "exit_code": 0, "total_tests": 5,
                        "passed_tests": 5, "failed_tests": 0,
                    }):
                        with patch("weft.eval_command.collect_human_feedback", return_value=None):
                            with patch("weft.eval_command.create_training_data"):
                                with patch("weft.eval_command.trigger_hook", mock_trigger_hook):
                                    exit_code = run_eval_command("test-plan")

        assert exit_code == 0

        # Verify trigger_hook was called exactly once with eval_complete
        eval_complete_calls = [c for c in hook_calls if c[0] == "eval_complete"]
        assert len(eval_complete_calls) == 1, "eval_complete hook should be called exactly once"

        # Verify hook context contains all required variables with correct types
        hook_context = eval_complete_calls[0][1]
        assert "training_data_dir" in hook_context
        assert "worktree_path" in hook_context
        assert "plan_path" in hook_context
        assert "plan_id" in hook_context
        assert "repo_root" in hook_context

        # Verify path types (should be Path objects)
        assert isinstance(hook_context["training_data_dir"], Path)
        assert isinstance(hook_context["worktree_path"], Path)
        assert isinstance(hook_context["plan_path"], Path)
        assert isinstance(hook_context["repo_root"], Path)

        # Verify paths point to expected locations
        assert "test-plan" in str(hook_context["training_data_dir"])
        assert str(hook_context["worktree_path"]).endswith("test-plan")
        assert hook_context["plan_id"] == "test-plan"

    def test_eval_complete_hook_not_triggered_when_training_data_skipped(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Verify hook is NOT triggered when training data creation is skipped."""
        tmp_path = _setup_eval_environment(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Create eval directory but WITHOUT human_feedback.md
        # This means training data creation will be skipped
        eval_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "test_results_after.json").write_text(json.dumps({
            "command": "pytest", "exit_code": 0, "total_tests": 5,
            "passed_tests": 5, "failed_tests": 0,
        }))
        # Note: deliberately NOT creating human_feedback.md

        mock_results = [JudgeResult(
            judge_name="test-judge", score=0.85, feedback="Test feedback", weight=0.5
        )]

        # Track trigger_hook calls
        hook_calls = []

        def mock_trigger_hook(hook_name: str, context: dict) -> None:
            hook_calls.append((hook_name, context.copy()))

        with patch("weft.eval_command.execute_judges_parallel", return_value=mock_results):
            with patch("weft.eval_command.get_openrouter_api_key", return_value="test_key"):
                with patch("weft.eval_command.run_before_tests", return_value=None):
                    with patch("weft.eval_command.run_after_tests", return_value={
                        "command": "test", "exit_code": 0, "total_tests": 5,
                        "passed_tests": 5, "failed_tests": 0,
                    }):
                        # collect_human_feedback returns None (user cancelled)
                        with patch("weft.eval_command.collect_human_feedback", return_value=None):
                            with patch("weft.eval_command.trigger_hook", mock_trigger_hook):
                                exit_code = run_eval_command("test-plan")

        assert exit_code == 0

        # Verify trigger_hook was NOT called
        eval_complete_calls = [c for c in hook_calls if c[0] == "eval_complete"]
        assert len(eval_complete_calls) == 0, "eval_complete hook should NOT be called when training data is skipped"

    def test_eval_command_no_hooks_flag_prevents_eval_complete(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Verify --no-hooks flag prevents hook execution even when training data is created."""
        tmp_path = _setup_eval_environment(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Pre-create all required files for training data creation
        eval_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "test_results_after.json").write_text(json.dumps({
            "command": "pytest", "exit_code": 0, "total_tests": 5,
            "passed_tests": 5, "failed_tests": 0,
        }))
        (eval_dir / "human_feedback.md").write_text("# Human Feedback\n\nGreat work!")

        mock_results = [JudgeResult(
            judge_name="test-judge", score=0.85, feedback="Test feedback", weight=0.5
        )]

        # Track trigger_hook calls
        hook_calls = []

        def mock_trigger_hook(hook_name: str, context: dict) -> None:
            hook_calls.append((hook_name, context.copy()))

        with patch("weft.eval_command.execute_judges_parallel", return_value=mock_results):
            with patch("weft.eval_command.get_openrouter_api_key", return_value="test_key"):
                with patch("weft.eval_command.run_before_tests", return_value=None):
                    with patch("weft.eval_command.run_after_tests", return_value={
                        "command": "test", "exit_code": 0, "total_tests": 5,
                        "passed_tests": 5, "failed_tests": 0,
                    }):
                        with patch("weft.eval_command.collect_human_feedback", return_value=None):
                            with patch("weft.eval_command.create_training_data"):
                                with patch("weft.eval_command.trigger_hook", mock_trigger_hook):
                                    # Call with no_hooks=True
                                    exit_code = run_eval_command("test-plan", no_hooks=True)

        assert exit_code == 0

        # Verify trigger_hook was NOT called when no_hooks=True
        assert len(hook_calls) == 0, "trigger_hook should NOT be called when no_hooks=True"

    def test_eval_command_succeeds_when_hook_raises_exception(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Verify eval command succeeds even when hook execution raises an exception.

        This tests the non-blocking requirement: hook failures must not fail
        the eval command. The trigger_hook function handles exceptions internally,
        but this test documents and verifies the expected contract.
        """
        tmp_path = _setup_eval_environment(tmp_path)
        monkeypatch.chdir(tmp_path)

        # Pre-create all required files for training data creation
        eval_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "eval"
        eval_dir.mkdir(parents=True)
        (eval_dir / "test_results_after.json").write_text(json.dumps({
            "command": "pytest", "exit_code": 0, "total_tests": 5,
            "passed_tests": 5, "failed_tests": 0,
        }))
        (eval_dir / "human_feedback.md").write_text("# Human Feedback\n\nGreat work!")

        mock_results = [JudgeResult(
            judge_name="test-judge", score=0.85, feedback="Test feedback", weight=0.5
        )]

        def failing_trigger_hook(hook_name: str, context: dict) -> None:
            """Simulate a hook that raises an exception."""
            raise RuntimeError("Hook execution failed unexpectedly")

        with patch("weft.eval_command.execute_judges_parallel", return_value=mock_results):
            with patch("weft.eval_command.get_openrouter_api_key", return_value="test_key"):
                with patch("weft.eval_command.run_before_tests", return_value=None):
                    with patch("weft.eval_command.run_after_tests", return_value={
                        "command": "test", "exit_code": 0, "total_tests": 5,
                        "passed_tests": 5, "failed_tests": 0,
                    }):
                        with patch("weft.eval_command.collect_human_feedback", return_value=None):
                            with patch("weft.eval_command.create_training_data"):
                                with patch("weft.eval_command.trigger_hook", failing_trigger_hook):
                                    exit_code = run_eval_command("test-plan")

        # Hook failure should NOT cause eval command to fail
        assert exit_code == 0, "Eval command should succeed even when hook raises exception"
