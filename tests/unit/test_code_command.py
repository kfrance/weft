"""Tests for code_command module.

Focused tests for the code_command module. Per CLAUDE.md, we don't test
interactive commands extensively - integration smoke tests cover the happy path.
These tests focus on:
- Pure function tests (_filter_env_vars)
- Critical error path tests with minimal mocking
- Patch capture workflow test (happy path with mocked SDK and CLI)
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import lw_coder.code_command as code_command
from lw_coder.code_command import _filter_env_vars, run_code_command
from lw_coder.patch_utils import EmptyPatchError, PatchCaptureError
from lw_coder.plan_validator import PlanValidationError
from lw_coder.worktree_utils import WorktreeError
from conftest import write_plan


def test_run_code_command_validation_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with plan validation failure."""
    # Setup
    plan_path = tmp_path / "plan.md"

    # Mock load_plan_metadata to raise PlanValidationError
    def mock_load_plan_metadata(path):
        raise PlanValidationError("Invalid git_sha")

    # Apply monkeypatch
    monkeypatch.setattr(code_command, "load_plan_metadata", mock_load_plan_metadata)

    # Execute
    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    # Assert
    assert exit_code == 1
    assert "Plan validation failed" in caplog.text
    assert "Invalid git_sha" in caplog.text


def test_run_code_command_worktree_failure(monkeypatch, caplog, git_repo) -> None:
    """Test run_code_command with worktree preparation failure.

    Uses git_repo fixture for real git operations. Mocks load_prompts (required
    for claude-code tool to proceed) and ensure_worktree (the failing component).
    """
    plan_path = git_repo.path / "test-plan.md"
    write_plan(plan_path, {
        "git_sha": git_repo.latest_commit(),
        "plan_id": "test-plan-fail",
        "status": "draft",
    })

    # Mock load_prompts so we can reach the worktree preparation step
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

    # Mock the failing component
    def mock_ensure_worktree(metadata):
        raise WorktreeError("Failed to create worktree")

    monkeypatch.setattr(code_command, "ensure_worktree", mock_ensure_worktree)

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "Worktree preparation failed" in caplog.text
    assert "Failed to create worktree" in caplog.text


