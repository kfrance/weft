"""Implementation of the finalize command for merging completed plans.

This command automates the workflow of finalizing work from a plan's worktree by
committing changes, merging them into the main branch, and cleaning up.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .executors import ExecutorError, ExecutorRegistry
from .host_runner import build_host_command, get_lw_coder_src_dir, host_runner_config
from .logging_config import get_logger
from .plan_backup import cleanup_backup
from .plan_lifecycle import PlanLifecycleError, update_plan_fields
from .plan_validator import PlanValidationError, extract_front_matter, load_plan_id
from .repo_utils import (
    RepoUtilsError,
    find_repo_root,
    load_prompt_template,
    verify_branch_merged_to_main,
)
from .worktree_utils import (
    WorktreeError,
    has_uncommitted_changes,
    validate_worktree_exists,
)

logger = get_logger(__name__)


class FinalizeCommandError(Exception):
    """Raised when finalize command operations fail."""


def _move_plan_to_worktree(plan_path: Path, worktree_path: Path, plan_id: str) -> None:
    """Move plan file to worktree's .lw_coder/tasks/ directory.

    Args:
        plan_path: Source plan file path.
        worktree_path: Worktree directory path.
        plan_id: Plan identifier.

    Raises:
        FinalizeCommandError: If moving fails.
    """
    dest_dir = worktree_path / ".lw_coder" / "tasks"

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, IOError) as exc:
        raise FinalizeCommandError(
            f"Failed to create tasks directory in worktree: {exc}"
        ) from exc

    dest_file = dest_dir / f"{plan_id}.md"
    try:
        shutil.move(str(plan_path), str(dest_file))
        logger.info("Moved plan file to worktree: %s", dest_file)
    except (OSError, IOError) as exc:
        raise FinalizeCommandError(
            f"Failed to move plan file to worktree at {dest_file}: {exc}. "
            f"Check file permissions and available disk space."
        ) from exc


def _cleanup_worktree_and_branch(
    repo_root: Path, worktree_path: Path, plan_id: str
) -> None:
    """Remove worktree and delete branch after successful finalization.

    Worktree must be removed first because Git won't allow deleting a branch
    that's currently checked out in a worktree.

    Args:
        repo_root: Repository root directory.
        worktree_path: Path to the worktree to remove.
        plan_id: Plan identifier (used as branch name).

    Raises:
        FinalizeCommandError: If cleanup operations fail.
    """
    branch_name = plan_id

    # Remove the worktree first (required before we can delete the branch)
    try:
        result = subprocess.run(
            ["git", "worktree", "remove", str(worktree_path)],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info("Removed worktree: %s", worktree_path)
    except subprocess.CalledProcessError as exc:
        raise FinalizeCommandError(
            f"Failed to remove worktree at {worktree_path}: {exc.stderr}. "
            f"You can manually remove the worktree with: git worktree remove {worktree_path}"
        ) from exc

    # Delete the branch after worktree is removed
    try:
        result = subprocess.run(
            ["git", "branch", "-d", branch_name],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info("Deleted branch: %s", branch_name)
    except subprocess.CalledProcessError as exc:
        # Provide helpful error message if branch is not fully merged
        if "not fully merged" in exc.stderr:
            raise FinalizeCommandError(
                f"Branch '{branch_name}' is not fully merged. "
                f"Verification passed but branch deletion failed. "
                f"The worktree was removed successfully. "
                f"If you're certain the merge succeeded, manually delete with: "
                f"git branch -D {branch_name}"
            ) from exc
        raise FinalizeCommandError(
            f"Failed to delete branch '{branch_name}': {exc.stderr}. "
            f"The worktree was removed successfully."
        ) from exc


def run_finalize_command(plan_path: Path | str, tool: str = "claude-code") -> int:
    """Execute the finalize command.

    Args:
        plan_path: Path to the plan file.
        tool: Name of the coding tool to use (default: "claude-code").

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    repo_root = None
    # Initialize to None; set after template loading, cleaned up in finally block
    prompt_file = None

    try:
        # Get the executor for the specified tool
        try:
            executor = ExecutorRegistry.get_executor(tool)
        except ExecutorError as exc:
            raise FinalizeCommandError(str(exc)) from exc

        # Pre-flight check for executor-specific authentication
        try:
            executor.check_auth()
        except ExecutorError as exc:
            raise FinalizeCommandError(str(exc)) from exc

        # Find repository root
        repo_root = find_repo_root()
        logger.debug("Repository root: %s", repo_root)

        # Load plan metadata
        plan_path_obj = Path(plan_path)
        plan_id, resolved_plan_path = load_plan_id(plan_path_obj)
        logger.info("Plan ID: %s", plan_id)

        # Validate worktree exists
        worktree_path = validate_worktree_exists(repo_root, plan_id)
        logger.info("Found worktree at: %s", worktree_path)

        # Check for uncommitted changes
        if not has_uncommitted_changes(worktree_path):
            raise FinalizeCommandError(
                f"No uncommitted changes found in worktree for plan '{plan_id}'. "
                f"Nothing to finalize."
            )

        logger.info("Found uncommitted changes in worktree")

        # Update plan status to "done" before moving (so moved file has correct status)
        try:
            content = resolved_plan_path.read_text(encoding="utf-8")
            front_matter, _ = extract_front_matter(content)
            current_status = front_matter.get("status", "").strip().lower() if isinstance(front_matter.get("status"), str) else ""

            if current_status != "done":
                update_plan_fields(resolved_plan_path, {"status": "done"})
                logger.info("Updated plan status to 'done'")
        except OSError as exc:
            # I/O errors - may be transient
            logger.warning("Failed to update plan status (I/O error): %s", exc)
        except (PlanValidationError, PlanLifecycleError) as exc:
            # Validation errors - likely a user error in plan format
            logger.warning("Failed to update plan status (validation error): %s", exc)

        # Move plan file to worktree (after status update so it has status="done")
        _move_plan_to_worktree(resolved_plan_path, worktree_path, plan_id)

        # Load template
        template = load_prompt_template(tool, "finalize")

        # Replace placeholder with plan_id
        combined_prompt = template.replace("{PLAN_ID}", plan_id)

        # Write prompt to temporary file to avoid command injection
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(combined_prompt)
            prompt_file = Path(f.name)

        # Set secure file permissions (user read/write only, not world-readable)
        os.chmod(prompt_file, 0o600)

        # Get lw_coder source directory
        try:
            lw_coder_src = get_lw_coder_src_dir()
        except RuntimeError as exc:
            raise FinalizeCommandError(str(exc)) from exc

        # Prepare paths for host configuration
        tasks_dir = repo_root / ".lw_coder" / "tasks"
        droids_dir = lw_coder_src / "droids"
        host_factory_dir = Path.home() / ".factory"
        git_dir = repo_root / ".git"

        logger.info("Starting %s session for finalization...", tool)
        logger.info("This will commit changes, rebase onto main, and merge")

        # Build command using the executor
        # Use default model "haiku" for finalize command (fast execution)
        command = executor.build_command(prompt_file, model="haiku")

        # Get executor-specific environment variables
        executor_env_vars = executor.get_env_vars(host_factory_dir)

        runner_config = host_runner_config(
            worktree_path=worktree_path,
            repo_git_dir=git_dir,
            tasks_dir=tasks_dir,
            droids_dir=droids_dir,
            command=command,
            host_factory_dir=host_factory_dir,
            env_vars=executor_env_vars,
        )

        # Build host command
        host_cmd, host_env = build_host_command(runner_config)

        # Run executor interactively on the host
        try:
            result = subprocess.run(
                host_cmd,
                check=False,
                env=host_env,
                cwd=worktree_path,
            )

            if result.returncode == 0:
                logger.info("Finalization session completed successfully")

                # Verify the merge succeeded by checking if branch was merged into main
                branch_name = plan_id
                try:
                    if verify_branch_merged_to_main(repo_root, branch_name):
                        logger.info("Verified branch was merged into main")

                        # Clean up worktree and branch
                        try:
                            _cleanup_worktree_and_branch(repo_root, worktree_path, plan_id)
                            logger.info(
                                "Successfully cleaned up worktree and branch for plan '%s'",
                                plan_id,
                            )
                        except FinalizeCommandError as exc:
                            logger.error("Cleanup failed: %s", exc)
                            logger.error(
                                "You may need to manually clean up:\n"
                                "  git worktree remove %s\n"
                                "  git branch -d %s",
                                worktree_path,
                                branch_name,
                            )
                            return 1

                        # Clean up backup reference (non-fatal if it fails)
                        cleanup_backup(repo_root, plan_id)
                        logger.info("Cleaned up backup reference for plan '%s'", plan_id)
                    else:
                        logger.warning(
                            "Branch '%s' was not merged into main - skipping cleanup",
                            branch_name,
                        )
                        logger.warning(
                            "Worktree and branch were not cleaned up. "
                            "Please verify the merge succeeded and clean up manually if needed."
                        )
                        return 1
                except RepoUtilsError as exc:
                    logger.error("Failed to verify commit: %s", exc)
                    logger.warning("Skipping cleanup due to verification failure")
                    return 1

            else:
                logger.warning("Finalization session exited with code %d", result.returncode)
                logger.info(
                    "Worktree and branch left intact for manual recovery at: %s",
                    worktree_path,
                )

            return result.returncode
        except KeyboardInterrupt:
            logger.info("Session interrupted by user.")
            return 130  # Standard Unix convention: 128 + signal number (SIGINT = 2)

    except (ExecutorError, FinalizeCommandError, WorktreeError, RepoUtilsError, PlanValidationError) as exc:
        logger.error("%s", exc)
        return 1

    finally:
        # Clean up prompt file
        if prompt_file:
            try:
                prompt_file.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to clean up prompt file: %s", exc)
