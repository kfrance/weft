"""Exploration name resolution.

Resolves exploration names to their stored findings content
from refs/weft/explorations/<name>.
"""

from __future__ import annotations

from pathlib import Path

from .exploration_store import (
    ExplorationNotFoundError,
    ExplorationStoreError,
    read_exploration,
)
from .logging_config import get_logger

logger = get_logger(__name__)


class ExplorationResolver:
    """Resolves exploration names to content strings."""

    @staticmethod
    def resolve(name: str, repo_root: Path) -> str | None:
        """Check for an exploration ref and return its content.

        Args:
            name: Exploration name to look up.
            repo_root: Repository root directory.

        Returns:
            Exploration content string if ref exists, None otherwise.
        """
        try:
            content = read_exploration(repo_root, name)
            logger.debug("Resolved exploration: %s", name)
            return content
        except ExplorationNotFoundError:
            return None
        except ExplorationStoreError as exc:
            logger.warning("Error resolving exploration '%s': %s", name, exc)
            return None
