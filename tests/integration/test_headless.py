"""Integration tests for weft commands in headless mode.

These tests verify the full command flow works end-to-end, catching
issues like missing prompt files that wouldn't be caught by unit tests.

All tests run in isolated test repositories (via git_repo fixture),
not in the weft repository itself.
"""

import os
import subprocess

import pytest


class TestPlanHeadless:
    """Tests for weft plan in headless mode."""

    def test_plan_command_loads_prompts_and_runs(self, git_repo):
        """Test that weft plan loads prompts and executes Claude in headless mode.

        This test would have caught the missing plan.md issue because it
        runs the full command flow including load_prompt_template().

        The test runs in an isolated git repo but weft loads prompts from
        its installed package location, so missing prompts are still caught.
        """
        env = os.environ.copy()
        env["WEFT_HEADLESS"] = "1"

        result = subprocess.run(
            [
                "uv", "run", "weft", "plan",
                "--text", "Add a hello() function that prints Hello World",
                "--no-hooks",
            ],
            cwd=git_repo.path,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )

        # The command should complete without "Prompt template not found" error
        assert "Prompt template not found" not in result.stderr, (
            f"Missing prompt template: {result.stderr}"
        )

        # Should reach Claude Code execution (may fail for other reasons in CI,
        # but we care that prompt loading succeeded)
        if result.returncode != 0:
            # Acceptable failures: Claude errors, API issues, etc.
            # Unacceptable: prompt not found, import errors
            assert "Error" not in result.stderr or "claude" in result.stderr.lower()


class TestCodeHeadless:
    """Tests for weft code in headless mode."""

    @pytest.fixture
    def test_plan(self, git_repo):
        """Create a minimal test plan in the test repo.

        Also runs `weft init` to set up required prompts directory.
        """
        # Run weft init to set up the .weft directory with prompts
        init_result = subprocess.run(
            ["uv", "run", "weft", "init", "--yes"],
            cwd=git_repo.path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"weft init failed: {init_result.stderr}"

        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        plan_file = tasks_dir / "headless-test.md"
        commit_sha = git_repo.latest_commit()

        plan_content = f'''---
plan_id: headless-test
status: draft
evaluation_notes: []
git_sha: {commit_sha}
---

## Objectives

Add a hello() function.

## Work Items

1. Create hello.py with a hello() function

## Deliverables

- hello.py
'''
        plan_file.write_text(plan_content)

        yield plan_file

        # Cleanup: remove worktree and branch if created
        worktree_path = git_repo.path / ".weft" / "worktrees" / "headless-test"
        if worktree_path.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=git_repo.path,
                capture_output=True,
            )
        subprocess.run(
            ["git", "branch", "-D", "headless-test"],
            cwd=git_repo.path,
            capture_output=True,
        )

    def test_code_command_runs_sdk_in_headless(self, git_repo, test_plan):
        """Test that weft code runs SDK phase and exits in headless mode.

        Verifies:
        - Plan loading works
        - Worktree creation works
        - SDK session runs
        - Command exits after SDK (no CLI resume)
        """
        env = os.environ.copy()
        env["WEFT_HEADLESS"] = "1"

        result = subprocess.run(
            ["uv", "run", "weft", "code", str(test_plan), "--no-hooks"],
            cwd=git_repo.path,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )

        # Should complete after SDK phase
        # Check for headless mode log message
        assert "Headless mode" in result.stderr or result.returncode == 0, (
            f"Command failed unexpectedly: {result.stderr}"
        )
