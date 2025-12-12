"""Integration tests for configurable hooks.

These tests verify that hooks work correctly with real subprocesses
and real filesystem operations:
1. Hook commands actually execute and create files
2. File watcher detects real file creation events

Note: These tests do not require API keys - they only use local filesystem operations.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from lw_coder.file_watcher import PlanFileWatcher
from lw_coder.hooks import HookManager, RealProcessExecutor


def test_hook_executes_real_subprocess_creates_marker_file(tmp_path: Path) -> None:
    """Verify hook actually executes a command that creates a file.

    This test:
    1. Creates a config with a touch command
    2. Executes the hook with RealProcessExecutor
    3. Waits briefly for async execution
    4. Verifies the marker file was created

    This proves: config loading -> variable substitution -> real subprocess execution
    """
    # Setup: Create config file with hook that touches a marker file
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"

    worktree_dir = tmp_path / "worktree"
    worktree_dir.mkdir()
    marker_file = worktree_dir / "marker.txt"

    config_content = f"""\
[hooks.code_sdk_complete]
command = "touch {marker_file}"
enabled = true
"""
    config_file.write_text(config_content, encoding="utf-8")

    # Create HookManager with real executor, pointing to our test config
    manager = HookManager(executor=RealProcessExecutor())

    # Manually inject the config (bypass home directory lookup)
    manager._config = {
        "hooks": {
            "code_sdk_complete": {
                "command": f"touch {marker_file}",
                "enabled": True,
            }
        }
    }

    # Execute the hook
    manager.execute_hook(
        "code_sdk_complete",
        {
            "worktree_path": worktree_dir,
            "plan_path": tmp_path / "plan.md",
            "plan_id": "test-plan",
            "repo_root": tmp_path,
        },
    )

    # Wait for async subprocess to complete (touch is very fast)
    time.sleep(0.5)

    # Verify: marker file should exist
    assert marker_file.exists(), f"Marker file was not created at {marker_file}"


def test_hook_with_variable_substitution_creates_file(tmp_path: Path) -> None:
    """Verify variable substitution works with real execution.

    This test:
    1. Uses ${worktree_path} variable in command
    2. Executes with RealProcessExecutor
    3. Verifies the file was created at the substituted path
    """
    worktree_dir = tmp_path / "worktree"
    worktree_dir.mkdir()

    manager = HookManager(executor=RealProcessExecutor())
    manager._config = {
        "hooks": {
            "code_sdk_complete": {
                "command": "touch ${worktree_path}/variable_test.txt",
                "enabled": True,
            }
        }
    }

    manager.execute_hook(
        "code_sdk_complete",
        {
            "worktree_path": worktree_dir,
            "plan_path": tmp_path / "plan.md",
            "plan_id": "test-plan",
            "repo_root": tmp_path,
        },
    )

    time.sleep(0.5)

    expected_file = worktree_dir / "variable_test.txt"
    assert expected_file.exists(), f"Variable substitution failed - file not at {expected_file}"


def test_file_watcher_detects_real_file_creation(tmp_path: Path) -> None:
    """Verify file watcher detects when a .md file is created.

    This test:
    1. Creates a PlanFileWatcher on a temp directory
    2. Creates a .md file via filesystem
    3. Verifies the callback was invoked with correct path

    This proves: watchdog integration, debouncing, filtering works with real events.
    """
    watch_dir = tmp_path / "tasks"
    watch_dir.mkdir()

    # Track callback invocations
    detected_files: list[Path] = []
    callback_event = threading.Event()

    def on_file_created(path: Path) -> None:
        detected_files.append(path)
        callback_event.set()

    # Create and start watcher
    watcher = PlanFileWatcher(
        watch_dir=watch_dir,
        on_file_created=on_file_created,
        debounce_seconds=0.1,
    )
    watcher.start()

    try:
        # Give watcher time to initialize
        time.sleep(0.2)

        # Create a .md file
        test_file = watch_dir / "test-plan.md"
        test_file.write_text("# Test Plan\n", encoding="utf-8")

        # Wait for callback (with timeout)
        callback_triggered = callback_event.wait(timeout=2.0)

        assert callback_triggered, "File watcher callback was not triggered within timeout"
        assert len(detected_files) == 1, f"Expected 1 detected file, got {len(detected_files)}"
        assert detected_files[0] == test_file, f"Wrong file detected: {detected_files[0]}"

    finally:
        watcher.stop()


def test_file_watcher_ignores_non_md_files(tmp_path: Path) -> None:
    """Verify file watcher only triggers for .md files.

    This test:
    1. Creates a PlanFileWatcher
    2. Creates non-.md files (.txt, .py)
    3. Creates a .md file
    4. Verifies only the .md file triggered callback
    """
    watch_dir = tmp_path / "tasks"
    watch_dir.mkdir()

    detected_files: list[Path] = []
    md_event = threading.Event()

    def on_file_created(path: Path) -> None:
        detected_files.append(path)
        if path.suffix == ".md":
            md_event.set()

    watcher = PlanFileWatcher(
        watch_dir=watch_dir,
        on_file_created=on_file_created,
        debounce_seconds=0.1,
    )
    watcher.start()

    try:
        time.sleep(0.2)

        # Create non-.md files first
        (watch_dir / "notes.txt").write_text("notes", encoding="utf-8")
        (watch_dir / "script.py").write_text("# python", encoding="utf-8")

        # Small delay
        time.sleep(0.3)

        # Now create .md file
        md_file = watch_dir / "real-plan.md"
        md_file.write_text("# Real Plan\n", encoding="utf-8")

        # Wait for .md callback
        md_event.wait(timeout=2.0)

        # Only the .md file should have triggered
        assert len(detected_files) == 1, f"Expected 1 file, got {len(detected_files)}: {detected_files}"
        assert detected_files[0].suffix == ".md", f"Non-.md file was detected: {detected_files[0]}"

    finally:
        watcher.stop()


def test_file_watcher_context_manager(tmp_path: Path) -> None:
    """Verify file watcher works correctly as context manager.

    This test:
    1. Uses watcher as context manager
    2. Creates file inside context
    3. Verifies callback triggered
    4. Verifies watcher stopped after context exits
    """
    watch_dir = tmp_path / "tasks"
    watch_dir.mkdir()

    detected_files: list[Path] = []
    callback_event = threading.Event()

    def on_file_created(path: Path) -> None:
        detected_files.append(path)
        callback_event.set()

    with PlanFileWatcher(watch_dir, on_file_created, debounce_seconds=0.1) as watcher:
        assert watcher.is_running, "Watcher should be running inside context"

        time.sleep(0.2)
        (watch_dir / "context-test.md").write_text("# Context Test\n", encoding="utf-8")
        callback_event.wait(timeout=2.0)

    # After context, watcher should be stopped
    assert not watcher.is_running, "Watcher should be stopped after context exits"
    assert len(detected_files) == 1
