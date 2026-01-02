"""Implementation of the plan command for interactive plan development.

Now runs directly on the host environment instead of in Docker containers.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

from .executors import ExecutorError, ExecutorRegistry
from .headless import is_headless
from .file_watcher import PlanFileWatcher
from .hooks import get_hook_manager, trigger_hook
from .host_runner import build_host_command, get_weft_src_dir, host_runner_config
from .logging_config import get_logger
from .param_validation import get_effective_model
from .plan_backup import PlanBackupError, create_backup
from .plan_file_copier import PlanFileCopyError, copy_plan_files, get_existing_files
from .plan_lifecycle import PlanLifecycleError, update_plan_fields
from .plan_validator import PLACEHOLDER_SHA, PlanValidationError, extract_front_matter
from .repo_utils import RepoUtilsError, find_repo_root, load_prompt_template
from .temp_worktree import TempWorktreeError, create_temp_worktree, remove_temp_worktree
from .session_manager import (
    SessionManagerError,
    create_session_directory,
    prune_old_sessions,
)
from .trace_capture import (
    TraceCaptureError,
    capture_session_trace,
)

logger = get_logger(__name__)

# Module-level constant for subagent configurations (single source of truth)
# Used by _write_plan_subagents() and accessible for testing
PLAN_SUBAGENT_CONFIGS = {
    "maintainability-reviewer": "Evaluates plans from a long-term maintenance perspective",
    "test-discovery": "Analyzes existing tests to inform testing questions during planning",
    "test-reviewer": "Reviews plan test coverage and identifies gaps",
}


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


def _write_plan_subagents(worktree_path: Path, tool: str, model: str) -> None:
    """Write plan subagents with appropriate YAML front matter for the tool.

    Args:
        worktree_path: Path to the temporary worktree.
        tool: Tool name ("droid" or "claude-code").
        model: Model to use (for Claude Code; ignored for Droid which uses gpt-5-codex).

    Raises:
        PlanCommandError: If subagent writing fails.
    """
    try:
        src_dir = get_weft_src_dir()
    except RuntimeError as exc:
        raise PlanCommandError(str(exc)) from exc

    # Determine destination directory and model based on tool
    if tool == "droid":
        dest_dir = worktree_path / ".factory" / "droids"
        effective_model = "gpt-5-codex"
        include_tools_field = True
    elif tool == "claude-code":
        dest_dir = worktree_path / ".claude" / "agents"
        effective_model = model
        include_tools_field = False
    else:
        raise PlanCommandError(f"Unknown tool: {tool}")

    # Create destination directory
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Write each subagent
    for subagent_name, description in PLAN_SUBAGENT_CONFIGS.items():
        # Load plain markdown prompt
        prompt_path = src_dir / "prompts" / "plan-subagents" / f"{subagent_name}.md"
        if not prompt_path.exists():
            raise PlanCommandError(
                f"Subagent prompt not found at {prompt_path}"
            )

        try:
            prompt_content = prompt_path.read_text(encoding="utf-8")
        except (OSError, IOError) as exc:
            raise PlanCommandError(
                f"Failed to read subagent prompt from {prompt_path}: {exc}"
            ) from exc

        # Generate YAML front matter based on tool
        if include_tools_field:
            # Droid format: includes tools field
            front_matter = f"""---
name: {subagent_name}
description: {description}
model: {effective_model}
tools: read-only
---

"""
        else:
            # Claude Code format: omits tools field for inheritance
            front_matter = f"""---
name: {subagent_name}
description: {description}
model: {effective_model}
---

