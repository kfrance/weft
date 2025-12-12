"""Worktree file synchronization for copying untracked files to worktrees.

This module provides functionality to copy untracked files (e.g., .env, config files)
from the main repository to temporary worktrees when the code command runs.

Pattern Matching:
    Uses glob patterns relative to the repository root. Patterns must not contain
    path traversal sequences (..), absolute paths (/), or home directory references (~).

File Operations:
    - Regular files: Copied with metadata preserved (permissions, timestamps)
    - Directories: Recursively copied maintaining structure
    - Symlinks: Preserved as symlinks (not dereferenced)

Size Limits:
    - Per-file limit (default: 100MB) prevents copying large individual files
    - Total limit (default: 500MB) prevents disk space issues

Security:
    All patterns are validated to prevent path traversal and escaping the repository.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..logging_config import get_logger

if TYPE_CHECKING:
    from typing import Any

logger = get_logger(__name__)


class FileSyncError(Exception):
    """Base exception for file sync errors."""


class UnsafePatternError(FileSyncError):
    """Exception for unsafe patterns that could escape the repository."""


class ConfigValidationError(FileSyncError):
    """Exception for configuration validation errors."""


class SizeLimitError(FileSyncError):
    """Exception for size limit violations."""


class CopyError(FileSyncError):
    """Exception for file copy failures."""


@dataclass
class FileSyncConfig:
    """Configuration for worktree file synchronization.

    Attributes:
        enabled: Whether file sync is enabled (default: True).
        patterns: List of glob patterns to match files.
        max_file_size_mb: Maximum size of individual files in MB (default: 100).
        max_total_size_mb: Maximum total size of all files in MB (default: 500).
    """

    enabled: bool = True
    patterns: list[str] = field(default_factory=list)
    max_file_size_mb: int = 100
    max_total_size_mb: int = 500


def validate_worktree_file_sync_config(config: dict[str, Any]) -> FileSyncConfig:
    """Validate and parse the [worktree.file_sync] configuration section.

    Args:
        config: The full configuration dictionary from config.toml.

    Returns:
        FileSyncConfig with validated settings.

    Raises:
        ConfigValidationError: If the configuration is invalid.
    """
    # Check schema_version if present in the config
    schema_version = config.get("schema_version")
    if schema_version is not None and schema_version != "1.0":
        raise ConfigValidationError(
            f"Invalid schema_version '{schema_version}'. Expected '1.0'."
        )

    # Get the worktree section
    worktree_section = config.get("worktree", {})
    if not isinstance(worktree_section, dict):
        raise ConfigValidationError(
            "[worktree] section must be a table."
        )

    # Get file_sync section (optional)
    file_sync_section = worktree_section.get("file_sync")
    if file_sync_section is None:
        # No file_sync section - return defaults with empty patterns
        return FileSyncConfig()

    if not isinstance(file_sync_section, dict):
        raise ConfigValidationError(
            "[worktree.file_sync] section must be a table."
        )

    # Validate no unknown keys
    valid_keys = {"enabled", "patterns", "max_file_size_mb", "max_total_size_mb"}
    unknown_keys = set(file_sync_section.keys()) - valid_keys
    if unknown_keys:
        raise ConfigValidationError(
            f"Unknown keys in [worktree.file_sync]: {', '.join(sorted(unknown_keys))}. "
            f"Valid keys: {', '.join(sorted(valid_keys))}"
        )

    # Validate 'enabled'
    enabled = file_sync_section.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigValidationError(
            f"[worktree.file_sync] enabled must be a boolean, got {type(enabled).__name__}."
        )

    # Validate 'patterns'
    patterns = file_sync_section.get("patterns", [])
    if not isinstance(patterns, list):
        raise ConfigValidationError(
            f"[worktree.file_sync] patterns must be a list of strings, got {type(patterns).__name__}."
        )
    for i, pattern in enumerate(patterns):
        if not isinstance(pattern, str):
            raise ConfigValidationError(
                f"[worktree.file_sync] patterns[{i}] must be a string, got {type(pattern).__name__}."
            )

    # Validate 'max_file_size_mb'
    max_file_size_mb = file_sync_section.get("max_file_size_mb", 100)
    if not isinstance(max_file_size_mb, int) or isinstance(max_file_size_mb, bool):
        raise ConfigValidationError(
            f"[worktree.file_sync] max_file_size_mb must be an integer, got {type(max_file_size_mb).__name__}."
        )
    if max_file_size_mb <= 0:
        raise ConfigValidationError(
            f"[worktree.file_sync] max_file_size_mb must be positive, got {max_file_size_mb}."
        )

    # Validate 'max_total_size_mb'
    max_total_size_mb = file_sync_section.get("max_total_size_mb", 500)
    if not isinstance(max_total_size_mb, int) or isinstance(max_total_size_mb, bool):
        raise ConfigValidationError(
            f"[worktree.file_sync] max_total_size_mb must be an integer, got {type(max_total_size_mb).__name__}."
        )
    if max_total_size_mb <= 0:
        raise ConfigValidationError(
            f"[worktree.file_sync] max_total_size_mb must be positive, got {max_total_size_mb}."
        )

    return FileSyncConfig(
        enabled=enabled,
        patterns=patterns,
        max_file_size_mb=max_file_size_mb,
        max_total_size_mb=max_total_size_mb,
    )


def validate_pattern_safety(pattern: str) -> None:
    """Validate that a pattern cannot escape the repository.

    Args:
        pattern: Glob pattern to validate.

    Raises:
        UnsafePatternError: If the pattern could access files outside the repository.
    """
    # Reject parent directory references
    if ".." in pattern:
        raise UnsafePatternError(
            f"Pattern '{pattern}' contains parent directory reference '..'. "
            "Patterns cannot access files outside the repository."
        )

    # Reject absolute paths
    if pattern.startswith("/"):
        raise UnsafePatternError(
            f"Pattern '{pattern}' is an absolute path. "
            "Patterns must be relative to the repository root."
        )

    # Reject home directory expansion
    if pattern.startswith("~"):
        raise UnsafePatternError(
            f"Pattern '{pattern}' contains home directory reference '~'. "
            "Patterns cannot access files outside the repository."
        )


class FileSyncPattern:
    """Handles glob pattern matching for file synchronization.

    Attributes:
        pattern: The glob pattern string.
        repo_root: Path to the repository root.
    """

    def __init__(self, pattern: str, repo_root: Path) -> None:
        """Initialize a file sync pattern.

        Args:
            pattern: Glob pattern to match files.
            repo_root: Path to the repository root.

        Raises:
            UnsafePatternError: If the pattern is unsafe.
        """
        validate_pattern_safety(pattern)
        self.pattern = pattern
        self.repo_root = repo_root

    def find_matches(self) -> list[Path]:
        """Find all files matching this pattern.

        Returns:
            List of matching paths relative to repo_root.
            Empty list if no matches found.
        """
        matches: list[Path] = []

        # Use repo_root.glob() for pattern matching
        for match in self.repo_root.glob(self.pattern):
            # Ensure match is within repo_root (safety check after resolution)
            try:
                match.resolve().relative_to(self.repo_root.resolve())
            except ValueError:
                logger.warning(
                    "Pattern '%s' matched path '%s' that escapes repo root, skipping",
                    self.pattern,
                    match,
                )
                continue

            # Get path relative to repo_root
            rel_path = match.relative_to(self.repo_root)
            matches.append(rel_path)
            logger.debug("Pattern '%s' matched: %s", self.pattern, rel_path)

        if not matches:
            logger.debug("Pattern '%s' matched no files", self.pattern)

        return matches


@dataclass
class FileSyncOperation:
    """Represents a file sync operation from source to destination.

    Attributes:
        source: Absolute path to the source file/directory.
        dest: Absolute path to the destination.
        rel_path: Path relative to repo root (for logging).
        max_file_size_bytes: Maximum size per file in bytes.
        max_total_size_bytes: Maximum total size in bytes.
    """

    source: Path
    dest: Path
    rel_path: Path
    max_file_size_bytes: int
    max_total_size_bytes: int
    _size: int = field(default=0, init=False, repr=False)

    def calculate_size(self) -> int:
        """Calculate the size of this operation.

        Returns:
            Total size in bytes.

        Raises:
            SizeLimitError: If any file exceeds the per-file size limit.
        """
        if self.source.is_symlink():
            # Symlinks don't contribute to size
            return 0

        if self.source.is_file():
            size = self.source.stat().st_size
            if size > self.max_file_size_bytes:
                raise SizeLimitError(
                    f"File '{self.rel_path}' is {size / (1024 * 1024):.1f}MB, "
                    f"exceeds max_file_size_mb limit of {self.max_file_size_bytes / (1024 * 1024):.0f}MB."
                )
            self._size = size
            return size

        if self.source.is_dir():
            total = 0
            for item in self.source.rglob("*"):
                if item.is_file() and not item.is_symlink():
                    size = item.stat().st_size
                    if size > self.max_file_size_bytes:
                        raise SizeLimitError(
                            f"File '{self.rel_path / item.relative_to(self.source)}' is {size / (1024 * 1024):.1f}MB, "
                            f"exceeds max_file_size_mb limit of {self.max_file_size_bytes / (1024 * 1024):.0f}MB."
                        )
                    total += size
            self._size = total
            return total

        return 0

    def execute(self) -> list[Path]:
        """Execute the copy operation.

        Returns:
            List of paths created (for cleanup tracking).

        Raises:
            CopyError: If the copy operation fails.
        """
        created_paths: list[Path] = []

        try:
            # Create parent directories if needed
            self.dest.parent.mkdir(parents=True, exist_ok=True)

            if self.source.is_symlink():
                # Preserve symlink
                target = os.readlink(self.source)
                if self.dest.exists() or self.dest.is_symlink():
                    self.dest.unlink()
                os.symlink(target, self.dest)
                created_paths.append(self.dest)
                logger.debug("Preserving symlink: %s -> %s", self.rel_path, target)

            elif self.source.is_file():
                # Copy file with metadata
                shutil.copy2(self.source, self.dest)
                created_paths.append(self.dest)
                logger.debug("Copying file: %s", self.rel_path)

            elif self.source.is_dir():
                # Copy directory recursively
                created_paths.extend(self._copy_directory())

            return created_paths

        except OSError as exc:
            raise CopyError(
                f"Failed to copy '{self.rel_path}': {exc}"
            ) from exc

    def _copy_directory(self) -> list[Path]:
        """Copy a directory recursively.

        Returns:
            List of created paths.
        """
        created: list[Path] = []

        # Create destination directory
        self.dest.mkdir(parents=True, exist_ok=True)
        created.append(self.dest)
        logger.debug("Creating directory: %s", self.rel_path)

        # Walk through source directory
        for item in self.source.rglob("*"):
            rel_to_source = item.relative_to(self.source)
            dest_item = self.dest / rel_to_source

            # Create parent directories
            dest_item.parent.mkdir(parents=True, exist_ok=True)

            if item.is_symlink():
                # Preserve symlink
                target = os.readlink(item)
                if dest_item.exists() or dest_item.is_symlink():
                    dest_item.unlink()
                os.symlink(target, dest_item)
                created.append(dest_item)
                logger.debug(
                    "Preserving symlink: %s -> %s",
                    self.rel_path / rel_to_source,
                    target,
                )

            elif item.is_file():
                # Copy file with metadata
                shutil.copy2(item, dest_item)
                created.append(dest_item)
                logger.debug("Copying file: %s", self.rel_path / rel_to_source)

            elif item.is_dir():
                # Create directory
                dest_item.mkdir(parents=True, exist_ok=True)
                created.append(dest_item)

        return created


class WorktreeFileCleanup:
    """Tracks copied files for cleanup.

    Usage:
        cleanup = WorktreeFileCleanup()
        cleanup.register_copied_path(path1)
        cleanup.register_copied_path(path2)
        # ... later in finally block ...
        cleanup.cleanup()
    """

    def __init__(self) -> None:
        """Initialize the cleanup tracker."""
        self._paths: list[Path] = []

    def register_copied_path(self, path: Path) -> None:
        """Register a path for cleanup.

        Args:
            path: Path that was created during file sync.
        """
        self._paths.append(path)

    def register_copied_paths(self, paths: list[Path]) -> None:
        """Register multiple paths for cleanup.

        Args:
            paths: List of paths that were created during file sync.
        """
        self._paths.extend(paths)

    def cleanup(self) -> None:
        """Remove all registered paths.

        Best-effort cleanup - logs warnings for failures but doesn't raise.
        Paths are removed in reverse order to handle directories properly.
        """
        # Separate files and directories for proper ordering
        files: list[Path] = []
        dirs: list[Path] = []

        for path in self._paths:
            if path.exists():
                if path.is_dir() and not path.is_symlink():
                    dirs.append(path)
                else:
                    files.append(path)

        # Remove files first (including symlinks)
        for path in reversed(files):
            try:
                path.unlink()
                logger.debug("Cleaned up: %s", path)
            except OSError as exc:
                logger.warning("Failed to clean up '%s': %s", path, exc)

        # Remove directories (deepest first by sorting by path length descending)
        dirs_sorted = sorted(dirs, key=lambda p: len(p.parts), reverse=True)
        for path in dirs_sorted:
            try:
                # Only remove if empty
                if not any(path.iterdir()):
                    path.rmdir()
                    logger.debug("Cleaned up directory: %s", path)
            except OSError as exc:
                logger.warning("Failed to clean up directory '%s': %s", path, exc)

        self._paths.clear()


def load_repo_config(repo_root: Path) -> dict[str, Any]:
    """Load configuration from .lw_coder/config.toml in the repository.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Parsed configuration dictionary, or empty dict if file doesn't exist.

    Raises:
        FileSyncError: If the file exists but cannot be parsed.
    """
    # Try to import tomllib (Python 3.11+) or tomli (fallback)
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[import-not-found]

    config_path = repo_root / ".lw_coder" / "config.toml"

    if not config_path.exists():
        logger.debug("No repo config at %s", config_path)
        return {}

    try:
        content = config_path.read_bytes()
    except OSError as exc:
        raise FileSyncError(f"Failed to read config file: {exc}") from exc

    try:
        config = tomllib.loads(content.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise FileSyncError(
            f"Failed to parse config file {config_path}: {exc}"
        ) from exc

    logger.debug("Loaded repo config from %s", config_path)
    return config


def sync_files_to_worktree(
    repo_root: Path,
    worktree_path: Path,
    cleanup_tracker: WorktreeFileCleanup | None = None,
) -> int:
    """Synchronize files from repo root to worktree based on config.

    Args:
        repo_root: Path to the repository root.
        worktree_path: Path to the worktree directory.
        cleanup_tracker: Optional tracker to register copied files for cleanup.

    Returns:
        Number of files copied.

    Raises:
        FileSyncError: If sync fails due to config, pattern, or copy errors.
    """
    # Load repo-level config
    config = load_repo_config(repo_root)

    if not config:
        logger.debug("No repo config found, skipping file sync")
        return 0

    # Validate and parse config
    sync_config = validate_worktree_file_sync_config(config)

    # Check if enabled
    if not sync_config.enabled:
        logger.debug("File sync disabled in config")
        return 0

    # Check if there are patterns to process
    if not sync_config.patterns:
        logger.debug("No file sync patterns configured")
        return 0

    # Convert size limits to bytes
    max_file_size_bytes = sync_config.max_file_size_mb * 1024 * 1024
    max_total_size_bytes = sync_config.max_total_size_mb * 1024 * 1024

    # Find all matches and prepare operations
    operations: list[FileSyncOperation] = []
    total_size = 0

    for pattern in sync_config.patterns:
        # Create pattern matcher (validates safety)
        pattern_matcher = FileSyncPattern(pattern, repo_root)

        # Find matches
        matches = pattern_matcher.find_matches()
        if not matches:
            raise FileSyncError(
                f"Pattern '{pattern}' matched no files. "
                "Check the pattern and ensure matching files exist in the repository."
            )

        for rel_path in matches:
            source = repo_root / rel_path
            dest = worktree_path / rel_path

            # Skip if destination already exists (worktree already has the file)
            if dest.exists() or dest.is_symlink():
                logger.debug("Skipping %s - already exists in worktree", rel_path)
                continue

            operation = FileSyncOperation(
                source=source,
                dest=dest,
                rel_path=rel_path,
                max_file_size_bytes=max_file_size_bytes,
                max_total_size_bytes=max_total_size_bytes,
            )
            operations.append(operation)

    # Calculate sizes and check limits
    for op in operations:
        op_size = op.calculate_size()
        total_size += op_size

        if total_size > max_total_size_bytes:
            raise SizeLimitError(
                f"Total size {total_size / (1024 * 1024):.1f}MB exceeds "
                f"max_total_size_mb limit of {sync_config.max_total_size_mb}MB."
            )

    # Execute operations
    copied_count = 0
    for op in operations:
        created_paths = op.execute()
        copied_count += 1
        if cleanup_tracker:
            cleanup_tracker.register_copied_paths(created_paths)

    # Log summary
    if copied_count > 0:
        logger.info(
            "Copied %d file(s) (%.1fMB) to worktree based on repo config",
            copied_count,
            total_size / (1024 * 1024),
        )

    return copied_count
