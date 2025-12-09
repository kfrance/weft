"""Tests for Droid authentication checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lw_coder.droid_auth import DroidAuthError, check_droid_auth


def test_check_droid_auth_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that check_droid_auth raises error when auth.json is missing."""
    # Create a fake home directory without auth.json
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    with pytest.raises(DroidAuthError, match="Droid authentication required"):
        check_droid_auth()


def test_check_droid_auth_missing_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that check_droid_auth raises error when auth.json lacks required keys."""
    # Create auth.json with incomplete data
    fake_home = tmp_path / "home"
    factory_dir = fake_home / ".factory"
    factory_dir.mkdir(parents=True)
    auth_file = factory_dir / "auth.json"

    # Missing refresh_token
    auth_file.write_text(json.dumps({"access_token": "test_token"}))
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    with pytest.raises(DroidAuthError, match="missing required keys: refresh_token"):
        check_droid_auth()


def test_check_droid_auth_invalid_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that check_droid_auth raises error when auth.json is invalid JSON."""
    fake_home = tmp_path / "home"
    factory_dir = fake_home / ".factory"
    factory_dir.mkdir(parents=True)
    auth_file = factory_dir / "auth.json"

    # Write invalid JSON
    auth_file.write_text("not valid json {")
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    with pytest.raises(DroidAuthError, match="Failed to read Droid authentication file"):
        check_droid_auth()


def test_check_droid_auth_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that check_droid_auth succeeds with valid authentication."""
    fake_home = tmp_path / "home"
    factory_dir = fake_home / ".factory"
    factory_dir.mkdir(parents=True)
    auth_file = factory_dir / "auth.json"

    # Write valid auth data
    auth_data = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
    }
    auth_file.write_text(json.dumps(auth_data))
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    result = check_droid_auth()
    assert result == auth_file
