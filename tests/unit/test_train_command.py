"""Tests for train_command module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.train_command import TrainCommandError, _validate_parameters, run_train_command


class TestValidateParameters:
    """Tests for _validate_parameters function."""

    def test_train_command_validates_batch_size_min(self) -> None:
        """Rejects invalid batch size below minimum."""
        with pytest.raises(TrainCommandError) as exc_info:
            _validate_parameters(variant="sonnet", batch_size=0, max_subagents=5)

        assert "Invalid batch_size" in str(exc_info.value)
        assert "at least 1" in str(exc_info.value)

    def test_train_command_validates_batch_size_max(self) -> None:
        """Rejects invalid batch size above maximum."""
        with pytest.raises(TrainCommandError) as exc_info:
            _validate_parameters(variant="sonnet", batch_size=15, max_subagents=5)

        assert "Invalid batch_size" in str(exc_info.value)
        assert "Maximum is 10" in str(exc_info.value)

    def test_train_command_validates_max_subagents_min(self) -> None:
        """Rejects invalid max_subagents below minimum."""
        with pytest.raises(TrainCommandError) as exc_info:
            _validate_parameters(variant="sonnet", batch_size=3, max_subagents=0)

        assert "Invalid max_subagents" in str(exc_info.value)
        assert "at least 1" in str(exc_info.value)

    def test_train_command_validates_max_subagents_max(self) -> None:
        """Rejects invalid max_subagents above maximum."""
        with pytest.raises(TrainCommandError) as exc_info:
            _validate_parameters(variant="sonnet", batch_size=3, max_subagents=15)

        assert "Invalid max_subagents" in str(exc_info.value)
        assert "Maximum is 10" in str(exc_info.value)

    def test_train_command_validates_invalid_variant(self) -> None:
        """Rejects invalid variant parameter."""
        with pytest.raises(TrainCommandError) as exc_info:
            _validate_parameters(variant="invalid-variant", batch_size=3, max_subagents=5)

        assert "Invalid variant" in str(exc_info.value)
        assert "invalid-variant" in str(exc_info.value)

    def test_train_command_valid_parameters(self) -> None:
        """Accepts valid parameters."""
        # Should not raise
        _validate_parameters(variant="sonnet", batch_size=3, max_subagents=5)
        _validate_parameters(variant="opus", batch_size=1, max_subagents=1)
        _validate_parameters(variant="haiku", batch_size=10, max_subagents=10)


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

    def test_train_command_invalid_batch_size(self) -> None:
        """Returns error for invalid batch_size parameter."""
        # Invalid batch_size should fail validation early
        result = run_train_command(variant="sonnet", batch_size=0, max_subagents=5)
        assert result == 1

    def test_train_command_invalid_max_subagents(self) -> None:
        """Returns error for invalid max_subagents parameter."""
        result = run_train_command(variant="sonnet", batch_size=3, max_subagents=0)
        assert result == 1

    def test_train_command_invalid_variant(self) -> None:
        """Returns error for invalid variant parameter."""
        result = run_train_command(variant="gpt4", batch_size=3, max_subagents=5)
        assert result == 1

    def test_train_command_repo_not_found(self) -> None:
        """Returns error when repository not found."""
        from lw_coder.repo_utils import RepoUtilsError

        with patch(
            "lw_coder.train_command.find_repo_root",
            side_effect=RepoUtilsError("Not a git repository"),
        ):
            result = run_train_command(variant="sonnet", batch_size=3, max_subagents=5)

            assert result == 1
