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
    - Internally uses GitRefStore for orphan commit + ref management
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

from .git_ref_store import GitRefStore, GitRefStoreError
from .logging_config import get_logger
from .plan_validator import _PLAN_ID_PATTERN

logger = get_logger(__name__)

# Internal ref store instances are created per-call since repo_root varies
_BACKUP_NAMESPACE = "plan-backups"
_ABANDONED_NAMESPACE = "plan-abandoned"


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


def _backup_store(repo_root: Path) -> GitRefStore:
    """Create a GitRefStore for the plan-backups namespace."""
    return GitRefStore(repo_root, _BACKUP_NAMESPACE)


def _abandoned_store(repo_root: Path) -> GitRefStore:
    """Create a GitRefStore for the plan-abandoned namespace."""
    return GitRefStore(repo_root, _ABANDONED_NAMESPACE)


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
    plan_file = repo_root / ".weft" / "tasks" / f"{plan_id}.md"

    # Read plan file content
    try:
        content = plan_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise PlanBackupError(
            f"Failed to read plan file at {plan_file}: {exc}"
        ) from exc

    try:
        # Create backup using the nested tree structure that plan_backup
        # originally used: .weft/tasks/<plan_id>.md
        # This preserves the tree structure for recover_backup compatibility
        # Build the nested tree structure manually (matching original behavior)
        # Original code creates: root -> .weft -> tasks -> <plan_id>.md
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

        # Create nested tree structure: .weft/tasks/<file>
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

        # Create .weft directory tree
        weft_tree_entry = f"040000 tree {tasks_tree_sha}\ttasks\n"
        result = subprocess.run(
            ["git", "mktree"],
            cwd=repo_root,
            input=weft_tree_entry,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        weft_tree_sha = result.stdout.strip()
        logger.debug("Created .weft tree object: %s", weft_tree_sha[:8])

        # Create root tree
        root_tree_entry = f"040000 tree {weft_tree_sha}\t.weft\n"
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
        ref_name = f"refs/{_BACKUP_NAMESPACE}/{plan_id}"
        subprocess.run(
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
    store = _backup_store(repo_root)
    store.delete(plan_id)


def _list_refs_in_namespace(repo_root: Path, namespace: str) -> list[tuple[str, int, bool]]:
    """List all refs in a given namespace with metadata.

    Args:
        repo_root: Repository root directory.
        namespace: Git refs namespace (e.g., "plan-backups", "plan-abandoned").

    Returns:
        List of (plan_id, timestamp, file_exists) tuples sorted by plan_id.

    Raises:
        PlanBackupError: If listing fails.
    """
    try:
        store = GitRefStore(repo_root, namespace)
        refs = store.list_refs()

        plans = []
        for plan_id, timestamp in refs:
            # Check if plan file exists
            plan_file = repo_root / ".weft" / "tasks" / f"{plan_id}.md"
            file_exists = plan_file.exists()
            plans.append((plan_id, timestamp, file_exists))

        return plans

    except GitRefStoreError as exc:
        raise PlanBackupError(str(exc)) from exc


def list_backups(repo_root: Path) -> list[tuple[str, int, bool]]:
    """List all plan backups with metadata.

    Returns:
        List of (plan_id, timestamp, file_exists) tuples sorted by plan_id.
        timestamp is Unix epoch seconds from commit timestamp.
        file_exists indicates if .weft/tasks/<plan_id>.md exists.

    Raises:
        PlanBackupError: If listing fails.
    """
    return _list_refs_in_namespace(repo_root, _BACKUP_NAMESPACE)


def recover_backup(
    repo_root: Path, plan_id: str, force: bool = False, namespace: str = "plan-backups"
) -> Path:
    """Recover a plan file from backup.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.
        force: If True, overwrite existing file. If False, raise error if file exists.
        namespace: Git refs namespace to recover from (default: "plan-backups").

    Returns:
        Path to the recovered plan file.

    Raises:
        BackupNotFoundError: If backup reference doesn't exist.
        BackupExistsError: If target file exists and force=False.
        PlanBackupError: If recovery fails for other reasons.
    """
    _validate_plan_id(plan_id)
    ref_name = f"refs/{namespace}/{plan_id}"
    plan_file = repo_root / ".weft" / "tasks" / f"{plan_id}.md"

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
            f"Use 'weft recover-plan' to list available backups."
        )

    # Check if target file exists
    if plan_file.exists() and not force:
        raise BackupExistsError(
            f"Plan file already exists at {plan_file}. "
            f"Use --force flag to overwrite."
        )

    # Extract file content from backup commit
    # Try current path first, then fall back to legacy path (.lw_coder -> .weft rename)
    backup_paths = [
        f".weft/tasks/{plan_id}.md",
        f".lw_coder/tasks/{plan_id}.md",  # Legacy path before rename
    ]

    content = None
    last_error = None

    for backup_path in backup_paths:
        try:
            result = subprocess.run(
                ["git", "show", f"{ref_name}:{backup_path}"],
                cwd=repo_root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )
            content = result.stdout
            logger.debug("Found backup content at path: %s", backup_path)
            break
        except subprocess.CalledProcessError as exc:
            last_error = exc
            continue

    if content is None:
        raise PlanBackupError(
            f"Failed to recover backup for plan '{plan_id}': {last_error.stderr if last_error else 'unknown error'}"
        )

    try:
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


def _move_ref_between_namespaces(
    repo_root: Path,
    plan_id: str,
    source_namespace: str,
    dest_namespace: str,
) -> None:
    """Move a backup reference from one namespace to another.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.
        source_namespace: Source namespace (e.g., "plan-backups").
        dest_namespace: Destination namespace (e.g., "plan-abandoned").

    Raises:
        PlanBackupError: If move operation fails.
    """
    _validate_plan_id(plan_id)
    source_store = GitRefStore(repo_root, source_namespace)
    dest_store = GitRefStore(repo_root, dest_namespace)

    try:
        source_store.move(plan_id, dest_store)
    except GitRefStoreError as exc:
        raise PlanBackupError(
            f"Failed to move ref from '{source_namespace}' to '{dest_namespace}' for plan '{plan_id}': {exc}"
        ) from exc


def move_backup_to_abandoned(repo_root: Path, plan_id: str) -> None:
    """Move backup reference from plan-backups to plan-abandoned namespace.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.

    Raises:
        PlanBackupError: If move operation fails.
    """
    _move_ref_between_namespaces(repo_root, plan_id, _BACKUP_NAMESPACE, _ABANDONED_NAMESPACE)


def move_abandoned_to_backup(repo_root: Path, plan_id: str) -> None:
    """Move reference from plan-abandoned back to plan-backups namespace.

    Used when recovering an abandoned plan.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.

    Raises:
        PlanBackupError: If move operation fails.
    """
    _move_ref_between_namespaces(repo_root, plan_id, _ABANDONED_NAMESPACE, _BACKUP_NAMESPACE)


def list_abandoned_plans(repo_root: Path) -> list[tuple[str, int, bool]]:
    """List all abandoned plans with metadata.

    Returns:
        List of (plan_id, timestamp, file_exists) tuples sorted by plan_id.
        timestamp is Unix epoch seconds from commit timestamp.
        file_exists indicates if .weft/tasks/<plan_id>.md exists.

    Raises:
        PlanBackupError: If listing fails.
    """
    return _list_refs_in_namespace(repo_root, _ABANDONED_NAMESPACE)


def backup_exists_in_namespace(repo_root: Path, plan_id: str, namespace: str) -> bool:
    """Check if a backup reference exists in the specified namespace.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.
        namespace: Git refs namespace (e.g., "plan-backups", "plan-abandoned").

    Returns:
        True if backup reference exists in the namespace.
    """
    _validate_plan_id(plan_id)
    store = GitRefStore(repo_root, namespace)
    return store.exists(plan_id)
