"""Initialize lw_coder in a git repository with frozen baseline templates.

This module provides the init command which bootstraps new projects with
judges and optimized prompts from the frozen baseline templates bundled
with lw_coder.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
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
    lw_coder_dir: Path, version_data: dict, category: str
) -> list[str]:
    """Detect which files have been customized from their baseline hashes.

    Args:
        lw_coder_dir: Path to the .lw_coder directory.
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

        file_path = lw_coder_dir / rel_path
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


# Gitignore marker and entries for lw_coder cache directories
_GITIGNORE_MARKER = "# lw_coder cache"
_GITIGNORE_ENTRIES = """
# lw_coder cache and temporary files
.lw_coder/dspy_cache/
.lw_coder/worktrees/
.lw_coder/runs/
.lw_coder/plan-traces/
"""


def update_gitignore(project_root: Path) -> None:
    """Add lw_coder cache directories to .gitignore.

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
            logger.debug(".gitignore already contains lw_coder cache entries")
            return

        # Append to existing .gitignore
        try:
            gitignore_path.write_text(
                content.rstrip() + "\n" + _GITIGNORE_ENTRIES, encoding="utf-8"
            )
            logger.info("Added lw_coder cache entries to .gitignore")
        except OSError as exc:
            logger.warning("Failed to update .gitignore: %s", exc)
    else:
        # Create new .gitignore
        try:
            gitignore_path.write_text(_GITIGNORE_ENTRIES.lstrip(), encoding="utf-8")
            logger.info("Created .gitignore with lw_coder cache entries")
        except OSError as exc:
            logger.warning("Failed to create .gitignore: %s", exc)


class AtomicInitializer:
    """Context manager for atomic initialization with rollback on failure.

    Copies templates to a staging directory first, then atomically moves
    them to the target location. On failure, cleans up the staging directory
    and leaves the filesystem in its original state.
    """

    def __init__(self, target_dir: Path, templates_dir: Path):
        """Initialize the atomic initializer.

        Args:
            target_dir: The target .lw_coder directory.
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
        self.staging_dir = Path(tempfile.mkdtemp(prefix="lw_coder_init_"))
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
    """Execute the init command to initialize lw_coder in a git repository.

    Args:
        force: Allow initialization when .lw_coder already exists.
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

        # Check if .lw_coder already exists
        lw_coder_dir = repo_root / ".lw_coder"

        if lw_coder_dir.exists() and not force:
            logger.error(
                "Directory .lw_coder already exists at %s. "
                "Use --force to reinitialize.",
                lw_coder_dir,
            )
            return 1

        # Determine what to copy
        overwrite_judges = True
        overwrite_prompts = True

        if lw_coder_dir.exists() and force:
            # Load VERSION to detect customizations
            version_path = lw_coder_dir / "VERSION"
            if version_path.exists():
                try:
                    version_data = load_version_file(version_path)

                    # Check for customized judges
                    customized_judges = detect_customizations(
                        lw_coder_dir, version_data, "judges"
                    )
                    if customized_judges:
                        display_customization_warnings(customized_judges, "judges")
                    overwrite_judges = prompt_yes_no(
                        "Overwrite existing judges?", skip_prompts=yes
                    )

                    # Check for customized prompts (check both old and new locations)
                    customized_prompts = detect_customizations(
                        lw_coder_dir, version_data, "optimized_prompts"
                    )
                    # Also check new location
                    customized_prompts.extend(detect_customizations(
                        lw_coder_dir, version_data, "prompts/active"
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
        with AtomicInitializer(lw_coder_dir, templates_dir) as initializer:
            # Copy everything to staging
            initializer.copy_judges()
            initializer.copy_optimized_prompts()
            initializer.copy_version_file()

            # Commit to target
            initializer.commit_to_target(
                overwrite_judges=overwrite_judges,
                overwrite_prompts=overwrite_prompts,
            )

        # Update .gitignore with lw_coder cache entries
        update_gitignore(repo_root)

        # Display appropriate message based on what was done
        if not overwrite_judges and not overwrite_prompts:
            # User declined both overwrites - nothing was changed
            print()
            print(f"No changes made - existing files preserved at {lw_coder_dir}")
        else:
            logger.info("Successfully initialized lw_coder at %s", lw_coder_dir)
            print()
            print("Next steps:")
            print("  1. Review judges in .lw_coder/judges/")
            print("  2. Review prompts in .lw_coder/prompts/active/")
            print("  3. Create a plan: lw_coder plan --text \"your feature idea\"")
            print("  4. Implement it: lw_coder code <plan_id>")

        return 0

    except InitCommandError as exc:
        logger.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Initialization cancelled by user.")
        return 1
