"""Plan file backup management using git orphan branch references.

This module provides automatic backup and recovery of plan files using git
orphan commits referenced at refs/plan-backups/<plan_id>. Backups are created
when plans are created/modified and automatically cleaned up when plans are
finalized (merged to main).

Backup Lifecycle:
    1. Plan creation/edit: create_backup() creates orphan commit at refs/plan-backups/<plan_id>
    2. Plan finalization: cleanup_backup() deletes the backup reference
    3. Recovery: recover_backup() restores plan file from backup reference

Architecture:
    - Backups stored as git orphan commits (no parent history)
    - Only latest backup kept per plan (force-update on subsequent backups)
    - References persist until explicitly deleted (no time-based cleanup)
    - All operations use low-level git plumbing commands for reliability

Git Object Accumulation:
    When backups are force-updated (create_backup called multiple times for the
    same plan_id), old commit objects and their trees/blobs become unreachable
    but remain in .git/objects until garbage collected. This is expected git
    behavior. For repositories with many backup iterations, you may want to
    periodically run `git gc` to reclaim disk space:

        git gc --prune=now

    Since plan files are small (<100KB typically), this accumulation is minor
    and only noticeable in long-running repositories with frequent plan edits.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .logging_config import get_logger
from .plan_validator import _PLAN_ID_PATTERN
from .repo_utils import RepoUtilsError, find_repo_root

logger = get_logger(__name__)


class PlanBackupError(Exception):
    """Base exception for plan backup operations."""


class BackupNotFoundError(PlanBackupError):
    """Raised when a backup reference doesn't exist."""


class BackupExistsError(PlanBackupError):
    """Raised when attempting to recover over an existing file."""


def _validate_plan_id(plan_id: str) -> None:
    """Validate plan_id to prevent shell injection and path traversal.

    Uses the same pattern as plan_validator.py to ensure consistency.

    Args:
        plan_id: Plan identifier to validate.

    Raises:
        PlanBackupError: If plan_id contains invalid characters.
    """
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise PlanBackupError("Plan ID cannot be empty")

    if not _PLAN_ID_PATTERN.fullmatch(plan_id.strip()):
        raise PlanBackupError(
            f"Invalid plan ID '{plan_id}'. Plan IDs must match pattern "
            "^[a-zA-Z0-9._-]{3,100}$ (3-100 chars, alphanumeric/._- only)."
        )


