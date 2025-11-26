"""Implementation of the plan command for interactive plan development.

Now runs directly on the host environment instead of in Docker containers.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .executors import ExecutorError, ExecutorRegistry
from .host_runner import build_host_command, get_lw_coder_src_dir, host_runner_config
from .logging_config import get_logger
from .plan_backup import PlanBackupError, create_backup
from .plan_file_copier import PlanFileCopyError, copy_plan_files, get_existing_files
from .plan_lifecycle import PlanLifecycleError, update_plan_fields
from .plan_validator import PLACEHOLDER_SHA, PlanValidationError, extract_front_matter
from .repo_utils import RepoUtilsError, find_repo_root, load_prompt_template
from .temp_worktree import TempWorktreeError, create_temp_worktree, remove_temp_worktree
from .trace_capture import (
    TraceCaptureError,
    capture_session_trace,
    create_plan_trace_directory,
    prune_old_plan_traces,
)

logger = get_logger(__name__)


class PlanCommandError(Exception):
    """Raised when plan command operations fail."""


def _extract_idea_text(plan_path: Path | None, text_input: str | None) -> str:
    """Extract the idea text from either a file or direct text input.

    If a plan file is provided, reads it and extracts only the body (ignoring frontmatter).
    Otherwise, uses the text input directly.

    Args:
        plan_path: Optional path to a markdown file.
        text_input: Optional direct text input.

    Returns:
        The idea text to be used in the template.

    Raises:
        PlanCommandError: If neither or both inputs are provided, or if file reading fails.
    """
    if plan_path and text_input:
        raise PlanCommandError("Cannot specify both <plan_path> and --text options.")

    if not plan_path and not text_input:
        raise PlanCommandError("Must specify either <plan_path> or --text option.")

    if text_input:
        return text_input

    # Read from file
    path = Path(plan_path).expanduser().resolve()
    if not path.exists():
        raise PlanCommandError(f"Plan file not found: {path}")

    logger.debug("Reading idea from file: %s", path)
    content = path.read_text(encoding="utf-8")

    # Try to extract front matter and ignore it
    try:
        _, body = extract_front_matter(content)
        return body.strip()
    except (PlanValidationError, ValueError, KeyError, TypeError):
        # If no front matter or parsing fails, use the whole content
        return content.strip()


def _copy_droids_for_plan(worktree_path: Path) -> None:
    """Copy maintainability-reviewer droid to worktree for Droid CLI.

    Copies the droid from src/lw_coder/droids/ to <worktree>/.factory/droids/
    so it's discoverable as a project droid.

    Args:
        worktree_path: Path to the temporary worktree.

    Raises:
        PlanCommandError: If droid copying fails.
    """
    try:
        src_dir = get_lw_coder_src_dir()
    except RuntimeError as exc:
        raise PlanCommandError(str(exc)) from exc

    source_droid = src_dir / "droids" / "maintainability-reviewer.md"
    if not source_droid.exists():
        raise PlanCommandError(
            f"Maintainability reviewer droid not found at {source_droid}"
        )

    dest_droids_dir = worktree_path / ".factory" / "droids"
    dest_droids_dir.mkdir(parents=True, exist_ok=True)

    dest_droid = dest_droids_dir / "maintainability-reviewer.md"
    try:
        shutil.copy2(source_droid, dest_droid)
        logger.info("Copied maintainability-reviewer droid to %s", dest_droids_dir)
    except (OSError, IOError) as exc:
        raise PlanCommandError(
            f"Failed to copy droid to {dest_droid}: {exc}"
        ) from exc


def _write_maintainability_agent(worktree_path: Path) -> None:
    """Write maintainability-reviewer agent for Claude Code CLI.

    Writes the agent from src/lw_coder/droids/ to <worktree>/.claude/agents/
    so it's discoverable by Claude Code CLI.

    Args:
        worktree_path: Path to the temporary worktree.

    Raises:
        PlanCommandError: If agent writing fails.
    """
    try:
        src_dir = get_lw_coder_src_dir()
    except RuntimeError as exc:
        raise PlanCommandError(str(exc)) from exc

    source_agent = src_dir / "droids" / "maintainability-reviewer.md"
    if not source_agent.exists():
        raise PlanCommandError(
            f"Maintainability reviewer agent not found at {source_agent}"
        )

    dest_agents_dir = worktree_path / ".claude" / "agents"
    dest_agents_dir.mkdir(parents=True, exist_ok=True)

    dest_agent = dest_agents_dir / "maintainability-reviewer.md"
    try:
        shutil.copy2(source_agent, dest_agent)
        logger.info("Wrote maintainability-reviewer agent to %s", dest_agents_dir)
    except (OSError, IOError) as exc:
        raise PlanCommandError(
            f"Failed to write agent to {dest_agent}: {exc}"
        ) from exc


def run_plan_command(plan_path: Path | None, text_input: str | None, tool: str) -> int:
    """Execute the plan command.

    Args:
        plan_path: Optional path to a markdown file with plan idea.
        text_input: Optional direct text input for the plan idea.
        tool: Name of the coding tool to use (default: "claude-code").

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    temp_worktree = None
    repo_root = None
    prompt_file = None

    try:
        # Get the executor for the specified tool
        try:
            executor = ExecutorRegistry.get_executor(tool)
        except ExecutorError as exc:
            raise PlanCommandError(str(exc)) from exc

        # Pre-flight check for executor-specific authentication
        try:
            executor.check_auth()
        except ExecutorError as exc:
            raise PlanCommandError(str(exc)) from exc

        # Find repository root
        repo_root = find_repo_root()
        logger.debug("Repository root: %s", repo_root)

        # Extract idea text
        idea_text = _extract_idea_text(plan_path, text_input)

        # Load template
        template = load_prompt_template(tool, "plan")

        # Replace placeholder
        combined_prompt = template.replace("{IDEA_TEXT}", idea_text)

        # Write prompt to temporary file to avoid command injection
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(combined_prompt)
            prompt_file = Path(f.name)

        # Set secure file permissions (user read/write only, not world-readable)
        os.chmod(prompt_file, 0o600)

        # Create temporary worktree
        temp_worktree = create_temp_worktree(repo_root)

        # Capture existing files before execution
        worktree_tasks_dir = temp_worktree / ".lw_coder" / "tasks"
        main_tasks_dir = repo_root / ".lw_coder" / "tasks"
        existing_files = get_existing_files(worktree_tasks_dir)

        # Get lw_coder source directory
        try:
            lw_coder_src = get_lw_coder_src_dir()
        except RuntimeError as exc:
            raise PlanCommandError(str(exc)) from exc

        # Prepare paths for host configuration
        tasks_dir = repo_root / ".lw_coder" / "tasks"
        droids_dir = lw_coder_src / "droids"
        host_factory_dir = Path.home() / ".factory"
        git_dir = repo_root / ".git"

        logger.info("Starting %s session...", tool)
        logger.info("Plans will be saved to .lw_coder/tasks/<plan_id>.md")
        logger.info("Processing plan with %s...", tool)

        # Set up agents/droids based on executor type
        try:
            if tool == "droid":
                _copy_droids_for_plan(temp_worktree)
            elif tool == "claude-code":
                _write_maintainability_agent(temp_worktree)
            logger.info("Sub-agents/droids configured for %s", tool)
        except PlanCommandError as exc:
            raise PlanCommandError(f"Failed to set up agents/droids: {exc}") from exc

        # Build command using the executor
        # Use default model "sonnet" for plan command
        command = executor.build_command(prompt_file, model="sonnet")

        # Get executor-specific environment variables
        executor_env_vars = executor.get_env_vars(host_factory_dir)

        runner_config = host_runner_config(
            worktree_path=temp_worktree,
            repo_git_dir=git_dir,
            tasks_dir=tasks_dir,
            droids_dir=droids_dir,
            command=command,
            host_factory_dir=host_factory_dir,
            env_vars=executor_env_vars,
        )

        # Build host command
        host_cmd, host_env = build_host_command(runner_config)

        # Create plan trace directory
        plan_trace_dir = None
        if tool == "claude-code":
            try:
                plan_trace_dir = create_plan_trace_directory(repo_root)
                logger.debug("Created plan trace directory: %s", plan_trace_dir)
            except TraceCaptureError as exc:
                logger.warning("Failed to create plan trace directory: %s", exc)

        # Prune old plan traces (non-fatal if it fails)
        if tool == "claude-code":
            try:
                prune_old_plan_traces(repo_root)
            except Exception as exc:
                logger.debug("Failed to prune old plan traces: %s", exc)

        # Capture execution start time for trace capture
        execution_start = time.time()

        # Run executor interactively on the host
        try:
            result = subprocess.run(
                host_cmd,
                check=False,
                env=host_env,
                cwd=temp_worktree,
            )

            # Capture execution end time for trace capture
            execution_end = time.time()

            # Capture conversation trace (non-fatal if it fails)
            if tool == "claude-code" and plan_trace_dir:
                try:
                    trace_file = capture_session_trace(
                        worktree_path=temp_worktree,
                        command="plan",
                        run_dir=plan_trace_dir,
                        execution_start=execution_start,
                        execution_end=execution_end,
                    )
                    if trace_file:
                        logger.debug("Trace captured at: %s", trace_file)
                except TraceCaptureError as exc:
                    logger.warning("Warning: Trace capture failed")
                    logger.debug("Trace capture error details: %s", exc)

            # Copy newly created plan files from worktree to main repository
            try:
                file_mapping = copy_plan_files(worktree_tasks_dir, main_tasks_dir, existing_files)
            except PlanFileCopyError as exc:
                logger.warning("Failed to copy plan files from worktree: %s", exc)
                file_mapping = {}

            try:
                _ensure_placeholder_git_sha(tasks_dir)
            except PlanLifecycleError as exc:
                logger.warning("Failed to normalize plan git_sha placeholder: %s", exc)

            # Create backups for all copied plan files (non-fatal)
            failed_backups = []
            for final_filename in file_mapping.values():
                try:
                    # Extract plan_id from file name (remove .md extension)
                    plan_id = Path(final_filename).stem
                    create_backup(repo_root, plan_id)
                    logger.info("Created backup for plan: %s", plan_id)
                except PlanBackupError as exc:
                    failed_backups.append((plan_id, str(exc)))
                    logger.error("Failed to create backup for plan '%s': %s", plan_id, exc)

            # Log summary if any backups failed (non-fatal)
            if failed_backups:
                logger.warning(
                    "Plan files copied successfully but %d backup(s) failed. "
                    "Plans may not be recoverable if deleted. Failed: %s",
                    len(failed_backups),
                    ", ".join(plan_id for plan_id, _ in failed_backups),
                )

            return result.returncode
        except KeyboardInterrupt:
            execution_end = time.time()
            logger.info("Session interrupted by user.")

            # Capture conversation trace even for interrupted sessions (non-fatal if it fails)
            if tool == "claude-code" and plan_trace_dir:
                try:
                    trace_file = capture_session_trace(
                        worktree_path=temp_worktree,
                        command="plan",
                        run_dir=plan_trace_dir,
                        execution_start=execution_start,
                        execution_end=execution_end,
                    )
                    if trace_file:
                        logger.debug("Trace captured at: %s", trace_file)
                except TraceCaptureError as exc:
                    logger.warning("Warning: Trace capture failed")
                    logger.debug("Trace capture error details: %s", exc)

            return 0

    except (ExecutorError, PlanCommandError, TempWorktreeError, RepoUtilsError) as exc:
        logger.error("%s", exc)
        return 1

    finally:
        # Clean up prompt file
        if prompt_file:
            try:
                prompt_file.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to clean up prompt file: %s", exc)

        # Clean up temporary worktree
        if temp_worktree and repo_root:
            try:
                remove_temp_worktree(repo_root, temp_worktree)
            except TempWorktreeError as exc:
                logger.warning("Failed to clean up temporary worktree: %s", exc)


def _ensure_placeholder_git_sha(tasks_dir: Path) -> None:
    """Ensure draft plans use the placeholder git SHA."""

    for plan_file in tasks_dir.glob("*.md"):
        try:
            content = plan_file.read_text(encoding="utf-8")
        except OSError:
            continue

        try:
            front_matter, _ = extract_front_matter(content)
        except PlanValidationError:
            continue

        git_sha = front_matter.get("git_sha")
        status = front_matter.get("status", "").strip().lower() if isinstance(front_matter.get("status"), str) else ""

        if status != "draft" or not isinstance(git_sha, str):
            continue

        if git_sha == PLACEHOLDER_SHA:
            continue

        update_plan_fields(plan_file, {"git_sha": PLACEHOLDER_SHA})
