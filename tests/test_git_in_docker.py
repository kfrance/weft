"""Integration test for git functionality inside Docker containers.

This test verifies that git commands work correctly inside Docker containers
when using worktree pointer patching.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from lw_coder.droid_session import (
    build_docker_command,
    create_container_group_file,
    create_container_passwd_file,
    DroidSessionConfig,
    patched_worktree_gitdir,
)

from tests.conftest import GitRepo


def test_git_status_works_in_docker_container(git_repo: GitRepo, tmp_path: Path) -> None:
    """Integration test: Verify git status works inside a Docker container.

    This test:
    1. Creates a real git worktree
    2. Patches the git pointers for container paths
    3. Actually runs a Docker container
    4. Executes 'git status' inside the container
    5. Verifies it succeeds without errors

    This validates that the git pointer patching (including newline handling)
    works correctly in a real Docker environment.
    """
    # Check if Docker image exists
    result = subprocess.run(
        ["docker", "images", "-q", "lw_coder_droid:latest"],
        capture_output=True,
        text=True
    )
    if not result.stdout.strip():
        pytest.fail(
            "Docker image 'lw_coder_droid:latest' not found. "
            "Build it first with: docker build -f docker/droid/Dockerfile -t lw_coder_droid:latest docker/droid"
        )

    # Create a worktree from the test git repo
    worktree_dir = tmp_path / "test-worktree"
    git_repo.run("worktree", "add", str(worktree_dir), "HEAD")

    # Verify worktree was created
    assert worktree_dir.exists()
    assert (worktree_dir / ".git").exists()
    assert (worktree_dir / "README.md").exists()

    # Create necessary files for Docker session
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()

    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"test": true}')

    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Test prompt")

    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    host_factory_dir = tmp_path / ".factory"
    host_factory_dir.mkdir()

    auth_file = host_factory_dir / "auth.json"
    auth_file.write_text('{"test": true}')

    # Create container user files
    passwd_file = create_container_passwd_file(
        uid=os.getuid(),
        gid=os.getgid(),
        username="testuser"
    )

    group_file = create_container_group_file(
        gid=os.getgid(),
        groupname="testgroup"
    )

    try:
        # Patch git pointers for container paths
        with patched_worktree_gitdir(worktree_dir, git_repo.path / ".git") as worktree_name:
            # Build Docker command configuration
            config = DroidSessionConfig(
                worktree_path=worktree_dir,
                repo_git_dir=git_repo.path / ".git",
                tasks_dir=tasks_dir,
                droids_dir=droids_dir,
                auth_file=auth_file,
                settings_file=settings_file,
                prompt_file=prompt_file,
                image_tag="lw_coder_droid:latest",
                worktree_name=worktree_name,
                command='git config --global --add safe.directory "*" 2>/dev/null || true && git status',
                container_uid=os.getuid(),
                container_gid=os.getgid(),
                container_home="/home/droiduser",
                host_factory_dir=host_factory_dir,
                passwd_file=passwd_file,
                group_file=group_file,
            )

            # Build the Docker command (but we'll modify it for non-interactive use)
            docker_cmd = build_docker_command(config)

            # Remove -it flags for non-interactive pytest execution
            docker_cmd_non_interactive = [arg for arg in docker_cmd if arg not in ['-it', '-i', '-t']]

            # Execute Docker container with git status
            result = subprocess.run(
                docker_cmd_non_interactive,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise AssertionError(
                    f"git status failed in container (exit {result.returncode}):\n"
                    f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                )

            # Verify git status output looks correct
            # Worktrees can show "On branch", "HEAD detached", or "Not currently on any branch"
            assert (
                "On branch" in result.stdout
                or "HEAD detached" in result.stdout
                or "Not currently on any branch" in result.stdout
            ), f"Unexpected git status output: {result.stdout}"

            # Verify no git errors about invalid gitdir
            assert "fatal:" not in result.stderr.lower(), \
                f"Git error in container: {result.stderr}"
            assert "not a git repository" not in result.stderr.lower(), \
                f"Git repository not recognized in container: {result.stderr}"

        # After exiting context, verify pointers are restored on host
        git_file = worktree_dir / ".git"
        git_content = git_file.read_text()

        # Should be restored to host path (not container path)
        assert "/repo-git/" not in git_content, \
            f"Git pointer not restored after context exit: {git_content}"
        assert "gitdir:" in git_content, \
            f"Git pointer format invalid after restore: {git_content}"

    finally:
        # Cleanup
        passwd_file.unlink(missing_ok=True)
        group_file.unlink(missing_ok=True)

        # Remove worktree
        git_repo.run("worktree", "remove", str(worktree_dir), "--force")
