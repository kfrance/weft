"""Unit tests for argparse/argcomplete integration.

These tests verify the integration between argparse and argcomplete
for tab completion. No external API calls are made.
"""

from __future__ import annotations

import pytest

# Check if argcomplete is available
try:
    import argcomplete
    ARGCOMPLETE_AVAILABLE = True
except ImportError:
    ARGCOMPLETE_AVAILABLE = False

from lw_coder.cli import create_parser


def test_argcomplete_available():
    """Test that argcomplete is installed (fail if missing per best practices)."""
    if not ARGCOMPLETE_AVAILABLE:
        pytest.fail(
            "argcomplete is not installed. Install it with: pip install argcomplete\n"
            "This is required for tab completion functionality."
        )


def test_parser_creation():
    """Test that argument parser can be created."""
    parser = create_parser()
    assert parser is not None
    assert parser.prog == "lw_coder"


def test_parser_has_completers():
    """Test that parser arguments have completer functions attached."""
    if not ARGCOMPLETE_AVAILABLE:
        pytest.skip("argcomplete not available")

    parser = create_parser()

    # Find the subparsers action
    subparsers_action = None
    for action in parser._subparsers._actions:
        if hasattr(action, "choices") and action.choices is not None:
            subparsers_action = action
            break

    assert subparsers_action is not None
    code_subparser = subparsers_action.choices.get("code")
    assert code_subparser is not None

    # Check that plan_path has a completer
    plan_path_action = None
    for action in code_subparser._actions:
        if action.dest == "plan_path":
            plan_path_action = action
            break

    assert plan_path_action is not None
    assert hasattr(plan_path_action, "completer")
    assert plan_path_action.completer is not None


def test_parser_tool_arg_has_completer():
    """Test that --tool argument has completer."""
    if not ARGCOMPLETE_AVAILABLE:
        pytest.skip("argcomplete not available")

    parser = create_parser()

    # Find the subparsers action
    subparsers_action = None
    for action in parser._subparsers._actions:
        if hasattr(action, "choices") and action.choices is not None:
            subparsers_action = action
            break

    assert subparsers_action is not None
    code_subparser = subparsers_action.choices.get("code")
    assert code_subparser is not None

    # Check that --tool has a completer
    tool_action = None
    for action in code_subparser._actions:
        if hasattr(action, "option_strings") and "--tool" in action.option_strings:
            tool_action = action
            break

    assert tool_action is not None
    assert hasattr(tool_action, "completer")
    assert tool_action.completer is not None


def test_parser_model_arg_has_completer():
    """Test that --model argument has completer."""
    if not ARGCOMPLETE_AVAILABLE:
        pytest.skip("argcomplete not available")

    parser = create_parser()

    # Find the subparsers action
    subparsers_action = None
    for action in parser._subparsers._actions:
        if hasattr(action, "choices") and action.choices is not None:
            subparsers_action = action
            break

    assert subparsers_action is not None
    code_subparser = subparsers_action.choices.get("code")
    assert code_subparser is not None

    # Check that --model has a completer
    model_action = None
    for action in code_subparser._actions:
        if hasattr(action, "option_strings") and "--model" in action.option_strings:
            model_action = action
            break

    assert model_action is not None
    assert hasattr(model_action, "completer")
    assert model_action.completer is not None


def test_argcomplete_integration():
    """Test that argcomplete can be applied to parser without errors."""
    if not ARGCOMPLETE_AVAILABLE:
        pytest.fail(
            "argcomplete is not installed. Install it with: pip install argcomplete\n"
            "This is required for tab completion functionality."
        )

    parser = create_parser()

    # This should not raise an error
    try:
        # We can't actually run autocomplete in tests, but we can verify
        # that the parser is compatible with argcomplete
        argcomplete.autocomplete(parser, exit_method=lambda code: None)
    except Exception as exc:
        pytest.fail(f"argcomplete.autocomplete() raised {type(exc).__name__}: {exc}")


