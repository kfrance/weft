"""Implementation of the plan command for interactive plan development."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .droid_auth import DroidAuthError, check_droid_auth
from .logging_config import get_logger
from .plan_validator import _extract_front_matter
from .temp_worktree import TempWorktreeError, create_temp_worktree, remove_temp_worktree

logger = get_logger(__name__)


class PlanCommandError(Exception):
    """Raised when plan command operations fail."""


def _get_lw_coder_src_dir() -> Path:
    """Get the lw_coder source directory (where prompts and droids are located).

    Returns:
        Path to the lw_coder source directory.

    Raises:
        PlanCommandError: If the source directory cannot be determined.
    """
    # The source directory is where this module is located
    return Path(__file__).parent


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
    src_dir = _get_lw_coder_src_dir()
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


def _build_docker_command(
    temp_worktree: Path,
    repo_root: Path,
    prompt_file: Path,
) -> list[str]:
    """Build the Docker command to run droid interactively.

    Args:
        temp_worktree: Path to the temporary worktree.
        repo_root: Path to the Git repository root.
        prompt_file: Path to the file containing the prompt.

    Returns:
        List of command arguments for subprocess.
    """
    lw_coder_src = _get_lw_coder_src_dir()
    tasks_dir = repo_root / ".lw_coder" / "tasks"
    droids_dir = lw_coder_src / "droids"
    auth_file = Path.home() / ".factory" / "auth.json"
    container_settings_file = lw_coder_src / "container_settings.json"
    git_dir = repo_root / ".git"

    # Ensure tasks directory exists
    tasks_dir.mkdir(parents=True, exist_ok=True)

    # Fix worktree's .git file to point to mounted git directory
    # Read the current gitdir path
    worktree_git_file = temp_worktree / ".git"
    original_gitdir = worktree_git_file.read_text().strip()
    # Extract worktree name (e.g., "temp-20251007_142615_613903-6f72d984")
    worktree_name = original_gitdir.split("/")[-1]
    # Write new gitdir pointing to container path
    worktree_git_file.write_text(f"gitdir: /repo-git/worktrees/{worktree_name}\n")

    cmd = [
        "docker", "run", "-it", "--rm",
        "--security-opt=no-new-privileges",
        "-v", f"{temp_worktree}:/workspace",
        "-v", f"{git_dir}:/repo-git:ro",
        "-v", f"{tasks_dir}:/output",
        "-v", f"{droids_dir}:/home/droiduser/.factory/droids:ro",
        "-v", f"{auth_file}:/home/droiduser/.factory/auth.json:ro",
        "-v", f"{container_settings_file}:/home/droiduser/.factory/settings.json:ro",
        "-v", f"{prompt_file}:/tmp/prompt.txt:ro",
        "-w", "/workspace",
        "lw_coder_droid:latest",
        "bash", "-c", "droid \"$(cat /tmp/prompt.txt)\"",
    ]

    return cmd


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

        # Build Docker command
        docker_cmd = _build_docker_command(temp_worktree, repo_root, prompt_file)

        logger.info("Starting interactive %s session...", tool)
        logger.info("Plans will be saved to .lw_coder/tasks/<plan_id>.md")
        logger.info("Exit %s (type 'exit' or press Ctrl+C) when finished.", tool)

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
