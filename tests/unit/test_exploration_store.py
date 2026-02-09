"""Tests for exploration store module."""

from __future__ import annotations

import pytest

from weft.exploration_store import (
    ExplorationExistsError,
    ExplorationNotFoundError,
    ExplorationStoreError,
    delete_exploration,
    exploration_exists,
    list_explorations,
    read_exploration,
    save_exploration,
)

from tests.helpers import GitRepo


def test_save_exploration_creates_ref(git_repo: GitRepo) -> None:
    """Verify exploration saved at refs/weft/explorations/<name>."""
    save_exploration(git_repo.path, "cache-ttl-bug", "Findings about cache TTL bug")

    result = git_repo.run("show-ref", "refs/weft/explorations/cache-ttl-bug")
    assert "refs/weft/explorations/cache-ttl-bug" in result.stdout


def test_save_exploration_atomic_rejects_duplicate(git_repo: GitRepo) -> None:
    """Verify error when name already exists."""
    save_exploration(git_repo.path, "cache-ttl-bug", "First findings")

    with pytest.raises(ExplorationExistsError, match="already exists"):
        save_exploration(git_repo.path, "cache-ttl-bug", "Second findings")


def test_read_exploration_returns_content(git_repo: GitRepo) -> None:
    """Verify content round-trip."""
    original = "## Findings\n\nThe cache TTL is set too low."
    save_exploration(git_repo.path, "cache-ttl-bug", original)

    content = read_exploration(git_repo.path, "cache-ttl-bug")
    assert content == original


def test_read_exploration_not_found_raises(git_repo: GitRepo) -> None:
    """Verify error on missing exploration."""
    with pytest.raises(ExplorationNotFoundError, match="not found"):
        read_exploration(git_repo.path, "nonexistent")


def test_list_explorations_returns_metadata(git_repo: GitRepo) -> None:
    """Verify listing with name and timestamp."""
    save_exploration(git_repo.path, "alpha-bug", "Alpha findings")
    save_exploration(git_repo.path, "bravo-fix", "Bravo findings")

    explorations = list_explorations(git_repo.path)

    assert len(explorations) == 2
    names = [name for name, _ in explorations]
    assert "alpha-bug" in names
    assert "bravo-fix" in names

    # Verify timestamps are positive integers
    for _, timestamp in explorations:
        assert isinstance(timestamp, int)
        assert timestamp > 0


def test_list_explorations_empty(git_repo: GitRepo) -> None:
    """Verify empty list."""
    explorations = list_explorations(git_repo.path)
    assert explorations == []


def test_delete_exploration_removes_ref(git_repo: GitRepo) -> None:
    """Verify ref deletion."""
    save_exploration(git_repo.path, "cache-ttl-bug", "Findings")
    assert exploration_exists(git_repo.path, "cache-ttl-bug") is True

    delete_exploration(git_repo.path, "cache-ttl-bug")
    assert exploration_exists(git_repo.path, "cache-ttl-bug") is False


def test_delete_exploration_idempotent(git_repo: GitRepo) -> None:
    """Verify no error on missing ref."""
    delete_exploration(git_repo.path, "nonexistent")
    delete_exploration(git_repo.path, "nonexistent")


def test_exploration_exists(git_repo: GitRepo) -> None:
    """Verify existence check."""
    assert exploration_exists(git_repo.path, "cache-ttl-bug") is False

    save_exploration(git_repo.path, "cache-ttl-bug", "Findings")
    assert exploration_exists(git_repo.path, "cache-ttl-bug") is True


def test_save_exploration_validates_name(git_repo: GitRepo) -> None:
    """Verify name validation (invalid chars, too short, too long)."""
    # Too short
    with pytest.raises(ExplorationStoreError, match="Invalid exploration name"):
        save_exploration(git_repo.path, "ab", "content")

    # Invalid characters
    with pytest.raises(ExplorationStoreError, match="Invalid exploration name"):
        save_exploration(git_repo.path, "test@name", "content")

    # Too long
    with pytest.raises(ExplorationStoreError, match="Invalid exploration name"):
        save_exploration(git_repo.path, "a" * 101, "content")

    # Empty
    with pytest.raises(ExplorationStoreError, match="cannot be empty"):
        save_exploration(git_repo.path, "", "content")


def test_save_exploration_rejects_empty_content(git_repo: GitRepo) -> None:
    """Verify error on empty content."""
    with pytest.raises(ExplorationStoreError, match="cannot be empty"):
        save_exploration(git_repo.path, "test-bug", "")

    with pytest.raises(ExplorationStoreError, match="cannot be empty"):
        save_exploration(git_repo.path, "test-bug", "   ")
