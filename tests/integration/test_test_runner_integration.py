"""Integration tests for test_runner module.

These tests verify that the test runner can execute Claude Code SDK
and produce valid test results JSON. They make actual API calls.

REQUIRED: This test is required to pass for task completion per plan.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lw_coder.test_runner import (
    TEST_RESULT_SCHEMA,
    TestRunnerError,
    run_tests_via_sdk,
    validate_test_results,
)


class TestTestRunnerIntegration:
    """Real integration tests that execute Claude Code SDK to run tests."""

    def test_sdk_runs_tests_and_produces_valid_json(self, tmp_path: Path):
        """SDK should run tests and produce valid JSON output.

        This test:
        1. Creates a minimal Python project with tests
        2. Runs Claude Code SDK to execute those tests
        3. Verifies the output JSON is valid and contains expected fields

        REQUIRED: This test must pass for task completion.
        """
        # Create a minimal project with CLAUDE.md and tests
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Create CLAUDE.md with test instructions
        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text("""# Test Project

## Development Commands
- **Run tests**: `python -m pytest tests/ -v`

## Testing
This project uses pytest for testing. Run tests with:
```
python -m pytest tests/ -v
```
""")

        # Create a minimal test file
        tests_dir = project_dir / "tests"
        tests_dir.mkdir()

        test_file = tests_dir / "test_simple.py"
        test_file.write_text("""\"\"\"Simple tests for integration testing.\"\"\"

def test_addition():
    assert 1 + 1 == 2

def test_string_concat():
    assert "hello" + " " + "world" == "hello world"

def test_list_append():
    items = [1, 2, 3]
    items.append(4)
    assert items == [1, 2, 3, 4]
""")

        # Create sdk_settings.json
        sdk_settings = project_dir / "sdk_settings.json"
        sdk_settings.write_text('{"sandbox": {"enabled": true}}')

        # Create output file path
        output_file = tmp_path / "test_results.json"

        # Run the test runner
        results = run_tests_via_sdk(
            worktree_path=project_dir,
            output_file=output_file,
            model="haiku",  # Cheapest/fastest model
        )

        # Verify results
        assert results is not None
        assert isinstance(results, dict)

        # Verify required fields
        assert "command" in results
        assert "exit_code" in results
        assert "total_tests" in results

        # Verify types
        assert isinstance(results["command"], str)
        assert isinstance(results["exit_code"], int)
        assert isinstance(results["total_tests"], int)

        # Verify output file exists
        assert output_file.exists()

        # Verify file content matches
        file_content = json.loads(output_file.read_text(encoding="utf-8"))
        assert file_content["command"] == results["command"]
        assert file_content["exit_code"] == results["exit_code"]

        # Verify our tests were detected
        # We created 3 tests, so total_tests should be >= 3
        assert results["total_tests"] >= 3

    def test_sdk_handles_test_failures_as_data(self, tmp_path: Path):
        """SDK should capture test failures as data, not errors.

        Test failures are DATA, not errors - eval command succeeds even if tests fail.
        This test verifies that failing tests result in valid JSON with failure details.
        """
        # Create project with failing tests
        project_dir = tmp_path / "failing_project"
        project_dir.mkdir()

        # Create CLAUDE.md
        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text("""# Test Project

## Development Commands
- **Run tests**: `python -m pytest tests/ -v`
""")

        # Create tests with intentional failures
        tests_dir = project_dir / "tests"
        tests_dir.mkdir()

        test_file = tests_dir / "test_failing.py"
        test_file.write_text("""\"\"\"Tests with intentional failures.\"\"\"

def test_passing():
    assert 1 == 1

def test_failing():
    assert 1 == 2, "This test is designed to fail"

def test_another_passing():
    assert "hello" == "hello"
""")

        # Create sdk_settings.json
        sdk_settings = project_dir / "sdk_settings.json"
        sdk_settings.write_text('{"sandbox": {"enabled": true}}')

        # Create output file path
        output_file = tmp_path / "test_results.json"

        # Run the test runner - should NOT raise even with test failures
        results = run_tests_via_sdk(
            worktree_path=project_dir,
            output_file=output_file,
            model="haiku",
        )

        # Verify results captured the failure
        assert results is not None
        assert isinstance(results, dict)

        # Verify we have failure data
        assert results["exit_code"] != 0  # Tests failed
        assert results.get("failed_tests", 0) >= 1  # At least one failure

        # Verify output file was created despite test failures
        assert output_file.exists()

    def test_validate_test_results_real_output(self, tmp_path: Path):
        """Validate that real SDK output passes our schema validation."""
        # Create minimal project
        project_dir = tmp_path / "minimal_project"
        project_dir.mkdir()

        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text("""# Test Project

## Development Commands
- **Run tests**: `python -m pytest tests/ -v`
""")

        tests_dir = project_dir / "tests"
        tests_dir.mkdir()

        test_file = tests_dir / "test_one.py"
        test_file.write_text("""def test_single(): assert True""")

        sdk_settings = project_dir / "sdk_settings.json"
        sdk_settings.write_text('{"sandbox": {"enabled": true}}')

        output_file = project_dir / "test_results.json"

        # Run SDK
        run_tests_via_sdk(
            worktree_path=project_dir,
            output_file=output_file,
            model="haiku",
        )

        # Validate the output passes schema validation
        validated_results = validate_test_results(output_file)

        # Verify validation passes
        assert validated_results is not None
        assert "command" in validated_results
        assert "exit_code" in validated_results
        assert "total_tests" in validated_results
