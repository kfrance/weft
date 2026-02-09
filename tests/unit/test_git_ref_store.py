"""Tests for git ref store abstraction."""

from __future__ import annotations

import pytest

from weft.git_ref_store import (
    GitRefStore,
    GitRefStoreError,
    RefExistsError,
    RefNotFoundError,
)

from tests.helpers import GitRepo


def test_save_creates_orphan_commit_and_ref(git_repo: GitRepo) -> None:
    """Verify ref created at expected path with correct content."""
    store = GitRefStore(git_repo.path, "test-ns")
    store.save("test-item", "hello world", "data.txt", "Test commit")

    # Verify ref exists
    result = git_repo.run("show-ref", "refs/test-ns/test-item")
    assert "refs/test-ns/test-item" in result.stdout

    # Verify content
    commit_sha = result.stdout.split()[0]
    content_result = git_repo.run("show", f"{commit_sha}:data.txt")
    assert content_result.stdout == "hello world"

    # Verify orphan commit (no parents)
    parents_result = git_repo.run("rev-list", "--parents", "-n", "1", commit_sha)
    parts = parents_result.stdout.strip().split()
    assert len(parts) == 1, "Commit should have no parents (orphan)"


def test_save_atomic_rejects_duplicate(git_repo: GitRepo) -> None:
    """Verify error when ref already exists and atomic=True."""
    store = GitRefStore(git_repo.path, "test-ns")
    store.save("test-item", "first", "data.txt", "First commit", atomic=True)

    with pytest.raises(RefExistsError, match="already exists"):
        store.save("test-item", "second", "data.txt", "Second commit", atomic=True)


def test_save_force_updates_existing(git_repo: GitRepo) -> None:
    """Verify force-update when atomic=False."""
    store = GitRefStore(git_repo.path, "test-ns")
    store.save("test-item", "first", "data.txt", "First commit", atomic=False)

    result1 = git_repo.run("show-ref", "--hash", "refs/test-ns/test-item")
    sha1 = result1.stdout.strip()

    store.save("test-item", "second", "data.txt", "Second commit", atomic=False)

    result2 = git_repo.run("show-ref", "--hash", "refs/test-ns/test-item")
    sha2 = result2.stdout.strip()

    assert sha1 != sha2

    # Verify updated content
    content = store.read("test-item", "data.txt")
    assert content == "second"


def test_read_returns_content(git_repo: GitRepo) -> None:
    """Verify content round-trip (save then read)."""
    store = GitRefStore(git_repo.path, "test-ns")
    original = "Some markdown\n\n## Section\n\nContent here."
    store.save("test-item", original, "findings.md", "Test commit")

    content = store.read("test-item", "findings.md")
    assert content == original


def test_read_not_found_raises(git_repo: GitRepo) -> None:
    """Verify error on missing ref."""
    store = GitRefStore(git_repo.path, "test-ns")
    with pytest.raises(RefNotFoundError, match="not found"):
        store.read("nonexistent", "data.txt")


def test_list_refs_returns_metadata(git_repo: GitRepo) -> None:
    """Verify listing returns name and timestamp."""
    store = GitRefStore(git_repo.path, "test-ns")
    store.save("alpha", "content-a", "data.txt", "Alpha")
    store.save("bravo", "content-b", "data.txt", "Bravo")

    refs = store.list_refs()

    assert len(refs) == 2
    names = [name for name, _ in refs]
    assert "alpha" in names
    assert "bravo" in names

    # Verify timestamps are positive integers
    for _, timestamp in refs:
        assert isinstance(timestamp, int)
        assert timestamp > 0

    # Verify sorted by name
    assert refs[0][0] == "alpha"
    assert refs[1][0] == "bravo"


def test_list_refs_empty(git_repo: GitRepo) -> None:
    """Verify empty list when no refs exist."""
    store = GitRefStore(git_repo.path, "test-ns")
    refs = store.list_refs()
    assert refs == []


def test_delete_removes_ref(git_repo: GitRepo) -> None:
    """Verify ref deletion."""
    store = GitRefStore(git_repo.path, "test-ns")
    store.save("test-item", "content", "data.txt", "Test commit")

    assert store.exists("test-item") is True

    store.delete("test-item")

    assert store.exists("test-item") is False


def test_delete_idempotent(git_repo: GitRepo) -> None:
    """Verify no error when ref doesn't exist."""
    store = GitRefStore(git_repo.path, "test-ns")
    # Should not raise
    store.delete("nonexistent")
    store.delete("nonexistent")  # Second call also fine


def test_exists_true_and_false(git_repo: GitRepo) -> None:
    """Verify existence check both ways."""
    store = GitRefStore(git_repo.path, "test-ns")

    assert store.exists("test-item") is False

    store.save("test-item", "content", "data.txt", "Test commit")

    assert store.exists("test-item") is True


def test_move_between_namespaces(git_repo: GitRepo) -> None:
    """Verify ref moved from source to destination namespace."""
    source = GitRefStore(git_repo.path, "source-ns")
    dest = GitRefStore(git_repo.path, "dest-ns")

    source.save("test-item", "content", "data.txt", "Test commit")

    assert source.exists("test-item") is True
    assert dest.exists("test-item") is False

    source.move("test-item", dest)

    assert source.exists("test-item") is False
    assert dest.exists("test-item") is True

    # Verify content preserved
    content = dest.read("test-item", "data.txt")
    assert content == "content"


def test_validates_name(git_repo: GitRepo) -> None:
    """Verify name pattern enforcement."""
    store = GitRefStore(git_repo.path, "test-ns")

    # Too short
    with pytest.raises(GitRefStoreError, match="Invalid name"):
        store.save("ab", "content", "data.txt", "Test commit")

    # Invalid characters
    with pytest.raises(GitRefStoreError, match="Invalid name"):
        store.save("test@name", "content", "data.txt", "Test commit")

    # Empty
    with pytest.raises(GitRefStoreError, match="cannot be empty"):
        store.save("", "content", "data.txt", "Test commit")
