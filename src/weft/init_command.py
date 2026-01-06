"""Initialize weft in a git repository with frozen baseline templates.

This module provides the init command which bootstraps new projects with
judges and optimized prompts from the frozen baseline templates bundled
with weft.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from .logging_config import get_logger
from .repo_utils import RepoUtilsError, find_repo_root

logger = get_logger(__name__)


class InitCommandError(Exception):
    """Raised when init command operations fail."""


def get_templates_dir() -> Path:
    """Get the path to the bundled init_templates directory.

    Returns:
        Path to the init_templates directory.

    Raises:
        InitCommandError: If the templates directory cannot be found.
    """
    # Get the directory containing this module
    module_dir = Path(__file__).parent
    templates_dir = module_dir / "init_templates"

    if not templates_dir.exists():
        raise InitCommandError(
            f"Templates directory not found at {templates_dir}. "
            "This may indicate a corrupted installation."
        )

    return templates_dir


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of a file.

    Args:
        file_path: Path to the file.

    Returns:
        Hash string in format "sha256:hexdigest".
    """
    sha256_hash = hashlib.sha256()
    sha256_hash.update(file_path.read_bytes())
    return f"sha256:{sha256_hash.hexdigest()}"


def load_version_file(path: Path) -> dict:
    """Load and parse a VERSION JSON file.

    Args:
        path: Path to the VERSION file.

    Returns:
        Parsed VERSION data as a dictionary.

    Raises:
        InitCommandError: If the file cannot be read or parsed.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise InitCommandError(f"Failed to read VERSION file at {path}: {exc}") from exc


def detect_customizations(
    weft_dir: Path, version_data: dict, category: str
) -> list[str]:
    """Detect which files have been customized from their baseline hashes.

    Args:
        weft_dir: Path to the .weft directory.
        version_data: Parsed VERSION file data containing file hashes.
        category: Category to check ("judges" or "optimized_prompts").

    Returns:
        List of relative file paths that have been modified from baseline.
    """
    customized = []
    files_data = version_data.get("files", {})

    for rel_path, file_info in files_data.items():
        # Filter to the requested category
        if not rel_path.startswith(category):
            continue

        file_path = weft_dir / rel_path
        if not file_path.exists():
            # File was deleted - consider this a customization
            customized.append(rel_path)
            continue

        expected_hash = file_info.get("hash", "")
        try:
            current_hash = calculate_file_hash(file_path)
            if current_hash != expected_hash:
                customized.append(rel_path)
        except OSError as exc:
            logger.debug("Cannot read file %s for customization check: %s", file_path, exc)
            continue

    return customized


def display_customization_warnings(customized_files: list[str], category: str) -> None:
    """Display warnings about customized files.

    Args:
        customized_files: List of customized file paths.
        category: Category name for display ("judges" or "prompts").
    """
    if not customized_files:
        return

    print(f"WARNING: {len(customized_files)} {category} have been customized from baseline:")
    for file_path in customized_files:
        print(f"  - {file_path}")


def prompt_yes_no(message: str, skip_prompts: bool = False) -> bool:
    """Prompt the user for yes/no confirmation.

    Args:
        message: The prompt message to display.
        skip_prompts: If True, return True without prompting.

    Returns:
        True for yes, False for no.
    """
    if skip_prompts:
        return True

    while True:
        try:
            response = input(f"{message} (y/n): ").strip().lower()
            if response in ("y", "yes"):
                return True
            if response in ("n", "no"):
                return False
            print("Please enter 'y' or 'n'.")
        except EOFError:
            # Non-interactive environment
            return False


# Gitignore marker and entries for weft cache directories
_GITIGNORE_MARKER = "# weft cache"
_GITIGNORE_ENTRIES = """
# weft cache and temporary files
.weft/dspy_cache/
.weft/worktrees/
.weft/runs/
.weft/plan-traces/
"""


def update_gitignore(project_root: Path) -> None:
    """Add weft cache directories to .gitignore.

    Args:
        project_root: Path to the project root directory.

    Note:
        - If .gitignore exists and already contains the marker, no changes are made.
        - If .gitignore exists without marker, entries are appended.
        - If .gitignore doesn't exist, it is created with the entries.
    """
    gitignore_path = project_root / ".gitignore"

    if gitignore_path.exists():
        try:
            content = gitignore_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read .gitignore: %s", exc)
            return

        # Check if already present
        if _GITIGNORE_MARKER in content:
            logger.debug(".gitignore already contains weft cache entries")
            return

        # Append to existing .gitignore
        try:
            gitignore_path.write_text(
                content.rstrip() + "\n" + _GITIGNORE_ENTRIES, encoding="utf-8"
            )
            logger.info("Added weft cache entries to .gitignore")
        except OSError as exc:
            logger.warning("Failed to update .gitignore: %s", exc)
    else:
        # Create new .gitignore
        try:
            gitignore_path.write_text(_GITIGNORE_ENTRIES.lstrip(), encoding="utf-8")
            logger.info("Created .gitignore with weft cache entries")
        except OSError as exc:
            logger.warning("Failed to create .gitignore: %s", exc)


# Template content for .weft/config.toml
_CONFIG_TEMPLATE = '''# weft repository configuration
# See docs/configuration.md for detailed documentation
schema_version = "1.0"

# Worktree file synchronization
# Copies untracked files (e.g., .env, config files) from the main repository
# to temporary worktrees when the `code` command runs.
#
# [worktree.file_sync]
# enabled = true
# patterns = [
#     ".env",           # Environment variables file
#     ".env.*",         # Environment-specific files (.env.local, .env.test)
#     "config/*.json",  # Configuration files in config directory
# ]
# max_file_size_mb = 100   # Maximum size per file (default: 100MB)
# max_total_size_mb = 500  # Maximum total size (default: 500MB)

# Setup commands run on the host before the coding session (optional)
# Commands execute sequentially after worktree creation.
# Available environment variables: WEFT_REPO_ROOT, WEFT_WORKTREE_PATH, WEFT_PLAN_ID, WEFT_PLAN_PATH
#
# [[code.setup]]
# name = "start-services"
# command = "docker-compose up -d"
# working_dir = "./services"        # Optional: defaults to repo root
# continue_on_failure = false       # Optional: defaults to false
'''


def create_config_template(weft_dir: Path) -> None:
    """Create template .weft/config.toml if it doesn't exist.

    Args:
        weft_dir: Path to the .weft directory.

    Note:
        - If config.toml already exists, no changes are made.
        - Creates parent directories if needed.
        - Logs info on creation, debug if already exists.
    """
    config_path = weft_dir / "config.toml"

    if config_path.exists():
        logger.debug("config.toml already exists at %s", config_path)
        return

    try:
        # Ensure .weft directory exists
        weft_dir.mkdir(parents=True, exist_ok=True)

        config_path.write_text(_CONFIG_TEMPLATE, encoding="utf-8")
        logger.info("Created config template at %s", config_path)
    except OSError as exc:
        logger.warning("Failed to create config template: %s", exc)


class AtomicInitializer:
    """Context manager for atomic initialization with rollback on failure.

    Copies templates to a staging directory first, then atomically moves
    them to the target location. On failure, cleans up the staging directory
    and leaves the filesystem in its original state.
    """

    def __init__(self, target_dir: Path, templates_dir: Path):
        """Initialize the atomic initializer.

        Args:
            target_dir: The target .weft directory.
            templates_dir: The source init_templates directory.
        """
        self.target_dir = target_dir
        self.templates_dir = templates_dir
        self.staging_dir: Path | None = None
        self._created_target = False
        self._created_subdirs: list[Path] = []
        self._committed_paths: list[Path] = []  # Track paths written during commit

    def __enter__(self) -> "AtomicInitializer":
        """Set up staging directory."""
        self.staging_dir = Path(tempfile.mkdtemp(prefix="weft_init_"))
        logger.debug("Created staging directory: %s", self.staging_dir)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Clean up on failure, commit on success."""
        if exc_type is not None:
            # Exception occurred - rollback
            logger.debug("Rolling back initialization due to error")
            self._rollback()
            return False
        return False

    def _rollback(self) -> None:
        """Roll back all changes made during initialization."""
        # Clean up staging directory
        if self.staging_dir and self.staging_dir.exists():
            try:
                shutil.rmtree(self.staging_dir)
                logger.debug("Cleaned up staging directory")
            except OSError as exc:
                logger.warning("Failed to clean up staging directory: %s", exc)

        # Remove committed paths (in reverse order - files before directories)
        for path in reversed(self._committed_paths):
            try:
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                        logger.debug("Removed committed directory: %s", path)
                    else:
                        path.unlink()
                        logger.debug("Removed committed file: %s", path)
            except OSError as exc:
                logger.debug("Failed to remove committed path %s: %s", path, exc)

        # Remove created subdirectories (in reverse order)
        for subdir in reversed(self._created_subdirs):
            try:
                if subdir.exists() and not any(subdir.iterdir()):
                    subdir.rmdir()
                    logger.debug("Removed empty directory: %s", subdir)
            except OSError:
                pass

        # Remove target directory if we created it and it's empty
        if self._created_target and self.target_dir.exists():
            try:
                if not any(self.target_dir.iterdir()):
                    self.target_dir.rmdir()
                    logger.debug("Removed target directory: %s", self.target_dir)
            except OSError:
                pass

    def copy_judges(self) -> None:
        """Copy judges from templates to staging directory."""
        source = self.templates_dir / "judges"
        if not source.exists():
            raise InitCommandError("Judges directory not found in templates")

        dest = self.staging_dir / "judges"
        try:
            shutil.copytree(source, dest)
            logger.debug("Copied judges to staging")
        except (OSError, shutil.Error) as exc:
            raise InitCommandError(f"Failed to copy judges: {exc}") from exc

    def copy_optimized_prompts(self) -> None:
        """Copy prompts from templates to staging directory."""
        source = self.templates_dir / "prompts"
        if not source.exists():
            raise InitCommandError("Prompts directory not found in templates")

        dest = self.staging_dir / "prompts" / "active"
        try:
            shutil.copytree(source, dest)
            logger.debug("Copied prompts/active to staging")
        except (OSError, shutil.Error) as exc:
            raise InitCommandError(f"Failed to copy optimized prompts: {exc}") from exc

    def copy_version_file(self) -> None:
        """Copy VERSION file from templates to staging directory."""
        source = self.templates_dir / "VERSION"
        if not source.exists():
            raise InitCommandError("VERSION file not found in templates")

        dest = self.staging_dir / "VERSION"
        try:
            shutil.copy2(source, dest)
            logger.debug("Copied VERSION to staging")
        except (OSError, shutil.Error) as exc:
            raise InitCommandError(f"Failed to copy VERSION file: {exc}") from exc

    def commit_to_target(
        self, overwrite_judges: bool = True, overwrite_prompts: bool = True
    ) -> None:
        """Move staged files to target directory.

        Args:
            overwrite_judges: Whether to copy judges to target.
            overwrite_prompts: Whether to copy prompts to target.
        """
        # Create target directory if it doesn't exist
        if not self.target_dir.exists():
            self.target_dir.mkdir(parents=True)
            self._created_target = True
            logger.debug("Created target directory: %s", self.target_dir)

        # Copy judges if requested
        if overwrite_judges:
            source = self.staging_dir / "judges"
            dest = self.target_dir / "judges"
            if source.exists():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(source, dest)
                self._committed_paths.append(dest)
                if not self._created_target:
                    self._created_subdirs.append(dest)
                logger.info("Copied judges to %s", dest)

        # Copy prompts if requested (to new prompts/active location)
        if overwrite_prompts:
            source = self.staging_dir / "prompts" / "active"
            dest = self.target_dir / "prompts" / "active"
            if source.exists():
                # Create prompts parent directory if needed
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(source, dest)
                self._committed_paths.append(dest)
                if not self._created_target:
                    self._created_subdirs.append(dest)
                logger.info("Copied prompts to %s", dest)

                # Also remove old optimized_prompts if it exists (cleanup migration)
                old_dest = self.target_dir / "optimized_prompts"
                if old_dest.exists():
                    shutil.rmtree(old_dest)
                    logger.info("Removed old optimized_prompts directory")

        # Only copy VERSION file if at least one category is being overwritten
        # Otherwise, the VERSION hashes won't match the user's kept files
        if overwrite_judges or overwrite_prompts:
            source = self.staging_dir / "VERSION"
            dest = self.target_dir / "VERSION"
            if source.exists():
                shutil.copy2(source, dest)
                self._committed_paths.append(dest)
                logger.info("Copied VERSION to %s", dest)

        # Clean up staging directory
        if self.staging_dir and self.staging_dir.exists():
            try:
                shutil.rmtree(self.staging_dir)
                logger.debug("Cleaned up staging directory")
            except OSError as exc:
                logger.warning("Failed to clean up staging directory: %s", exc)


