"""Tests for CLI argument parsing and validation."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.cli import main


def test_code_command_explicit_tool(monkeypatch, tmp_path) -> None:
    """Test code command with explicit --tool parameter."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

    # Run CLI with explicit tool
    exit_code = main(["code", str(plan_path), "--tool", "droid"])

    assert exit_code == 0
    assert captured_args["tool"] == "droid"


def test_code_command_explicit_model(monkeypatch, tmp_path) -> None:
    """Test code command with explicit --model parameter."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

    # Run CLI with explicit model
    exit_code = main(["code", str(plan_path), "--model", "opus"])

    assert exit_code == 0
    assert captured_args["model"] == "opus"


def test_code_command_tool_and_model(monkeypatch, tmp_path) -> None:
    """Test code command with both --tool and --model parameters."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

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


def test_plan_command_tool_parameter(monkeypatch, tmp_path) -> None:
    """Test plan command accepts --tool parameter."""
    captured_args = {}

    def mock_run_plan_command(path, text, tool, no_hooks=False):
        captured_args["path"] = path
        captured_args["text"] = text
        captured_args["tool"] = tool
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.plan_command.run_plan_command", mock_run_plan_command)

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

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        return 0

    monkeypatch.setattr("lw_coder.cli.configure_logging", mock_configure_logging)
    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

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

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

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
    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run)

    caplog.set_level(logging.ERROR)

    # Run CLI with invalid model
    exit_code = main(["code", str(plan_path), "--model", "gpt-4"])

    assert exit_code == 1
    assert "Unknown model 'gpt-4'" in caplog.text
    mock_run.assert_not_called()


# Quick Fix CLI Tests


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
    assert captured_args["model"] == "sonnet"

    # Verify plan file was created
    plan_path = captured_args["path"]
    assert plan_path.exists()
    assert plan_path.name.startswith("quick-fix-")
    assert "Fix the login button" in plan_path.read_text(encoding="utf-8")


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


def test_code_command_text_with_tool_flag(monkeypatch, git_repo) -> None:
    """Test --text works with --tool flag."""
    monkeypatch.chdir(git_repo.path)

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

    # Run CLI with --text and --tool
    exit_code = main(["code", "--text", "Fix bug", "--tool", "droid"])

    assert exit_code == 0
    assert captured_args["tool"] == "droid"
    assert captured_args["model"] is None  # droid ignores model


def test_code_command_text_with_model_flag(monkeypatch, git_repo) -> None:
    """Test --text works with --model flag."""
    monkeypatch.chdir(git_repo.path)

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

    # Run CLI with --text and --model
    exit_code = main(["code", "--text", "Fix bug", "--model", "opus"])

    assert exit_code == 0
    assert captured_args["model"] == "opus"


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
# Init Command CLI Tests
# =============================================================================


def test_init_command_success(monkeypatch, git_repo) -> None:
    """Test init command success via CLI."""
    captured_args = {}

    def mock_run_init_command(force=False, yes=False):
        captured_args["force"] = force
        captured_args["yes"] = yes
        return 0

    monkeypatch.setattr("lw_coder.cli.run_init_command", mock_run_init_command)

    exit_code = main(["init"])

    assert exit_code == 0
    assert captured_args["force"] is False
    assert captured_args["yes"] is False


def test_init_command_with_force(monkeypatch, git_repo) -> None:
    """Test init command with --force flag."""
    captured_args = {}

    def mock_run_init_command(force=False, yes=False):
        captured_args["force"] = force
        captured_args["yes"] = yes
        return 0

    monkeypatch.setattr("lw_coder.cli.run_init_command", mock_run_init_command)

    exit_code = main(["init", "--force"])

    assert exit_code == 0
    assert captured_args["force"] is True
    assert captured_args["yes"] is False


def test_init_command_with_yes(monkeypatch, git_repo) -> None:
    """Test init command with --yes flag."""
    captured_args = {}

    def mock_run_init_command(force=False, yes=False):
        captured_args["force"] = force
        captured_args["yes"] = yes
        return 0

    monkeypatch.setattr("lw_coder.cli.run_init_command", mock_run_init_command)

    exit_code = main(["init", "--yes"])

    assert exit_code == 0
    assert captured_args["force"] is False
    assert captured_args["yes"] is True


