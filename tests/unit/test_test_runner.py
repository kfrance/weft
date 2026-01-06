"""Tests for test_runner module."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from weft.test_runner import (
    TestRunnerError,
    get_plan_git_sha,
    run_after_tests,
    run_before_tests,
    run_tests_via_sdk,
    validate_git_sha,
    validate_test_results,
)


class TestValidateTestResults:
    """Tests for validate_test_results function."""

    def test_valid_results_pass_validation(self, tmp_path: Path) -> None:
        """Valid test results JSON passes validation."""
        results_file = tmp_path / "test_results.json"
        results = {
            "command": "uv run pytest",
            "exit_code": 0,
            "total_tests": 45,
            "passed_tests": 45,
            "failed_tests": 0,
        }
        results_file.write_text(json.dumps(results), encoding="utf-8")

        validated = validate_test_results(results_file)

        assert validated["command"] == "uv run pytest"
        assert validated["exit_code"] == 0
        assert validated["total_tests"] == 45

    def test_raises_when_file_not_found(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when results file doesn't exist."""
        missing_file = tmp_path / "missing.json"

        with pytest.raises(TestRunnerError, match="Test results file not found"):
            validate_test_results(missing_file)

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when file contains invalid JSON."""
        results_file = tmp_path / "test_results.json"
        results_file.write_text("not valid json {", encoding="utf-8")

        with pytest.raises(TestRunnerError, match="Invalid JSON"):
            validate_test_results(results_file)

    def test_raises_on_missing_required_fields(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when required fields are missing."""
        results_file = tmp_path / "test_results.json"
        results = {"exit_code": 0}  # Missing command and total_tests
        results_file.write_text(json.dumps(results), encoding="utf-8")

        with pytest.raises(TestRunnerError, match="missing required fields"):
            validate_test_results(results_file)

    def test_raises_on_invalid_field_type_command(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when command is not a string."""
        results_file = tmp_path / "test_results.json"
        results = {"command": 123, "exit_code": 0, "total_tests": 10}
        results_file.write_text(json.dumps(results), encoding="utf-8")

        with pytest.raises(TestRunnerError, match="'command' must be a string"):
            validate_test_results(results_file)

    def test_raises_on_invalid_field_type_exit_code(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when exit_code is not an integer."""
        results_file = tmp_path / "test_results.json"
        results = {"command": "pytest", "exit_code": "0", "total_tests": 10}
        results_file.write_text(json.dumps(results), encoding="utf-8")

        with pytest.raises(TestRunnerError, match="'exit_code' must be an integer"):
            validate_test_results(results_file)

    def test_raises_on_invalid_field_type_total_tests(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when total_tests is not an integer."""
        results_file = tmp_path / "test_results.json"
        results = {"command": "pytest", "exit_code": 0, "total_tests": "many"}
        results_file.write_text(json.dumps(results), encoding="utf-8")

        with pytest.raises(TestRunnerError, match="'total_tests' must be an integer"):
            validate_test_results(results_file)

    def test_optional_fields_accepted(self, tmp_path: Path) -> None:
        """Optional fields are accepted when present."""
        results_file = tmp_path / "test_results.json"
        results = {
            "command": "pytest tests/",
            "exit_code": 1,
            "total_tests": 10,
            "passed_tests": 8,
            "failed_tests": 2,
            "failed_test_details": [
                {"test_name": "test_fail", "file": "tests/test.py", "error_message": "Error"}
            ],
            "summary": "2 tests failed",
            "analysis": "Some analysis",
            "possible_solutions": ["Fix 1", "Fix 2"],
            "recommended_fix": "Do this",
        }
        results_file.write_text(json.dumps(results), encoding="utf-8")

        validated = validate_test_results(results_file)

        assert validated["passed_tests"] == 8
        assert validated["failed_tests"] == 2
        assert len(validated["failed_test_details"]) == 1


class TestGetPlanGitSha:
    """Tests for get_plan_git_sha function."""

    def test_extracts_git_sha_from_plan(self, tmp_path: Path) -> None:
        """Extracts git_sha from plan file front matter."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("""---
plan_id: test-plan
git_sha: abc123def456
status: coding
---

# Test Plan
""", encoding="utf-8")

        sha = get_plan_git_sha(plan_file)

        assert sha == "abc123def456"

    def test_returns_none_when_git_sha_missing(self, tmp_path: Path) -> None:
        """Returns None when git_sha is not in front matter."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("""---
plan_id: test-plan
status: coding
---

# Test Plan
""", encoding="utf-8")

        sha = get_plan_git_sha(plan_file)

        assert sha is None

    def test_returns_none_for_short_sha(self, tmp_path: Path) -> None:
        """Returns None when git_sha is too short (< 7 chars)."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("""---
plan_id: test-plan
git_sha: abc
status: coding
---

# Test Plan
""", encoding="utf-8")

        sha = get_plan_git_sha(plan_file)

        assert sha is None

    def test_returns_none_when_file_not_found(self, tmp_path: Path) -> None:
        """Returns None when plan file doesn't exist."""
        missing_file = tmp_path / "missing.md"

        sha = get_plan_git_sha(missing_file)

        assert sha is None


class TestValidateGitSha:
    """Tests for validate_git_sha function."""

    def test_valid_sha_returns_true(self, tmp_path: Path) -> None:
        """Returns True for a valid SHA in the repo."""
        # Create a git repo with a commit
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            check=True,
        )
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

        # Get the actual SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        sha = result.stdout.strip()

        assert validate_git_sha(tmp_path, sha) is True

    def test_invalid_sha_returns_false(self, tmp_path: Path) -> None:
        """Returns False for an invalid SHA."""
        # Create a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

        assert validate_git_sha(tmp_path, "0000000000000000") is False

    def test_non_repo_returns_false(self, tmp_path: Path) -> None:
        """Returns False when not in a git repo."""
        assert validate_git_sha(tmp_path, "abc123") is False


class TestRunTestsViaSdk:
    """Tests for run_tests_via_sdk function."""

    def test_success_returns_validated_results(self, tmp_path: Path) -> None:
        """Successful SDK run returns validated results."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        expected_output = worktree / "test_results.json"
        output_file = tmp_path / "output.json"

        # Mock SDK to create the expected output
        def mock_headless_session(**kwargs):
            expected_output.write_text(json.dumps({
                "command": "pytest",
                "exit_code": 0,
                "total_tests": 5,
            }), encoding="utf-8")
            return expected_output

        with patch("weft.test_runner.run_headless_session", side_effect=mock_headless_session):
            with patch("weft.test_runner.get_weft_src_dir") as mock_src:
                mock_src.return_value = tmp_path
                (tmp_path / "sdk_settings.json").write_text("{}")

                results = run_tests_via_sdk(worktree, output_file, "haiku")

        assert results["command"] == "pytest"
        assert results["exit_code"] == 0
        assert results["total_tests"] == 5

    def test_raises_when_sdk_settings_missing(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when SDK settings file is missing."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        with patch("weft.test_runner.get_weft_src_dir") as mock_src:
            mock_src.return_value = tmp_path  # No sdk_settings.json

            with pytest.raises(TestRunnerError, match="SDK settings file not found"):
                run_tests_via_sdk(worktree, tmp_path / "output.json", "haiku")

    def test_raises_on_sdk_failure(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when SDK session fails."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        from weft.claude_session import ClaudeSessionError

        with patch("weft.test_runner.run_headless_session") as mock_session:
            mock_session.side_effect = ClaudeSessionError("SDK error")

            with patch("weft.test_runner.get_weft_src_dir") as mock_src:
                mock_src.return_value = tmp_path
                (tmp_path / "sdk_settings.json").write_text("{}")

                with pytest.raises(TestRunnerError, match="Test execution via SDK failed"):
                    run_tests_via_sdk(worktree, tmp_path / "output.json", "haiku")


class TestRunBeforeTests:
    """Tests for run_before_tests function."""

    def test_returns_none_when_git_sha_missing(self, tmp_path: Path) -> None:
        """Returns None when plan has no git_sha."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("""---
plan_id: test-plan
status: coding
---

# Test Plan
""", encoding="utf-8")

        result = run_before_tests(
            plan_path=plan_file,
            plan_id="test-plan",
            repo_root=tmp_path,
            output_dir=tmp_path,
            model="haiku",
        )

        assert result is None

    def test_returns_none_when_git_sha_invalid(self, tmp_path: Path) -> None:
        """Returns None when git_sha is not found in repo."""
        # Create a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

        plan_file = tmp_path / "plan.md"
        # Use a SHA that doesn't match the all-zeros format git recognizes
        plan_file.write_text("""---
plan_id: test-plan
git_sha: deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
status: coding
---

# Test Plan
""", encoding="utf-8")

        result = run_before_tests(
            plan_path=plan_file,
            plan_id="test-plan",
            repo_root=tmp_path,
            output_dir=tmp_path,
            model="haiku",
        )

        assert result is None


class TestRunAfterTests:
    """Tests for run_after_tests function with patch-based worktree.

    The run_after_tests function now creates a temp worktree at git_sha,
    applies the AI patch, and runs tests there (instead of using the plan worktree).
    """

    def _create_git_repo(self, tmp_path: Path) -> str:
        """Create a git repo and return the initial commit SHA."""
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            check=True,
        )
        test_file = tmp_path / "test.txt"
        test_file.write_text("initial content")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def test_raises_when_git_sha_missing(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when plan has no git_sha."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("""---
plan_id: test-plan
status: coding
---

# Test Plan
""", encoding="utf-8")

        with pytest.raises(TestRunnerError, match="git_sha not found"):
            run_after_tests(
                plan_path=plan_file,
                plan_id="test-plan",
                repo_root=tmp_path,
                output_dir=tmp_path,
                model="haiku",
            )

    def test_raises_when_patch_missing(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when patch file doesn't exist."""
        sha = self._create_git_repo(tmp_path)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text(f"""---
plan_id: test-plan
git_sha: {sha}
status: coding
---

# Test Plan
""", encoding="utf-8")

        with pytest.raises(TestRunnerError, match="AI patch file not found"):
            run_after_tests(
                plan_path=plan_file,
                plan_id="test-plan",
                repo_root=tmp_path,
                output_dir=tmp_path,
                model="haiku",
            )

    def test_raises_when_git_sha_invalid(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when git_sha doesn't exist in repo."""
        self._create_git_repo(tmp_path)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("""---
plan_id: test-plan
git_sha: deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
status: coding
---

# Test Plan
""", encoding="utf-8")

        with pytest.raises(TestRunnerError, match="not found in repository"):
            run_after_tests(
                plan_path=plan_file,
                plan_id="test-plan",
                repo_root=tmp_path,
                output_dir=tmp_path,
                model="haiku",
            )

    def test_applies_patch_and_runs_tests(self, tmp_path: Path) -> None:
        """Creates temp worktree, applies patch, and runs tests."""
        sha = self._create_git_repo(tmp_path)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text(f"""---
plan_id: test-plan
git_sha: {sha}
status: coding
---

# Test Plan
""", encoding="utf-8")

        # Create patch file with a simple change
        patch_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "code"
        patch_dir.mkdir(parents=True)
        patch_file = patch_dir / "ai_changes.patch"
        # Simple patch that creates a new file
        patch_content = """diff --git a/new_file.txt b/new_file.txt
new file mode 100644
--- /dev/null
+++ b/new_file.txt
@@ -0,0 +1 @@
+new file content
"""
        patch_file.write_text(patch_content, encoding="utf-8")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Mock run_tests_via_sdk to verify it's called with temp worktree
        with patch("weft.test_runner.run_tests_via_sdk") as mock_run:
            mock_run.return_value = {
                "command": "pytest",
                "exit_code": 0,
                "total_tests": 10,
            }

            results = run_after_tests(
                plan_path=plan_file,
                plan_id="test-plan",
                repo_root=tmp_path,
                output_dir=output_dir,
                model="haiku",
            )

        assert results["total_tests"] == 10
        mock_run.assert_called_once()
        call_args = mock_run.call_args

        # Verify the worktree path is the temp worktree, not plan worktree
        worktree_arg = call_args[0][0]
        assert "temp-worktrees" in str(worktree_arg)
        assert "test-plan-after" in str(worktree_arg)

        # Verify temp worktree was cleaned up
        temp_worktree = tmp_path / ".weft" / "temp-worktrees" / "test-plan-after"
        assert not temp_worktree.exists(), "Temp worktree should be cleaned up"

    def test_cleans_up_temp_worktree_on_failure(self, tmp_path: Path) -> None:
        """Temp worktree is cleaned up even when tests fail."""
        sha = self._create_git_repo(tmp_path)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text(f"""---
plan_id: test-plan
git_sha: {sha}
status: coding
---

# Test Plan
""", encoding="utf-8")

        # Create patch file
        patch_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "code"
        patch_dir.mkdir(parents=True)
        patch_file = patch_dir / "ai_changes.patch"
        patch_file.write_text("""diff --git a/new.txt b/new.txt
new file mode 100644
--- /dev/null
+++ b/new.txt
@@ -0,0 +1 @@
+content
""", encoding="utf-8")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Mock run_tests_via_sdk to raise an error
        with patch("weft.test_runner.run_tests_via_sdk") as mock_run:
            mock_run.side_effect = TestRunnerError("Test execution failed")

            with pytest.raises(TestRunnerError):
                run_after_tests(
                    plan_path=plan_file,
                    plan_id="test-plan",
                    repo_root=tmp_path,
                    output_dir=output_dir,
                    model="haiku",
                )

        # Verify temp worktree was still cleaned up
        temp_worktree = tmp_path / ".weft" / "temp-worktrees" / "test-plan-after"
        assert not temp_worktree.exists(), "Temp worktree should be cleaned up even on failure"

    def test_raises_when_patch_conflicts(self, tmp_path: Path) -> None:
        """Raises TestRunnerError when patch cannot be applied."""
        sha = self._create_git_repo(tmp_path)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text(f"""---
plan_id: test-plan
git_sha: {sha}
status: coding
---

# Test Plan
""", encoding="utf-8")

        # Create a patch that modifies test.txt in a way that would conflict
        # with an invalid context (trying to modify a line that doesn't exist)
        patch_dir = tmp_path / ".weft" / "sessions" / "test-plan" / "code"
        patch_dir.mkdir(parents=True)
        patch_file = patch_dir / "ai_changes.patch"
        # Invalid patch - tries to modify content that doesn't exist
        patch_file.write_text("""diff --git a/test.txt b/test.txt
--- a/test.txt
+++ b/test.txt
@@ -1,3 +1,3 @@
-nonexistent line 1
-nonexistent line 2
-nonexistent line 3
+modified line 1
+modified line 2
+modified line 3
""", encoding="utf-8")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(TestRunnerError, match="Failed to apply AI patch"):
            run_after_tests(
                plan_path=plan_file,
                plan_id="test-plan",
                repo_root=tmp_path,
                output_dir=output_dir,
                model="haiku",
            )
