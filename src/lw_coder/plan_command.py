"""Implementation of the plan command for interactive plan development.

Now runs directly on the host environment instead of in Docker containers.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from .droid_auth import DroidAuthError, check_droid_auth
from .host_runner import build_host_command, get_lw_coder_src_dir, host_runner_config
from .logging_config import get_logger
from .plan_lifecycle import PlanLifecycleError, update_plan_fields
from .plan_validator import PLACEHOLDER_SHA, PlanValidationError, _extract_front_matter
from .temp_worktree import TempWorktreeError, create_temp_worktree, remove_temp_worktree

logger = get_logger(__name__)


class PlanCommandError(Exception):
    """Raised when plan command operations fail."""




def _find_repo_root() -> Path:
    """Find the Git repository root from the current working directory.

    Returns:
        Path to the Git repository root.

    Raises:
        PlanCommandError: If not in a Git repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return Path(result.stdout.strip()).resolve()
    except subprocess.CalledProcessError as exc:
        raise PlanCommandError(
            "Must be run from within a Git repository."
        ) from exc


def _load_template(tool: str) -> str:
    """Load the prompt template for the specified tool.

    Args:
        tool: Name of the tool (e.g., "droid").

    Returns:
        Template content as a string.

    Raises:
        PlanCommandError: If the template file cannot be loaded.
    """
    try:
        src_dir = get_lw_coder_src_dir()
    except RuntimeError as exc:
        raise PlanCommandError(str(exc)) from exc

    template_path = src_dir / "prompts" / tool / "plan.md"

    if not template_path.exists():
        raise PlanCommandError(
            f"Prompt template not found for tool '{tool}' at {template_path}"
        )

    logger.debug("Loading template from %s", template_path)
    return template_path.read_text(encoding="utf-8")


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
        _, body = _extract_front_matter(content)
        return body.strip()
    except (PlanValidationError, ValueError, KeyError, TypeError):
        # If no front matter or parsing fails, use the whole content
        return content.strip()




def run_plan_command(plan_path: Path | None, text_input: str | None, tool: str) -> int:
    """Execute the plan command.

    Args:
        plan_path: Optional path to a markdown file with plan idea.
        text_input: Optional direct text input for the plan idea.
        tool: Name of the coding tool to use (default: "droid").

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    temp_worktree = None
    repo_root = None
    prompt_file = None

    try:
        # Pre-flight check for authentication
        check_droid_auth()

        # Find repository root
        repo_root = _find_repo_root()
        logger.debug("Repository root: %s", repo_root)

        # Extract idea text
        idea_text = _extract_idea_text(plan_path, text_input)

        # Load template
        template = _load_template(tool)

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

        # Get lw_coder source directory
        try:
            lw_coder_src = get_lw_coder_src_dir()
        except RuntimeError as exc:
            raise PlanCommandError(str(exc)) from exc

        # Prepare paths for host configuration
        tasks_dir = repo_root / ".lw_coder" / "tasks"
        droids_dir = lw_coder_src / "droids"
        host_factory_dir = Path.home() / ".factory"
        auth_file = host_factory_dir / "auth.json"
        settings_file = lw_coder_src / "container_settings.json"
        git_dir = repo_root / ".git"

        logger.info("Starting %s session...", tool)
        logger.info("Plans will be saved to .lw_coder/tasks/<plan_id>.md")
        logger.info("Processing plan with %s...", tool)

        # Run droid session on host (interactive mode)
        # Prepare droid command with properly escaped paths to prevent shell injection
        prompt_path_escaped = shlex.quote(str(prompt_file))
        droid_command = f'droid "$(cat {prompt_path_escaped})"'

        runner_config = host_runner_config(
            worktree_path=temp_worktree,
            repo_git_dir=git_dir,
            tasks_dir=tasks_dir,
            droids_dir=droids_dir,
            auth_file=auth_file,
            settings_file=settings_file,
            command=droid_command,
            host_factory_dir=host_factory_dir,
        )

        # Build host command
        host_cmd, host_env = build_host_command(runner_config)

        # Run droid interactively on the host
        try:
            result = subprocess.run(
                host_cmd,
                check=False,
                env=host_env,
                cwd=temp_worktree,
            )

            try:
                _ensure_placeholder_git_sha(tasks_dir)
            except PlanLifecycleError as exc:
                logger.warning("Failed to normalize plan git_sha placeholder: %s", exc)

            return result.returncode
        except KeyboardInterrupt:
            logger.info("Session interrupted by user.")
            return 0

    except (DroidAuthError, PlanCommandError, TempWorktreeError) as exc:
        logger.error("%s", exc)
        return 1

    finally:
        # Clean up prompt file
        if prompt_file and prompt_file.exists():
            try:
                prompt_file.unlink()
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
            front_matter, _ = _extract_front_matter(content)
        except PlanValidationError:
            continue

        git_sha = front_matter.get("git_sha")
        status = front_matter.get("status", "").strip().lower() if isinstance(front_matter.get("status"), str) else ""

        if status != "draft" or not isinstance(git_sha, str):
            continue

        if git_sha == PLACEHOLDER_SHA:
            continue

        update_plan_fields(plan_file, {"git_sha": PLACEHOLDER_SHA})
