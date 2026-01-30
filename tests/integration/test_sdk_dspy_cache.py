"""Integration tests for DSPy cache access via weft sandbox.

These tests verify that the weft sandbox configuration correctly grants
access to the DSPy cache directory at ~/.weft/dspy_cache/.

With the weft sandbox implementation:
- DSPy cache access is configured via [sandbox] read_write_paths in config.toml
- The bwrap wrapper mounts the cache directory with read-write access
- No dynamic SDK settings injection is needed
"""

from __future__ import annotations

from pathlib import Path

from weft.judge_executor import get_cache_dir
from weft.sandbox import SandboxConfig, build_bwrap_command, expand_path


def test_get_cache_dir_returns_expected_path() -> None:
    """Test that get_cache_dir() returns the expected location."""
    expected = Path.home() / ".weft" / "dspy_cache"
    assert get_cache_dir() == expected


def test_sandbox_config_with_dspy_cache_path(tmp_path: Path) -> None:
    """Test that sandbox config correctly handles DSPy cache path."""
    # Create sandbox config with DSPy cache path (as used in weft repo)
    # Config is created to verify SandboxConfig accepts the path without error
    SandboxConfig(
        read_write_paths=["~/.weft/dspy_cache"],
    )

    # Verify path is expanded correctly
    expanded = expand_path("~/.weft/dspy_cache")
    expected = str(Path.home() / ".weft" / "dspy_cache")
    assert expanded == expected


def test_bwrap_command_includes_dspy_cache(tmp_path: Path) -> None:
    """Test that bwrap command mounts DSPy cache directory."""
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    # Create config with DSPy cache path
    dspy_cache_path = str(get_cache_dir())
    config = SandboxConfig(
        read_write_paths=[dspy_cache_path],
    )

    # Build bwrap command
    cmd = build_bwrap_command("echo test", config, worktree)
    cmd_str = " ".join(cmd)

    # Verify DSPy cache is mounted with --bind (read-write)
    assert f"--bind {dspy_cache_path}" in cmd_str


def test_weft_repo_config_grants_dspy_cache_access(tmp_path: Path) -> None:
    """Test that standard weft repo config grants DSPy cache access.

    This verifies the config pattern used in .weft/config.toml:
    [sandbox]
    read_write_paths = ["~/.weft/dspy_cache", "~/.cache/uv"]
    """
    from weft.sandbox import load_sandbox_config

    # Create a config file mimicking weft's standard setup
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[sandbox]
read_write_paths = ["~/.weft/dspy_cache", "~/.cache/uv"]
disallowed_commands = ["git add:*", "git commit:*"]
""",
        encoding="utf-8",
    )

    # Load config
    config = load_sandbox_config(config_path)

    # Verify DSPy cache is in read_write_paths
    assert "~/.weft/dspy_cache" in config.read_write_paths

    # Build bwrap command and verify cache is mounted
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    cmd = build_bwrap_command("echo test", config, worktree)
    cmd_str = " ".join(cmd)

    # After path expansion, cache should be mounted with --bind
    dspy_cache_expanded = expand_path("~/.weft/dspy_cache")
    assert f"--bind {dspy_cache_expanded}" in cmd_str
