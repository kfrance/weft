"""Exploration artifact storage using git refs.

Thin wrapper around GitRefStore for managing exploration artifacts
at refs/weft/explorations/<name>. Content is stored as findings.md
in orphan commits with atomic creation (prevents overwriting).
"""

from __future__ import annotations

from pathlib import Path

from .git_ref_store import GitRefStore, GitRefStoreError, RefExistsError, RefNotFoundError
from .logging_config import get_logger
from .plan_validator import _PLAN_ID_PATTERN

logger = get_logger(__name__)

_NAMESPACE = "weft/explorations"
_FILE_PATH = "findings.md"


class ExplorationStoreError(Exception):
    """Base exception for exploration store operations."""


class ExplorationExistsError(ExplorationStoreError):
    """Raised when an exploration with the same name already exists."""


class ExplorationNotFoundError(ExplorationStoreError):
    """Raised when an exploration doesn't exist."""


def _validate_exploration_name(name: str) -> None:
    """Validate exploration name.

    Args:
        name: Exploration name to validate.

    Raises:
        ExplorationStoreError: If name is invalid.
    """
    if not isinstance(name, str) or not name.strip():
        raise ExplorationStoreError("Exploration name cannot be empty")

    if not _PLAN_ID_PATTERN.fullmatch(name.strip()):
        raise ExplorationStoreError(
            f"Invalid exploration name '{name}'. Names must match pattern "
            "^[a-zA-Z0-9._-]{3,100}$ (3-100 chars, alphanumeric/._- only)."
        )


def _store(repo_root: Path) -> GitRefStore:
    """Create a GitRefStore for explorations."""
    return GitRefStore(repo_root, _NAMESPACE)


def save_exploration(repo_root: Path, name: str, content: str) -> None:
    """Save exploration findings as an atomic orphan commit.

    Args:
        repo_root: Repository root directory.
        name: Exploration name (chosen by LLM, kebab-case).
        content: Findings content (markdown body, no frontmatter).

    Raises:
        ExplorationStoreError: If save fails.
        ExplorationExistsError: If an exploration with this name already exists.
    """
    _validate_exploration_name(name)

    if not content or not content.strip():
        raise ExplorationStoreError("Exploration content cannot be empty")

    store = _store(repo_root)
    try:
        store.save(
            name=name,
            content=content,
            file_path=_FILE_PATH,
            commit_message=f"Exploration: {name}",
            atomic=True,
        )
        logger.info("Saved exploration: %s", name)
    except RefExistsError as exc:
        raise ExplorationExistsError(
            f"Exploration '{name}' already exists. Choose a different name."
        ) from exc
    except GitRefStoreError as exc:
        raise ExplorationStoreError(
            f"Failed to save exploration '{name}': {exc}"
        ) from exc


def read_exploration(repo_root: Path, name: str) -> str:
    """Read exploration findings content.

    Args:
        repo_root: Repository root directory.
        name: Exploration name.

    Returns:
        The findings content string.

    Raises:
        ExplorationNotFoundError: If exploration doesn't exist.
        ExplorationStoreError: If read fails.
    """
    _validate_exploration_name(name)
    store = _store(repo_root)
    try:
        return store.read(name, _FILE_PATH)
    except RefNotFoundError as exc:
        raise ExplorationNotFoundError(
            f"Exploration '{name}' not found."
        ) from exc
    except GitRefStoreError as exc:
        raise ExplorationStoreError(
            f"Failed to read exploration '{name}': {exc}"
        ) from exc


def list_explorations(repo_root: Path) -> list[tuple[str, int]]:
    """List all explorations with metadata.

    Args:
        repo_root: Repository root directory.

    Returns:
        List of (name, timestamp) tuples sorted by name.
        timestamp is Unix epoch seconds from commit timestamp.

    Raises:
        ExplorationStoreError: If listing fails.
    """
    store = _store(repo_root)
    try:
        return store.list_refs()
    except GitRefStoreError as exc:
        raise ExplorationStoreError(
            f"Failed to list explorations: {exc}"
        ) from exc


def delete_exploration(repo_root: Path, name: str) -> None:
    """Delete an exploration ref (idempotent).

    Args:
        repo_root: Repository root directory.
        name: Exploration name.

    Raises:
        ExplorationStoreError: If name validation fails.
    """
    _validate_exploration_name(name)
    store = _store(repo_root)
    try:
        store.delete(name)
    except GitRefStoreError as exc:
        raise ExplorationStoreError(
            f"Failed to delete exploration '{name}': {exc}"
        ) from exc
    logger.info("Deleted exploration: %s", name)


def exploration_exists(repo_root: Path, name: str) -> bool:
    """Check if an exploration ref exists.

    Args:
        repo_root: Repository root directory.
        name: Exploration name.

    Returns:
        True if the exploration exists.
    """
    _validate_exploration_name(name)
    store = _store(repo_root)
    try:
        return store.exists(name)
    except GitRefStoreError as exc:
        raise ExplorationStoreError(
            f"Failed to check exploration '{name}': {exc}"
        ) from exc
