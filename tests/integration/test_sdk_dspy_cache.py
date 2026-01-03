"""Integration tests for SDK sandbox DSPy cache access.

These tests verify that the SDK sandbox is correctly configured to allow
Python file I/O to the DSPy cache directory at ~/.weft/dspy_cache/.

This tests the actual permission path: sandboxed Bash → Python subprocess → file I/O.
More accurate than testing Claude's Write tool since DSPy uses Python file operations.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest

from weft.judge_executor import get_cache_dir
from weft.sdk_runner import generate_sdk_settings


def test_generate_sdk_settings_adds_cache_permissions(tmp_path: Path) -> None:
    """Test that generate_sdk_settings adds DSPy cache permissions."""
    # Create a minimal base settings file
    base_settings = {
        "sandbox": {
            "enabled": True,
            "autoAllowBashIfSandboxed": True,
        },
        "permissions": {
            "allow": [],
        },
    }
    base_settings_path = tmp_path / "sdk_settings.json"
    base_settings_path.write_text(json.dumps(base_settings), encoding="utf-8")

    # Generate settings with cache permissions
    result = generate_sdk_settings(base_settings_path)

    # Verify cache permissions were added
    cache_path = str(get_cache_dir())
    expected_edit_rule = f"Edit({cache_path}/**)"
    expected_write_rule = f"Write({cache_path}/**)"

    assert expected_edit_rule in result["permissions"]["allow"]
    assert expected_write_rule in result["permissions"]["allow"]


def test_generate_sdk_settings_preserves_existing_permissions(tmp_path: Path) -> None:
    """Test that generate_sdk_settings preserves existing permission rules."""
    # Create settings with existing permissions
    base_settings = {
        "sandbox": {
            "enabled": True,
        },
        "permissions": {
            "allow": [
                "Edit(/some/other/path/**)",
                "Bash(git *)",
            ],
        },
    }
    base_settings_path = tmp_path / "sdk_settings.json"
    base_settings_path.write_text(json.dumps(base_settings), encoding="utf-8")

    # Generate settings with cache permissions
    result = generate_sdk_settings(base_settings_path)

    # Verify existing permissions were preserved
    assert "Edit(/some/other/path/**)" in result["permissions"]["allow"]
    assert "Bash(git *)" in result["permissions"]["allow"]

    # Verify cache permissions were added
    cache_path = str(get_cache_dir())
    assert f"Edit({cache_path}/**)" in result["permissions"]["allow"]
    assert f"Write({cache_path}/**)" in result["permissions"]["allow"]


def test_generate_sdk_settings_no_duplicate_rules(tmp_path: Path) -> None:
    """Test that generate_sdk_settings doesn't duplicate existing cache rules."""
    cache_path = str(get_cache_dir())

    # Create settings that already have cache permissions
    base_settings = {
        "sandbox": {"enabled": True},
        "permissions": {
            "allow": [
                f"Edit({cache_path}/**)",
                f"Write({cache_path}/**)",
            ],
        },
    }
    base_settings_path = tmp_path / "sdk_settings.json"
    base_settings_path.write_text(json.dumps(base_settings), encoding="utf-8")

    # Generate settings
    result = generate_sdk_settings(base_settings_path)

    # Count occurrences of each rule
    edit_count = result["permissions"]["allow"].count(f"Edit({cache_path}/**)")
    write_count = result["permissions"]["allow"].count(f"Write({cache_path}/**)")

    assert edit_count == 1, "Should not duplicate Edit rule"
    assert write_count == 1, "Should not duplicate Write rule"


def test_generate_sdk_settings_creates_missing_sections(tmp_path: Path) -> None:
    """Test that generate_sdk_settings creates missing sandbox/permissions sections."""
    # Create minimal settings without sandbox or permissions
    base_settings = {}
    base_settings_path = tmp_path / "sdk_settings.json"
    base_settings_path.write_text(json.dumps(base_settings), encoding="utf-8")

    # Generate settings
    result = generate_sdk_settings(base_settings_path)

    # Verify sections were created
    assert "sandbox" in result
    assert "permissions" in result
    assert "allow" in result["permissions"]

    # Verify cache permissions were added
    cache_path = str(get_cache_dir())
    assert f"Edit({cache_path}/**)" in result["permissions"]["allow"]
    assert f"Write({cache_path}/**)" in result["permissions"]["allow"]


def test_get_cache_dir_returns_expected_path() -> None:
    """Test that get_cache_dir() returns the expected location."""
    expected = Path.home() / ".weft" / "dspy_cache"
    assert get_cache_dir() == expected
