"""Test execution via Claude Code SDK.

This module handles running tests before and after implementation using
the Claude Code SDK in headless mode. Tests are delegated to Claude Code
which reads CLAUDE.md for test instructions.

Test failures are DATA, not errors - the eval command succeeds even if tests fail.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from .claude_session import ClaudeSessionError, run_headless_session
from .host_runner import get_weft_src_dir
from .logging_config import get_logger
from .patch_utils import PatchApplicationError, apply_patch
from .plan_validator import extract_front_matter

logger = get_logger(__name__)

# JSON schema for test results
TEST_RESULT_SCHEMA = {
    "type": "object",
    "required": ["command", "exit_code", "total_tests"],
    "properties": {
        "command": {"type": "string"},
        "exit_code": {"type": "integer"},
        "total_tests": {"type": "integer"},
        "passed_tests": {"type": "integer"},
        "failed_tests": {"type": "integer"},
        "failed_test_details": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test_name": {"type": "string"},
                    "file": {"type": "string"},
                    "error_message": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
        "analysis": {"type": "string"},
        "possible_solutions": {"type": "array", "items": {"type": "string"}},
        "recommended_fix": {"type": "string"},
    },
}

# Test execution prompt template
TEST_EXECUTION_PROMPT = """# Test Execution for Evaluation

You need to run all tests in this codebase and report the results in a structured format.

## Instructions

1. **Check CLAUDE.md**: Look for the CLAUDE.md file in the repository root. This file should contain instructions on how to run tests for this project.

2. **Run all tests**: Execute ALL test types documented in CLAUDE.md:
   - Unit tests
   - Integration tests
   - End-to-end tests
   - Any other test categories

   If CLAUDE.md lists multiple test commands or categories, run them all.

   **IMPORTANT**: When using uv commands, always include the `--no-cache` parameter to ensure fresh package resolution.

3. **Collect results**: Observe the test execution and collect:
   - The command(s) you ran
   - The exit code
   - Total number of tests
   - Number of passed tests
   - Number of failed tests
   - Details of any failed tests (test name, error message, file location)

4. **Create output file**: Write the results to `test_results.json` in the current directory with this exact schema:
   ```json
   {
     "command": "the full test command you ran",
     "exit_code": 0,
     "total_tests": 45,
     "passed_tests": 45,
     "failed_tests": 0,
     "failed_test_details": [
       {
         "test_name": "test_example",
         "file": "tests/test_example.py",
         "error_message": "AssertionError: expected X but got Y"
       }
     ],
     "summary": "Brief summary of test results",
     "analysis": "Your analysis of what the test results mean",
     "possible_solutions": ["Solution 1", "Solution 2"],
     "recommended_fix": "Your recommendation for addressing any failures"
   }
   ```

5. **Handle failures**: If tests fail, that's okay - capture the failure details in the JSON. Don't treat test failures as errors in your execution.

## Important Notes

