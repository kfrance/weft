"""Tests for Docker image build."""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_dockerfile_builds_successfully() -> None:
    """Test that the Dockerfile builds successfully."""
    # Find the Dockerfile
    dockerfile_dir = Path(__file__).parent.parent / "docker" / "droid"
    dockerfile = dockerfile_dir / "Dockerfile"

    assert dockerfile.exists(), f"Dockerfile not found at {dockerfile}"

    # Attempt to build the Docker image
    result = subprocess.run(
        ["docker", "build", "-t", "lw_coder_droid:latest", str(dockerfile_dir)],
        capture_output=True,
        text=True,
    )

    # Check that build succeeded
    assert result.returncode == 0, f"Docker build failed:\n{result.stderr}"
    assert "Successfully tagged lw_coder_droid:latest" in result.stdout or result.returncode == 0


def test_droid_runs_in_container() -> None:
    """Smoke test: verify droid binary actually runs inside the container.

    This catches issues like:
    - Binary incompatibility (glibc vs musl)
    - Missing dependencies
    - PATH configuration
    - Permission issues
    """
    # Run droid --version inside the container
    result = subprocess.run(
        ["docker", "run", "--rm", "lw_coder_droid:latest", "droid", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # Check that droid executed successfully
    assert result.returncode == 0, (
        f"Droid failed to run in container:\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    # Verify we got a version number
    assert result.stdout.strip(), "Droid produced no output"
    # Version should be like "0.19.1"
    assert any(char.isdigit() for char in result.stdout), (
        f"Droid output doesn't look like a version: {result.stdout}"
    )
