from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


@dataclass
class GitRepo:
    path: Path

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.path,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def latest_commit(self) -> str:
        return self.run("rev-parse", "HEAD").stdout.strip()


@pytest.fixture()
def git_repo(tmp_path: Path) -> GitRepo:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=repo_path, check=True)

    (repo_path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    return GitRepo(path=repo_path)


def write_plan(path: Path, data: dict, body: str = "# Plan Body") -> None:
    """Helper function to write a plan file with YAML front matter.

    Args:
        path: Path where the plan file will be written.
        data: Dictionary containing the YAML front matter data.
        body: Markdown body content for the plan. Defaults to "# Plan Body".
    """
    yaml_block = yaml.safe_dump(data, sort_keys=False).strip()
    content = f"---\n{yaml_block}\n---\n\n{body}\n"
    path.write_text(content, encoding="utf-8")


@pytest.fixture()
def mock_executor_factory():
    """Factory fixture for creating mock executors in tests."""
    def _factory(tool="claude-code"):
        """Create a mock executor for the specified tool.

        Args:
            tool: Tool name ("claude-code" or "droid").

        Returns:
            SimpleNamespace with mock executor methods.
        """
        if tool == "droid":
            return SimpleNamespace(
                check_auth=lambda: None,
                build_command=lambda p, model: f'droid "$(cat {p})"',
                get_env_vars=lambda factory_dir: {}
            )
        else:  # claude-code
            return SimpleNamespace(
                check_auth=lambda: None,
                build_command=lambda p, model: f'claude --model {model} "$(cat {p})"',
                get_env_vars=lambda factory_dir: {}
            )
    return _factory
