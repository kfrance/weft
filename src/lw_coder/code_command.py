"""Implementation of the code command for plan validation and worktree preparation.

This module provides the core business logic for the `lw_coder code` command,
separating it from CLI argument parsing and dispatch.

Now runs directly on the host environment instead of in Docker containers.
"""

from __future__ import annotations

import fnmatch
import os
import shlex
import subprocess
from pathlib import Path

from .host_runner import build_host_command, get_lw_coder_src_dir, host_runner_config
from .dspy.prompt_orchestrator import generate_code_prompts
from .logging_config import get_logger
from .plan_lifecycle import (
    PlanLifecycleError,
    get_current_head_sha,
    update_plan_fields,
)
from .plan_validator import (
    PLACEHOLDER_SHA,
    PlanValidationError,
    _extract_front_matter,
    _find_repo_root,
    load_plan_metadata,
)
from .run_manager import (
    RunManagerError,
    copy_coding_droids,
    create_run_directory,
    prune_old_runs,
)
from .worktree_utils import WorktreeError, ensure_worktree

logger = get_logger(__name__)


def _filter_env_vars(patterns: list[str]) -> dict[str, str]:
    """Filter environment variables based on patterns.

    Args:
        patterns: List of patterns (supports wildcards and "*" for all)

    Returns:
        Dictionary of matching environment variables
    """
    if "*" in patterns:
        # Forward all environment variables
        return dict(os.environ)

    filtered = {}
    for pattern in patterns:
        for key, value in os.environ.items():
            if fnmatch.fnmatch(key, pattern):
                filtered[key] = value

    return filtered