- If CLAUDE.md is missing or doesn't document test commands, write a JSON file with an error message explaining this
- Don't make assumptions about the test framework (pytest, unittest, jest, etc.) - let CLAUDE.md guide you
- If multiple commands are needed, run them all and combine the results
- The analysis, possible_solutions, and recommended_fix fields should contain YOUR insights about the test results
"""


class TestRunnerError(Exception):
    """Raised when test execution fails."""

    pass


def validate_test_results(results_path: Path) -> dict[str, Any]:
    """Validate test results JSON file against schema.

    Args:
        results_path: Path to the test_results.json file

    Returns:
        Parsed and validated test results dictionary

    Raises:
        TestRunnerError: If file is invalid or doesn't match schema
    """
    if not results_path.exists():
        raise TestRunnerError(f"Test results file not found: {results_path}")

    try:
        content = results_path.read_text(encoding="utf-8")
        results = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TestRunnerError(f"Invalid JSON in test results: {exc}") from exc
    except OSError as exc:
        raise TestRunnerError(f"Failed to read test results: {exc}") from exc

    # Validate required fields
    required_fields = ["command", "exit_code", "total_tests"]
    missing_fields = [f for f in required_fields if f not in results]
    if missing_fields:
        raise TestRunnerError(
            f"Test results missing required fields: {missing_fields}"
        )

    # Validate field types
    if not isinstance(results.get("command"), str):
        raise TestRunnerError("Test results 'command' must be a string")
    if not isinstance(results.get("exit_code"), int):
        raise TestRunnerError("Test results 'exit_code' must be an integer")
    if not isinstance(results.get("total_tests"), int):
        raise TestRunnerError("Test results 'total_tests' must be an integer")

    logger.info(
        "Test results validated: %d total, %d passed, %d failed",
        results.get("total_tests", 0),
        results.get("passed_tests", 0),
        results.get("failed_tests", 0),
    )

    return results


def run_tests_via_sdk(
    worktree_path: Path,
    output_file: Path,
    model: str,
) -> dict[str, Any]:
    """Run tests in a worktree using Claude Code SDK.

    Args:
        worktree_path: Path to the worktree where tests should run
        output_file: Path where test_results.json should be created
        model: Model to use for Claude Code SDK

    Returns:
        Validated test results dictionary

    Raises:
        TestRunnerError: If SDK fails or output is invalid
    """
    src_dir = get_weft_src_dir()
    sdk_settings_path = src_dir / "sdk_settings.json"

    if not sdk_settings_path.exists():
        raise TestRunnerError(
            f"SDK settings file not found at {sdk_settings_path}. "
            "Ensure the package is properly installed."
        )

    # The SDK will create test_results.json in the worktree root
    expected_output = worktree_path / "test_results.json"

    try:
        run_headless_session(
            worktree_path=worktree_path,
            prompt=TEST_EXECUTION_PROMPT,
            model=model,
            expected_output=expected_output,
            sdk_settings_path=sdk_settings_path,
        )
    except ClaudeSessionError as exc:
        raise TestRunnerError(f"Test execution via SDK failed: {exc}") from exc

    # Validate and parse results
    results = validate_test_results(expected_output)

    # Copy results to the requested output location if different
    if output_file != expected_output:
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(results, indent=2), encoding="utf-8"
            )
            # Clean up the worktree copy
            expected_output.unlink(missing_ok=True)
        except OSError as exc:
            raise TestRunnerError(f"Failed to save test results: {exc}") from exc

    return results


def get_plan_git_sha(plan_path: Path) -> Optional[str]:
    """Extract git_sha from plan file.

    Args:
        plan_path: Path to the plan file

    Returns:
        The git_sha value or None if not found/invalid
    """
    try:
        content = plan_path.read_text(encoding="utf-8")
        front_matter, _ = extract_front_matter(content)
        git_sha = front_matter.get("git_sha")
        if isinstance(git_sha, str) and len(git_sha) >= 7:
            return git_sha.strip()
    except Exception as exc:
        logger.warning("Failed to extract git_sha from plan: %s", exc)
    return None


def validate_git_sha(repo_root: Path, sha: str) -> bool:
    """Validate that a git SHA exists in the repository.

    Args:
        repo_root: Repository root directory
        sha: Git SHA to validate

    Returns:
        True if SHA is valid and exists, False otherwise
    """
    try:
        # Use git cat-file -e to verify the object actually exists
        # git rev-parse --verify only checks format, not existence
        result = subprocess.run(
            ["git", "cat-file", "-e", sha],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def run_before_tests(
    plan_path: Path,
    plan_id: str,
    repo_root: Path,
    output_dir: Path,
    model: str,
) -> Optional[dict[str, Any]]:
    """Run tests in the "before" state (at plan's git_sha commit).

    Args:
        plan_path: Path to the plan file
        plan_id: Plan identifier
        repo_root: Repository root directory
        output_dir: Directory where test_results_before.json should be saved
        model: Model to use for Claude Code SDK

    Returns:
        Test results dictionary, or None if before-tests were skipped

    Raises:
        TestRunnerError: If test execution fails (not if tests themselves fail)
    """
    # Get git_sha from plan
    git_sha = get_plan_git_sha(plan_path)
    if not git_sha:
        logger.warning("Plan's git_sha not found. Skipping before-tests.")
        return None

    # Validate SHA exists
    if not validate_git_sha(repo_root, git_sha):
        logger.warning(
            "Plan's git_sha '%s' not found in repository. Skipping before-tests.",
            git_sha,
        )
        return None

    # Create temporary worktree at git_sha
    temp_worktree = repo_root / ".weft" / "temp-worktrees" / f"{plan_id}-before"

    try:
        # Clean up any existing temp worktree
        if temp_worktree.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(temp_worktree)],
                cwd=repo_root,
                capture_output=True,
                check=False,
            )

        # Create worktree at the specific SHA
        logger.info("Creating temporary worktree at %s for before-tests...", git_sha[:7])
        result = subprocess.run(
            ["git", "worktree", "add", str(temp_worktree), git_sha],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise TestRunnerError(
                f"Failed to create worktree at {git_sha}: {result.stderr}"
            )

        # Run tests in temp worktree
        output_file = output_dir / "test_results_before.json"
        results = run_tests_via_sdk(temp_worktree, output_file, model)

        logger.info(
            "Before tests: %d total, %d passed, %d failed",
            results.get("total_tests", 0),
            results.get("passed_tests", 0),
            results.get("failed_tests", 0),
        )

        return results

    finally:
        # Clean up temp worktree
        if temp_worktree.exists():
            logger.debug("Cleaning up temporary worktree...")
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(temp_worktree)],
                cwd=repo_root,
                capture_output=True,
                check=False,
            )


def run_after_tests(
    plan_path: Path,
    plan_id: str,
    repo_root: Path,
    output_dir: Path,
    model: str,
) -> dict[str, Any]:
    """Run tests in the "after" state using AI patch applied to git_sha.

    Creates a temporary worktree at the plan's git_sha, applies the AI-generated
    patch from the code session, runs tests, and cleans up the temporary worktree.

    Args:
        plan_path: Path to the plan file
        plan_id: Plan identifier
        repo_root: Repository root directory
        output_dir: Directory where test_results_after.json should be saved
        model: Model to use for Claude Code SDK

    Returns:
        Test results dictionary

    Raises:
        TestRunnerError: If test execution fails (not if tests themselves fail)
    """
    # Get git_sha from plan
    git_sha = get_plan_git_sha(plan_path)
    if not git_sha:
        raise TestRunnerError(
            "Plan's git_sha not found. Cannot run after-tests without a valid git_sha."
        )

    # Validate SHA exists
    if not validate_git_sha(repo_root, git_sha):
        raise TestRunnerError(
            f"Plan's git_sha '{git_sha}' not found in repository."
        )

    # Check that patch file exists
    patch_path = repo_root / ".weft" / "sessions" / plan_id / "code" / "ai_changes.patch"
    if not patch_path.exists():
        raise TestRunnerError(
            f"AI patch file not found: {patch_path}. "
            f"Run 'weft code {plan_id}' first to generate the patch."
        )

    # Create temporary worktree at git_sha
    temp_worktree = repo_root / ".weft" / "temp-worktrees" / f"{plan_id}-after"

    try:
        # Clean up any existing temp worktree
        if temp_worktree.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(temp_worktree)],
                cwd=repo_root,
                capture_output=True,
                check=False,
            )

        # Create worktree at the specific SHA
        logger.info("Creating temporary worktree at %s for after-tests...", git_sha[:7])
        result = subprocess.run(
            ["git", "worktree", "add", str(temp_worktree), git_sha],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise TestRunnerError(
                f"Failed to create worktree at {git_sha}: {result.stderr}"
            )

        # Apply the AI patch to the temp worktree
        logger.info("Applying AI patch to temporary worktree...")
        try:
            apply_patch(patch_path, temp_worktree)
        except PatchApplicationError as exc:
            raise TestRunnerError(
                f"Failed to apply AI patch: {exc}"
            ) from exc

        # Run tests in temp worktree
        output_file = output_dir / "test_results_after.json"
        results = run_tests_via_sdk(temp_worktree, output_file, model)

        logger.info(
            "After tests: %d total, %d passed, %d failed",
            results.get("total_tests", 0),
            results.get("passed_tests", 0),
            results.get("failed_tests", 0),
        )

        return results

    finally:
        # Clean up temp worktree (even on failure)
        if temp_worktree.exists():
            logger.debug("Cleaning up temporary worktree...")
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(temp_worktree)],
                cwd=repo_root,
                capture_output=True,
                check=False,
            )
