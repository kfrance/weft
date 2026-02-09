"""Implementation of the explore command for open-ended exploration sessions.

Provides isolated sandbox environments for investigating bugs, brainstorming
solutions, evaluating architectural options, or prototyping ideas. Explorations
produce optional findings artifacts stored in git refs.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .executors import ExecutorError, ExecutorRegistry
from .exploration_store import (
    ExplorationExistsError,
    ExplorationStoreError,
    save_exploration,
)
from .headless import is_headless
from .host_runner import build_host_command, host_runner_config
from .logging_config import get_logger
from .param_validation import get_effective_model
from .plan_validator import _PLAN_ID_PATTERN
from .repo_utils import RepoUtilsError, find_repo_root, load_prompt_template
from .sandbox import SandboxConfigError, SandboxDependencyError, get_disallowed_tools_args, load_sandbox_config
from .temp_worktree import TempWorktreeError, create_temp_worktree, remove_temp_worktree
from .worktree.file_sync import (
    FileSyncError,
    WorktreeFileCleanup,
    load_repo_config,
    should_sync_for_command,
    sync_files_to_worktree,
    validate_worktree_file_sync_config,
)

logger = get_logger(__name__)

_DEFAULT_TOPIC = "Open-ended exploration. The user will guide the session interactively."
_ARTIFACT_FILENAME = ".exploration_artifact.md"
_FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n?(.*)$",
    re.DOTALL,
)
_NAME_PATTERN = re.compile(r"^name:\s*(.+)$", re.MULTILINE)


class ExploreCommandError(Exception):
    """Raised when explore command operations fail."""


def _parse_artifact(content: str) -> tuple[str, str]:
    """Parse exploration artifact file into (name, findings_body).

    Args:
        content: Raw content of .exploration_artifact.md.

    Returns:
        Tuple of (name, findings_body) where findings_body is everything
        after the frontmatter.

    Raises:
        ExploreCommandError: If artifact format is invalid.
    """
    match = _FRONTMATTER_PATTERN.match(content)
    if not match:
        raise ExploreCommandError(
            "Artifact file has invalid format. Expected YAML frontmatter "
            "delimited by --- markers."
        )

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    # Extract name from frontmatter
    name_match = _NAME_PATTERN.search(frontmatter_text)
    if not name_match:
        raise ExploreCommandError(
            "Artifact frontmatter is missing 'name' field. "
            "Expected format:\n---\nname: <exploration-name>\n---"
        )

    name = name_match.group(1).strip()

    # Validate name
    if not _PLAN_ID_PATTERN.fullmatch(name):
        raise ExploreCommandError(
            f"Invalid exploration name '{name}'. Names must match pattern "
            "^[a-zA-Z0-9._-]{3,100}$ (3-100 chars, alphanumeric/._- only)."
        )

    if not body:
        raise ExploreCommandError(
            "Artifact has empty findings body. Expected content after frontmatter."
        )

    return name, body


def run_explore_command(
    text: str | None = None,
    tool: str = "claude-code",
    model: str | None = None,
    no_hooks: bool = False,
) -> int:
    """Execute the explore command.

    Args:
        text: Optional topic text for the exploration.
        tool: Name of the coding tool to use (default: "claude-code").
        model: Model variant to use.
        no_hooks: If True, disable execution of configured hooks.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    temp_worktree = None
    repo_root = None
    prompt_file = None
    file_sync_cleanup: WorktreeFileCleanup | None = None

    try:
        # Get the executor for the specified tool
        try:
            executor = ExecutorRegistry.get_executor(tool)
        except ExecutorError as exc:
            raise ExploreCommandError(str(exc)) from exc

        # Pre-flight check for executor-specific authentication
        try:
            executor.check_auth()
        except ExecutorError as exc:
            raise ExploreCommandError(str(exc)) from exc

        # Find repository root
        repo_root = find_repo_root()
        logger.debug("Repository root: %s", repo_root)

        # Load explore prompt template and inject topic text
        template = load_prompt_template(tool, "explore")
        topic_text = text if text else _DEFAULT_TOPIC
        combined_prompt = template.replace("{TOPIC_TEXT}", topic_text)

        # Write prompt to /tmp/claude which is bind-mounted into the sandbox
        prompt_dir = Path("/tmp/claude/weft")
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = prompt_dir / f"explore-{os.getpid()}.txt"
        prompt_file.write_text(combined_prompt, encoding="utf-8")
        os.chmod(prompt_file, 0o600)

        # Create temporary worktree
        temp_worktree = create_temp_worktree(repo_root)
        logger.info("Created exploration worktree: %s", temp_worktree)

        # Sync files from repo to worktree based on .weft/config.toml
        try:
            repo_config = load_repo_config(repo_root)
            sync_config = validate_worktree_file_sync_config(repo_config)
            if should_sync_for_command(sync_config, "explore"):
                file_sync_cleanup = WorktreeFileCleanup()
                sync_files_to_worktree(repo_root, temp_worktree, file_sync_cleanup)
            else:
                logger.debug("File sync skipped: 'explore' not in commands list")
        except FileSyncError as exc:
            logger.error("File sync failed: %s", exc)
            return 1

        # Load sandbox configuration from .weft/config.toml
        config_path = repo_root / ".weft" / "config.toml"
        try:
            sandbox_config = load_sandbox_config(config_path)
        except SandboxConfigError as exc:
            raise ExploreCommandError(f"Failed to load sandbox configuration: {exc}") from exc

        # Build command using the executor
        effective_model = get_effective_model(model, "explore")
        command = executor.build_command(
            prompt_file,
            model=effective_model,
            headless=is_headless(),
            skip_permissions=True,
            disallowed_tools=get_disallowed_tools_args(sandbox_config),
        )

        # Prepare paths for host configuration
        tasks_dir = repo_root / ".weft" / "tasks"
        host_factory_dir = Path.home() / ".factory"
        git_dir = repo_root / ".git"

        # Get executor-specific environment variables
        executor_env_vars = executor.get_env_vars(host_factory_dir)

        runner_config = host_runner_config(
            worktree_path=temp_worktree,
            repo_git_dir=git_dir,
            tasks_dir=tasks_dir,
            command=command,
            host_factory_dir=host_factory_dir,
            env_vars=executor_env_vars,
            sandbox_config=sandbox_config,
        )

        # Build host command
        host_cmd, host_env = build_host_command(runner_config)

        logger.info("Starting exploration session...")

        # Run executor interactively (single-phase, like weft plan)
        try:
            subprocess.run(
                host_cmd,
                check=False,
                env=host_env,
                cwd=temp_worktree,
            )

            # Post-session: check for exploration artifact
            artifact_path = temp_worktree / _ARTIFACT_FILENAME
            if artifact_path.exists():
                return _handle_findings(repo_root, temp_worktree, artifact_path)
            else:
                return _handle_no_findings(repo_root, temp_worktree)

        except KeyboardInterrupt:
            logger.info("Exploration session interrupted by user.")
            # Check for artifact even on interrupt
            artifact_path = temp_worktree / _ARTIFACT_FILENAME
            if artifact_path.exists():
                return _handle_findings(repo_root, temp_worktree, artifact_path)
            return 0

    except (ExecutorError, ExploreCommandError, TempWorktreeError, RepoUtilsError, SandboxDependencyError) as exc:
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


