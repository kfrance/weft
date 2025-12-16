"""Tests for CLI argument parsing and validation.

These tests focus on:
1. CLI validation logic (not argparse behavior)
2. Quick-fix plan creation with --text flag
3. Import/dispatch safety checks

Integration tests for CLI validation via subprocess are in
tests/integration/test_cli_validation.py
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from lw_coder.cli import main


# =============================================================================
# Validation Logic Tests
# =============================================================================


def test_code_command_validation_error_droid_with_model(monkeypatch, caplog, tmp_path) -> None:
    """Test code command raises validation error for droid with model."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    # Mock run_code_command - should not be called due to validation error
    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with incompatible parameters
    exit_code = main(["code", str(plan_path), "--tool", "droid", "--model", "sonnet"])

    assert exit_code == 1
    assert "cannot be used with --tool droid" in caplog.text
    mock_run.assert_not_called()


def test_code_command_validation_error_invalid_tool(monkeypatch, caplog, tmp_path) -> None:
    """Test code command raises validation error for invalid tool."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    # Mock run_code_command - should not be called due to validation error
    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with invalid tool
    exit_code = main(["code", str(plan_path), "--tool", "invalid-tool"])

    assert exit_code == 1
    assert "Unknown tool 'invalid-tool'" in caplog.text
    mock_run.assert_not_called()


def test_code_command_invalid_model(monkeypatch, caplog, tmp_path) -> None:
    """Test code command raises validation error for invalid model."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    # Mock run_code_command - should not be called due to validation error
    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with invalid model
    exit_code = main(["code", str(plan_path), "--model", "gpt-4"])

    assert exit_code == 1
    assert "Unknown model 'gpt-4'" in caplog.text
    mock_run.assert_not_called()


def test_code_command_text_mutual_exclusivity(monkeypatch, caplog, tmp_path, git_repo) -> None:
    """Test that plan_path and --text are mutually exclusive."""
    monkeypatch.chdir(git_repo.path)

    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with both plan_path and --text
    exit_code = main(["code", str(plan_path), "--text", "Fix something"])

    assert exit_code == 1
    assert "mutually exclusive" in caplog.text
    mock_run.assert_not_called()


def test_code_command_text_empty_error(monkeypatch, caplog, git_repo) -> None:
    """Test that empty --text is rejected."""
    monkeypatch.chdir(git_repo.path)

    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with empty text
    exit_code = main(["code", "--text", ""])

    assert exit_code == 1
    assert "Failed to create quick-fix plan" in caplog.text
    mock_run.assert_not_called()


def test_code_command_neither_path_nor_text(monkeypatch, caplog, git_repo) -> None:
    """Test that error is raised when neither plan_path nor --text is provided."""
    monkeypatch.chdir(git_repo.path)

    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with no arguments
    exit_code = main(["code"])

    assert exit_code == 1
    assert "Must specify either plan_path or --text" in caplog.text
    mock_run.assert_not_called()


# =============================================================================
# Quick-Fix Creation Tests
# =============================================================================


def test_code_command_with_text_flag(monkeypatch, tmp_path, git_repo) -> None:
    """Test code command with --text flag creates quick-fix plan."""
    monkeypatch.chdir(git_repo.path)

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

    # Run CLI with --text flag
    exit_code = main(["code", "--text", "Fix the login button"])

    assert exit_code == 0
    assert captured_args["tool"] == "claude-code"
    # model=None means run_code_command will resolve via get_effective_model()
    assert captured_args["model"] is None

    # Verify plan file was created
    plan_path = captured_args["path"]
    assert plan_path.exists()
    assert plan_path.name.startswith("quick-fix-")
    assert "Fix the login button" in plan_path.read_text(encoding="utf-8")


def test_code_command_text_multiline(monkeypatch, git_repo) -> None:
    """Test --text with multiline input."""
    monkeypatch.chdir(git_repo.path)

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

    multiline_text = "Fix login\n\nUpdate button styles\nAdd hover effect"

    # Run CLI with multiline text
    exit_code = main(["code", "--text", multiline_text])

    assert exit_code == 0

    # Verify multiline text is preserved
    plan_path = captured_args["path"]
    content = plan_path.read_text(encoding="utf-8")
    assert multiline_text in content


# =============================================================================
# Import/Dispatch Safety Tests
# =============================================================================


@pytest.mark.parametrize("subcommand", [
    "plan",
    "code",
    "init",
    "finalize",
    "recover-plan",
    "abandon",
    "completion",
    "eval",
])
def test_subcommand_help_no_import_errors(subcommand: str) -> None:
    """Test that all subcommands can show --help without import errors.

    This catches UnboundLocalError and similar issues caused by shadowed
    imports or incorrect lazy loading patterns in the CLI dispatch code.
    """
    with pytest.raises(SystemExit) as exc_info:
        main([subcommand, "--help"])

    # argparse exits with 0 when showing help
    assert exc_info.value.code == 0


def test_all_subcommands_dispatch_without_import_errors(monkeypatch, tmp_path) -> None:
    """Test that all subcommand dispatch blocks execute without import errors.

    This catches UnboundLocalError caused by local imports shadowing module-level
    imports (e.g., lazy 'from .plan_resolver import PlanResolver' inside one
    if-block shadows the top-level import for earlier if-blocks in the same function).

    Each subcommand is tested by mocking its handler and verifying the dispatch
    code reaches it without raising UnboundLocalError or similar import issues.
    """
    # Create a dummy plan file for commands that require one
    plan_file = tmp_path / "test-plan.md"
    plan_file.write_text("# Test Plan\n")

    # Mock all command handlers to return 0
    monkeypatch.setattr("lw_coder.plan_command.run_plan_command", lambda *args, **kwargs: 0)
    monkeypatch.setattr("lw_coder.code_command.run_code_command", lambda *args, **kwargs: 0)
    monkeypatch.setattr("lw_coder.cli.run_init_command", lambda *args, **kwargs: 0)
    monkeypatch.setattr("lw_coder.finalize_command.run_finalize_command", lambda *args, **kwargs: 0)
    monkeypatch.setattr("lw_coder.recover_command.run_recover_command", lambda *args, **kwargs: 0)
    monkeypatch.setattr("lw_coder.abandon_command.run_abandon_command", lambda *args, **kwargs: 0)
    monkeypatch.setattr("lw_coder.eval_command.run_eval_command", lambda *args, **kwargs: 0)

    # Test each subcommand with minimal valid arguments
    # These exercise the dispatch code paths where import errors would manifest
    test_cases = [
        (["plan", "--text", "test"], "plan"),
        (["code", str(plan_file)], "code"),
        (["init"], "init"),
        (["finalize", str(plan_file)], "finalize"),
        (["recover-plan"], "recover-plan"),
        (["abandon", str(plan_file), "--yes"], "abandon"),
        (["eval", "test-plan"], "eval"),
    ]

    for args, cmd_name in test_cases:
        # If this raises UnboundLocalError, the test fails with a clear message
        try:
            exit_code = main(args)
            assert exit_code == 0, f"{cmd_name} command failed with exit code {exit_code}"
        except UnboundLocalError as e:
            pytest.fail(f"{cmd_name} command raised UnboundLocalError: {e}")
