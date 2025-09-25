from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


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