def test_init_command_with_force_and_yes(monkeypatch, git_repo) -> None:
    """Test init command with both --force and --yes flags."""
    captured_args = {}

    def mock_run_init_command(force=False, yes=False):
        captured_args["force"] = force
        captured_args["yes"] = yes
        return 0

    monkeypatch.setattr("lw_coder.cli.run_init_command", mock_run_init_command)

    exit_code = main(["init", "--force", "--yes"])

    assert exit_code == 0
    assert captured_args["force"] is True
    assert captured_args["yes"] is True


def test_init_command_help_text(capsys) -> None:
    """Test init command help text is displayed."""
    with pytest.raises(SystemExit) as exc_info:
        main(["init", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    # Check that help is displayed (may be in either out or err depending on argparse version)
    help_text = captured.out + captured.err
    assert "--force" in help_text
    assert "--yes" in help_text
    assert "init" in help_text


# =============================================================================
# --no-hooks Flag CLI Tests
# =============================================================================


def test_plan_command_no_hooks_flag(monkeypatch) -> None:
    """Test plan command accepts --no-hooks flag."""
    captured_args = {}

    def mock_run_plan_command(path, text, tool, no_hooks=False):
        captured_args["path"] = path
        captured_args["text"] = text
        captured_args["tool"] = tool
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.plan_command.run_plan_command", mock_run_plan_command)

    # Run plan command with --no-hooks
    exit_code = main(["plan", "--text", "Test idea", "--no-hooks"])

    assert exit_code == 0
    assert captured_args["no_hooks"] is True


def test_plan_command_no_hooks_default_false(monkeypatch) -> None:
    """Test plan command --no-hooks defaults to False."""
    captured_args = {}

    def mock_run_plan_command(path, text, tool, no_hooks=False):
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.plan_command.run_plan_command", mock_run_plan_command)

    # Run plan command without --no-hooks
    exit_code = main(["plan", "--text", "Test idea"])

    assert exit_code == 0
    assert captured_args["no_hooks"] is False


def test_code_command_no_hooks_flag(monkeypatch, tmp_path) -> None:
    """Test code command accepts --no-hooks flag."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["path"] = path
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

    # Run code command with --no-hooks
    exit_code = main(["code", str(plan_path), "--no-hooks"])

    assert exit_code == 0
    assert captured_args["no_hooks"] is True


def test_code_command_no_hooks_default_false(monkeypatch, tmp_path) -> None:
    """Test code command --no-hooks defaults to False."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

    # Run code command without --no-hooks
    exit_code = main(["code", str(plan_path)])

    assert exit_code == 0
    assert captured_args["no_hooks"] is False


def test_code_command_no_hooks_with_other_flags(monkeypatch, tmp_path) -> None:
    """Test code command --no-hooks works with other flags."""
    plan_path = tmp_path / "test.md"
    plan_path.write_text("# Test Plan\n")

    captured_args = {}

    def mock_run_code_command(path, tool="claude-code", model=None, no_hooks=False):
        captured_args["tool"] = tool
        captured_args["model"] = model
        captured_args["no_hooks"] = no_hooks
        return 0

    monkeypatch.setattr("lw_coder.code_command.run_code_command", mock_run_code_command)

    # Run code command with multiple flags
    exit_code = main(["code", str(plan_path), "--model", "opus", "--no-hooks"])

    assert exit_code == 0
    assert captured_args["model"] == "opus"
    assert captured_args["no_hooks"] is True


def test_no_hooks_help_text_plan(capsys) -> None:
    """Test --no-hooks appears in plan command help."""
    with pytest.raises(SystemExit) as exc_info:
        main(["plan", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    help_text = captured.out + captured.err
    assert "--no-hooks" in help_text


def test_no_hooks_help_text_code(capsys) -> None:
    """Test --no-hooks appears in code command help."""
    with pytest.raises(SystemExit) as exc_info:
        main(["code", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    help_text = captured.out + captured.err
    assert "--no-hooks" in help_text

