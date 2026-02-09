"""Shared git ref storage abstraction for orphan commit-based content storage.

This module provides a reusable `GitRefStore` class that encapsulates the common
pattern of storing content as orphan commits referenced by git refs. Used by
plan_backup.py for plan backups and exploration_store.py for exploration artifacts.

Architecture:
    - Content stored as orphan commits (no parent history)
    - Each ref points to the latest commit for that name
    - References persist until explicitly deleted
    - All operations use low-level git plumbing commands for reliability
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .logging_config import get_logger
from .plan_validator import _PLAN_ID_PATTERN

logger = get_logger(__name__)


class GitRefStoreError(Exception):
    """Base exception for git ref store operations."""


class RefNotFoundError(GitRefStoreError):
    """Raised when a ref doesn't exist."""


class RefExistsError(GitRefStoreError):
    """Raised when a ref already exists and atomic creation was requested."""


def _validate_name(name: str) -> None:
    """Validate name to prevent shell injection and path traversal.

    Uses the same pattern as plan_validator.py to ensure consistency.

    Args:
        name: Name to validate.

    Raises:
        GitRefStoreError: If name contains invalid characters.
    """
    if not isinstance(name, str) or not name.strip():
        raise GitRefStoreError("Name cannot be empty")

    if not _PLAN_ID_PATTERN.fullmatch(name.strip()):
        raise GitRefStoreError(
            f"Invalid name '{name}'. Names must match pattern "
            "^[a-zA-Z0-9._-]{3,100}$ (3-100 chars, alphanumeric/._- only)."
        )


