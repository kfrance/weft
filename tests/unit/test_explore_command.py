"""Tests for explore command module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from weft.explore_command import (
    ExploreCommandError,
    _handle_findings,
    _handle_no_findings,
    _parse_artifact,
    run_explore_command,
)

from tests.helpers import GitRepo


# =============================================================================
# Artifact Parsing Tests
# =============================================================================


def test_parse_artifact_valid() -> None:
    """Verify valid artifact parses correctly."""
    content = "---\nname: cache-ttl-bug\n---\n## Findings\n\nThe TTL is too low."
    name, body = _parse_artifact(content)
    assert name == "cache-ttl-bug"
    assert body == "## Findings\n\nThe TTL is too low."


def test_parse_artifact_missing_frontmatter() -> None:
    """Verify error when no frontmatter delimiters."""
    with pytest.raises(ExploreCommandError, match="invalid format"):
        _parse_artifact("No frontmatter here")


def test_parse_artifact_missing_name() -> None:
    """Verify error when name field is missing."""
    content = "---\nstatus: done\n---\nSome findings."
    with pytest.raises(ExploreCommandError, match="missing 'name' field"):
        _parse_artifact(content)


def test_parse_artifact_invalid_name() -> None:
    """Verify error when name has invalid characters."""
    content = "---\nname: test@invalid!\n---\nSome findings."
    with pytest.raises(ExploreCommandError, match="Invalid exploration name"):
        _parse_artifact(content)


def test_parse_artifact_empty_body() -> None:
    """Verify error when body is empty."""
    content = "---\nname: valid-name\n---\n"
    with pytest.raises(ExploreCommandError, match="empty findings body"):
        _parse_artifact(content)


def test_parse_artifact_name_too_short() -> None:
    """Verify error when name is too short (< 3 chars)."""
    content = "---\nname: ab\n---\nSome findings."
    with pytest.raises(ExploreCommandError, match="Invalid exploration name"):
        _parse_artifact(content)


def test_parse_artifact_whitespace_only_body() -> None:
    """Verify error when body is only whitespace."""
    content = "---\nname: valid-name\n---\n   \n  \n  "
    with pytest.raises(ExploreCommandError, match="empty findings body"):
        _parse_artifact(content)


# =============================================================================
# Handle Findings Tests
# =============================================================================


def test_handle_findings_success(git_repo: GitRepo, tmp_path: Path) -> None:
    """Verify findings are saved and success message printed."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    artifact_path = worktree_path / ".exploration_artifact.md"
    artifact_path.write_text(
        "---\nname: cache-bug\n---\n## Findings\n\nCache TTL too low.",
        encoding="utf-8",
    )

    with patch("weft.explore_command.save_exploration") as mock_save:
        exit_code = _handle_findings(git_repo.path, worktree_path, artifact_path)

    assert exit_code == 0
    mock_save.assert_called_once_with(
        git_repo.path, "cache-bug", "## Findings\n\nCache TTL too low."
    )


def test_handle_findings_duplicate_name(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    """Verify error when exploration name already exists."""
    from weft.exploration_store import ExplorationExistsError

    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    artifact_path = worktree_path / ".exploration_artifact.md"
    artifact_path.write_text(
        "---\nname: existing-name\n---\nSome findings.",
        encoding="utf-8",
    )

    with patch(
        "weft.explore_command.save_exploration",
        side_effect=ExplorationExistsError("already exists"),
    ):
        exit_code = _handle_findings(git_repo.path, worktree_path, artifact_path)

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "already exists" in captured.out


def test_handle_findings_invalid_artifact(git_repo: GitRepo, tmp_path: Path, capsys) -> None:
    """Verify error when artifact is malformed."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    artifact_path = worktree_path / ".exploration_artifact.md"
    artifact_path.write_text("invalid content without frontmatter", encoding="utf-8")

    exit_code = _handle_findings(git_repo.path, worktree_path, artifact_path)

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Failed to process" in captured.out


# =============================================================================
# Handle No Findings Tests
# =============================================================================


def test_handle_no_findings_cleanup_yes(git_repo: GitRepo, tmp_path: Path, monkeypatch) -> None:
    """Verify worktree cleaned up when user says yes."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    monkeypatch.setattr("builtins.input", lambda prompt: "y")

    with patch("weft.explore_command.remove_temp_worktree") as mock_remove:
        exit_code = _handle_no_findings(git_repo.path, worktree_path)

    assert exit_code == 0
    mock_remove.assert_called_once_with(git_repo.path, worktree_path)


def test_handle_no_findings_preserve_no(git_repo: GitRepo, tmp_path: Path, monkeypatch, capsys) -> None:
    """Verify worktree preserved when user says no."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    with patch("weft.explore_command.remove_temp_worktree") as mock_remove:
        exit_code = _handle_no_findings(git_repo.path, worktree_path)

    assert exit_code == 0
    mock_remove.assert_not_called()
    captured = capsys.readouterr()
    assert "preserved" in captured.out.lower()


def test_handle_no_findings_eof(git_repo: GitRepo, tmp_path: Path, monkeypatch, capsys) -> None:
    """Verify worktree preserved on Ctrl+D (EOFError)."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    def raise_eof(prompt):
        raise EOFError()

    monkeypatch.setattr("builtins.input", raise_eof)

    with patch("weft.explore_command.remove_temp_worktree") as mock_remove:
        exit_code = _handle_no_findings(git_repo.path, worktree_path)

    assert exit_code == 0
    mock_remove.assert_not_called()


# =============================================================================
# Run Explore Command Tests
# =============================================================================


def test_run_explore_command_invalid_tool() -> None:
    """Verify error with unknown tool."""
    exit_code = run_explore_command(text="test", tool="nonexistent-tool")
    assert exit_code == 1


def test_run_explore_command_returns_int() -> None:
    """Verify run_explore_command returns an integer."""
    # Quick test with invalid tool to ensure function returns int
    result = run_explore_command(text="test", tool="nonexistent-tool")
    assert isinstance(result, int)
