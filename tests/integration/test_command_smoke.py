"""Smoke tests that verify commands can complete setup without errors.

These tests run the full command initialization path but mock the final
execution step (subprocess.run in plan_command / code_command modules).
They catch:
- Missing imports
- Missing directories/files
- Configuration errors
- Validation issues

These tests would have caught the "droids directory not found" bug where
code referenced a directory that had been moved during refactoring.

NOTE: These tests run against the REAL lw_coder repository (not a temp repo)
because they need access to real project files like optimized_prompts/.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import lw_coder.code_command as code_command
import lw_coder.plan_command as plan_command
from lw_coder.code_command import run_code_command
from lw_coder.plan_command import run_plan_command
from lw_coder.repo_utils import find_repo_root


def _write_plan(path: Path, data: dict, body: str = "# Plan Body") -> None:
    """Write a plan file with YAML front matter."""
    yaml_block = yaml.safe_dump(data, sort_keys=False).strip()
    content = f"---\n{yaml_block}\n---\n\n{body}\n"
    path.write_text(content, encoding="utf-8")


def _get_head_sha(repo_root: Path) -> str:
    """Get current HEAD SHA."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.mark.integration
class TestPlanCommandSmoke:
    """Smoke tests for plan command setup phase."""

    def test_plan_command_setup_completes(self, monkeypatch):
        """Plan command setup completes without missing files/imports.

        This test exercises the full plan command initialization:
        - Executor loading and auth check
        - Template loading from prompts directory
        - Worktree creation
        - Plan subagent file writing
        - Host command building

        If any imports fail or directories are missing, this test will fail.
        """
        # Mock only subprocess.run in plan_command module (the interactive CLI part)
        # This allows git commands to still work via the real subprocess module
        subprocess_calls = []

        def mock_subprocess_run(*args, **kwargs):
            subprocess_calls.append((args, kwargs))
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(plan_command, "subprocess", SimpleNamespace(run=mock_subprocess_run))

        exit_code = run_plan_command(
            plan_path=None,
            text_input="Add a simple hello world function",
            tool="claude-code",
            no_hooks=True,
        )

        # If setup had missing imports/files, we'd get an exception before here
        assert exit_code == 0
        # Verify subprocess.run was actually called (command was built)
        assert len(subprocess_calls) > 0, "Expected subprocess.run to be called"


def _cleanup_worktree(repo_root: Path, plan_id: str) -> None:
    """Clean up worktree and branch created during test."""
    worktree_path = repo_root / ".lw_coder" / "worktrees" / plan_id
    if worktree_path.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_root,
            capture_output=True,
        )
    # Delete the branch
    subprocess.run(
        ["git", "branch", "-D", plan_id],
        cwd=repo_root,
        capture_output=True,
    )


@pytest.mark.integration
class TestCodeCommandSmoke:
    """Smoke tests for code command setup phase."""

    def test_code_command_setup_completes(self, monkeypatch, tmp_path):
        """Code command setup completes without missing files/imports.

        This test exercises the full code command initialization:
        - Plan validation and metadata loading
        - Session directory creation
        - Prompt loading from optimized_prompts
        - Worktree preparation
        - Sub-agent file writing
        - SDK settings loading
        - Host command building

        If any imports fail or directories are missing, this test will fail.
        """
        # Use real repo for prompts, create plan file in it temporarily
        repo_root = find_repo_root()
        plan_id = "test-smoke-temp"
        plan_path = repo_root / f"{plan_id}.md"
        head_sha = _get_head_sha(repo_root)

        try:
            _write_plan(plan_path, {
                "plan_id": plan_id,
                "git_sha": head_sha,
                "status": "draft",
            })

            # Mock SDK session (the API call part)
            monkeypatch.setattr(
                code_command,
                "run_sdk_session_sync",
                lambda **kw: "mock-session-id"
            )

            # Mock subprocess.run in code_command module (the interactive CLI part)
            subprocess_calls = []

            def mock_subprocess_run(*args, **kwargs):
                subprocess_calls.append((args, kwargs))
                return SimpleNamespace(returncode=0)

            monkeypatch.setattr(code_command, "subprocess", SimpleNamespace(run=mock_subprocess_run))

            exit_code = run_code_command(
                plan_path=plan_path,
                tool="claude-code",
                no_hooks=True,
            )

            # If setup had missing imports/files, we'd get an exception before here
            assert exit_code == 0
            # Verify subprocess.run was actually called (command was built)
            assert len(subprocess_calls) > 0, "Expected subprocess.run to be called"
        finally:
            # Clean up temporary plan file
            if plan_path.exists():
                plan_path.unlink()
            # Clean up worktree and branch
            _cleanup_worktree(repo_root, plan_id)