class GitRefStore:
    """Stores content as orphan commits referenced by git refs.

    Each instance is bound to a specific namespace (e.g., "plan-backups",
    "weft/explorations"). Content is stored as files in orphan commits,
    with refs at ``refs/<namespace>/<name>``.

    Args:
        repo_root: Repository root directory.
        namespace: Git refs namespace (e.g., "plan-backups", "weft/explorations").
    """

    def __init__(self, repo_root: Path, namespace: str) -> None:
        self.repo_root = repo_root
        self.namespace = namespace

    def _ref_path(self, name: str) -> str:
        """Build the full ref path for a name."""
        return f"refs/{self.namespace}/{name}"

    def save(
        self,
        name: str,
        content: str,
        file_path: str,
        commit_message: str,
        atomic: bool = False,
    ) -> None:
        """Create orphan commit with content and create/update ref.

        Args:
            name: Identifier for this ref entry.
            content: Text content to store.
            file_path: Path within the commit tree (e.g., "findings.md").
            commit_message: Git commit message.
            atomic: If True, fail if ref already exists. If False, force-update.

        Raises:
            GitRefStoreError: If save fails.
            RefExistsError: If atomic=True and ref already exists.
        """
        _validate_name(name)
        ref_name = self._ref_path(name)

        try:
            # Create blob object for content
            result = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                cwd=self.repo_root,
                input=content,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            blob_sha = result.stdout.strip()
            logger.debug("Created blob object: %s", blob_sha[:8])

            # Create tree with the file
            tree_entry = f"100644 blob {blob_sha}\t{file_path}\n"
            result = subprocess.run(
                ["git", "mktree"],
                cwd=self.repo_root,
                input=tree_entry,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            tree_sha = result.stdout.strip()
            logger.debug("Created tree object: %s", tree_sha[:8])

            # Create orphan commit (no parent)
            result = subprocess.run(
                ["git", "commit-tree", tree_sha, "-m", commit_message],
                cwd=self.repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            commit_sha = result.stdout.strip()
            logger.debug("Created commit object: %s", commit_sha[:8])

            # Create/update reference
            if atomic:
                # Use null SHA as expected value to ensure ref doesn't exist
                null_sha = "0" * 40
                result = subprocess.run(
                    ["git", "update-ref", ref_name, commit_sha, null_sha],
                    cwd=self.repo_root,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
                if result.returncode != 0:
                    raise RefExistsError(
                        f"Ref '{ref_name}' already exists. "
                        f"Cannot create atomically."
                    )
            else:
                # Force-update reference (overwrites existing)
                subprocess.run(
                    ["git", "update-ref", ref_name, commit_sha],
                    cwd=self.repo_root,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )

            logger.info("Created ref: %s", ref_name)

        except RefExistsError:
            raise
        except subprocess.CalledProcessError as exc:
            raise GitRefStoreError(
                f"Failed to save '{name}' in namespace '{self.namespace}': {exc.stderr}"
            ) from exc

    def read(self, name: str, file_path: str) -> str:
        """Read content from a ref.

        Args:
            name: Identifier for the ref entry.
            file_path: Path within the commit tree.

        Returns:
            The stored content string.

        Raises:
            RefNotFoundError: If the ref doesn't exist.
            GitRefStoreError: If read fails.
        """
        _validate_name(name)
        ref_name = self._ref_path(name)

        try:
            result = subprocess.run(
                ["git", "show", f"{ref_name}:{file_path}"],
                cwd=self.repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            return result.stdout
        except subprocess.CalledProcessError as exc:
            # Check if it's a "not found" error
            if "does not exist" in exc.stderr or "not exist" in exc.stderr or "fatal" in exc.stderr:
                raise RefNotFoundError(
                    f"Ref '{ref_name}' not found."
                ) from exc
            raise GitRefStoreError(
                f"Failed to read '{name}' from namespace '{self.namespace}': {exc.stderr}"
            ) from exc

    def list_refs(self) -> list[tuple[str, int]]:
        """List all refs in namespace with metadata.

        Returns:
            List of (name, timestamp) tuples sorted by name.
            timestamp is Unix epoch seconds from commit timestamp.

        Raises:
            GitRefStoreError: If listing fails.
        """
        try:
            result = subprocess.run(
                [
                    "git", "for-each-ref",
                    f"refs/{self.namespace}/",
                    "--format=%(objectname) %(refname)",
                ],
                cwd=self.repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            if not result.stdout.strip():
                return []

            refs = []
            for line in result.stdout.strip().splitlines():
                commit_sha, ref_name = line.split(maxsplit=1)

                # Extract name from ref path
                # refs/<namespace>/<name> -> <name>
                # namespace may contain slashes, so split on prefix
                prefix = f"refs/{self.namespace}/"
                name = ref_name[len(prefix):]

                # Get commit timestamp
                timestamp_result = subprocess.run(
                    ["git", "show", "-s", "--format=%ct", commit_sha],
                    cwd=self.repo_root,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
                timestamp = int(timestamp_result.stdout.strip())

                refs.append((name, timestamp))

            # Sort by name
            refs.sort(key=lambda x: x[0])
            return refs

        except subprocess.CalledProcessError as exc:
            raise GitRefStoreError(
                f"Failed to list refs in namespace '{self.namespace}': {exc.stderr}"
            ) from exc
        except (ValueError, IndexError) as exc:
            raise GitRefStoreError(
                f"Failed to parse ref list output for namespace '{self.namespace}': {exc}"
            ) from exc

    def delete(self, name: str) -> None:
        """Delete a ref (idempotent).

        Args:
            name: Identifier for the ref entry.

        Raises:
            GitRefStoreError: If deletion fails for reasons other than missing ref.
        """
        _validate_name(name)
        ref_name = self._ref_path(name)

        try:
            result = subprocess.run(
                ["git", "update-ref", "-d", ref_name],
                cwd=self.repo_root,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            if result.returncode == 0:
                logger.info("Deleted ref: %s", ref_name)
            else:
                if "does not exist" in result.stderr or "not exist" in result.stderr:
                    logger.debug("Ref already deleted: %s", ref_name)
                else:
                    logger.warning(
                        "Failed to delete ref '%s': %s",
                        ref_name,
                        result.stderr,
                    )

        except subprocess.CalledProcessError as exc:
            logger.warning(
                "Unexpected error deleting ref '%s': %s",
                ref_name,
                exc.stderr,
            )

    def exists(self, name: str) -> bool:
        """Check if a ref exists.

        Args:
            name: Identifier for the ref entry.

        Returns:
            True if the ref exists.
        """
        _validate_name(name)
        ref_name = self._ref_path(name)

        result = subprocess.run(
            ["git", "show-ref", "--verify", ref_name],
            cwd=self.repo_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        return result.returncode == 0

    def move(self, name: str, dest_store: GitRefStore) -> None:
        """Move a ref from this namespace to another GitRefStore's namespace.

        Args:
            name: Identifier for the ref entry.
            dest_store: Destination GitRefStore.

        Raises:
            GitRefStoreError: If move fails.
        """
        _validate_name(name)
        source_ref = self._ref_path(name)
        dest_ref = dest_store._ref_path(name)

        try:
            # Get the commit SHA from source ref
            result = subprocess.run(
                ["git", "show-ref", "--hash", source_ref],
                cwd=self.repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            commit_sha = result.stdout.strip()

            # Create/update the dest ref (force-update if exists)
            subprocess.run(
                ["git", "update-ref", dest_ref, commit_sha],
                cwd=self.repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            logger.info("Created ref: %s", dest_ref)

            # Delete the source ref
            subprocess.run(
                ["git", "update-ref", "-d", source_ref],
                cwd=self.repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            logger.info("Deleted ref: %s", source_ref)

        except subprocess.CalledProcessError as exc:
            raise GitRefStoreError(
                f"Failed to move ref from '{self.namespace}' to "
                f"'{dest_store.namespace}' for '{name}': {exc.stderr}"
            ) from exc