def test_filter_env_vars_with_patterns(monkeypatch) -> None:
    """Test _filter_env_vars with wildcard patterns."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "key123")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://api.openrouter.ai")
    monkeypatch.setenv("OTHER_VAR", "value")

    result = _filter_env_vars(["OPENROUTER_*"])

    assert "OPENROUTER_API_KEY" in result
    assert "OPENROUTER_BASE_URL" in result
    assert "OTHER_VAR" not in result


def test_filter_env_vars_with_star(monkeypatch) -> None:
    """Test _filter_env_vars with * pattern (all vars)."""
    monkeypatch.setenv("VAR1", "value1")
    monkeypatch.setenv("VAR2", "value2")

    result = _filter_env_vars(["*"])

    assert "VAR1" in result
    assert "VAR2" in result
    assert len(result) > 2  # Should include all env vars


def test_filter_env_vars_no_matches(monkeypatch) -> None:
    """Test _filter_env_vars when no vars match."""
    result = _filter_env_vars(["NONEXISTENT_*"])

    assert result == {}


def test_code_command_error_when_sha_mismatch(git_repo, caplog) -> None:
    """Test run_code_command errors when plan SHA doesn't match HEAD.

    This is a critical safety feature that prevents coding against stale code.
    Uses git_repo fixture for real git operations - minimal mocking.
    """
    initial_sha = git_repo.latest_commit()
    extra_file = git_repo.path / "extra.txt"
    extra_file.write_text("extra", encoding="utf-8")
    git_repo.run("add", "extra.txt")
    git_repo.run("commit", "-m", "extra commit")
    head_sha = git_repo.latest_commit()
    assert head_sha != initial_sha

    plan_path = git_repo.path / "plan-mismatch.md"
    write_plan(
        plan_path,
        {
            "git_sha": initial_sha,
            "plan_id": "plan-mismatch",
            "status": "coding",
        },
    )

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "does not match repository HEAD" in caplog.text
    assert "uncommitted changes" in caplog.text or "rebasing" in caplog.text


class TestCodeCommandPatchCapture:
    """Tests for patch capture integration in code command."""

    def test_code_command_fails_on_empty_patch(self, monkeypatch, caplog, git_repo) -> None:
        """Test code command fails when SDK session produces no changes.

        Mocks the SDK session to succeed but capture_ai_patch raises EmptyPatchError
        because no files were modified.
        """
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-empty-patch",
            "status": "draft",
        })

        # Mock all the components needed to reach the patch capture step
        mock_prompts = {
            "main_prompt": "Main prompt content",
            "code_review_auditor": "Code review prompt",
            "plan_alignment_checker": "Plan alignment prompt",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        # Create a mock worktree path
        worktree_path = git_repo.path / ".lw_coder" / "worktrees" / "test-empty-patch"
        worktree_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        # Mock capture_ai_patch to raise EmptyPatchError
        def mock_capture_ai_patch(wt_path):
            raise EmptyPatchError("SDK session produced no changes.")

        monkeypatch.setattr(code_command, "capture_ai_patch", mock_capture_ai_patch)

        caplog.set_level(logging.ERROR)
        exit_code = run_code_command(plan_path)

        assert exit_code == 1
        assert "no changes" in caplog.text.lower()

    def test_code_command_fails_on_patch_capture_error(self, monkeypatch, caplog, git_repo) -> None:
        """Test code command fails when patch capture encounters a git error.

        Mocks capture_ai_patch to raise PatchCaptureError simulating git failure.
        """
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-patch-error",
            "status": "draft",
        })

        mock_prompts = {
            "main_prompt": "Main prompt content",
            "code_review_auditor": "Code review prompt",
            "plan_alignment_checker": "Plan alignment prompt",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        worktree_path = git_repo.path / ".lw_coder" / "worktrees" / "test-patch-error"
        worktree_path.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(code_command, "ensure_worktree", lambda m: worktree_path)

        def mock_capture_ai_patch(wt_path):
            raise PatchCaptureError("Git command failed: mock error")

        monkeypatch.setattr(code_command, "capture_ai_patch", mock_capture_ai_patch)

        caplog.set_level(logging.ERROR)
        exit_code = run_code_command(plan_path)

        assert exit_code == 1
        assert "Failed to capture AI changes" in caplog.text

    def test_code_command_patch_capture_workflow(self, monkeypatch, caplog, git_repo) -> None:
        """Test happy path: SDK session creates changes, patch is captured.

        This test verifies the complete patch capture workflow:
        - SDK session runs and creates file changes
        - Patch is captured and saved to session directory
        - Worktree has no staged changes after capture
        - code_sdk_complete hook is called after patch is saved
        """
        plan_path = git_repo.path / "test-plan.md"
        write_plan(plan_path, {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "test-workflow",
            "status": "draft",
        })

        # Mock prompts
        mock_prompts = {
            "main_prompt": "Implement the feature",
            "code_review_auditor": "Code review prompt",
            "plan_alignment_checker": "Plan alignment prompt",
        }
        monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)

        # Track worktree path and simulate file changes in SDK session
        worktree_paths_used: list[Path] = []

        def mock_ensure_worktree(metadata: Any) -> Path:
            """Create a real worktree for the test."""
            worktree_path = git_repo.path / ".lw_coder" / "worktrees" / metadata.plan_id
            worktree_path.mkdir(parents=True, exist_ok=True)

            # Initialize as a git worktree
            git_repo.run("worktree", "add", str(worktree_path), "HEAD")
            worktree_paths_used.append(worktree_path)
            return worktree_path

        monkeypatch.setattr(code_command, "ensure_worktree", mock_ensure_worktree)

        # Mock SDK session to create file changes in the worktree
        def mock_sdk_session(*args: Any, **kwargs: Any) -> str:
            """Simulate SDK session that creates file changes."""
            worktree_path = kwargs.get("worktree_path") or args[0]
            # Create a new file to simulate AI-generated changes
            new_file = worktree_path / "new_feature.py"
            new_file.write_text("def new_feature():\n    return 'implemented'\n", encoding="utf-8")
            return "mock-session-id-workflow"

        monkeypatch.setattr(code_command, "run_sdk_session_sync", mock_sdk_session)

        # Track hook calls
        hook_calls: list[tuple[str, dict]] = []

        def mock_trigger_hook(hook_name: str, context: dict) -> None:
            hook_calls.append((hook_name, context.copy()))

        monkeypatch.setattr(code_command, "trigger_hook", mock_trigger_hook)

        # Mock subprocess.run to skip CLI resume (returns success)
        original_subprocess_run = subprocess.run

        def mock_subprocess_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
            # Skip actual CLI execution but allow git commands
            if isinstance(cmd, list) and len(cmd) > 0:
                if cmd[0] == "git":
                    return original_subprocess_run(cmd, *args, **kwargs)
                # For CLI resume commands (claude -r ...), return success
                return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")
            return original_subprocess_run(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

        # Execute
        caplog.set_level(logging.INFO)
        exit_code = run_code_command(plan_path)

        # Verify exit code
        assert exit_code == 0, f"Expected success, got exit code {exit_code}"

        # Verify patch file exists in session directory
        session_dir = git_repo.path / ".lw_coder" / "sessions" / "test-workflow" / "code"
        patch_path = session_dir / "ai_changes.patch"
        assert patch_path.exists(), f"Patch file should exist at {patch_path}"

        # Verify patch content contains the changes
        patch_content = patch_path.read_text(encoding="utf-8")
        assert "new_feature.py" in patch_content, "Patch should contain new_feature.py"
        assert "def new_feature" in patch_content, "Patch should contain the function definition"

        # Verify worktree has no staged changes
        assert len(worktree_paths_used) > 0, "Should have used a worktree"
        worktree_path = worktree_paths_used[0]
        result = subprocess.run(
            ["git", "diff", "--cached", "--stat"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.stdout.strip() == "", "Worktree should have no staged changes after capture"

        # Verify code_sdk_complete hook was called
        sdk_complete_calls = [c for c in hook_calls if c[0] == "code_sdk_complete"]
        assert len(sdk_complete_calls) == 1, "code_sdk_complete hook should be called exactly once"

        # Verify hook context
        hook_context = sdk_complete_calls[0][1]
        assert "worktree_path" in hook_context
        assert "plan_path" in hook_context
        assert "plan_id" in hook_context
        assert hook_context["plan_id"] == "test-workflow"

        # Cleanup worktree
        try:
            git_repo.run("worktree", "remove", "--force", str(worktree_path))
        except subprocess.CalledProcessError:
            pass  # Cleanup is best-effort
