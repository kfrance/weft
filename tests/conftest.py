from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import lw_coder.hooks as hooks_module


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


@pytest.fixture(autouse=True)
def mock_sdk_runner(request, monkeypatch):
    """Auto-mock SDK runner to prevent real SDK calls in tests.

    This fixture is auto-used for all tests to ensure we never accidentally
    make real SDK API calls during testing. Returns a mock session ID.

    Tests marked with @pytest.mark.integration will skip this mock.
    """
    # Skip mocking for integration tests
    if request.node.get_closest_marker("integration"):
        return

    import lw_coder.code_command as code_command
    monkeypatch.setattr(
        code_command,
        "run_sdk_session_sync",
        lambda *args, **kwargs: "mock-session-id-12345"
    )


@pytest.fixture(autouse=True)
def reset_hooks_global_state(request, monkeypatch, tmp_path):
    """Reset hooks module global state before each test.

    This fixture:
    1. Resets _global_manager to None
    2. Monkeypatches Path.home to use tmp_path for non-integration tests

    This prevents tests from reading the user's real ~/.lw_coder/config.toml
    which might have hooks configured that open GUI applications (e.g., code-oss).

    Tests marked with @pytest.mark.integration will skip the Path.home mock
    but will still reset global state.
    """
    # Always reset global state before each test
    monkeypatch.setattr(hooks_module, "_global_manager", None)

    # For non-integration tests, also mock Path.home to prevent reading real config
    if not request.node.get_closest_marker("integration"):
        # Create a fake home directory with empty config
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir(exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

    yield

    # Clean up after test - reset global state again
    hooks_module._global_manager = None
