"""Tests for worktree utility functions."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from weft.plan_validator import load_plan_metadata
from weft.worktree_utils import (
    WorktreeError,
    ensure_worktree,
    get_branch_name_from_plan_id,
    get_branch_tip,
    get_branch_worktree,
    get_worktree_path,
    has_uncommitted_changes,
    is_git_worktree,
)
from tests.helpers import write_plan


def test_get_branch_name_from_plan_id():
    assert get_branch_name_from_plan_id("my-plan") == "my-plan"
    assert get_branch_name_from_plan_id("feature-123") == "feature-123"


def test_is_git_worktree_nonexistent(git_repo):
    path = git_repo.path / ".weft" / "worktrees" / "nonexistent"
    assert not is_git_worktree(path, git_repo.path)


def test_is_git_worktree_directory_not_worktree(git_repo, tmp_path):
    # Create a regular directory
    regular_dir = tmp_path / "regular"
    regular_dir.mkdir()
    assert not is_git_worktree(regular_dir, git_repo.path)


def test_ensure_worktree_creates_new(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["Test worktree creation"],
            "plan_id": "test-create-worktree",
            "status": "draft",
        },
    )

    metadata = load_plan_metadata(plan_path)
    worktree_path = ensure_worktree(metadata)

    assert worktree_path.exists()
    assert is_git_worktree(worktree_path, git_repo.path)
    assert worktree_path == git_repo.path / ".weft" / "worktrees" / "test-create-worktree"

    # Verify branch exists and is at correct commit
    branch_name = "test-create-worktree"
    branch_tip = get_branch_tip(git_repo.path, branch_name)
    assert branch_tip == git_repo.latest_commit()


def test_ensure_worktree_reuses_existing(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["Test worktree reuse"],
            "plan_id": "test-reuse-worktree",
            "status": "draft",
        },
    )

    metadata = load_plan_metadata(plan_path)

    # Create worktree first time
    worktree_path1 = ensure_worktree(metadata)

    # Call again - should reuse
    worktree_path2 = ensure_worktree(metadata)

    assert worktree_path1 == worktree_path2
    assert worktree_path1.exists()


def test_ensure_worktree_fails_on_non_worktree_directory(git_repo):
    # Create a non-worktree directory at the expected path
    plan_id = "test-non-worktree"
    worktree_path = git_repo.path / ".weft" / "worktrees" / plan_id
    worktree_path.mkdir(parents=True)
    (worktree_path / "dummy.txt").write_text("not a worktree")

    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["Test non-worktree error"],
            "plan_id": plan_id,
            "status": "draft",
        },
    )

    metadata = load_plan_metadata(plan_path)

    with pytest.raises(WorktreeError, match="not a registered Git worktree"):
        ensure_worktree(metadata)


def test_ensure_worktree_fails_on_branch_mismatch(git_repo):
    # Create a branch with different commit
    plan_id = "test-branch-mismatch"
    branch_name = plan_id

    # Create a second commit
    (git_repo.path / "file2.txt").write_text("content")
    git_repo.run("add", "file2.txt")
    git_repo.run("commit", "-m", "second commit")
    second_commit = git_repo.latest_commit()

    # Create branch at second commit
    git_repo.run("branch", branch_name, second_commit)

    # But plan references first commit
    first_commit = git_repo.run("rev-parse", "HEAD~1").stdout.strip()

    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": first_commit,
            "evaluation_notes": ["Test branch mismatch"],
            "plan_id": plan_id,
            "status": "draft",
        },
    )

    metadata = load_plan_metadata(plan_path)

    with pytest.raises(WorktreeError, match="mismatched branch tip"):
        ensure_worktree(metadata)


def test_ensure_worktree_fails_on_branch_checked_out_elsewhere(git_repo):
    plan_id = "test-branch-elsewhere"
    branch_name = plan_id

    # Create the branch
    git_repo.run("branch", branch_name, git_repo.latest_commit())

    # Create a worktree for the branch at a different location
    other_worktree = git_repo.path / "other_worktree"
    git_repo.run("worktree", "add", str(other_worktree), branch_name)

    # Try to create worktree at expected location
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["Test branch elsewhere"],
            "plan_id": plan_id,
            "status": "draft",
        },
    )

    metadata = load_plan_metadata(plan_path)

    with pytest.raises(WorktreeError, match="already checked out in worktree"):
        ensure_worktree(metadata)


def test_get_branch_worktree_finds_existing(git_repo):
    branch_name = "test-find"
    git_repo.run("branch", branch_name, git_repo.latest_commit())

    worktree_path = git_repo.path / ".weft" / "worktrees" / "test-find"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    git_repo.run("worktree", "add", str(worktree_path), branch_name)

    found_path = get_branch_worktree(git_repo.path, branch_name)
    assert found_path == worktree_path


def test_get_branch_worktree_returns_none_if_not_found(git_repo):
    found_path = get_branch_worktree(git_repo.path, "nonexistent-branch")
    assert found_path is None


def test_get_branch_tip_returns_sha(git_repo):
    # Get current branch name
    current_branch = git_repo.run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    tip = get_branch_tip(git_repo.path, current_branch)
    assert tip == git_repo.latest_commit()
    assert len(tip) == 40


def test_get_branch_tip_returns_none_for_nonexistent(git_repo):
    tip = get_branch_tip(git_repo.path, "nonexistent-branch")
    assert tip is None


def test_ensure_worktree_creates_intermediate_directories(git_repo):
    """Test that ensure_worktree creates .weft/worktrees if it doesn't exist."""
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["Test intermediate dirs"],
            "plan_id": "test-intermediate",
            "status": "draft",
        },
    )

    # Ensure .weft/worktrees doesn't exist
    worktrees_dir = git_repo.path / ".weft" / "worktrees"
    if worktrees_dir.exists():
        import shutil
        shutil.rmtree(worktrees_dir)

    metadata = load_plan_metadata(plan_path)
    worktree_path = ensure_worktree(metadata)

    assert worktree_path.exists()
    assert worktree_path.parent.exists()  # .weft/worktrees
    assert worktree_path.parent.parent.exists()  # .weft


