# Integration test fixtures - see tests/conftest.py for shared fixtures

# Re-export helpers from parent conftest for backward compatibility with imports
# These are used as `from conftest import GitRepo, write_plan` in test files
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class GitRepo:
    """Git repository helper for tests.

    This class is duplicated from tests/conftest.py to avoid circular imports
    when test files do `from conftest import GitRepo`.
    """
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


def write_plan(path: Path, data: dict, body: str = "# Plan Body") -> None:
    """Helper function to write a plan file with YAML front matter.

    This function is duplicated from tests/conftest.py to avoid circular imports
    when test files do `from conftest import write_plan`.

    Args:
        path: Path where the plan file will be written.
        data: Dictionary containing the YAML front matter data.
        body: Markdown body content for the plan. Defaults to "# Plan Body".
    """
    yaml_block = yaml.safe_dump(data, sort_keys=False).strip()
    content = f"---\n{yaml_block}\n---\n\n{body}\n"
    path.write_text(content, encoding="utf-8")


__all__ = ["GitRepo", "write_plan"]
