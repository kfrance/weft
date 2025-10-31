"""Tests for CLI argument parsing and validation."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.cli import main


def test_code_command_default_tool_and_model(monkeypatch, caplog, tmp_path) -> None:
    """Test code command with default tool and model."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    # Mock the run_code_command to capture arguments
    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        return 0

    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run_code_command)

    # Run CLI with just plan path
    exit_code = main(["code", str(plan_path)])

    assert exit_code == 0
    assert captured_args["tool"] == "claude-code"
    assert captured_args["model"] == "sonnet"  # Default from docopt


def test_code_command_explicit_tool(monkeypatch, tmp_path) -> None:
    """Test code command with explicit --tool parameter."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        return 0

    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run_code_command)

    # Run CLI with explicit tool
    exit_code = main(["code", str(plan_path), "--tool", "droid"])

    assert exit_code == 0
    assert captured_args["tool"] == "droid"


def test_code_command_explicit_model(monkeypatch, tmp_path) -> None:
    """Test code command with explicit --model parameter."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        return 0

    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run_code_command)

    # Run CLI with explicit model
    exit_code = main(["code", str(plan_path), "--model", "opus"])

    assert exit_code == 0
    assert captured_args["model"] == "opus"


def test_code_command_tool_and_model(monkeypatch, tmp_path) -> None:
    """Test code command with both --tool and --model parameters."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        return 0

    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run_code_command)

    # Run CLI with both tool and model
    exit_code = main(["code", str(plan_path), "--tool", "claude-code", "--model", "haiku"])

    assert exit_code == 0
    assert captured_args["tool"] == "claude-code"
    assert captured_args["model"] == "haiku"


def test_code_command_validation_error_droid_with_model(monkeypatch, caplog, tmp_path) -> None:
    """Test code command raises validation error for droid with model."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    # Mock run_code_command - should not be called due to validation error
    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run)

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
    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with invalid tool
    exit_code = main(["code", str(plan_path), "--tool", "invalid-tool"])

    assert exit_code == 1
    assert "Unknown tool 'invalid-tool'" in caplog.text
    mock_run.assert_not_called()


def test_plan_command_tool_parameter(monkeypatch, tmp_path) -> None:
    """Test plan command accepts --tool parameter."""
    captured_args = {}

    def mock_run_plan_command(path, text, tool):
        captured_args["path"] = path
        captured_args["text"] = text
        captured_args["tool"] = tool
        return 0

    monkeypatch.setattr("lw_coder.cli.run_plan_command", mock_run_plan_command)

    # Run plan command with tool
    exit_code = main(["plan", "--text", "Test idea", "--tool", "droid"])

    assert exit_code == 0
    assert captured_args["tool"] == "droid"
    assert captured_args["text"] == "Test idea"


def test_code_command_debug_flag(monkeypatch, tmp_path) -> None:
    """Test code command with --debug flag."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_debug = {}

    def mock_configure_logging(debug=False):
        captured_debug["value"] = debug

    def mock_run_code_command(path, tool="claude-code", model=None):
        return 0

    monkeypatch.setattr("lw_coder.cli.configure_logging", mock_configure_logging)
    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run_code_command)

    # Run with debug flag (must come before subcommand in argparse)
    exit_code = main(["--debug", "code", str(plan_path)])

    assert exit_code == 0
    assert captured_debug["value"] is True


def test_help_flag() -> None:
    """Test --help flag shows help and exits."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    # argparse exits with 0 when showing help
    assert exc_info.value.code == 0


def test_code_command_parameter_order(monkeypatch, tmp_path) -> None:
    """Test code command parameters can be specified in different orders."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        return 0

    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run_code_command)

    # Test different parameter orders
    test_cases = [
        (["code", str(plan_path), "--model", "opus", "--tool", "claude-code"], "opus", "claude-code"),
        (["code", "--tool", "claude-code", str(plan_path), "--model", "haiku"], "haiku", "claude-code"),
        (["code", "--model", "sonnet", "--tool", "claude-code", str(plan_path)], "sonnet", "claude-code"),
    ]

    for args, expected_model, expected_tool in test_cases:
        exit_code = main(args)
        assert exit_code == 0
        assert captured_args["model"] == expected_model
        assert captured_args["tool"] == expected_tool


def test_code_command_invalid_model(monkeypatch, caplog, tmp_path) -> None:
    """Test code command raises validation error for invalid model."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    # Mock run_code_command - should not be called due to validation error
    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with invalid model
    exit_code = main(["code", str(plan_path), "--model", "gpt-4"])

    assert exit_code == 1
    assert "Unknown model 'gpt-4'" in caplog.text
    mock_run.assert_not_called()


def test_code_command_droid_with_model_error(monkeypatch, caplog, tmp_path) -> None:
    """Test code command rejects droid tool with model parameter."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    # Mock run_code_command - should not be called due to validation error
    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with droid + model (invalid combination)
    exit_code = main(["code", str(plan_path), "--tool", "droid", "--model", "sonnet"])

    assert exit_code == 1
    assert "cannot be used with --tool droid" in caplog.text
    mock_run.assert_not_called()


def test_code_command_invalid_tool_error(monkeypatch, caplog, tmp_path) -> None:
    """Test code command rejects invalid tool name."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    # Mock run_code_command - should not be called due to validation error
    mock_run = MagicMock()
    monkeypatch.setattr("lw_coder.cli.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with invalid tool
    exit_code = main(["code", str(plan_path), "--tool", "invalid-tool"])

    assert exit_code == 1
    assert "Unknown tool 'invalid-tool'" in caplog.text
    mock_run.assert_not_called()