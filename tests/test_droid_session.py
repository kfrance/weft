"""Tests for droid_session module."""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.droid_session import (
    DroidSessionConfig,
    build_docker_command,
    create_container_group_file,
    create_container_passwd_file,
    get_lw_coder_src_dir,
    patched_worktree_gitdir,
)


def test_get_lw_coder_src_dir() -> None:
    """Test that get_lw_coder_src_dir returns the parent directory of the module."""
    src_dir = get_lw_coder_src_dir()
    assert src_dir.exists()
    assert src_dir.is_dir()
    assert (src_dir / "droid_session.py").exists()


def test_patched_worktree_gitdir_patches_and_restores(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir rewrites .git file and restores it."""
    # Create a fake worktree directory
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create a fake .git file with a gitdir pointer
    git_file = worktree / ".git"
    original_content = "gitdir: /home/user/repo/.git/worktrees/my-worktree-name"
    git_file.write_text(original_content)

    # Create a fake repo git dir (not actually used in the function, but required by signature)
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()

    # Before context: original content
    assert git_file.read_text() == original_content

    # Inside context: patched content
    with patched_worktree_gitdir(worktree, repo_git_dir) as worktree_name:
        assert worktree_name == "my-worktree-name"
        patched_content = git_file.read_text()
        assert patched_content == "gitdir: /repo-git/worktrees/my-worktree-name\n"

    # After context: restored content
    assert git_file.read_text() == original_content


def test_patched_worktree_gitdir_missing_git_file(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir raises error if .git file doesn't exist."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"

    with pytest.raises(RuntimeError, match="Worktree .git file not found"):
        with patched_worktree_gitdir(worktree, repo_git_dir):
            pass


def test_patched_worktree_gitdir_invalid_git_file(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir raises error if .git file is invalid."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    git_file.write_text("not a gitdir pointer")
    repo_git_dir = tmp_path / ".git"

    with pytest.raises(RuntimeError, match="does not contain a gitdir pointer"):
        with patched_worktree_gitdir(worktree, repo_git_dir):
            pass


def test_patched_worktree_gitdir_restores_on_exception(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir restores content even if exception occurs."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    original_content = "gitdir: /home/user/repo/.git/worktrees/test-worktree"
    git_file.write_text(original_content)
    repo_git_dir = tmp_path / ".git"

    with pytest.raises(ValueError, match="Test error"):
        with patched_worktree_gitdir(worktree, repo_git_dir):
            raise ValueError("Test error")

    # Should still restore original content
    assert git_file.read_text() == original_content


def test_build_docker_command_creates_tasks_dir(tmp_path: Path) -> None:
    """Test that build_docker_command creates the tasks directory if missing."""
    # Setup paths
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    tasks_dir = tmp_path / "tasks"
    host_factory_dir = tmp_path / ".factory"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    auth_file = tmp_path / ".factory" / "auth.json"
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    passwd_file = tmp_path / "passwd"
    passwd_file.touch()
    group_file = tmp_path / "group"
    group_file.touch()

    # Tasks directory should not exist yet
    assert not tasks_dir.exists()
    # Factory directory should not exist yet
    assert not host_factory_dir.exists()

    config = DroidSessionConfig(
        worktree_path=worktree,
        repo_git_dir=repo_git_dir,
        tasks_dir=tasks_dir,
        droids_dir=droids_dir,
        auth_file=auth_file,
        settings_file=settings_file,
        prompt_file=prompt_file,
        image_tag="test:latest",
        worktree_name="test-worktree",
        command='echo "test"',
        container_uid=1000,
        container_gid=1000,
        container_home="/home/droiduser",
        host_factory_dir=host_factory_dir,
        passwd_file=passwd_file,
        group_file=group_file,
    )

    cmd = build_docker_command(config)

    # Tasks directory should now exist
    assert tasks_dir.exists()
    assert tasks_dir.is_dir()

    # Factory directory should now exist
    assert host_factory_dir.exists()
    assert host_factory_dir.is_dir()

    # Verify command structure
    assert cmd[0:4] == ["docker", "run", "-it", "--rm"]
    assert "--security-opt=no-new-privileges" in cmd
    assert "--user" in cmd
    assert "1000:1000" in cmd
    assert "-e" in cmd
    assert "HOME=/home/droiduser" in cmd
    assert f"-v" in cmd
    assert f"{worktree}:/workspace" in cmd
    assert f"{repo_git_dir}:/repo-git:ro" in cmd
    assert f"{tasks_dir}:/output" in cmd
    assert f"{host_factory_dir}:/home/droiduser/.factory" in cmd
    assert f"{passwd_file}:/etc/passwd:ro" in cmd
    assert f"{group_file}:/etc/group:ro" in cmd
    assert "test:latest" in cmd
    assert "bash" in cmd
    assert "-c" in cmd
    assert 'echo "test"' in cmd


def test_build_docker_command_with_existing_tasks_dir(tmp_path: Path) -> None:
    """Test that build_docker_command works when tasks directory already exists."""
    # Setup paths
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()  # Create it in advance
    host_factory_dir = tmp_path / ".factory"
    host_factory_dir.mkdir()  # Create it in advance
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    auth_file = tmp_path / ".factory" / "auth.json"
    auth_file.touch()
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    passwd_file = tmp_path / "passwd"
    passwd_file.touch()
    group_file = tmp_path / "group"
    group_file.touch()

    config = DroidSessionConfig(
        worktree_path=worktree,
        repo_git_dir=repo_git_dir,
        tasks_dir=tasks_dir,
        droids_dir=droids_dir,
        auth_file=auth_file,
        settings_file=settings_file,
        prompt_file=prompt_file,
        image_tag="lw_coder_droid:latest",
        worktree_name="my-worktree",
        command='droid "$(cat /tmp/prompt.txt)"',
        container_uid=1000,
        container_gid=1000,
        container_home="/home/droiduser",
        host_factory_dir=host_factory_dir,
        passwd_file=passwd_file,
        group_file=group_file,
    )

    cmd = build_docker_command(config)

    # Verify the command was built successfully
    assert "docker" in cmd
    assert "lw_coder_droid:latest" in cmd
    assert 'droid "$(cat /tmp/prompt.txt)"' in cmd

    # Verify all mount points are present
    mount_args = " ".join(cmd)
    assert f"{worktree}:/workspace" in mount_args
    assert f"{repo_git_dir}:/repo-git:ro" in mount_args
    assert f"{tasks_dir}:/output" in mount_args
    assert f"{host_factory_dir}:/home/droiduser/.factory" in mount_args
    assert f"{droids_dir}:/home/droiduser/.factory/droids:ro" in mount_args
    assert f"{settings_file}:/home/droiduser/.factory/settings.json:ro" in mount_args
    assert f"{prompt_file}:/tmp/prompt.txt:ro" in mount_args
    assert f"{passwd_file}:/etc/passwd:ro" in mount_args
    assert f"{group_file}:/etc/group:ro" in mount_args

    # Verify user and home settings
    assert "--user" in cmd
    assert "1000:1000" in cmd
    assert "-e" in cmd
    assert "HOME=/home/droiduser" in cmd


def test_create_container_passwd_file() -> None:
    """Test that create_container_passwd_file creates a valid passwd file."""
    passwd_file = create_container_passwd_file(uid=1000, gid=1000, username="testuser")

    try:
        # File should exist
        assert passwd_file.exists()
        assert passwd_file.is_file()

        # Read content and verify format
        content = passwd_file.read_text()
        assert content == "testuser:x:1000:1000:Container User:/home/testuser:/bin/bash\n"
    finally:
        # Clean up
        passwd_file.unlink(missing_ok=True)


def test_create_container_group_file() -> None:
    """Test that create_container_group_file creates a valid group file."""
    group_file = create_container_group_file(gid=1000, groupname="testgroup")

    try:
        # File should exist
        assert group_file.exists()
        assert group_file.is_file()

        # Read content and verify format
        content = group_file.read_text()
        assert content == "testgroup:x:1000:\n"
    finally:
        # Clean up
        group_file.unlink(missing_ok=True)
