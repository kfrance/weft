"""Implementation of the code command for plan validation and worktree preparation.

This module provides the core business logic for the `lw_coder code` command,
separating it from CLI argument parsing and dispatch.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from pathlib import Path

from .droid_session import (
    build_docker_command,
    droid_session_config,
    get_lw_coder_src_dir,
    patched_worktree_gitdir,
)
from .dspy.prompt_orchestrator import generate_code_prompts
from .logging_config import get_logger
from .plan_validator import PlanValidationError, load_plan_metadata
from .run_manager import (
    RunManagerError,
    copy_coding_droids,
    create_run_directory,
    prune_old_runs,
)
from .worktree_utils import WorktreeError, ensure_worktree

logger = get_logger(__name__)


def _check_docker_image(image_tag: str) -> bool:
    """Check if a Docker image exists locally.

    Args:
        image_tag: Docker image tag to check

    Returns:
        True if image exists, False otherwise
    """
    try:
        result = subprocess.run(
            ["docker", "images", "-q", image_tag],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


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


def _build_base_image() -> None:
    """Build the base lw_coder_droid image if it doesn't exist.

    Raises:
        RuntimeError: If docker build fails
    """
    logger.info("Building base Docker image lw_coder_droid:latest...")

    # Find docker/droid/Dockerfile
    dockerfile_path = Path("docker/droid/Dockerfile")
    if not dockerfile_path.exists():
        raise RuntimeError(
            f"Base Dockerfile not found at {dockerfile_path}. "
            "Ensure you're running from the repository root."
        )

    try:
        result = subprocess.run(
            [
                "docker",
                "build",
                "-t",
                "lw_coder_droid:latest",
                "-f",
                str(dockerfile_path),
                "docker/droid",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )
        logger.debug("Base image build output: %s", result.stdout)
        logger.info("Base image lw_coder_droid:latest built successfully")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to build base image: %s", e.stderr)
        raise RuntimeError(
            f"Docker build failed for base image: {e.stderr}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Docker build timed out after 10 minutes") from e


def _build_repo_image(repo_root: Path, build_args: list[str]) -> str:
    """Build repo-specific Docker image with MCP installations.

    Args:
        repo_root: Repository root directory
        build_args: Additional docker build arguments from config

    Returns:
        Tag of the built repo-specific image

    Raises:
        RuntimeError: If docker build fails
    """
    # Compute repo hash for image tag
    repo_hash = hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()[:12]
    image_tag = f"lw_coder_droid:{repo_hash}"

    # Check if image already exists
    if _check_docker_image(image_tag):
        logger.info("Repo-specific image %s already exists, skipping build", image_tag)
        return image_tag

    logger.info("Building repo-specific Docker image %s...", image_tag)

    # Find .lw_coder/code.Dockerfile
    dockerfile_path = repo_root / ".lw_coder" / "code.Dockerfile"
    dockerignore_path = repo_root / ".lw_coder" / ".dockerignore"

    if not dockerfile_path.exists():
        raise RuntimeError(
            f"Repo Dockerfile not found at {dockerfile_path}. "
            "Create .lw_coder/code.Dockerfile to define repo-specific image."
        )

    # Build command
    cmd = [
        "docker",
        "build",
        "-t",
        image_tag,
        "-f",
        str(dockerfile_path),
    ]

    # Add build args from config
    cmd.extend(build_args)

    # Add build context (repo root)
    cmd.append(str(repo_root))

    try:
        # Use dockerignore if it exists
        if dockerignore_path.exists():
            logger.debug("Using .dockerignore from %s", dockerignore_path)

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )
        logger.debug("Repo image build output: %s", result.stdout)
        logger.info("Repo-specific image %s built successfully", image_tag)
        return image_tag
    except subprocess.CalledProcessError as e:
        logger.error("Failed to build repo image: %s", e.stderr)
        raise RuntimeError(
            f"Docker build failed for repo image: {e.stderr}"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Docker build timed out after 10 minutes") from e


def run_code_command(plan_path: Path | str) -> int:
    """Execute the code command: end-to-end coding workflow.

    This function orchestrates:
    1. Plan validation
    2. Configuration loading
    3. Run directory setup
    4. DSPy prompt generation
    5. Worktree preparation
    6. Docker environment setup
    7. Interactive droid session launch

    Args:
        plan_path: Path to the plan file (string or Path object).

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    # Resolve plan path
    if isinstance(plan_path, str):
        plan_path = Path(plan_path)

    # Load and validate plan metadata
    try:
        metadata = load_plan_metadata(plan_path)
    except PlanValidationError as exc:
        logger.error("Plan validation failed: %s", exc)
        return 1

    logger.info("Plan validation succeeded for %s", metadata.plan_path)

    # Use sensible defaults for Docker configuration
    # (Configuration was previously loaded from .lw_coder/config.toml, but that has been deprecated)
    docker_build_args: list[str] = []
    docker_run_args: list[str] = []
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

    # Build Docker images
    try:
        # Build base image if needed
        if not _check_docker_image("lw_coder_droid:latest"):
            _build_base_image()

        # Build repo-specific image with MCP
        repo_image_tag = _build_repo_image(metadata.repo_root, docker_build_args)
    except RuntimeError as exc:
        logger.error("Docker image build failed: %s", exc)
        return 1

    # Filter environment variables to forward
    env_vars = _filter_env_vars(forward_env_patterns)
    if env_vars:
        logger.debug("Forwarding %d environment variable(s) to container", len(env_vars))

    # Log run artifacts location
    logger.info("Run artifacts available at: %s", run_dir)
    logger.info("  Main prompt: %s", prompt_artifacts.main_prompt_path)
    logger.info("  Review droid: %s", prompt_artifacts.review_prompt_path)
    logger.info("  Alignment droid: %s", prompt_artifacts.alignment_prompt_path)
    logger.info("  Coding droids: %s", droids_dir)

    # Get source droids and settings for mounting
    src_dir = get_lw_coder_src_dir()
    settings_file = src_dir / "container_settings.json"

    # Create minimal settings file if it doesn't exist
    # This should ideally be part of package installation, but we handle it here
    # to ensure the file exists before Docker session launch
    if not settings_file.exists():
        try:
            settings_file.write_text('{"version": "1.0"}\n')
            logger.debug("Created minimal settings file at %s", settings_file)
        except (OSError, IOError) as exc:
            logger.error("Failed to create settings file: %s", exc)
            return 1

    # Use auth file from home directory
    auth_file = Path.home() / ".factory" / "auth.json"

    # Prepare droid command (prompt is mounted at /tmp/prompt.txt)
    droid_command = 'droid "$(cat /tmp/prompt.txt)"'

    # Launch Docker session with patched worktree and automatic temp file management
    with patched_worktree_gitdir(worktree_path, metadata.repo_root / ".git") as worktree_name:
        with droid_session_config(
            worktree_path=worktree_path,
            repo_git_dir=metadata.repo_root / ".git",
            tasks_dir=metadata.repo_root / ".lw_coder" / "tasks",
            droids_dir=droids_dir,
            auth_file=auth_file,
            settings_file=settings_file,
            prompt_file=prompt_artifacts.main_prompt_path,
            image_tag=repo_image_tag,
            worktree_name=worktree_name,
            command=droid_command,
            container_uid=os.getuid(),
            container_gid=os.getgid(),
            container_home="/home/droiduser",
            host_factory_dir=Path.home() / ".factory",
            env_vars=env_vars,
            extra_docker_args=docker_run_args,
        ) as session_config:
            # Build and run Docker command
            docker_cmd = build_docker_command(session_config)
            logger.info("Launching interactive droid session...")
            logger.debug("Docker command: %s", " ".join(docker_cmd))

            try:
                # Run interactively, streaming output to user
                result = subprocess.run(
                    docker_cmd,
                    check=False,  # Don't raise on non-zero exit
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

                # Return the Docker container's exit code
                return result.returncode

            except KeyboardInterrupt:
                logger.info("Droid session interrupted by user")
                return 130  # Standard exit code for SIGINT
            except Exception as exc:
                logger.error("Failed to run Docker container: %s", exc)
                return 1
