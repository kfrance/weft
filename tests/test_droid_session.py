"""Tests for droid_session module."""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.droid_session import (
    DroidSessionConfig,
    build_docker_command,
    create_container_group_file,
    create_container_passwd_file,
    droid_session_config,
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
    """Test that patched_worktree_gitdir rewrites .git file and reverse pointer and restores them."""
    # Create a fake worktree directory
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create a fake .git file with a gitdir pointer (with trailing newline to test exact restoration)
    git_file = worktree / ".git"
    original_content = "gitdir: /home/user/repo/.git/worktrees/my-worktree-name\n"
    git_file.write_text(original_content)

    # Create a fake repo git dir with worktree metadata
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    worktree_metadata_dir = repo_git_dir / "worktrees" / "my-worktree-name"
    worktree_metadata_dir.mkdir(parents=True)
    reverse_gitdir_file = worktree_metadata_dir / "gitdir"
    original_reverse_content = "/home/user/repo/worktree/.git\n"
    reverse_gitdir_file.write_text(original_reverse_content)

    # Before context: original content
    assert git_file.read_text() == original_content
    assert reverse_gitdir_file.read_text() == original_reverse_content

    # Inside context: patched content
    with patched_worktree_gitdir(worktree, repo_git_dir) as worktree_name:
        assert worktree_name == "my-worktree-name"
        patched_content = git_file.read_text()
        assert patched_content == "gitdir: /repo-git/worktrees/my-worktree-name\n"
        # Verify reverse pointer is also patched
        assert reverse_gitdir_file.read_text() == "/workspace/.git\n"

    # After context: restored content
    assert git_file.read_text() == original_content
    assert reverse_gitdir_file.read_text() == original_reverse_content


def test_patched_worktree_gitdir_missing_git_file(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir raises error if .git file doesn't exist."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create a valid repo_git_dir structure (needed for validation)
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    (repo_git_dir / "worktrees").mkdir()

    with pytest.raises(RuntimeError, match="Worktree .git file not found"):
        with patched_worktree_gitdir(worktree, repo_git_dir):
            pass


def test_patched_worktree_gitdir_invalid_git_file(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir raises error if .git file is invalid."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    git_file.write_text("not a gitdir pointer")

    # Create a valid repo_git_dir structure (needed for validation)
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    (repo_git_dir / "worktrees").mkdir()

    with pytest.raises(RuntimeError, match="does not contain a gitdir pointer"):
        with patched_worktree_gitdir(worktree, repo_git_dir):
            pass


def test_patched_worktree_gitdir_restores_on_exception(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir restores both pointers even if exception occurs."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    original_content = "gitdir: /home/user/repo/.git/worktrees/test-worktree\n"
    git_file.write_text(original_content)

    # Create repo git dir with worktree metadata and reverse pointer
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    worktree_metadata_dir = repo_git_dir / "worktrees" / "test-worktree"
    worktree_metadata_dir.mkdir(parents=True)
    reverse_gitdir_file = worktree_metadata_dir / "gitdir"
    original_reverse_content = "/home/user/repo/worktree/.git\n"
    reverse_gitdir_file.write_text(original_reverse_content)

    with pytest.raises(ValueError, match="Test error"):
        with patched_worktree_gitdir(worktree, repo_git_dir):
            raise ValueError("Test error")

    # Should still restore both pointers exactly (including newlines)
    assert git_file.read_text() == original_content
    assert reverse_gitdir_file.read_text() == original_reverse_content


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
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    auth_file.touch()
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


def test_build_docker_command_with_env_vars(tmp_path: Path) -> None:
    """Test that build_docker_command correctly adds environment variables."""
    # Setup paths
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    tasks_dir = tmp_path / "tasks"
    host_factory_dir = tmp_path / ".factory"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    passwd_file = tmp_path / "passwd"
    passwd_file.touch()
    group_file = tmp_path / "group"
    group_file.touch()
    auth_file = tmp_path / "auth.json"
    auth_file.touch()

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
        env_vars={"OPENROUTER_API_KEY": "test-key", "DEBUG": "1"},
    )

    cmd = build_docker_command(config)

    # Verify environment variables are in the command
    cmd_str = " ".join(cmd)
    assert "-e" in cmd
    assert "OPENROUTER_API_KEY=test-key" in cmd
    assert "DEBUG=1" in cmd

    # Verify HOME is still present
    assert "HOME=/home/droiduser" in cmd


def test_build_docker_command_with_extra_docker_args(tmp_path: Path) -> None:
    """Test that build_docker_command correctly adds extra docker arguments."""
    # Setup paths
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    tasks_dir = tmp_path / "tasks"
    host_factory_dir = tmp_path / ".factory"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    passwd_file = tmp_path / "passwd"
    passwd_file.touch()
    group_file = tmp_path / "group"
    group_file.touch()
    auth_file = tmp_path / "auth.json"
    auth_file.touch()

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
        extra_docker_args=["--network=host", "--read-only"],
    )

    cmd = build_docker_command(config)

    # Verify extra arguments are in the command before the image tag
    assert "--network=host" in cmd
    assert "--read-only" in cmd

    # Verify they appear before the image tag
    image_index = cmd.index("test:latest")
    network_index = cmd.index("--network=host")
    read_only_index = cmd.index("--read-only")

    assert network_index < image_index
    assert read_only_index < image_index


def test_patched_worktree_gitdir_works_with_real_worktree(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir works with a real git worktree.

    This tests the git pointer patching with an actual git repository and worktree,
    verifying that both forward and reverse pointers are correctly patched and restored.
    """
    import subprocess

    # Create a real git repository
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)

    # Create a file and commit
    (repo_dir / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

    # Create a worktree
    worktree_dir = tmp_path / "worktree"
    subprocess.run(["git", "worktree", "add", str(worktree_dir), "HEAD"], cwd=repo_dir, check=True, capture_output=True)

    # Verify worktree was created
    assert worktree_dir.exists()
    git_file = worktree_dir / ".git"
    assert git_file.exists()

    # Read original pointer
    original_content = git_file.read_text()
    assert original_content.strip().startswith("gitdir:")

    repo_git_dir = repo_dir / ".git"

    # Test patching
    with patched_worktree_gitdir(worktree_dir, repo_git_dir) as worktree_name:
        # Verify forward pointer is patched
        patched_content = git_file.read_text()
        assert patched_content == f"gitdir: /repo-git/worktrees/{worktree_name}\n"

        # Verify reverse pointer is patched
        reverse_gitdir_file = repo_git_dir / "worktrees" / worktree_name / "gitdir"
        assert reverse_gitdir_file.exists()
        assert reverse_gitdir_file.read_text() == "/workspace/.git\n"

    # Verify pointers are restored
    restored_content = git_file.read_text()
    assert restored_content == original_content

    # Clean up
    subprocess.run(["git", "worktree", "remove", str(worktree_dir), "--force"], cwd=repo_dir, check=True, capture_output=True)


def test_build_docker_command_with_both_env_and_extra_args(tmp_path: Path) -> None:
    """Test that build_docker_command works with both env_vars and extra_docker_args."""
    # Setup paths
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    tasks_dir = tmp_path / "tasks"
    host_factory_dir = tmp_path / ".factory"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    passwd_file = tmp_path / "passwd"
    passwd_file.touch()
    group_file = tmp_path / "group"
    group_file.touch()
    auth_file = tmp_path / "auth.json"
    auth_file.touch()

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
        env_vars={"MY_VAR": "my_value"},
        extra_docker_args=["--cpus=2"],
    )

    cmd = build_docker_command(config)

    # Verify both are present
    assert "MY_VAR=my_value" in cmd
    assert "--cpus=2" in cmd

    # Verify structure is correct
    assert "test:latest" in cmd
    assert "bash" in cmd


def test_droid_session_config_creates_temp_files(tmp_path: Path) -> None:
    """Test that droid_session_config creates passwd and group temp files."""
    # Setup minimal paths
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    tasks_dir = tmp_path / "tasks"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    auth_file = tmp_path / "auth.json"
    auth_file.touch()
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    host_factory_dir = tmp_path / ".factory"

    with droid_session_config(
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
    ) as config:
        # Temp files should exist inside the context
        assert config.passwd_file.exists()
        assert config.group_file.exists()

        # Verify passwd file content
        passwd_content = config.passwd_file.read_text()
        assert passwd_content == "droiduser:x:1000:1000:Container User:/home/droiduser:/bin/bash\n"

        # Verify group file content
        group_content = config.group_file.read_text()
        assert group_content == "droiduser:x:1000:\n"


def test_droid_session_config_populates_config(tmp_path: Path) -> None:
    """Test that droid_session_config populates DroidSessionConfig correctly."""
    # Setup paths
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    tasks_dir = tmp_path / "tasks"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    auth_file = tmp_path / "auth.json"
    auth_file.touch()
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    host_factory_dir = tmp_path / ".factory"

    env_vars = {"MY_VAR": "my_value", "DEBUG": "1"}
    extra_args = ["--network=host"]

    with droid_session_config(
        worktree_path=worktree,
        repo_git_dir=repo_git_dir,
        tasks_dir=tasks_dir,
        droids_dir=droids_dir,
        auth_file=auth_file,
        settings_file=settings_file,
        prompt_file=prompt_file,
        image_tag="my_image:v1.2.3",
        worktree_name="my-worktree",
        command='droid "$(cat /tmp/prompt.txt)"',
        container_uid=5000,
        container_gid=5000,
        container_home="/home/customuser",
        host_factory_dir=host_factory_dir,
        container_username="customuser",
        container_groupname="customgroup",
        env_vars=env_vars,
        extra_docker_args=extra_args,
    ) as config:
        # Verify all fields are populated correctly
        assert config.worktree_path == worktree
        assert config.repo_git_dir == repo_git_dir
        assert config.tasks_dir == tasks_dir
        assert config.droids_dir == droids_dir
        assert config.auth_file == auth_file
        assert config.settings_file == settings_file
        assert config.prompt_file == prompt_file
        assert config.image_tag == "my_image:v1.2.3"
        assert config.worktree_name == "my-worktree"
        assert config.command == 'droid "$(cat /tmp/prompt.txt)"'
        assert config.container_uid == 5000
        assert config.container_gid == 5000
        assert config.container_home == "/home/customuser"
        assert config.host_factory_dir == host_factory_dir
        assert config.env_vars == env_vars
        assert config.extra_docker_args == extra_args

        # Verify temp files exist and have correct content
        passwd_content = config.passwd_file.read_text()
        assert "customuser:x:5000:5000" in passwd_content

        group_content = config.group_file.read_text()
        assert "customgroup:x:5000:" in group_content


def test_droid_session_config_cleanup_on_success(tmp_path: Path) -> None:
    """Test that droid_session_config cleans up temp files on normal exit."""
    # Setup paths
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    tasks_dir = tmp_path / "tasks"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    auth_file = tmp_path / "auth.json"
    auth_file.touch()
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    host_factory_dir = tmp_path / ".factory"

    passwd_file_path = None
    group_file_path = None

    with droid_session_config(
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
    ) as config:
        # Save paths to check after context exits
        passwd_file_path = config.passwd_file
        group_file_path = config.group_file

        # Files exist inside context
        assert passwd_file_path.exists()
        assert group_file_path.exists()

    # Files should be deleted after context exits
    assert not passwd_file_path.exists()
    assert not group_file_path.exists()


def test_droid_session_config_cleanup_on_exception(tmp_path: Path) -> None:
    """Test that droid_session_config cleans up temp files even if exception occurs."""
    # Setup paths
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    tasks_dir = tmp_path / "tasks"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    auth_file = tmp_path / "auth.json"
    auth_file.touch()
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    host_factory_dir = tmp_path / ".factory"

    passwd_file_path = None
    group_file_path = None

    with pytest.raises(ValueError, match="Test exception"):
        with droid_session_config(
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
        ) as config:
            # Save paths to check after context exits
            passwd_file_path = config.passwd_file
            group_file_path = config.group_file

            # Files exist inside context
            assert passwd_file_path.exists()
            assert group_file_path.exists()

            # Raise exception to test cleanup
            raise ValueError("Test exception")

    # Files should still be deleted after exception
    assert not passwd_file_path.exists()
    assert not group_file_path.exists()


def test_droid_session_config_with_patched_worktree(tmp_path: Path) -> None:
    """Test that droid_session_config works correctly with patched_worktree_gitdir."""
    import subprocess

    # Create a real git repository
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)

    # Create a file and commit
    (repo_dir / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True, capture_output=True)

    # Create a worktree
    worktree_dir = tmp_path / "worktree"
    subprocess.run(["git", "worktree", "add", str(worktree_dir), "HEAD"], cwd=repo_dir, check=True, capture_output=True)

    repo_git_dir = repo_dir / ".git"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir()
    auth_file = tmp_path / "auth.json"
    auth_file.touch()
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.touch()
    tasks_dir = tmp_path / "tasks"
    host_factory_dir = tmp_path / ".factory"

    try:
        # Test nested context managers work together
        with patched_worktree_gitdir(worktree_dir, repo_git_dir) as worktree_name:
            with droid_session_config(
                worktree_path=worktree_dir,
                repo_git_dir=repo_git_dir,
                tasks_dir=tasks_dir,
                droids_dir=droids_dir,
                auth_file=auth_file,
                settings_file=settings_file,
                prompt_file=prompt_file,
                image_tag="test:latest",
                worktree_name=worktree_name,
                command='echo "test"',
                container_uid=1000,
                container_gid=1000,
                container_home="/home/droiduser",
                host_factory_dir=host_factory_dir,
            ) as config:
                # Config should have correct worktree_name
                assert config.worktree_name == worktree_name

                # Temp files should exist
                assert config.passwd_file.exists()
                assert config.group_file.exists()

                # Git pointers should be patched
                git_file = worktree_dir / ".git"
                assert f"/repo-git/worktrees/{worktree_name}" in git_file.read_text()

                # Could build docker command successfully
                cmd = build_docker_command(config)
                assert "test:latest" in cmd

        # After both contexts exit, temp files should be cleaned up
        # and git pointers should be restored
        git_file = worktree_dir / ".git"
        git_content = git_file.read_text()
        assert "/repo-git/" not in git_content
        assert str(repo_git_dir) in git_content

    finally:
        # Clean up worktree
        subprocess.run(["git", "worktree", "remove", str(worktree_dir), "--force"], cwd=repo_dir, check=True, capture_output=True)


def test_patched_worktree_gitdir_validates_repo_git_dir_exists(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir validates repo_git_dir exists and is a directory."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    git_file.write_text("gitdir: /home/user/repo/.git/worktrees/test")

    # Test with non-existent repo_git_dir
    non_existent_repo_git_dir = tmp_path / "nonexistent" / ".git"
    with pytest.raises(RuntimeError, match="Invalid repo_git_dir"):
        with patched_worktree_gitdir(worktree, non_existent_repo_git_dir):
            pass

    # Test with repo_git_dir that is a file, not a directory
    file_repo_git_dir = tmp_path / ".git"
    file_repo_git_dir.touch()  # Create as file
    with pytest.raises(RuntimeError, match="Invalid repo_git_dir"):
        with patched_worktree_gitdir(worktree, file_repo_git_dir):
            pass


def test_patched_worktree_gitdir_validates_worktrees_directory_exists(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir validates worktrees directory exists."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    git_file.write_text("gitdir: /home/user/repo/.git/worktrees/test")

    # Create repo_git_dir but without worktrees subdirectory
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()

    with pytest.raises(RuntimeError, match="Repository has no worktrees directory"):
        with patched_worktree_gitdir(worktree, repo_git_dir):
            pass


def test_patched_worktree_gitdir_validates_worktree_metadata_dir_exists(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir validates worktree metadata directory exists."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    git_file.write_text("gitdir: /home/user/repo/.git/worktrees/missing-worktree")

    # Create repo_git_dir with worktrees directory, but not the specific worktree metadata
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    (repo_git_dir / "worktrees").mkdir()

    with pytest.raises(RuntimeError, match="Worktree metadata directory not found"):
        with patched_worktree_gitdir(worktree, repo_git_dir):
            pass


def test_patched_worktree_gitdir_handles_missing_reverse_pointer(tmp_path: Path) -> None:
    """Test that patched_worktree_gitdir handles case where reverse pointer doesn't initially exist."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    git_file = worktree / ".git"
    original_content = "gitdir: /home/user/repo/.git/worktrees/test-worktree\n"
    git_file.write_text(original_content)

    # Create repo_git_dir with worktree metadata but NO reverse pointer file
    repo_git_dir = tmp_path / ".git"
    repo_git_dir.mkdir()
    worktree_metadata_dir = repo_git_dir / "worktrees" / "test-worktree"
    worktree_metadata_dir.mkdir(parents=True)
    reverse_gitdir_file = worktree_metadata_dir / "gitdir"
    # Don't create the reverse pointer file

    assert not reverse_gitdir_file.exists()

    # Patch should create the reverse pointer
    with patched_worktree_gitdir(worktree, repo_git_dir) as worktree_name:
        assert worktree_name == "test-worktree"
        # Reverse pointer should now exist with container path
        assert reverse_gitdir_file.exists()
        assert reverse_gitdir_file.read_text() == "/workspace/.git\n"

    # After context, reverse pointer should be removed (since it didn't exist originally)
    assert not reverse_gitdir_file.exists()
    # Forward pointer should be restored
    assert git_file.read_text() == original_content
