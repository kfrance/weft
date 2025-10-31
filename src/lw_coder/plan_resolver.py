"""Plan path resolution utilities.

This module provides centralized logic for resolving plan paths from various inputs:
- Plan IDs (e.g., "fix-subagent" -> ".lw_coder/tasks/fix-subagent.md")
- Full paths (e.g., ".lw_coder/tasks/fix-subagent.md" -> unchanged)
- Relative/absolute paths (e.g., "../tasks/plan.md" -> resolved)

This ensures consistent behavior between CLI argument parsing and completion.
"""

from __future__ import annotations

from pathlib import Path

from .logging_config import get_logger
from .repo_utils import RepoUtilsError, find_repo_root

logger = get_logger(__name__)


class PlanResolver:
    """Resolves plan paths from user input."""

    @staticmethod
    def resolve(user_input: str | Path, cwd: Path | None = None) -> Path:
        """Resolve a plan path from user input.

        Handles three types of input:
        1. Plan ID (e.g., "fix-subagent") -> searches .lw_coder/tasks/<plan_id>.md
        2. Full/relative path (e.g., ".lw_coder/tasks/plan.md") -> resolves to absolute
        3. Absolute path -> validates and returns as-is

        Args:
            user_input: Plan ID or path provided by user.
            cwd: Current working directory (defaults to Path.cwd()).

        Returns:
            Absolute Path to the plan file.

        Raises:
            FileNotFoundError: If the plan file cannot be found.
        """
        if cwd is None:
            cwd = Path.cwd()

        # Convert to Path if needed
        input_path = Path(user_input) if isinstance(user_input, str) else user_input

        # Case 1: Absolute path
        if input_path.is_absolute():
            if not input_path.exists():
                raise FileNotFoundError(
                    f"Plan file not found: {input_path}\n"
                    f"Tip: Check the path and ensure the file exists."
                )
            return input_path.resolve()

        # Case 2: Path with directory separators (relative path)
        if "/" in str(user_input) or "\\" in str(user_input):
            resolved = (cwd / input_path).resolve()
            if not resolved.exists():
                raise FileNotFoundError(
                    f"Plan file not found: {resolved}\n"
                    f"Searched from current directory: {cwd}\n"
                    f"Tip: Check the path and ensure the file exists."
                )
            return resolved

        # Case 3: Plan ID - search in .lw_coder/tasks/
        try:
            repo_root = find_repo_root(cwd)
        except RepoUtilsError as exc:
            raise FileNotFoundError(
                f"Cannot resolve plan ID '{user_input}': not in a git repository.\n"
                f"Tip: Run this command from within a git repository or provide a full path."
            ) from exc

        tasks_dir = repo_root / ".lw_coder" / "tasks"
        plan_path = tasks_dir / f"{user_input}.md"

        if not plan_path.exists():
            raise FileNotFoundError(
                f"Plan file not found: {plan_path}\n"
                f"Searched for plan ID '{user_input}' in {tasks_dir}\n"
                f"Tip: Use 'ls {tasks_dir}' to see available plans."
            )

        return plan_path.resolve()