def create_backup(repo_root: Path, plan_id: str) -> None:
    """Create or update backup of a plan file as a git orphan commit.

    Creates an orphan commit containing the plan file and stores a reference
    at refs/plan-backups/<plan_id>. If a backup already exists, it is
    force-updated (previous backup becomes unreachable).

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier (used to locate file and create ref).

    Raises:
        PlanBackupError: If backup creation fails.
    """
    _validate_plan_id(plan_id)
    plan_file = repo_root / ".lw_coder" / "tasks" / f"{plan_id}.md"

    # Read plan file content
    try:
        content = plan_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanBackupError(
            f"Failed to read plan file at {plan_file}: {exc}"
        ) from exc

    try:
        # Create blob object for plan file content
        result = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=repo_root,
            input=content,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        blob_sha = result.stdout.strip()
        logger.debug("Created blob object: %s", blob_sha[:8])

        # Create nested tree structure: .lw_coder/tasks/<file>
        # Start from innermost tree (tasks directory)
        tasks_tree_entry = f"100644 blob {blob_sha}\t{plan_id}.md\n"
        result = subprocess.run(
            ["git", "mktree"],
            cwd=repo_root,
            input=tasks_tree_entry,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        tasks_tree_sha = result.stdout.strip()
        logger.debug("Created tasks tree object: %s", tasks_tree_sha[:8])

        # Create .lw_coder directory tree
        lw_coder_tree_entry = f"040000 tree {tasks_tree_sha}\ttasks\n"
        result = subprocess.run(
            ["git", "mktree"],
            cwd=repo_root,
            input=lw_coder_tree_entry,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        lw_coder_tree_sha = result.stdout.strip()
        logger.debug("Created .lw_coder tree object: %s", lw_coder_tree_sha[:8])

        # Create root tree
        root_tree_entry = f"040000 tree {lw_coder_tree_sha}\t.lw_coder\n"
        result = subprocess.run(
            ["git", "mktree"],
            cwd=repo_root,
            input=root_tree_entry,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        tree_sha = result.stdout.strip()
        logger.debug("Created root tree object: %s", tree_sha[:8])

        # Create orphan commit (no parent)
        commit_message = f"Backup of plan: {plan_id}"
        result = subprocess.run(
            ["git", "commit-tree", tree_sha, "-m", commit_message],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        commit_sha = result.stdout.strip()
        logger.debug("Created commit object: %s", commit_sha[:8])

        # Force-update reference (overwrites existing backup)
        ref_name = f"refs/plan-backups/{plan_id}"
        result = subprocess.run(
            ["git", "update-ref", ref_name, commit_sha],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        logger.info("Created backup reference: %s", ref_name)

    except subprocess.CalledProcessError as exc:
        raise PlanBackupError(
            f"Failed to create backup for plan '{plan_id}': {exc.stderr}"
        ) from exc


def cleanup_backup(repo_root: Path, plan_id: str) -> None:
    """Delete backup reference for a plan (idempotent).

    Removes the backup reference at refs/plan-backups/<plan_id>. If the
    reference doesn't exist, logs a warning but doesn't raise an error.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.

    Raises:
        PlanBackupError: If cleanup fails for reasons other than missing ref.
    """
    _validate_plan_id(plan_id)
    ref_name = f"refs/plan-backups/{plan_id}"

    try:
        # Delete reference (idempotent)
        result = subprocess.run(
            ["git", "update-ref", "-d", ref_name],
            cwd=repo_root,
            check=False,  # Don't raise on non-zero exit
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        if result.returncode == 0:
            logger.info("Deleted backup reference: %s", ref_name)
        else:
            # Check if error is due to missing ref (expected, idempotent)
            if "does not exist" in result.stderr or "not exist" in result.stderr:
                logger.debug("Backup reference already deleted: %s", ref_name)
            else:
                # Unexpected error - log warning but don't fail finalize
                logger.warning(
                    "Failed to delete backup reference '%s': %s",
                    ref_name,
                    result.stderr,
                )

    except subprocess.CalledProcessError as exc:
        # This shouldn't happen with check=False, but handle it anyway
        logger.warning(
            "Unexpected error deleting backup reference '%s': %s",
            ref_name,
            exc.stderr,
        )


def list_backups(repo_root: Path) -> list[tuple[str, int, bool]]:
    """List all plan backups with metadata.

    Returns:
        List of (plan_id, timestamp, file_exists) tuples sorted by plan_id.
        timestamp is Unix epoch seconds from commit timestamp.
        file_exists indicates if .lw_coder/tasks/<plan_id>.md exists.

    Raises:
        PlanBackupError: If listing fails.
    """
    try:
        # List all backup references with commit timestamp
        # Format: <commit_sha> <ref_name>
        result = subprocess.run(
            ["git", "for-each-ref", "refs/plan-backups/", "--format=%(objectname) %(refname)"],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        if not result.stdout.strip():
            return []

        backups = []
        for line in result.stdout.strip().splitlines():
            commit_sha, ref_name = line.split(maxsplit=1)

            # Extract plan_id from ref name
            # refs/plan-backups/<plan_id> -> <plan_id>
            plan_id = ref_name.split("/", 2)[2]

            # Get commit timestamp
            timestamp_result = subprocess.run(
                ["git", "show", "-s", "--format=%ct", commit_sha],
                cwd=repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            timestamp = int(timestamp_result.stdout.strip())

            # Check if plan file exists
            plan_file = repo_root / ".lw_coder" / "tasks" / f"{plan_id}.md"
            file_exists = plan_file.exists()

            backups.append((plan_id, timestamp, file_exists))

        # Sort by plan_id
        backups.sort(key=lambda x: x[0])
        return backups

    except subprocess.CalledProcessError as exc:
        raise PlanBackupError(
            f"Failed to list backups: {exc.stderr}"
        ) from exc
    except (ValueError, IndexError) as exc:
        raise PlanBackupError(
            f"Failed to parse backup list output: {exc}"
        ) from exc


def recover_backup(repo_root: Path, plan_id: str, force: bool = False) -> Path:
    """Recover a plan file from backup.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.
        force: If True, overwrite existing file. If False, raise error if file exists.

    Returns:
        Path to the recovered plan file.

    Raises:
        BackupNotFoundError: If backup reference doesn't exist.
        BackupExistsError: If target file exists and force=False.
        PlanBackupError: If recovery fails for other reasons.
    """
    _validate_plan_id(plan_id)
    ref_name = f"refs/plan-backups/{plan_id}"
    plan_file = repo_root / ".lw_coder" / "tasks" / f"{plan_id}.md"

    # Verify backup reference exists
    try:
        result = subprocess.run(
            ["git", "show-ref", ref_name],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except subprocess.CalledProcessError:
        raise BackupNotFoundError(
            f"No backup found for plan '{plan_id}'. "
            f"Use 'lw_coder recover-plan' to list available backups."
        )

    # Check if target file exists
    if plan_file.exists() and not force:
        raise BackupExistsError(
            f"Plan file already exists at {plan_file}. "
            f"Use --force flag to overwrite."
        )

    # Extract file content from backup commit
    try:
        result = subprocess.run(
            ["git", "show", f"{ref_name}:.lw_coder/tasks/{plan_id}.md"],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        content = result.stdout

        # Ensure tasks directory exists
        plan_file.parent.mkdir(parents=True, exist_ok=True)

        # Write recovered content
        plan_file.write_text(content, encoding="utf-8")
        logger.info("Recovered plan file to: %s", plan_file)

        return plan_file

    except subprocess.CalledProcessError as exc:
        raise PlanBackupError(
            f"Failed to recover backup for plan '{plan_id}': {exc.stderr}"
        ) from exc
    except OSError as exc:
        raise PlanBackupError(
            f"Failed to write recovered plan file to {plan_file}: {exc}"
        ) from exc