def run_init_command(force: bool = False, yes: bool = False) -> int:
    """Execute the init command to initialize weft in a git repository.

    Args:
        force: Allow initialization when .weft already exists.
        yes: Skip interactive prompts (for CI/CD automation).

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    try:
        # Find repository root
        try:
            repo_root = find_repo_root()
        except RepoUtilsError as exc:
            logger.error("%s", exc)
            logger.error("Suggestion: Run 'git init' to create a repository.")
            return 1

        logger.debug("Repository root: %s", repo_root)

        # Get templates directory
        templates_dir = get_templates_dir()
        logger.debug("Templates directory: %s", templates_dir)

        # Check if .weft already exists
        weft_dir = repo_root / ".weft"

        if weft_dir.exists() and not force:
            logger.error(
                "Directory .weft already exists at %s. "
                "Use --force to reinitialize.",
                weft_dir,
            )
            return 1

        # Determine what to copy
        overwrite_judges = True
        overwrite_prompts = True

        if weft_dir.exists() and force:
            # Load VERSION to detect customizations
            version_path = weft_dir / "VERSION"
            if version_path.exists():
                try:
                    version_data = load_version_file(version_path)

                    # Check for customized judges
                    customized_judges = detect_customizations(
                        weft_dir, version_data, "judges"
                    )
                    if customized_judges:
                        display_customization_warnings(customized_judges, "judges")
                    overwrite_judges = prompt_yes_no(
                        "Overwrite existing judges?", skip_prompts=yes
                    )

                    # Check for customized prompts (check both old and new locations)
                    customized_prompts = detect_customizations(
                        weft_dir, version_data, "optimized_prompts"
                    )
                    # Also check new location
                    customized_prompts.extend(detect_customizations(
                        weft_dir, version_data, "prompts/active"
                    ))
                    if customized_prompts:
                        display_customization_warnings(customized_prompts, "prompts")
                    overwrite_prompts = prompt_yes_no(
                        "Overwrite existing prompts?", skip_prompts=yes
                    )

                except InitCommandError as exc:
                    logger.warning("Could not read VERSION file: %s", exc)
                    # Fall back to simple prompts without customization info
                    overwrite_judges = prompt_yes_no(
                        "Overwrite existing judges?", skip_prompts=yes
                    )
                    overwrite_prompts = prompt_yes_no(
                        "Overwrite existing prompts?", skip_prompts=yes
                    )
            else:
                # No VERSION file - simple prompts
                overwrite_judges = prompt_yes_no(
                    "Overwrite existing judges?", skip_prompts=yes
                )
                overwrite_prompts = prompt_yes_no(
                    "Overwrite existing prompts?", skip_prompts=yes
                )

        # Perform atomic initialization
        with AtomicInitializer(weft_dir, templates_dir) as initializer:
            # Copy everything to staging
            initializer.copy_judges()
            initializer.copy_optimized_prompts()
            initializer.copy_version_file()

            # Commit to target
            initializer.commit_to_target(
                overwrite_judges=overwrite_judges,
                overwrite_prompts=overwrite_prompts,
            )

        # Update .gitignore with weft cache entries
        update_gitignore(repo_root)

        # Create config.toml template if it doesn't exist
        create_config_template(weft_dir)

        # Display appropriate message based on what was done
        if not overwrite_judges and not overwrite_prompts:
            # User declined both overwrites - nothing was changed
            print()
            print(f"No changes made - existing files preserved at {weft_dir}")
        else:
            logger.info("Successfully initialized weft at %s", weft_dir)
            print()
            print("Next steps:")
            print("  1. Review judges in .weft/judges/")
            print("  2. Review prompts in .weft/prompts/active/")
            print("  3. Create a plan: weft plan --text \"your feature idea\"")
            print("  4. Implement it: weft code <plan_id>")

        return 0

    except InitCommandError as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Initialization cancelled by user.")
        return 1