def test_get_worktree_path_rejects_path_traversal(git_repo):
    """Test that get_worktree_path rejects plan_ids with path traversal sequences."""
    with pytest.raises(WorktreeError, match="path traversal"):
        get_worktree_path(git_repo.path, "../../../etc")

    with pytest.raises(WorktreeError, match="path traversal"):
        get_worktree_path(git_repo.path, "test/../../../etc")

    with pytest.raises(WorktreeError, match="path traversal"):
        get_worktree_path(git_repo.path, "..test")


def test_get_worktree_path_valid_plan_ids(git_repo):
    """Test that valid plan_ids work correctly."""
    # These should all work fine
    path1 = get_worktree_path(git_repo.path, "test-plan")
    assert path1 == git_repo.path / ".weft" / "worktrees" / "test-plan"

    path2 = get_worktree_path(git_repo.path, "test_plan")
    assert path2 == git_repo.path / ".weft" / "worktrees" / "test_plan"

    path3 = get_worktree_path(git_repo.path, "test.plan")
    assert path3 == git_repo.path / ".weft" / "worktrees" / "test.plan"


def test_has_uncommitted_changes_with_changes(tmp_path: Path) -> None:
    """Test has_uncommitted_changes returns True when there are changes."""
    # Setup a git repo with uncommitted changes
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    # Assert
    assert has_uncommitted_changes(tmp_path) is True


def test_has_uncommitted_changes_clean_working_dir(tmp_path: Path) -> None:
    """Test has_uncommitted_changes returns False for clean working directory."""
    # Setup a git repo with no changes
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    subprocess.run(["git", "add", "test.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)

    # Assert
    assert has_uncommitted_changes(tmp_path) is False


def test_get_worktree_status_with_modified_and_untracked(tmp_path: Path) -> None:
    """Test get_worktree_status returns correct categorization of changes."""
    from weft.worktree_utils import get_worktree_status

    # Setup a git repo with both modified and untracked files
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

    # Create and commit a file
    tracked_file = tmp_path / "tracked.txt"
    tracked_file.write_text("original content")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)

    # Modify the tracked file
    tracked_file.write_text("modified content")

    # Create an untracked file
    untracked_file = tmp_path / "untracked.txt"
    untracked_file.write_text("new content")

    # Get status
    status = get_worktree_status(tmp_path)

    # Assert
    assert "tracked.txt" in status["modified"]
    assert "untracked.txt" in status["untracked"]
    assert len(status["modified"]) == 1
    assert len(status["untracked"]) == 1


def test_get_worktree_status_clean_directory(tmp_path: Path) -> None:
    """Test get_worktree_status returns empty lists for clean worktree."""
    from weft.worktree_utils import get_worktree_status

    # Setup a clean git repo
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    subprocess.run(["git", "add", "test.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)

    # Get status
    status = get_worktree_status(tmp_path)

    # Assert
    assert status["modified"] == []
    assert status["untracked"] == []


def test_get_worktree_status_various_change_types(tmp_path: Path) -> None:
    """Test get_worktree_status correctly categorizes various types of changes.

    Tests:
    - Modified tracked file (unstaged)
    - Staged new file
    - Staged modification
    - Deleted file
    - Untracked file
    """
    from weft.worktree_utils import get_worktree_status

    # Setup git repo with initial files
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)

    # Create and commit initial files
    (tmp_path / "will_modify.txt").write_text("original")
    (tmp_path / "will_stage_modify.txt").write_text("original")
    (tmp_path / "will_delete.txt").write_text("to be deleted")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)

    # Make various types of changes:
    # 1. Modify a tracked file (unstaged) - should be in "modified"
    (tmp_path / "will_modify.txt").write_text("modified content")

    # 2. Stage a modification - should be in "modified"
    (tmp_path / "will_stage_modify.txt").write_text("staged modification")
    subprocess.run(["git", "add", "will_stage_modify.txt"], cwd=tmp_path, check=True)

    # 3. Delete a tracked file - should be in "modified"
    (tmp_path / "will_delete.txt").unlink()

    # 4. Create and stage a new file - should be in "modified" (it's an 'A' status)
    (tmp_path / "new_staged.txt").write_text("new staged file")
    subprocess.run(["git", "add", "new_staged.txt"], cwd=tmp_path, check=True)

    # 5. Create an untracked file - should be in "untracked"
    (tmp_path / "untracked.txt").write_text("untracked content")

    # Get status
    status = get_worktree_status(tmp_path)

    # Assert - all tracked file changes go to "modified"
    assert "will_modify.txt" in status["modified"]
    assert "will_stage_modify.txt" in status["modified"]
    assert "will_delete.txt" in status["modified"]
    assert "new_staged.txt" in status["modified"]

    # Untracked files go to "untracked"
    assert "untracked.txt" in status["untracked"]

    # Verify counts
    assert len(status["modified"]) == 4
    assert len(status["untracked"]) == 1
