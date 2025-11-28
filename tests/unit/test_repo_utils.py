"""Tests for repo_utils module."""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.repo_utils import (
    RepoUtilsError,
    find_repo_root,
    load_prompt_template,
    verify_branch_merged_to_main,
)


def test_find_repo_root_from_cwd(git_repo) -> None:
    """Test find_repo_root from current working directory."""
    # Execute (git_repo fixture is already in a git repository)
    result = find_repo_root()

    # Assert - should return a valid path
    assert isinstance(result, Path)
    assert result.exists()
    assert (result / ".git").exists()


def test_find_repo_root_from_file_path(git_repo) -> None:
    """Test find_repo_root when given a file path."""
    # Setup - create a file in the repo
    test_file = git_repo.path / "test.md"
    test_file.write_text("test")

    # Execute
    result = find_repo_root(test_file)

    # Assert
    assert result == git_repo.path


def test_find_repo_root_from_directory_path(git_repo) -> None:
    """Test find_repo_root when given a directory path."""
    # Setup - create a subdirectory
    subdir = git_repo.path / "subdir"
    subdir.mkdir()

    # Execute
    result = find_repo_root(subdir)

    # Assert
    assert result == git_repo.path


def test_find_repo_root_not_in_git(tmp_path: Path, monkeypatch) -> None:
    """Test find_repo_root when not in a git repository."""
    # Setup - change to a non-git directory
    monkeypatch.chdir(tmp_path)

    # Execute and assert
    with pytest.raises(RepoUtilsError, match="Must be run from within a Git repository"):
        find_repo_root()


def test_load_prompt_template_success(tmp_path: Path, monkeypatch) -> None:
    """Test successful prompt template loading."""
    # Setup
    src_dir = tmp_path / "src"
    prompts_dir = src_dir / "prompts" / "claude-code"
    prompts_dir.mkdir(parents=True)

    template_path = prompts_dir / "finalize.md"
    expected_content = "# Claude Code Finalize Template\nPlan: {PLAN_ID}"
    template_path.write_text(expected_content)

    # Mock get_lw_coder_src_dir
    monkeypatch.setattr(
        "lw_coder.host_runner.get_lw_coder_src_dir",
        lambda: src_dir
    )

    # Execute
    result = load_prompt_template("claude-code", "finalize")

    # Assert
    assert result == expected_content


def test_load_prompt_template_not_found(tmp_path: Path, monkeypatch) -> None:
    """Test prompt template loading when template doesn't exist."""
    # Setup
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)

    # Mock get_lw_coder_src_dir
    monkeypatch.setattr(
        "lw_coder.host_runner.get_lw_coder_src_dir",
        lambda: src_dir
    )

    # Execute and assert
    with pytest.raises(RepoUtilsError, match="Prompt template not found"):
        load_prompt_template("nonexistent-tool", "plan")


@pytest.mark.parametrize("tool,template_name", [
    ("claude-code", "plan"),
    ("claude-code", "finalize"),
    ("droid", "plan"),
    ("droid", "finalize"),
])
def test_load_prompt_template_different_tools(tmp_path: Path, monkeypatch, tool: str, template_name: str) -> None:
    """Test prompt template loading for different tools and template names."""
    # Setup
    src_dir = tmp_path / "src"
    prompts_dir = src_dir / "prompts" / tool
    prompts_dir.mkdir(parents=True)

    template_path = prompts_dir / f"{template_name}.md"
    expected_content = f"# {tool} {template_name} template"
    template_path.write_text(expected_content)

    # Mock get_lw_coder_src_dir
    monkeypatch.setattr(
        "lw_coder.host_runner.get_lw_coder_src_dir",
        lambda: src_dir
    )

    # Execute
    result = load_prompt_template(tool, template_name)

    # Assert
    assert result == expected_content


def test_verify_branch_merged_to_main_success(git_repo) -> None:
    """Test verify_branch_merged_to_main when branch was merged."""
    # Setup - create a branch, make a commit, and merge it to main
    import subprocess

    # Ensure we're on main branch (create it if needed)
    subprocess.run(
        ["git", "checkout", "-b", "main"],
        cwd=git_repo.path,
        check=False,  # Don't fail if main already exists
        capture_output=True,
    )

    # Create and switch to a test branch
    subprocess.run(
        ["git", "checkout", "-b", "test-branch"],
        cwd=git_repo.path,
        check=True,
        capture_output=True,
    )

    # Make a commit on the branch
    test_file = git_repo.path / "test.txt"
    test_file.write_text("test content")

    subprocess.run(
        ["git", "add", "test.txt"],
        cwd=git_repo.path,
        check=True,
        capture_output=True,
    )

    subprocess.run(
        ["git", "commit", "-m", "Add test file"],
        cwd=git_repo.path,
        check=True,
        capture_output=True,
    )

    # Switch back to main and merge
    subprocess.run(
        ["git", "checkout", "main"],
        cwd=git_repo.path,
        check=True,
        capture_output=True,
    )

    subprocess.run(
        ["git", "merge", "--ff-only", "test-branch"],
        cwd=git_repo.path,
        check=True,
        capture_output=True,
    )

    # Execute
    result = verify_branch_merged_to_main(git_repo.path, "test-branch")

    # Assert
    assert result is True


def test_verify_branch_merged_to_main_not_merged(git_repo) -> None:
    """Test verify_branch_merged_to_main when branch was not merged."""
    # Setup - create a branch with a commit but don't merge it
    import subprocess

    # Ensure we're on main branch (create it if needed)
    subprocess.run(
        ["git", "checkout", "-b", "main"],
        cwd=git_repo.path,
        check=False,  # Don't fail if main already exists
        capture_output=True,
    )

    subprocess.run(
        ["git", "checkout", "-b", "unmerged-branch"],
        cwd=git_repo.path,
        check=True,
        capture_output=True,
    )

    test_file = git_repo.path / "test.txt"
    test_file.write_text("unmerged content")

    subprocess.run(
        ["git", "add", "test.txt"],
        cwd=git_repo.path,
        check=True,
        capture_output=True,
    )

    subprocess.run(
        ["git", "commit", "-m", "Unmerged commit"],
        cwd=git_repo.path,
        check=True,
        capture_output=True,
    )

    # Switch back to main without merging
    subprocess.run(
        ["git", "checkout", "main"],
        cwd=git_repo.path,
        check=True,
        capture_output=True,
    )

    # Execute
    result = verify_branch_merged_to_main(git_repo.path, "unmerged-branch")

    # Assert
    assert result is False


def test_verify_branch_merged_to_main_invalid_branch(git_repo) -> None:
    """Test verify_branch_merged_to_main with non-existent branch."""
    # Execute and assert
    with pytest.raises(RepoUtilsError, match="Failed to verify merge"):
        verify_branch_merged_to_main(git_repo.path, "nonexistent-branch")
