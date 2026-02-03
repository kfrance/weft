"""Implementation of the finalize command for completing work from a plan's worktree.

This command runs an interactive session to finalize work (e.g., commit, push, create PR).
The specific workflow is determined by the repo-specific finalize prompt at
`.weft/prompts/active/<tool>/finalize.md`.

After the session completes successfully, the worktree is cleaned up (branch preserved).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .executors import ExecutorError, ExecutorRegistry
from .host_runner import build_host_command, host_runner_config
from .logging_config import get_logger
from .param_validation import get_effective_model
from .plan_backup import cleanup_backup
from .plan_lifecycle import PlanLifecycleError, update_plan_fields
from .plan_validator import PlanValidationError, extract_front_matter, load_plan_id
from .prompt_loader import PromptLoadingError, load_finalize_prompt
from .repo_utils import (
    RepoUtilsError,
    find_repo_root,
)
from .worktree_utils import (
    WorktreeError,
    get_worktree_status,
    has_uncommitted_changes,
    validate_worktree_exists,
)
from .worktree.file_sync import (
    FileSyncError,
    WorktreeFileCleanup,
    load_repo_config,
    should_sync_for_command,
    sync_files_to_worktree,
    validate_worktree_file_sync_config,
)

logger = get_logger(__name__)


class FinalizeCommandError(Exception):
    """Raised when finalize command operations fail."""


def _move_plan_to_worktree(plan_path: Path, worktree_path: Path, plan_id: str) -> None:
    """Move plan file to worktree's .weft/tasks/ directory.

    Args:
        plan_path: Source plan file path.
        worktree_path: Worktree directory path.
        plan_id: Plan identifier.

    Raises:
        FinalizeCommandError: If moving fails.
    """
    dest_dir = worktree_path / ".weft" / "tasks"

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


def _cleanup_worktree(repo_root: Path, worktree_path: Path, *, force: bool = False) -> None:
    """Remove worktree after successful finalization.

    The branch is preserved (not deleted). If force=True, the worktree is removed
    even if it contains uncommitted changes.

    Args:
        repo_root: Repository root directory.
        worktree_path: Path to the worktree to remove.
        force: If True, use --force to remove worktree with uncommitted changes.

    Raises:
        FinalizeCommandError: If cleanup operations fail.
    """
    cmd = ["git", "worktree", "remove"]
    if force:
        cmd.append("--force")
    cmd.append(str(worktree_path))

    try:
        subprocess.run(
            cmd,
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
            f"You can manually remove the worktree with: git worktree remove --force {worktree_path}"
        ) from exc


def _confirm_cleanup_with_changes(
    worktree_path: Path,
    modified: list[str],
    untracked: list[str],
) -> bool:
    """Prompt user to confirm cleanup when there are uncommitted changes.

    Displays the list of modified and untracked files and asks for confirmation.

    Args:
        worktree_path: Path to the worktree.
        modified: List of modified file paths.
        untracked: List of untracked file paths.

    Returns:
        True if user confirms cleanup, False otherwise.
    """
    print(f"\nWorktree at {worktree_path} has uncommitted changes:\n")

    if modified:
        print("Modified files:")
        for f in modified:
            print(f"  M {f}")

    if untracked:
        if modified:
            print()
        print("Untracked files:")
        for f in untracked:
            print(f"  ? {f}")

    print()
    try:
        response = input("Remove worktree and discard these changes? [y/N] ").strip().lower()
        return response == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def run_finalize_command(
    plan_path: Path | str,
    tool: str = "claude-code",
    model: str | None = None,
) -> int:
    """Execute the finalize command.

    Args:
        plan_path: Path to the plan file.
        tool: Name of the coding tool to use (default: "claude-code").
        model: Model variant to use (e.g., "sonnet", "opus", "haiku").
               If None, uses config.toml default or hardcoded default (haiku).

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    repo_root = None
    # Initialize to None; set after template loading, cleaned up in finally block
    prompt_file = None
    file_sync_cleanup: WorktreeFileCleanup | None = None

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

        # Sync files from repo to worktree based on .weft/config.toml
        # Only sync if "finalize" is in the commands list
        try:
            repo_config = load_repo_config(repo_root)
            sync_config = validate_worktree_file_sync_config(repo_config)
            if should_sync_for_command(sync_config, "finalize"):
                file_sync_cleanup = WorktreeFileCleanup()
                sync_files_to_worktree(repo_root, worktree_path, file_sync_cleanup)
            else:
                logger.debug("File sync skipped: 'finalize' not in commands list")
        except FileSyncError as exc:
            logger.error("File sync failed: %s", exc)
            return 1

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

        # Load finalize prompt from repo-specific location (auto-copies from bundled if missing)
        template = load_finalize_prompt(repo_root, tool)

        # Replace placeholder with plan_id
        combined_prompt = template.replace("{PLAN_ID}", plan_id)

        # Write prompt file to /tmp/claude which is bind-mounted into the sandbox
        # (bwrap creates a fresh tmpfs at /tmp, but /tmp/claude is overlaid on top)
        prompt_dir = Path("/tmp/claude/weft")
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = prompt_dir / f"finalize-{plan_id}.txt"
        prompt_file.write_text(combined_prompt, encoding="utf-8")

        # Set secure file permissions (user read/write only, not world-readable)
        os.chmod(prompt_file, 0o600)

        # Prepare paths for host configuration
        tasks_dir = repo_root / ".weft" / "tasks"
        host_factory_dir = Path.home() / ".factory"
        git_dir = repo_root / ".git"

        logger.info("Starting %s session for finalization...", tool)

        # Build command using the executor
        # Use 3-tier precedence: CLI flag > config.toml > hardcoded default (haiku)
        effective_model = get_effective_model(model, "finalize")
        command = executor.build_command(prompt_file, model=effective_model)

        # Get executor-specific environment variables
        executor_env_vars = executor.get_env_vars(host_factory_dir)

        runner_config = host_runner_config(
            worktree_path=worktree_path,
            repo_git_dir=git_dir,
            tasks_dir=tasks_dir,
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

                # Check for uncommitted changes before cleanup
                status = get_worktree_status(worktree_path)
                has_changes = status["modified"] or status["untracked"]

                if has_changes:
                    # Prompt user to confirm cleanup with uncommitted changes
                    if _confirm_cleanup_with_changes(
                        worktree_path, status["modified"], status["untracked"]
                    ):
                        try:
                            _cleanup_worktree(repo_root, worktree_path, force=True)
                            logger.info(
                                "Cleaned up worktree for plan '%s' (branch preserved)",
                                plan_id,
                            )
                            cleanup_backup(repo_root, plan_id)
                        except FinalizeCommandError as exc:
                            logger.error("Cleanup failed: %s", exc)
                            logger.error(
                                "You may need to manually clean up:\n"
                                "  git worktree remove --force %s",
                                worktree_path,
                            )
                            return 1
                    else:
                        logger.info(
                            "Worktree preserved at %s (user declined cleanup)",
                            worktree_path,
                        )
                else:
                    # Clean worktree - safe to remove without force
                    try:
                        _cleanup_worktree(repo_root, worktree_path)
                        logger.info(
                            "Cleaned up worktree for plan '%s' (branch preserved)",
                            plan_id,
                        )
                        cleanup_backup(repo_root, plan_id)
                    except FinalizeCommandError as exc:
                        logger.error("Cleanup failed: %s", exc)
                        logger.error(
                            "You may need to manually clean up:\n"
                            "  git worktree remove %s",
                            worktree_path,
                        )
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

    except (ExecutorError, FinalizeCommandError, WorktreeError, RepoUtilsError, PlanValidationError, PromptLoadingError) as exc:
        logger.error("%s", exc)
        return 1

    finally:
        # Clean up synced files from worktree
        if file_sync_cleanup:
            file_sync_cleanup.cleanup()

        # Clean up prompt file
        if prompt_file:
            try:
                prompt_file.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to clean up prompt file: %s", exc)
