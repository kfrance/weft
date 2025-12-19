"""Tests for patch_utils module.

Tests patch capture, save, and apply functionality used for
capturing AI-generated changes during SDK sessions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from weft.patch_utils import (
    EmptyPatchError,
    PatchApplicationError,
    PatchCaptureError,
    apply_patch,
    capture_ai_patch,
    save_patch,
)


class TestCaptureAiPatch:
    """Tests for capture_ai_patch function."""

    def test_capture_all_change_types(self, git_repo) -> None:
        """Test patch captures new files, modifications, and deletions."""
        # Create a new untracked file
        new_file = git_repo.path / "new_file.txt"
        new_file.write_text("new content\n", encoding="utf-8")

        # Modify an existing tracked file
        readme = git_repo.path / "README.md"
        readme.write_text("modified seed\n", encoding="utf-8")

        # Delete a tracked file (create one first, commit, then delete)
        to_delete = git_repo.path / "to_delete.txt"
        to_delete.write_text("will be deleted\n", encoding="utf-8")
        git_repo.run("add", "to_delete.txt")
        git_repo.run("commit", "-m", "add file to delete")
        to_delete.unlink()

        # Capture the patch
        patch_content = capture_ai_patch(git_repo.path)

        # Verify patch contains all change types
        assert "new_file.txt" in patch_content
        assert "new content" in patch_content
        assert "README.md" in patch_content
        assert "modified seed" in patch_content
        assert "to_delete.txt" in patch_content
        assert "deleted file" in patch_content.lower() or "diff --git" in patch_content

        # Verify worktree has no staged changes after capture
        result = git_repo.run("diff", "--cached", "--stat")
        assert result.stdout.strip() == "", "Worktree should have no staged changes"

    def test_capture_empty_raises_error(self, git_repo) -> None:
        """Test EmptyPatchError is raised when no changes exist."""
        # No changes in worktree
        with pytest.raises(EmptyPatchError) as exc_info:
            capture_ai_patch(git_repo.path)

        assert "no changes" in str(exc_info.value).lower()

    def test_capture_restores_state_on_error(self, git_repo, monkeypatch) -> None:
        """Test git reset is called even when git diff fails."""
        # Create a change to stage
        new_file = git_repo.path / "test.txt"
        new_file.write_text("test\n", encoding="utf-8")

        # Track calls to subprocess.run
        original_run = subprocess.run
        call_sequence = []

        def mock_run(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd)
            call_sequence.append(cmd_str)
            # Fail on diff --cached
            if "diff" in cmd and "--cached" in cmd:
                result = subprocess.CompletedProcess(
                    cmd, returncode=1, stdout="", stderr="mock diff error"
                )
                raise subprocess.CalledProcessError(1, cmd, stderr="mock diff error")
            return original_run(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run)

        with pytest.raises(PatchCaptureError):
            capture_ai_patch(git_repo.path)

        # Verify git reset was called after the failure
        reset_calls = [c for c in call_sequence if "reset" in c]
        assert len(reset_calls) > 0, "git reset should be called in finally block"


class TestSavePatch:
    """Tests for save_patch function."""

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """Test patch content is saved to file."""
        patch_content = "diff --git a/test.txt b/test.txt\n+new line"
        output_path = tmp_path / "patches" / "test.patch"

        result = save_patch(patch_content, output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8") == patch_content

    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test save_patch creates parent directories if needed."""
        patch_content = "diff content"
        output_path = tmp_path / "deep" / "nested" / "dir" / "test.patch"

        save_patch(patch_content, output_path)

        assert output_path.exists()


class TestApplyPatch:
    """Tests for apply_patch function."""

    def test_apply_success(self, git_repo) -> None:
        """Test successful patch application."""
        # Create a change, capture the patch, then reset
        test_file = git_repo.path / "test.txt"
        test_file.write_text("new content\n", encoding="utf-8")
        git_repo.run("add", "test.txt")

        # Get the patch
        result = git_repo.run("diff", "--cached")
        patch_content = result.stdout

        # Reset to clean state
        git_repo.run("reset", "HEAD")
        test_file.unlink()

        # Save patch to file
        patch_path = git_repo.path / "test.patch"
        patch_path.write_text(patch_content, encoding="utf-8")

        # Apply the patch
        apply_patch(patch_path, git_repo.path)

        # Verify the file was created
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == "new content\n"

    def test_apply_to_different_worktree(self, git_repo, tmp_path: Path) -> None:
        """Test applying patch from one location to another worktree."""
        # Create changes in main repo
        test_file = git_repo.path / "new_feature.py"
        test_file.write_text("def feature():\n    pass\n", encoding="utf-8")

        # Capture patch using capture_ai_patch
        patch_content = capture_ai_patch(git_repo.path)

        # Save patch
        patch_path = tmp_path / "feature.patch"
        save_patch(patch_content, patch_path)

        # Create a second worktree at the same commit
        second_worktree = tmp_path / "second_worktree"
        subprocess.run(
            ["git", "worktree", "add", str(second_worktree), "HEAD"],
            cwd=git_repo.path,
            check=True,
            capture_output=True,
        )

        try:
            # Apply patch to second worktree
            apply_patch(patch_path, second_worktree)

            # Verify file exists in second worktree
            assert (second_worktree / "new_feature.py").exists()
            assert (second_worktree / "new_feature.py").read_text(encoding="utf-8") == \
                "def feature():\n    pass\n"
        finally:
            # Cleanup
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(second_worktree)],
                cwd=git_repo.path,
                check=False,
                capture_output=True,
            )

    def test_apply_failure_on_conflict(self, git_repo) -> None:
        """Test PatchApplicationError on conflicting changes."""
        # Create a file and commit
        test_file = git_repo.path / "conflict.txt"
        test_file.write_text("original line 1\noriginal line 2\n", encoding="utf-8")
        git_repo.run("add", "conflict.txt")
        git_repo.run("commit", "-m", "add conflict.txt")

        # Create a modification and generate patch
        test_file.write_text("modified line 1\noriginal line 2\n", encoding="utf-8")
        git_repo.run("add", "conflict.txt")
        result = git_repo.run("diff", "--cached")
        patch_content = result.stdout
        git_repo.run("reset", "HEAD")

        # Make a different modification to the same lines (create conflict)
        test_file.write_text("conflicting line 1\noriginal line 2\n", encoding="utf-8")

        # Save patch
        patch_path = git_repo.path / "conflict.patch"
        patch_path.write_text(patch_content, encoding="utf-8")

        # Try to apply - should fail
        with pytest.raises(PatchApplicationError) as exc_info:
            apply_patch(patch_path, git_repo.path)

        assert "Failed to apply patch" in str(exc_info.value)

    def test_apply_missing_patch_file(self, git_repo) -> None:
        """Test PatchApplicationError when patch file doesn't exist."""
        nonexistent = git_repo.path / "nonexistent.patch"

        with pytest.raises(PatchApplicationError) as exc_info:
            apply_patch(nonexistent, git_repo.path)

        assert "not found" in str(exc_info.value).lower()
