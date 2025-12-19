"""Caching for plan file completion.

This module provides TTL-based caching for scanning plan files to improve
tab completion performance.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import NamedTuple

from ..logging_config import get_logger
from ..plan_validator import PlanValidationError, extract_front_matter

logger = get_logger(__name__)


class CacheEntry(NamedTuple):
    """Cached plan list with timestamp."""

    plan_ids: list[str]
    timestamp: float


class PlanCompletionCache:
    """TTL-based cache for active plan IDs."""

    def __init__(self, ttl_seconds: float = 2.0):
        """Initialize the cache.

        Args:
            ttl_seconds: Time-to-live for cached entries in seconds (default: 2.0).
        """
        self._ttl_seconds = ttl_seconds
        self._cache: CacheEntry | None = None

    def get_active_plans(self, tasks_dir: Path | None = None) -> list[str]:
        """Get list of active (non-done) plan IDs.

        Scans .weft/tasks/*.md files and returns plan IDs (file stems)
        for plans where status != "done" in YAML front matter.

        Args:
            tasks_dir: Path to .weft/tasks directory. If None, attempts to
                      discover from repository root.

        Returns:
            Sorted list of plan IDs (file stems without .md extension).
        """
        # Check cache validity
        now = time.time()
        if self._cache and (now - self._cache.timestamp) < self._ttl_seconds:
            logger.debug("Using cached plan list (%d plans)", len(self._cache.plan_ids))
            return self._cache.plan_ids

        # Find tasks directory if not provided
        if tasks_dir is None:
            try:
                from ..repo_utils import find_repo_root

                repo_root = find_repo_root()
                tasks_dir = repo_root / ".weft" / "tasks"
            except Exception:
                # Not in a git repo or can't find root
                logger.debug("Could not find .weft/tasks directory")
                return []

        # Scan for plan files
        plan_ids = []
        if not tasks_dir.exists():
            logger.debug("Tasks directory does not exist: %s", tasks_dir)
            return []

        for plan_file in tasks_dir.glob("*.md"):
            try:
                # Read and parse front matter
                content = plan_file.read_text(encoding="utf-8")
                front_matter, _ = extract_front_matter(content)

                # Check status field
                status = front_matter.get("status", "").strip().lower()
                if status != "done":
                    plan_ids.append(plan_file.stem)

            except (OSError, IOError) as exc:
                # Skip unreadable files
                logger.debug("Skipping unreadable plan file %s: %s", plan_file, exc)
                continue
            except PlanValidationError:
                # Skip files with invalid YAML, but include them by default
                # (they might be valid plans with formatting issues)
                logger.debug("Skipping plan file with invalid YAML: %s", plan_file)
                plan_ids.append(plan_file.stem)
                continue
            except Exception as exc:
                # Skip any other errors gracefully
                logger.debug("Error processing plan file %s: %s", plan_file, exc)
                continue

        # Sort for consistent ordering
        plan_ids.sort()

        # Update cache
        self._cache = CacheEntry(plan_ids=plan_ids, timestamp=now)
        logger.debug("Cached %d active plans", len(plan_ids))

        return plan_ids

    def invalidate(self) -> None:
        """Invalidate the cache, forcing a refresh on next access."""
        self._cache = None


# Global cache instance for CLI usage
# This global cache is appropriate for the CLI use case where each command execution
# is a short-lived, single-threaded process. The cache persists only for the duration
# of a single CLI invocation. For testing, use the autouse fixture in test files to
# invalidate the cache before each test (see tests/completion/test_completers.py).
# If this module is ever used in a long-running or multi-threaded context, consider
# passing cache instances explicitly instead of using this global.
_global_cache = PlanCompletionCache()


def get_active_plans(tasks_dir: Path | None = None) -> list[str]:
    """Get list of active plan IDs using the global cache.

    Convenience function for accessing the global cache instance.

    Args:
        tasks_dir: Path to .weft/tasks directory.

    Returns:
        Sorted list of active plan IDs.
    """
    return _global_cache.get_active_plans(tasks_dir)
