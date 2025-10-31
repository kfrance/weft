"""Repository and filesystem utilities for lw_coder commands."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


class RepoUtilsError(Exception):
    """Raised when repository or filesystem operations fail."""


def find_repo_root(start_path: Path | None = None) -> Path:
    """Find the Git repository root directory.

    Args:
        start_path: Starting directory or file path. If a file path is provided,
            its parent directory is used. If None, uses the current working directory.

    Returns:
        Path to the Git repository root (resolved to absolute path).

    Raises:
        RepoUtilsError: If not in a Git repository or path doesn't exist.
    """
    if start_path is None:
        # Use current working directory
        cmd = ["git", "rev-parse", "--show-toplevel"]
    else:
        # Check if path exists
        if not start_path.exists():
            raise RepoUtilsError(f"Path does not exist: {start_path}")

        # If start_path is a file, use its parent directory
        directory = start_path.parent if start_path.is_file() else start_path
        cmd = ["git", "-C", str(directory), "rev-parse", "--show-toplevel"]

    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return Path(result.stdout.strip()).resolve()
    except subprocess.CalledProcessError as exc:
        raise RepoUtilsError("Must be run from within a Git repository.") from exc


def load_prompt_template(tool: str, template_name: str) -> str:
    """Load a prompt template for the specified tool and template name.

    Args:
        tool: Tool name (e.g., "claude-code", "droid").
        template_name: Template name (e.g., "plan", "code", "finalize").

    Returns:
        Template content as a string.

    Raises:
        RepoUtilsError: If the template file cannot be loaded.
    """
    from .host_runner import get_lw_coder_src_dir

    try:
        src_dir = get_lw_coder_src_dir()
    except RuntimeError as exc:
        raise RepoUtilsError(f"Failed to locate source directory: {exc}") from exc

    template_path = src_dir / "prompts" / tool / f"{template_name}.md"

    if not template_path.exists():
        raise RepoUtilsError(
            f"Prompt template not found for tool '{tool}' at {template_path}"
        )

    logger.debug("Loading template from %s", template_path)
    return template_path.read_text(encoding="utf-8")


def verify_branch_merged_to_main(
    repo_root: Path, branch_name: str
) -> bool:
    """Verify that a branch was successfully merged into main.

    Checks if the branch's tip commit is an ancestor of main's HEAD,
    which confirms the branch was merged (via fast-forward or otherwise).

    Args:
        repo_root: Repository root directory.
        branch_name: Name of the branch to check.

    Returns:
        True if the branch was merged into main, False otherwise.

    Raises:
        RepoUtilsError: If git commands fail.
    """
    try:
        # Check if branch tip is an ancestor of main's HEAD
        # Exit code 0 means it is an ancestor (merged), 1 means it's not
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", branch_name, "main"],
            cwd=repo_root,
            check=False,  # Don't raise on non-zero exit
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode == 0:
            logger.debug(
                "Branch '%s' was successfully merged into main",
                branch_name,
            )
            return True
        elif result.returncode == 1:
            logger.warning(
                "Branch '%s' was not merged into main",
                branch_name,
            )
            return False
        else:
            # Unexpected error
            raise RepoUtilsError(
                f"Failed to verify merge for branch '{branch_name}': {result.stderr}"
            )

    except subprocess.CalledProcessError as exc:
        raise RepoUtilsError(
            f"Failed to verify merge for branch '{branch_name}': {exc.stderr}"
        ) from exc
