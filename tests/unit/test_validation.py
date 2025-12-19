"""CLI parameter validation tests.

These tests verify validation logic for all commands before reaching
the command handlers. Consolidating them here makes it easier to:
- Ensure consistent validation patterns across commands
- Update validation rules in one place
- Use parametrization for similar validation patterns

For command-specific behavior tests, see:
- tests/unit/test_train_command.py
- tests/unit/test_cli.py (CLI wiring and dispatch)
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from weft.cli import main
from weft.train_command import TrainCommandError, _validate_parameters


class TestTrainCommandValidation:
    """Parametrized tests for train command parameter validation."""

    @pytest.mark.parametrize(
        ("variant", "batch_size", "max_subagents", "expected_error"),
        [
            pytest.param(
                "sonnet",
                0,
                5,
                "Invalid batch_size.*at least 1",
                id="batch_size_below_min",
            ),
            pytest.param(
                "sonnet",
                15,
                5,
                "Invalid batch_size.*Maximum is 10",
                id="batch_size_above_max",
            ),
            pytest.param(
                "sonnet",
                3,
                0,
                "Invalid max_subagents.*at least 1",
                id="max_subagents_below_min",
            ),
            pytest.param(
                "sonnet",
                3,
                15,
                "Invalid max_subagents.*Maximum is 10",
                id="max_subagents_above_max",
            ),
            pytest.param(
                "invalid-variant",
                3,
                5,
                "Invalid variant.*invalid-variant",
                id="invalid_variant",
            ),
        ],
    )
    def test_train_command_rejects_invalid_parameters(
        self, variant: str, batch_size: int, max_subagents: int, expected_error: str
    ) -> None:
        """Validate that invalid parameters raise TrainCommandError with appropriate message."""
        with pytest.raises(TrainCommandError, match=expected_error):
            _validate_parameters(variant=variant, batch_size=batch_size, max_subagents=max_subagents)

    @pytest.mark.parametrize(
        ("variant", "batch_size", "max_subagents"),
        [
            pytest.param("sonnet", 1, 1, id="boundary_min"),
            pytest.param("opus", 10, 10, id="boundary_max"),
            pytest.param("haiku", 5, 5, id="mid_range"),
        ],
    )
    def test_train_command_accepts_valid_parameters(
        self, variant: str, batch_size: int, max_subagents: int
    ) -> None:
        """Validate that valid parameters do not raise errors."""
        # Should not raise
        _validate_parameters(variant=variant, batch_size=batch_size, max_subagents=max_subagents)


class TestCodeCommandValidation:
    """Parametrized tests for code command parameter validation."""

    @pytest.mark.parametrize(
        ("args", "expected_error"),
        [
            pytest.param(
                ["code", "test.md", "--tool", "droid", "--model", "sonnet"],
                "cannot be used with --tool droid",
                id="droid_with_model",
            ),
            pytest.param(
                ["code", "test.md", "--tool", "invalid-tool"],
                "Unknown tool 'invalid-tool'",
                id="invalid_tool",
            ),
            pytest.param(
                ["code", "test.md", "--model", "gpt-4"],
                "Unknown model 'gpt-4'",
                id="invalid_model",
            ),
        ],
    )
    def test_code_command_rejects_invalid_tool_model_combinations(
        self, monkeypatch, caplog, tmp_path: Path, args: list[str], expected_error: str
    ) -> None:
        """Validate that invalid tool/model combinations are rejected."""
        # Create a plan file for tests that need it
        plan_path = tmp_path / "test.md"
        plan_path.write_text("# Test Plan\n")

        # Replace plan path placeholder with actual path
        resolved_args = [str(plan_path) if arg == "test.md" else arg for arg in args]

        # Mock run_code_command - should not be called due to validation error
        mock_run = MagicMock()
        monkeypatch.setattr("weft.code_command.run_code_command", mock_run)

        caplog.set_level(logging.ERROR)

        exit_code = main(resolved_args)

        assert exit_code == 1
        assert expected_error in caplog.text
        mock_run.assert_not_called()

    @pytest.mark.parametrize(
        ("args", "expected_error"),
        [
            pytest.param(
                ["code", "test.md", "--text", "Fix something"],
                "mutually exclusive",
                id="plan_path_with_text",
            ),
            pytest.param(
                ["code", "--text", ""],
                "Failed to create quick-fix plan",
                id="empty_text",
            ),
            pytest.param(
                ["code"],
                "Must specify either plan_path or --text",
                id="neither_path_nor_text",
            ),
        ],
    )
    def test_code_command_rejects_invalid_input_combinations(
        self, monkeypatch, caplog, tmp_path: Path, git_repo, args: list[str], expected_error: str
    ) -> None:
        """Validate that invalid input combinations (plan_path/text) are rejected."""
        monkeypatch.chdir(git_repo.path)

        # Create a plan file for tests that need it
        plan_path = tmp_path / "test.md"
        plan_path.write_text("# Test Plan\n")

        # Replace plan path placeholder with actual path
        resolved_args = [str(plan_path) if arg == "test.md" else arg for arg in args]

        # Mock run_code_command - should not be called due to validation error
        mock_run = MagicMock()
        monkeypatch.setattr("weft.code_command.run_code_command", mock_run)

        caplog.set_level(logging.ERROR)

        exit_code = main(resolved_args)

        assert exit_code == 1
        assert expected_error in caplog.text
        mock_run.assert_not_called()
