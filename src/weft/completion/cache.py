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


class PlanInfo(NamedTuple):
    """Information about a plan file."""

    plan_id: str
    status: str
    mtime: float


class CacheEntry(NamedTuple):
    """Cached plan list with timestamp."""

    plans: list[PlanInfo]
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

    def _scan_plans(self, tasks_dir: Path) -> list[PlanInfo]:
        """Scan for all plan files and extract info.

        Args:
            tasks_dir: Path to .weft/tasks directory.

        Returns:
            List of PlanInfo for all plans (unfiltered).
        """
        plans = []
        if not tasks_dir.exists():
            logger.debug("Tasks directory does not exist: %s", tasks_dir)
            return []

        for plan_file in tasks_dir.glob("*.md"):
            try:
                # Read and parse front matter
                content = plan_file.read_text(encoding="utf-8")
                front_matter, _ = extract_front_matter(content)

                # Get status and mtime
                status = front_matter.get("status", "").strip().lower()
                mtime = plan_file.stat().st_mtime

                plans.append(PlanInfo(
                    plan_id=plan_file.stem,
                    status=status,
                    mtime=mtime,
                ))

            except (OSError, IOError) as exc:
                # Skip unreadable files
                logger.debug("Skipping unreadable plan file %s: %s", plan_file, exc)
                continue
            except PlanValidationError:
                # Include files with invalid YAML (status unknown)
                # They might be valid plans with formatting issues
                logger.debug("Plan file with invalid YAML: %s", plan_file)
                try:
                    mtime = plan_file.stat().st_mtime
                except OSError:
                    mtime = 0.0
                plans.append(PlanInfo(
                    plan_id=plan_file.stem,
                    status="",  # Unknown status
                    mtime=mtime,
                ))
                continue
            except Exception as exc:
                # Skip any other errors gracefully
                logger.debug("Error processing plan file %s: %s", plan_file, exc)
                continue

        return plans

    def _ensure_cache_valid(self, tasks_dir: Path | None) -> list[PlanInfo]:
        """Ensure cache is valid and return all plans.

        Args:
            tasks_dir: Path to .weft/tasks directory.

        Returns:
            List of all PlanInfo from cache.
        """
        now = time.time()
        if self._cache and (now - self._cache.timestamp) < self._ttl_seconds:
            logger.debug("Using cached plan list (%d plans)", len(self._cache.plans))
            return self._cache.plans

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
        plans = self._scan_plans(tasks_dir)

        # Update cache
        self._cache = CacheEntry(plans=plans, timestamp=now)
        logger.debug("Cached %d plans", len(plans))

        return plans

    def get_active_plans(
        self, tasks_dir: Path | None = None, include_finished: bool = False
    ) -> list[str]:
        """Get list of plan IDs, optionally including finished plans.

        Scans .weft/tasks/*.md files and returns plan IDs (file stems).
        By default, only returns plans where status != "done".

        Args:
            tasks_dir: Path to .weft/tasks directory. If None, attempts to
                      discover from repository root.
            include_finished: If True, also include plans with status == "done".

        Returns:
            Sorted list of plan IDs (file stems without .md extension).
        """
        plans = self._ensure_cache_valid(tasks_dir)

        # Filter based on include_finished parameter
        if include_finished:
            plan_ids = [p.plan_id for p in plans]
        else:
            plan_ids = [p.plan_id for p in plans if p.status != "done"]

        # Sort for consistent ordering
        plan_ids.sort()

        return plan_ids

    def get_all_plans(self, tasks_dir: Path | None = None) -> list[PlanInfo]:
        """Get list of all plan info including status and mtime.

        Used by completers that need ordering by mtime or access to status.

        Args:
            tasks_dir: Path to .weft/tasks directory. If None, attempts to
                      discover from repository root.

        Returns:
            List of PlanInfo for all plans (no filtering).
        """
        return self._ensure_cache_valid(tasks_dir)

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


def get_active_plans(
    tasks_dir: Path | None = None, include_finished: bool = False
) -> list[str]:
    """Get list of active plan IDs using the global cache.

    Convenience function for accessing the global cache instance.

    Args:
        tasks_dir: Path to .weft/tasks directory.
        include_finished: If True, also include plans with status == "done".

    Returns:
        Sorted list of plan IDs.
    """
    return _global_cache.get_active_plans(tasks_dir, include_finished=include_finished)


def get_all_plans(tasks_dir: Path | None = None) -> list[PlanInfo]:
    """Get list of all plan info using the global cache.

    Convenience function for accessing the global cache instance.

    Args:
        tasks_dir: Path to .weft/tasks directory.

    Returns:
        List of PlanInfo for all plans.
    """
    return _global_cache.get_all_plans(tasks_dir)
