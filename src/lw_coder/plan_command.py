"""Implementation of the plan command for interactive plan development."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .droid_auth import DroidAuthError, check_droid_auth
from .droid_session import (
    DroidSessionConfig,
    build_docker_command,
    get_lw_coder_src_dir,
    patched_worktree_gitdir,
)
from .logging_config import get_logger
from .plan_validator import _extract_front_matter
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
    except Exception:
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
    import tempfile

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

        # Make prompt file readable by the container user
        os.chmod(prompt_file, 0o644)

        # Create temporary worktree
        temp_worktree = create_temp_worktree(repo_root)

        # Get lw_coder source directory
        try:
            lw_coder_src = get_lw_coder_src_dir()
        except RuntimeError as exc:
            raise PlanCommandError(str(exc)) from exc

        # Prepare paths for Docker configuration
        tasks_dir = repo_root / ".lw_coder" / "tasks"
        droids_dir = lw_coder_src / "droids"
        auth_file = Path.home() / ".factory" / "auth.json"
        container_settings_file = lw_coder_src / "container_settings.json"
        git_dir = repo_root / ".git"

        logger.info("Starting interactive %s session...", tool)
        logger.info("Plans will be saved to .lw_coder/tasks/<plan_id>.md")
        logger.info("Exit %s (type 'exit' or press Ctrl+C) when finished.", tool)

        # Patch worktree .git file and run Docker with the patched configuration
        with patched_worktree_gitdir(temp_worktree, git_dir) as worktree_name:
            # Build Docker configuration
            config = DroidSessionConfig(
                worktree_path=temp_worktree,
                repo_git_dir=git_dir,
                tasks_dir=tasks_dir,
                droids_dir=droids_dir,
                auth_file=auth_file,
                settings_file=container_settings_file,
                prompt_file=prompt_file,
                image_tag="lw_coder_droid:latest",
                worktree_name=worktree_name,
                command='droid "$(cat /tmp/prompt.txt)"',
            )

            # Build Docker command
            docker_cmd = build_docker_command(config)

            # Run Docker interactively
            try:
                result = subprocess.run(docker_cmd, check=False)
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
