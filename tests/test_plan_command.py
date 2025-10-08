"""Tests for plan command functionality."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lw_coder.plan_command import (
    PlanCommandError,
    _extract_idea_text,
    _load_template,
)
import lw_coder.plan_command
from lw_coder.droid_session import DroidSessionConfig, build_docker_command


def test_load_template_success() -> None:
    """Test loading a valid template."""
    template = _load_template("droid")
    assert "{IDEA_TEXT}" in template
    assert "Your task:" in template


def test_load_template_nonexistent_tool() -> None:
    """Test loading template for nonexistent tool."""
    with pytest.raises(PlanCommandError, match="Prompt template not found"):
        _load_template("nonexistent_tool")


def test_extract_idea_text_from_text_input() -> None:
    """Test extracting idea text from direct text input."""
    text = "This is my plan idea"
    result = _extract_idea_text(None, text)
    assert result == text


def test_extract_idea_text_from_file(tmp_path: Path) -> None:
    """Test extracting idea text from a file."""
    plan_file = tmp_path / "idea.md"
    content = "# My Plan\n\nThis is the plan content."
    plan_file.write_text(content)

    result = _extract_idea_text(plan_file, None)
    assert result == content.strip()


def test_extract_idea_text_from_file_with_frontmatter(tmp_path: Path) -> None:
    """Test extracting idea text from a file with YAML frontmatter (should be ignored)."""
    plan_file = tmp_path / "idea.md"
    content = """---
plan_id: test-plan
git_sha: 1234567890abcdef1234567890abcdef12345678
status: draft
evaluation_notes:
  - Test note
---

# My Plan

