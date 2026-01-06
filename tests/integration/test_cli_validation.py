"""Integration tests for CLI validation via subprocess.

These tests verify CLI validation behavior by invoking weft as a subprocess
and checking exit codes and error messages. This tests the full CLI stack
without mocking, catching issues that unit tests might miss.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path



def run_weft(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run weft CLI as a subprocess and return the result.

    Args:
        *args: Command-line arguments to pass to weft.
        cwd: Working directory for the subprocess. Defaults to current directory.

    Returns:
        CompletedProcess with stdout, stderr, and returncode.
    """
    return subprocess.run(
        ["uv", "run", "weft", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


class TestCliValidation:
    """Integration tests for CLI parameter validation."""

    def test_cli_rejects_droid_with_model(self, tmp_path: Path) -> None:
        """Test that --tool droid with --model returns exit code 1 with correct error."""
        # Create a minimal plan file
        plan_file = tmp_path / "test.md"
        plan_file.write_text("# Test Plan\n")

        result = run_weft(
            "code",
            str(plan_file),
            "--tool", "droid",
            "--model", "sonnet",
            cwd=tmp_path,
        )

        assert result.returncode == 1
        assert "cannot be used with --tool droid" in result.stderr

    def test_cli_rejects_invalid_tool(self, tmp_path: Path) -> None:
        """Test that --tool invalid-tool returns exit code 1 with correct error."""
        # Create a minimal plan file
        plan_file = tmp_path / "test.md"
        plan_file.write_text("# Test Plan\n")

        result = run_weft(
            "code",
            str(plan_file),
            "--tool", "invalid-tool",
            cwd=tmp_path,
        )

        assert result.returncode == 1
        assert "Unknown tool" in result.stderr

    def test_cli_rejects_invalid_model(self, tmp_path: Path) -> None:
        """Test that --model gpt-4 returns exit code 1 with correct error."""
        # Create a minimal plan file
        plan_file = tmp_path / "test.md"
        plan_file.write_text("# Test Plan\n")

        result = run_weft(
            "code",
            str(plan_file),
            "--model", "gpt-4",
            cwd=tmp_path,
        )

        assert result.returncode == 1
        assert "Unknown model" in result.stderr

    def test_cli_rejects_plan_path_and_text(self, tmp_path: Path) -> None:
        """Test that both plan_path and --text returns exit code 1 with correct error."""
        # Create a minimal plan file
        plan_file = tmp_path / "test.md"
        plan_file.write_text("# Test Plan\n")

        # Initialize git repo for --text to work
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        result = run_weft(
            "code",
            str(plan_file),
            "--text", "Fix something",
            cwd=tmp_path,
        )

        assert result.returncode == 1
        assert "mutually exclusive" in result.stderr


class TestCliInitCommand:
    """Integration tests for init command."""

    def test_init_fails_outside_git_repo(self) -> None:
        """Test that weft init outside git repo returns exit code 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Ensure no .git directory exists
            result = run_weft("init", cwd=Path(tmpdir))

            assert result.returncode == 1
            # Should fail with a git-related error (could be various messages)
            assert any(
                msg in result.stderr.lower()
                for msg in ["git", "repository", "not a git"]
            ), f"Expected git-related error, got: {result.stderr}"

    def test_init_force_yes_completes(self, tmp_path: Path) -> None:
        """Test that weft init --force --yes succeeds non-interactively."""
        # Initialize a git repository
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        # Create initial commit
        (tmp_path / "README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        result = run_weft("init", "--force", "--yes", cwd=tmp_path)

        assert result.returncode == 0, f"init failed: {result.stderr}"
        # Verify .weft directory was created
        weft_dir = tmp_path / ".weft"
        assert weft_dir.exists(), ".weft directory should be created"