"""

        # Combine front matter and prompt content
        full_content = front_matter + prompt_content

        # Write to destination
        dest_file = dest_dir / f"{subagent_name}.md"
        try:
            dest_file.write_text(full_content, encoding="utf-8")
            logger.debug("Wrote %s subagent to %s", subagent_name, dest_file)
        except (OSError, IOError) as exc:
            raise PlanCommandError(
                f"Failed to write subagent to {dest_file}: {exc}"
            ) from exc

    logger.info("Configured %s plan subagents in %s", len(PLAN_SUBAGENT_CONFIGS), dest_dir)


def run_plan_command(
    plan_path: Path | None,
    text_input: str | None,
    tool: str,
    model: str | None = None,
    no_hooks: bool = False,
) -> int:
    """Execute the plan command.

    Args:
        plan_path: Optional path to a markdown file with plan idea.
        text_input: Optional direct text input for the plan idea.
        tool: Name of the coding tool to use (default: "claude-code").
        model: Model variant to use (e.g., "sonnet", "opus", "haiku").
               If None, uses config.toml default or hardcoded default (sonnet).
        no_hooks: If True, disable execution of configured hooks.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    temp_worktree = None
    repo_root = None
    prompt_file = None
    file_watcher = None

    if no_hooks:
        logger.info("Hooks disabled via --no-hooks flag")

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
        worktree_tasks_dir = temp_worktree / ".weft" / "tasks"
        main_tasks_dir = repo_root / ".weft" / "tasks"
        existing_files = get_existing_files(worktree_tasks_dir)

        # Prepare paths for host configuration
        tasks_dir = repo_root / ".weft" / "tasks"
        host_factory_dir = Path.home() / ".factory"
        git_dir = repo_root / ".git"

        logger.info("Starting %s session...", tool)
        logger.info("Plans will be saved to .weft/tasks/<plan_id>.md")
        logger.info("Processing plan with %s...", tool)

        # Set up plan subagents (maintainability-reviewer and test-planner)
        try:
            _write_plan_subagents(temp_worktree, tool, "sonnet")
        except PlanCommandError as exc:
            raise PlanCommandError(f"Failed to set up plan subagents: {exc}") from exc

        # Build command using the executor
        # Use 3-tier precedence: CLI flag > config.toml > hardcoded default (sonnet)
        effective_model = get_effective_model(model, "plan")
        command = executor.build_command(
            prompt_file, model=effective_model, headless=is_headless()
        )

        # Get executor-specific environment variables
        executor_env_vars = executor.get_env_vars(host_factory_dir)

        runner_config = host_runner_config(
            worktree_path=temp_worktree,
            repo_git_dir=git_dir,
            tasks_dir=tasks_dir,
            command=command,
            host_factory_dir=host_factory_dir,
            env_vars=executor_env_vars,
        )

        # Build host command
        host_cmd, host_env = build_host_command(runner_config)

        # Prune old session directories (non-fatal if it fails)
        if tool == "claude-code":
            try:
                prune_old_sessions(repo_root)
            except SessionManagerError as exc:
                logger.debug("Failed to prune old session directories: %s", exc)

        # Capture execution start time for trace capture
        execution_start = time.time()

        # Set up file watcher for plan_file_created hook (if hooks are enabled)
        if not no_hooks:
            hook_manager = get_hook_manager()

            def on_plan_file_created(file_path: Path) -> None:
                """Callback when a plan file is created."""
                logger.debug("File watcher detected plan file: %s", file_path)
                plan_id = file_path.stem
                # Map worktree path to main repo path for the plan
                final_plan_path = main_tasks_dir / file_path.name
                trigger_hook(
                    "plan_file_created",
                    {
                        "worktree_path": temp_worktree,
                        "plan_path": final_plan_path,
                        "plan_id": plan_id,
                        "repo_root": repo_root,
                    },
                    manager=hook_manager,
                )

            file_watcher = PlanFileWatcher(
                watch_dir=worktree_tasks_dir,
                on_file_created=on_plan_file_created,
            )
            file_watcher.start()
            logger.debug("Started file watcher for plan_file_created hook on %s", worktree_tasks_dir)

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

            # Create backups and capture trace for all copied plan files (non-fatal)
            failed_backups = []
            for final_filename in file_mapping.values():
                try:
                    # Extract plan_id from file name (remove .md extension)
                    plan_id = Path(final_filename).stem
                    create_backup(repo_root, plan_id)
                    logger.info("Created backup for plan: %s", plan_id)

                    # Capture conversation trace to session directory (non-fatal if it fails)
                    # Now we know the plan_id, so we can create the session directory
                    if tool == "claude-code":
                        try:
                            plan_session_dir = create_session_directory(
                                repo_root, plan_id, "plan"
                            )
                            trace_file = capture_session_trace(
                                worktree_path=temp_worktree,
                                command="plan",
                                run_dir=plan_session_dir,
                                execution_start=execution_start,
                                execution_end=execution_end,
                            )
                            if trace_file:
                                logger.debug("Trace captured at: %s", trace_file)
                        except (SessionManagerError, TraceCaptureError) as exc:
                            logger.warning("Warning: Trace capture failed")
                            logger.debug("Trace capture error details: %s", exc)
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

            # For interrupted sessions, we can still capture trace if any plan files were created
            # Try to copy any plan files first to get the plan_id
            if tool == "claude-code":
                try:
                    file_mapping = copy_plan_files(worktree_tasks_dir, main_tasks_dir, existing_files)
                    for final_filename in file_mapping.values():
                        plan_id = Path(final_filename).stem
                        try:
                            plan_session_dir = create_session_directory(
                                repo_root, plan_id, "plan"
                            )
                            trace_file = capture_session_trace(
                                worktree_path=temp_worktree,
                                command="plan",
                                run_dir=plan_session_dir,
                                execution_start=execution_start,
                                execution_end=execution_end,
                            )
                            if trace_file:
                                logger.debug("Trace captured at: %s", trace_file)
                        except (SessionManagerError, TraceCaptureError) as exc:
                            logger.warning("Warning: Trace capture failed")
                            logger.debug("Trace capture error details: %s", exc)
                except PlanFileCopyError:
                    logger.debug("No plan files to copy on interrupt")

            return 0

    except (ExecutorError, PlanCommandError, TempWorktreeError, RepoUtilsError) as exc:
        logger.error("%s", exc)
        return 1

    finally:
        # Stop file watcher
        if file_watcher:
            try:
                file_watcher.stop()
                logger.debug("Stopped file watcher")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to stop file watcher: %s", exc)

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