def _handle_findings(repo_root: Path, worktree_path: Path, artifact_path: Path) -> int:
    """Handle post-session when findings artifact exists.

    Args:
        repo_root: Repository root directory.
        worktree_path: Path to the exploration worktree.
        artifact_path: Path to the .exploration_artifact.md file.

    Returns:
        Exit code.
    """
    try:
        content = artifact_path.read_text(encoding="utf-8")
        name, body = _parse_artifact(content)
    except (OSError, ExploreCommandError) as exc:
        logger.error("Failed to process exploration artifact: %s", exc)
        print(  # noqa: T201
            f"\nFailed to process exploration artifact: {exc}\n"
            f"Worktree preserved at: {worktree_path}\n"
        )
        return 1

    # Save exploration to git ref
    try:
        save_exploration(repo_root, name, body)
    except ExplorationExistsError:
        logger.error("Exploration '%s' already exists.", name)
        print(  # noqa: T201
            f"\nExploration '{name}' already exists.\n"
            f"Worktree preserved at: {worktree_path}\n"
            f"Edit {artifact_path} and choose a different name, then re-run.\n"
        )
        return 1
    except ExplorationStoreError as exc:
        logger.error("Failed to save exploration: %s", exc)
        print(  # noqa: T201
            f"\nFailed to save exploration: {exc}\n"
            f"Worktree preserved at: {worktree_path}\n"
        )
        return 1

    # Print success message with next steps
    print(  # noqa: T201
        f"\nExploration saved: {name}\n"
        f"\nNext steps:\n"
        f"  weft plan {name}    # Design a detailed plan\n"
        f"  weft code {name}    # Implement directly\n"
    )

    # Worktree is NOT cleaned up (persists for potential revisiting)
    return 0


def _handle_no_findings(repo_root: Path, worktree_path: Path) -> int:
    """Handle post-session when no findings artifact exists.

    Args:
        repo_root: Repository root directory.
        worktree_path: Path to the exploration worktree.

    Returns:
        Exit code.
    """
    print("\nNo findings were saved.", end=" ")  # noqa: T201
    try:
        response = input("Delete the worktree? (y/n) ").strip().lower()
    except EOFError:
        # Ctrl+D: treat as "no" (preserve worktree)
        response = "n"
        print()  # noqa: T201

    if response in ("y", "yes"):
        try:
            remove_temp_worktree(repo_root, worktree_path)
            logger.info("Cleaned up exploration worktree: %s", worktree_path)
        except TempWorktreeError as exc:
            logger.warning("Failed to clean up worktree: %s", exc)
            print(f"Warning: Failed to clean up worktree: {exc}")  # noqa: T201
    else:
        print(f"Worktree preserved at: {worktree_path}")  # noqa: T201

    return 0
