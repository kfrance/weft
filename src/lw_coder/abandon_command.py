"""Implementation of the abandon command for cleaning up failed or unwanted plans.

This command provides a clean way to abandon plans by:
1. Force-deleting the worktree (regardless of uncommitted changes)
2. Force-deleting the branch (regardless of unmerged commits)
3. Deleting the plan file
4. Moving the backup reference to abandoned namespace for potential recovery
5. Optionally logging the abandonment reason
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .logging_config import get_logger
from .plan_backup import PlanBackupError, move_backup_to_abandoned
from .plan_validator import PlanValidationError, load_plan_id
from .repo_utils import RepoUtilsError, find_repo_root
from .worktree_utils import (
    WorktreeError,
    branch_exists,
    get_worktree_path,
    has_uncommitted_changes,
    is_git_worktree,
)

logger = get_logger(__name__)


class AbandonCommandError(Exception):
    """Raised when abandon command operations fail."""


@dataclass
class PlanArtifacts:
    """Information about existing artifacts for a plan."""

    worktree_exists: bool
    worktree_has_changes: bool  # For prompt message
    branch_exists: bool
    branch_unmerged_commits: int  # For prompt message
    plan_file_exists: bool
    backup_ref_exists: bool


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""

    success: bool
    already_clean: bool  # Artifact didn't exist
    error_message: str | None


def _get_default_branch(repo_root: Path) -> str | None:
    """Detect the default branch for the repository.

    Tries to find the default branch in order:
    1. refs/remotes/origin/HEAD (remote default)
    2. 'main' if it exists
    3. 'master' if it exists
    4. None if no default can be determined

    Args:
        repo_root: Repository root directory.

    Returns:
        Default branch name, or None if not determinable.
    """
    # Try to get origin/HEAD reference
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "symbolic-ref", "refs/remotes/origin/HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Result is like "refs/remotes/origin/main"
        ref = result.stdout.strip()
        if ref.startswith("refs/remotes/origin/"):
            return ref.replace("refs/remotes/origin/", "")
    except subprocess.CalledProcessError:
        pass

    # Try common default branch names
    for branch in ("main", "master"):
        result = subprocess.run(
            ["git", "-C", str(repo_root), "show-ref", "--verify", f"refs/heads/{branch}"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            return branch

    return None


def _detect_plan_artifacts(repo_root: Path, plan_id: str) -> PlanArtifacts:
    """Detect what artifacts exist for the plan.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.

    Returns:
        PlanArtifacts containing status of each artifact.
    """
    # Check worktree
    try:
        worktree_path = get_worktree_path(repo_root, plan_id)
        worktree_exists = worktree_path.exists() and is_git_worktree(worktree_path, repo_root)
        worktree_has_changes = worktree_exists and has_uncommitted_changes(worktree_path)
    except WorktreeError:
        worktree_exists = False
        worktree_has_changes = False

    # Check branch
    branch_name = plan_id
    branch_exists_flag = branch_exists(repo_root, branch_name)

    # Count unmerged commits
    branch_unmerged_commits = 0
    if branch_exists_flag:
        try:
            # Detect default branch (main, master, or HEAD reference)
            default_branch = _get_default_branch(repo_root)
            if default_branch:
                # Count commits not in default branch
                result = subprocess.run(
                    ["git", "-C", str(repo_root), "rev-list", "--count", f"{default_branch}..{branch_name}"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                branch_unmerged_commits = int(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            # Assume 0 if we can't determine
            branch_unmerged_commits = 0

    # Check plan file
    plan_file = repo_root / ".lw_coder" / "tasks" / f"{plan_id}.md"
    plan_file_exists = plan_file.exists()

    # Check backup ref
    backup_ref_exists = _backup_ref_exists(repo_root, plan_id)

    return PlanArtifacts(
        worktree_exists=worktree_exists,
        worktree_has_changes=worktree_has_changes,
        branch_exists=branch_exists_flag,
        branch_unmerged_commits=branch_unmerged_commits,
        plan_file_exists=plan_file_exists,
        backup_ref_exists=backup_ref_exists,
    )


def _backup_ref_exists(repo_root: Path, plan_id: str) -> bool:
    """Check if a backup reference exists for the plan.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.

    Returns:
        True if backup reference exists.
    """
    ref_name = f"refs/plan-backups/{plan_id}"
    result = subprocess.run(
        ["git", "-C", str(repo_root), "show-ref", "--verify", ref_name],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.returncode == 0


def _show_confirmation_prompt(plan_id: str, artifacts: PlanArtifacts) -> bool:
    """Show confirmation prompt and get user confirmation.

    Args:
        plan_id: Plan identifier.
        artifacts: Information about existing artifacts.

    Returns:
        True if user confirms, False otherwise.
    """
    # Build warning message
    print(f"\nPlan '{plan_id}' will be abandoned:")

    warnings = []
    if artifacts.worktree_exists:
        if artifacts.worktree_has_changes:
            warnings.append("  - Worktree will be force-deleted (has uncommitted changes)")
        else:
            warnings.append("  - Worktree will be force-deleted")

    if artifacts.branch_exists:
        if artifacts.branch_unmerged_commits > 0:
            warnings.append(f"  - Branch will be force-deleted (has {artifacts.branch_unmerged_commits} unmerged commits)")
        else:
            warnings.append("  - Branch will be force-deleted")

    if artifacts.plan_file_exists:
        warnings.append("  - Plan file will be deleted")

    if artifacts.backup_ref_exists:
        warnings.append(f"  - Backup moved to refs/plan-abandoned/{plan_id}")

    if not warnings:
        print("  (no artifacts found to clean up)")
        return True

    for warning in warnings:
        print(warning)

    print()
    response = input("Continue? (y/n) ").strip().lower()
    return response in ("y", "yes")


def _cleanup_worktree(repo_root: Path, plan_id: str) -> CleanupResult:
    """Force-delete the worktree.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.

    Returns:
        CleanupResult indicating success/failure.
    """
    try:
        worktree_path = get_worktree_path(repo_root, plan_id)
    except WorktreeError as exc:
        return CleanupResult(success=False, already_clean=False, error_message=str(exc))

    if not worktree_path.exists():
        logger.debug("Worktree already deleted: %s", worktree_path)
        return CleanupResult(success=True, already_clean=True, error_message=None)

    if not is_git_worktree(worktree_path, repo_root):
        # Directory exists but not a worktree - skip
        logger.debug("Directory exists but is not a worktree: %s", worktree_path)
        return CleanupResult(success=True, already_clean=True, error_message=None)

    try:
        # Force-remove worktree
        result = subprocess.run(
            ["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info("Force-deleted worktree: %s", worktree_path)
        return CleanupResult(success=True, already_clean=False, error_message=None)
    except subprocess.CalledProcessError as exc:
        error_msg = f"Failed to force-delete worktree: {exc.stderr}"
        logger.error(error_msg)
        return CleanupResult(success=False, already_clean=False, error_message=error_msg)


def _cleanup_branch(repo_root: Path, plan_id: str) -> CleanupResult:
    """Force-delete the branch.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier (used as branch name).

    Returns:
        CleanupResult indicating success/failure.
    """
    branch_name = plan_id

    if not branch_exists(repo_root, branch_name):
        logger.debug("Branch already deleted: %s", branch_name)
        return CleanupResult(success=True, already_clean=True, error_message=None)

    try:
        # Force-delete branch (ignores unmerged commits)
        result = subprocess.run(
            ["git", "-C", str(repo_root), "branch", "-D", branch_name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info("Force-deleted branch: %s", branch_name)
        return CleanupResult(success=True, already_clean=False, error_message=None)
    except subprocess.CalledProcessError as exc:
        error_msg = f"Failed to force-delete branch: {exc.stderr}"
        logger.error(error_msg)
        return CleanupResult(success=False, already_clean=False, error_message=error_msg)


def _cleanup_plan_file(repo_root: Path, plan_id: str) -> CleanupResult:
    """Delete the plan file.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.

    Returns:
        CleanupResult indicating success/failure.
    """
    plan_file = repo_root / ".lw_coder" / "tasks" / f"{plan_id}.md"

    if not plan_file.exists():
        logger.debug("Plan file already deleted: %s", plan_file)
        return CleanupResult(success=True, already_clean=True, error_message=None)

    try:
        plan_file.unlink()
        logger.info("Deleted plan file: %s", plan_file)
        return CleanupResult(success=True, already_clean=False, error_message=None)
    except OSError as exc:
        error_msg = f"Failed to delete plan file: {exc}"
        logger.error(error_msg)
        return CleanupResult(success=False, already_clean=False, error_message=error_msg)


def _move_backup_to_abandoned_ref(repo_root: Path, plan_id: str) -> CleanupResult:
    """Move backup reference to abandoned namespace.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.

    Returns:
        CleanupResult indicating success/failure.
    """
    if not _backup_ref_exists(repo_root, plan_id):
        logger.debug("No backup reference to move for plan: %s", plan_id)
        return CleanupResult(success=True, already_clean=True, error_message=None)

    try:
        move_backup_to_abandoned(repo_root, plan_id)
        logger.info("Moved backup to abandoned namespace: refs/plan-abandoned/%s", plan_id)
        return CleanupResult(success=True, already_clean=False, error_message=None)
    except PlanBackupError as exc:
        error_msg = f"Failed to move backup to abandoned namespace: {exc}"
        logger.error(error_msg)
        return CleanupResult(success=False, already_clean=False, error_message=error_msg)


def _log_abandonment(repo_root: Path, plan_id: str, reason: str) -> None:
    """Log abandonment reason to the abandoned-plans.log file.

    Args:
        repo_root: Repository root directory.
        plan_id: Plan identifier.
        reason: Reason for abandonment.
    """
    log_file = repo_root / ".lw_coder" / "abandoned-plans.log"

    # Format timestamp with local timezone offset
    now = datetime.now().astimezone()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S %z")

    # Build log entry
    entry = f"## {plan_id} - {timestamp}\n{reason}\n\n"

    try:
        # Ensure directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Append to file (create if doesn't exist)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)

        logger.info("Logged abandonment reason to: %s", log_file)
    except OSError as exc:
        logger.warning("Failed to log abandonment reason: %s", exc)


def run_abandon_command(
    plan_path: Path | str,
    reason: str | None = None,
    skip_confirmation: bool = False,
) -> int:
    """Execute the abandon command.

    Args:
        plan_path: Path to the plan file or plan ID.
        reason: Optional reason for abandonment (logged if provided).
        skip_confirmation: If True, skip the confirmation prompt.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    try:
        # Find repository root
        repo_root = find_repo_root()
        logger.debug("Repository root: %s", repo_root)

        # Load plan_id from plan file
        plan_path_obj = Path(plan_path)

        # Check if it's a path or a plan ID
        if plan_path_obj.exists():
            plan_id, _ = load_plan_id(plan_path_obj)
        else:
            # Try to resolve as plan ID
            tasks_dir = repo_root / ".lw_coder" / "tasks"
            plan_file = tasks_dir / f"{plan_path}.md"
            if plan_file.exists():
                plan_id, _ = load_plan_id(plan_file)
            else:
                # Treat as plan_id directly (artifacts may exist even without plan file)
                plan_id = str(plan_path)
                logger.debug("Treating input as plan_id: %s", plan_id)

        logger.info("Plan ID: %s", plan_id)

        # Detect existing artifacts
        artifacts = _detect_plan_artifacts(repo_root, plan_id)

        # Check if there's anything to clean up
        has_artifacts = any([
            artifacts.worktree_exists,
            artifacts.branch_exists,
            artifacts.plan_file_exists,
            artifacts.backup_ref_exists,
        ])

        if not has_artifacts:
            logger.info("No artifacts found for plan '%s'. Nothing to clean up.", plan_id)
            print(f"No artifacts found for plan '{plan_id}'. Nothing to clean up.")
            return 0

        # Show confirmation prompt (unless skipped)
        if not skip_confirmation:
            if not _show_confirmation_prompt(plan_id, artifacts):
                logger.info("Abandonment cancelled by user")
                print("Abandonment cancelled.")
                return 0

        # Perform cleanup operations (best-effort)
        any_failure = False

        # 1. Delete worktree first (must be done before branch deletion)
        if artifacts.worktree_exists:
            result = _cleanup_worktree(repo_root, plan_id)
            if not result.success:
                any_failure = True
                print(f"Warning: {result.error_message}")

        # 2. Delete branch
        if artifacts.branch_exists:
            result = _cleanup_branch(repo_root, plan_id)
            if not result.success:
                any_failure = True
                print(f"Warning: {result.error_message}")

        # 3. Delete plan file
        if artifacts.plan_file_exists:
            result = _cleanup_plan_file(repo_root, plan_id)
            if not result.success:
                any_failure = True
                print(f"Warning: {result.error_message}")

        # 4. Move backup to abandoned namespace
        if artifacts.backup_ref_exists:
            result = _move_backup_to_abandoned_ref(repo_root, plan_id)
            if not result.success:
                any_failure = True
                print(f"Warning: {result.error_message}")

        # 5. Log reason if provided
        if reason:
            _log_abandonment(repo_root, plan_id, reason)

        # Report result
        if any_failure:
            logger.warning("Plan '%s' abandoned with some errors", plan_id)
            print(f"\nPlan '{plan_id}' abandoned with some errors. See warnings above.")
            return 1
        else:
            logger.info("Plan '%s' successfully abandoned", plan_id)
            print(f"\nPlan '{plan_id}' successfully abandoned.")
            if artifacts.backup_ref_exists:
                print(f"Backup preserved at: refs/plan-abandoned/{plan_id}")
                print(f"To recover: lw_coder recover-plan --abandoned {plan_id}")
            return 0

    except (RepoUtilsError, PlanValidationError, AbandonCommandError) as exc:
        logger.error("%s", exc)
        return 1
