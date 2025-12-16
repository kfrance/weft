"""Tests for train_command module.

# Parameter validation tests: see tests/unit/test_validation.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lw_coder.train_command import run_train_command


class TestRunTrainCommand:
    """Tests for run_train_command function."""

    def test_train_command_no_training_data(self, tmp_path: Path) -> None:
        """Returns error when no training data."""
        with patch("lw_coder.train_command.find_repo_root", return_value=tmp_path):
            # Create empty .lw_coder directory without training data
            (tmp_path / ".lw_coder").mkdir()

            result = run_train_command(variant="sonnet", batch_size=3, max_subagents=5)

            assert result == 1  # Error exit code

    def test_train_command_no_active_prompts(self, tmp_path: Path) -> None:
        """Returns error when no active prompts."""
        with patch("lw_coder.train_command.find_repo_root", return_value=tmp_path):
            # Create training data directory with a sample
            training_dir = tmp_path / ".lw_coder" / "training_data" / "test-sample"
            training_dir.mkdir(parents=True)
            (training_dir / "human_feedback.md").write_text("Feedback")
            (training_dir / "test_results_after.json").write_text('{"passed": 10}')
            (training_dir / "judge_test.json").write_text(
                '{"judge_name": "test", "score": 0.8, "weight": 0.5, "feedback": "OK"}'
            )

            # But no prompts directory
            result = run_train_command(variant="sonnet", batch_size=3, max_subagents=5)

            assert result == 1  # Error exit code

    def test_train_command_repo_not_found(self) -> None:
        """Returns error when repository not found."""
        from lw_coder.repo_utils import RepoUtilsError

        with patch(
            "lw_coder.train_command.find_repo_root",
            side_effect=RepoUtilsError("Not a git repository"),
        ):
            result = run_train_command(variant="sonnet", batch_size=3, max_subagents=5)

            assert result == 1