This is the plan content without frontmatter."""
    plan_file.write_text(content)

    result = _extract_idea_text(plan_file, None)
    # Should extract only the body, ignoring frontmatter
    assert "# My Plan" in result
    assert "This is the plan content without frontmatter." in result
    assert "plan_id" not in result


def test_extract_idea_text_missing_file(tmp_path: Path) -> None:
    """Test extracting idea text from nonexistent file."""
    nonexistent = tmp_path / "nonexistent.md"
    with pytest.raises(PlanCommandError, match="Plan file not found"):
        _extract_idea_text(nonexistent, None)


def test_extract_idea_text_both_inputs() -> None:
    """Test that providing both file and text raises error."""
    with pytest.raises(PlanCommandError, match="Cannot specify both"):
        _extract_idea_text(Path("file.md"), "text input")


def test_extract_idea_text_no_inputs() -> None:
    """Test that providing neither file nor text raises error."""
    with pytest.raises(PlanCommandError, match="Must specify either"):
        _extract_idea_text(None, None)


def test_build_docker_command_removed() -> None:
    """Test that _build_docker_command no longer exists (moved to droid_session)."""
    assert not hasattr(lw_coder.plan_command, "_build_docker_command")


def test_load_template_delegates_to_droid_session(monkeypatch) -> None:
    """Test that _load_template uses get_lw_coder_src_dir from droid_session."""
    # Track if get_lw_coder_src_dir was called
    calls = []

    def mock_get_lw_coder_src_dir():
        calls.append(1)
        # Return the actual source directory so template loading works
        return Path(__file__).resolve().parent.parent / "src" / "lw_coder"

    # Patch it in the plan_command module where it's imported
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", mock_get_lw_coder_src_dir
    )

    # Call _load_template which should use the mocked function
    template = _load_template("droid")

    # Verify the mock was called
    assert len(calls) == 1
    # Verify template was loaded successfully
    assert "{IDEA_TEXT}" in template


def test_load_template_runtime_error_becomes_plan_command_error(monkeypatch) -> None:
    """Test that RuntimeError from get_lw_coder_src_dir becomes PlanCommandError."""
    def mock_get_lw_coder_src_dir():
        raise RuntimeError("Source directory not found")

    # Patch it in the plan_command module where it's imported
    monkeypatch.setattr(
        lw_coder.plan_command, "get_lw_coder_src_dir", mock_get_lw_coder_src_dir
    )

    with pytest.raises(PlanCommandError, match="Source directory not found"):
        _load_template("droid")


def test_build_docker_command_with_realistic_config(tmp_path: Path) -> None:
    """Unit test: verify build_docker_command produces correct Docker command structure.

    This test verifies that build_docker_command (used by plan_command) correctly:
    1. Creates the expected Docker command structure
    2. Includes all required mounts and settings
    3. Creates the tasks directory if missing
    4. Uses the provided configuration correctly

    Note: This tests build_docker_command in isolation, not the full plan_command workflow.
    Integration between plan_command and droid_session is verified by delegation tests
    (test_load_template_delegates_to_droid_session) and CLI integration tests.
    """
    # Setup: Create test directory structure
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    repo_git_dir = tmp_path / "repo" / ".git"
    repo_git_dir.mkdir(parents=True)
    tasks_dir = tmp_path / ".lw_coder" / "tasks"
    host_factory_dir = tmp_path / ".factory"
    droids_dir = tmp_path / "droids"
    droids_dir.mkdir(parents=True)
    auth_file = tmp_path / ".factory" / "auth.json"
    settings_file = tmp_path / "settings.json"
    settings_file.touch()
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("Test prompt")
    passwd_file = tmp_path / "passwd"
    passwd_file.touch()
    group_file = tmp_path / "group"
    group_file.touch()

    # Create fake .git file in worktree
    git_file = worktree / ".git"
    git_file.write_text("gitdir: /original/path/.git/worktrees/test-worktree")

    # Create DroidSessionConfig (this is what plan_command would create)
    config = DroidSessionConfig(
        worktree_path=worktree,
        repo_git_dir=repo_git_dir,
        tasks_dir=tasks_dir,
        droids_dir=droids_dir,
        auth_file=auth_file,
        settings_file=settings_file,
        prompt_file=prompt_file,
        image_tag="lw_coder_droid:latest",
        worktree_name="test-worktree",
        command='droid "$(cat /tmp/prompt.txt)"',
        container_uid=1000,
        container_gid=1000,
        container_home="/home/droiduser",
        host_factory_dir=host_factory_dir,
        passwd_file=passwd_file,
        group_file=group_file,
    )

    # Execute: Use REAL build_docker_command (no mocking)
    docker_cmd = build_docker_command(config)

    # Assert: Verify the command structure
    assert docker_cmd[0:4] == ["docker", "run", "-it", "--rm"]
    assert "--security-opt=no-new-privileges" in docker_cmd

    # Verify all required mounts are present
    cmd_str = " ".join(docker_cmd)
    assert f"{worktree}:/workspace" in cmd_str
    assert f"{repo_git_dir}:/repo-git:ro" in cmd_str
    assert f"{tasks_dir}:/output" in cmd_str
    assert f"{host_factory_dir}:/home/droiduser/.factory" in cmd_str
    assert f"{droids_dir}:/home/droiduser/.factory/droids:ro" in cmd_str
    assert f"{settings_file}:/home/droiduser/.factory/settings.json:ro" in cmd_str
    assert f"{prompt_file}:/tmp/prompt.txt:ro" in cmd_str
    assert f"{passwd_file}:/etc/passwd:ro" in cmd_str
    assert f"{group_file}:/etc/group:ro" in cmd_str

    # Verify user and home settings
    assert "--user" in docker_cmd
    assert "1000:1000" in docker_cmd
    assert "-e" in docker_cmd
    assert "HOME=/home/droiduser" in docker_cmd

    # Verify working directory and image
    assert "-w" in docker_cmd
    assert "/workspace" in docker_cmd
    assert "lw_coder_droid:latest" in docker_cmd

    # Verify command execution
    assert "bash" in docker_cmd
    assert "-c" in docker_cmd
    assert 'droid "$(cat /tmp/prompt.txt)"' in docker_cmd

    # Verify tasks directory was created by build_docker_command
    assert tasks_dir.exists()
    assert tasks_dir.is_dir()

    # Verify factory directory was created by build_docker_command
    assert host_factory_dir.exists()
    assert host_factory_dir.is_dir()