def run_code_command(plan_path: Path | str) -> int:
    """Execute the code command: end-to-end coding workflow.

    This function orchestrates:
    1. Plan validation
    2. Configuration loading
    3. Run directory setup
    4. DSPy prompt generation
    5. Worktree preparation
    6. Host-based droid session launch

    Args:
        plan_path: Path to the plan file (string or Path object).

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    # Resolve plan path
    if isinstance(plan_path, str):
        plan_path = Path(plan_path)

    head_sha: str | None = None
    front_matter: dict[str, object] | None = None

    try:
        repo_root = _find_repo_root(plan_path)
    except PlanValidationError:
        repo_root = None

    if repo_root is not None:
        try:
            head_sha = get_current_head_sha(repo_root)
        except PlanLifecycleError as exc:
            logger.error("Failed to resolve repository HEAD: %s", exc)
            return 1

    if plan_path.exists():
        try:
            content = plan_path.read_text(encoding="utf-8")
            fm, _ = _extract_front_matter(content)
            if isinstance(fm, dict):
                front_matter = fm
        except (OSError, PlanValidationError):
            front_matter = None

    plan_updated = False
    original_fields: dict[str, str] = {}

    if front_matter and head_sha:
        existing_git_sha = front_matter.get("git_sha")
        normalized_git_sha = (
            existing_git_sha.strip().lower()
            if isinstance(existing_git_sha, str)
            else None
        )

        if isinstance(existing_git_sha, str):
            original_fields["git_sha"] = existing_git_sha
        status_field = front_matter.get("status")
        if isinstance(status_field, str):
            original_fields["status"] = status_field

        if (
            normalized_git_sha
            and normalized_git_sha != PLACEHOLDER_SHA
            and normalized_git_sha != head_sha
        ):
            logger.error(
                "Plan git_sha %s does not match repository HEAD %s. "
                "Please ensure the plan is in sync with the latest commit before running code. "
                "Check for uncommitted changes or regenerate the plan after rebasing.",
                normalized_git_sha,
                head_sha,
            )
            return 1

        try:
            update_plan_fields(plan_path, {"git_sha": head_sha, "status": "coding"})
            plan_updated = True
        except PlanLifecycleError as exc:
            logger.error("Failed to update plan metadata before coding session: %s", exc)
            return 1
    elif head_sha and not plan_path.exists():
        logger.error("Plan file not found: %s", plan_path)
        return 1

    # Load and validate plan metadata
    try:
        metadata = load_plan_metadata(plan_path)
    except PlanValidationError as exc:
        if plan_updated and original_fields:
            try:
                update_plan_fields(plan_path, original_fields)
            except PlanLifecycleError as rollback_exc:
                logger.warning(
                    "Failed to restore plan metadata after validation error: %s",
                    rollback_exc,
                )
        logger.error("Plan validation failed: %s", exc)
        return 1

    logger.info("Plan validation succeeded for %s", metadata.plan_path)

    # Use sensible defaults for environment configuration
    forward_env_patterns: list[str] = ["OPENROUTER_*"]

    # Create run directory
    try:
        run_dir = create_run_directory(metadata.repo_root, metadata.plan_id)
    except RunManagerError as exc:
        logger.error("Failed to create run directory: %s", exc)
        return 1

    # Copy coding droids to run directory
    try:
        droids_dir = copy_coding_droids(run_dir)
    except RunManagerError as exc:
        logger.error("Failed to copy coding droids: %s", exc)
        return 1

    # Generate prompts using DSPy
    try:
        logger.info("Generating prompts using DSPy...")
        prompt_artifacts = generate_code_prompts(metadata, run_dir)
        logger.info("DSPy prompt generation completed")
    except Exception as exc:
        logger.error("Prompt generation failed: %s", exc)
        logger.debug("Exception details:", exc_info=True)
        return 1

    # Prune old run directories (non-fatal if it fails)
    try:
        prune_old_runs(metadata.repo_root, active_run_dir=run_dir)
    except RunManagerError as exc:
        logger.warning("Failed to prune old run directories: %s", exc)

    # Prepare worktree
    try:
        worktree_path = ensure_worktree(metadata)
        logger.info("Worktree prepared at: %s", worktree_path)
    except WorktreeError as exc:
        logger.error("Worktree preparation failed: %s", exc)
        return 1

    # Filter environment variables to forward
    env_vars = _filter_env_vars(forward_env_patterns)
    if env_vars:
        logger.debug("Forwarding %d environment variable(s) to droid", len(env_vars))

    # Log run artifacts location
    logger.info("Run artifacts available at: %s", run_dir)
    logger.info("  Main prompt: %s", prompt_artifacts.main_prompt_path)
    logger.info("  Review droid: %s", prompt_artifacts.review_prompt_path)
    logger.info("  Alignment droid: %s", prompt_artifacts.alignment_prompt_path)
    logger.info("  Coding droids: %s", droids_dir)

    # Get source droids and settings
    src_dir = get_lw_coder_src_dir()
    settings_file = src_dir / "container_settings.json"

    # Create minimal settings file if it doesn't exist
    if not settings_file.exists():
        try:
            settings_file.write_text('{"version": "1.0"}\n')
            logger.debug("Created minimal settings file at %s", settings_file)
        except (OSError, IOError) as exc:
            logger.error("Failed to create settings file: %s", exc)
            return 1

    # Use auth file from home directory
    auth_file = Path.home() / ".factory" / "auth.json"

    # Prepare droid command with properly escaped paths to prevent shell injection
    prompt_path_escaped = shlex.quote(str(prompt_artifacts.main_prompt_path))
    droid_command = f'droid "$(cat {prompt_path_escaped})"'

    # Launch host-based session
    runner_config = host_runner_config(
        worktree_path=worktree_path,
        repo_git_dir=metadata.repo_root / ".git",
        tasks_dir=metadata.repo_root / ".lw_coder" / "tasks",
        droids_dir=droids_dir,
        auth_file=auth_file,
        settings_file=settings_file,
        command=droid_command,
        host_factory_dir=Path.home() / ".factory",
        env_vars=env_vars,
    )

    # Build host command
    host_cmd, host_env = build_host_command(runner_config)
    logger.info("Launching interactive droid session on host...")
    logger.debug("Host command: %s", " ".join(host_cmd))

    try:
        # Run interactively, streaming output to user
        result = subprocess.run(
            host_cmd,
            check=False,  # Don't raise on non-zero exit
            env=host_env,
            cwd=worktree_path,
        )

        if result.returncode == 0:
            try:
                update_plan_fields(plan_path, {"status": "done"})
            except PlanLifecycleError as exc:
                logger.warning(
                    "Failed to update plan status to 'done' after successful session: %s",
                    exc,
                )

        if result.returncode != 0:
            logger.warning("Droid session exited with code %d", result.returncode)
        else:
            logger.info("Droid session completed successfully")

        # Log follow-up information
        logger.info(
            "\nSession complete. Worktree remains at: %s\n"
            "To resume, cd to the worktree and continue working.\n"
            "Run artifacts saved to: %s",
            worktree_path,
            run_dir,
        )

        # Return the session's exit code
        return result.returncode

    except KeyboardInterrupt:
        logger.info("Droid session interrupted by user")
        return 130  # Standard exit code for SIGINT
    except Exception as exc:
        logger.error("Failed to run droid session: %s", exc)
        return 1
