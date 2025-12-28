from __future__ import annotations

# IMPORTANT: Set NO_PROXY before any imports that might initialize httpx/litellm
# This prevents SOCKS proxy errors during test collection when litellm initializes
import os
os.environ["NO_PROXY"] = "*"

# TEMPORARY: Disable DSPy cache to avoid cache-related issues during testing
os.environ["DSPY_CACHEDIR"] = ""

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import weft.hooks as hooks_module

# Import shared test helpers from the dedicated module
from tests.helpers import GitRepo, write_plan


@pytest.fixture(scope="session", autouse=True)
def disable_dspy_cache():
    """Disable DSPy cache for all tests to avoid cache initialization issues.

    TEMPORARY: This disables DSPy caching during tests to work around
    SOCKS proxy issues during test collection/initialization.
    """
    try:
        import dspy
        # Disable both disk and memory cache
        dspy.configure_cache(
            enable_disk_cache=False,
            enable_memory_cache=False,
        )
    except ImportError:
        # DSPy not available, skip
        pass


def _is_integration_test(request: pytest.FixtureRequest) -> bool:
    """Check if the current test is an integration test based on file path.

    Integration tests are detected by their location in the tests/integration/
    directory rather than by pytest markers. This enables directory-based
    test organization where test type is determined solely by file location.

    Args:
        request: The pytest fixture request object.

    Returns:
        True if the test file is located under tests/integration/, False otherwise.
    """
    test_file = Path(request.fspath)
    return "tests/integration" in str(test_file) or "tests\\integration" in str(test_file)


@pytest.fixture()
def git_repo(tmp_path: Path) -> GitRepo:
    """Create an isolated git repository for testing.

    Creates a temporary git repository with an initial commit,
    suitable for testing functions that require a git context.

    Args:
        tmp_path: pytest's temporary directory fixture.

    Returns:
        GitRepo: A helper object for the test repository.
    """
    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "config", "user.email", "ci@example.com"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "CI"], cwd=repo_path, check=True)

    (repo_path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    return GitRepo(path=repo_path)


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
def isolate_cwd(request, tmp_path, monkeypatch):
    """Isolate current working directory to prevent tests from operating in real repo.

    Changes CWD to tmp_path for unit tests. This prevents functions like
    find_repo_root() from accidentally finding the real weft repository
    when called without an explicit path argument.

    Integration tests (in tests/integration/) skip this isolation since they
    may need to access real project files.
    """
    if _is_integration_test(request):
        return
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def mock_sdk_runner(request, monkeypatch):
    """Auto-mock SDK runner to prevent real SDK calls in tests.

    This fixture is auto-used for all tests to ensure we never accidentally
    make real SDK API calls during testing. Returns a mock session ID.

    Integration tests (in tests/integration/) skip this mock.
    """
    # Skip mocking for integration tests (detected by file path)
    if _is_integration_test(request):
        return

    import weft.code_command as code_command
    monkeypatch.setattr(
        code_command,
        "run_sdk_session_sync",
        lambda *args, **kwargs: "mock-session-id-12345"
    )


@pytest.fixture(autouse=True)
def isolate_config(request, monkeypatch, tmp_path):
    """Isolate config file access to prevent tests from reading user's config.

    This fixture mocks CONFIG_PATH in the config module to use a non-existent
    path in tmp_path. This ensures tests use hardcoded defaults rather than
    reading from ~/.weft/config.toml.

    Integration tests (in tests/integration/) skip this mock.
    """
    if _is_integration_test(request):
        return

    import weft.config as config_module
    monkeypatch.setattr(
        config_module,
        "CONFIG_PATH",
        tmp_path / "nonexistent_config" / "config.toml"
    )


@pytest.fixture(autouse=True)
def reset_hooks_global_state(request, monkeypatch, tmp_path):
    """Reset hooks module global state before each test.

    This fixture:
    1. Resets _global_manager to None
    2. Monkeypatches Path.home to use tmp_path for non-integration tests

    This prevents tests from reading the user's real ~/.weft/config.toml
    which might have hooks configured that open GUI applications (e.g., code-oss).

    Integration tests (in tests/integration/) skip the Path.home mock
    but will still reset global state.
    """
    # Always reset global state before each test
    monkeypatch.setattr(hooks_module, "_global_manager", None)

    # For non-integration tests, also mock Path.home to prevent reading real config
    if not _is_integration_test(request):
        # Create a fake home directory with empty config
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir(exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: fake_home)

    yield

    # Clean up after test - reset global state again
    hooks_module._global_manager = None


# Re-export helpers for convenience (test files should import from tests.helpers directly)
__all__ = ["GitRepo", "write_plan", "git_repo", "mock_executor_factory"]
