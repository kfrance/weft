"""Shared test helpers for weft tests.

This module provides common utilities used across unit and integration tests.
Test files should import directly from this module to avoid circular import
issues that previously caused code duplication across conftest files.

Example:
    from tests.helpers import GitRepo, write_plan
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class GitRepo:
    """Git repository helper for tests.

    Provides convenience methods for running git commands in a test repository.
    Used by the git_repo fixture in tests/conftest.py.

    Attributes:
        path: Path to the repository root.
    """
    path: Path

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run a git command in this repository.

        Args:
            *args: Arguments to pass to git (e.g., "status", "-s").

        Returns:
            CompletedProcess with captured stdout/stderr.

        Raises:
            subprocess.CalledProcessError: If the command fails.
        """
        return subprocess.run(
            ["git", *args],
            cwd=self.path,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def latest_commit(self) -> str:
        """Get the SHA of the latest commit.

        Returns:
            The full SHA of HEAD.
        """
        return self.run("rev-parse", "HEAD").stdout.strip()


def write_plan(path: Path, data: dict, body: str = "# Plan Body") -> None:
    """Write a plan file with YAML front matter.

    Creates a plan file in the standard weft format with YAML front matter
    separated by --- markers.

    Args:
        path: Path where the plan file will be written.
        data: Dictionary containing the YAML front matter data.
        body: Markdown body content for the plan. Defaults to "# Plan Body".

    Example:
        write_plan(
            tmp_path / "my-plan.md",
            {"plan_id": "my-plan", "status": "draft", "git_sha": "abc123"},
            body="# Implementation Plan\\n\\nDetails here..."
        )
    """
    yaml_block = yaml.safe_dump(data, sort_keys=False).strip()
    content = f"---\n{yaml_block}\n---\n\n{body}\n"
    path.write_text(content, encoding="utf-8")


__all__ = ["GitRepo", "write_plan"]
