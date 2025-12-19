"""Tests for file_watcher module."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from weft.file_watcher import PlanFileWatcher


class TestPlanFileWatcher:
    """Tests for PlanFileWatcher class."""

    def test_watcher_creates_directory_if_missing(self, tmp_path: Path) -> None:
        """Test that watcher creates watch directory if it doesn't exist."""
        watch_dir = tmp_path / "nonexistent" / "tasks"
        callback = MagicMock()

        watcher = PlanFileWatcher(watch_dir, callback)
        watcher.start()

        try:
            assert watch_dir.exists()
        finally:
            watcher.stop()

    def test_watcher_start_and_stop(self, tmp_path: Path) -> None:
        """Test watcher can be started and stopped."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        watcher = PlanFileWatcher(watch_dir, callback)

        assert not watcher.is_running
        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running

    def test_watcher_context_manager(self, tmp_path: Path) -> None:
        """Test watcher as context manager."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        with PlanFileWatcher(watch_dir, callback) as watcher:
            assert watcher.is_running

        assert not watcher.is_running

    def test_watcher_detects_md_file_creation(self, tmp_path: Path) -> None:
        """Test watcher detects .md file creation."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        with PlanFileWatcher(watch_dir, callback, debounce_seconds=0.01) as watcher:
            # Create a .md file
            test_file = watch_dir / "test-plan.md"
            test_file.write_text("# Test Plan\n")

            # Wait for watcher to process
            time.sleep(0.2)

        # Callback should have been called with the file path
        assert callback.called
        called_path = callback.call_args_list[0][0][0]
        assert called_path.name == "test-plan.md"
        assert called_path.parent == watch_dir

    def test_watcher_ignores_non_md_files(self, tmp_path: Path) -> None:
        """Test watcher ignores non-.md files."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        with PlanFileWatcher(watch_dir, callback, debounce_seconds=0.01) as watcher:
            # Create non-.md files
            (watch_dir / "test.txt").write_text("test")
            (watch_dir / "test.json").write_text("{}")
            (watch_dir / "test.py").write_text("# python")

            # Wait for watcher to process
            time.sleep(0.2)

        # Callback should not have been called
        assert callback.call_count == 0

    def test_watcher_ignores_directories(self, tmp_path: Path) -> None:
        """Test watcher ignores directory creation."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        with PlanFileWatcher(watch_dir, callback, debounce_seconds=0.01) as watcher:
            # Create a subdirectory
            (watch_dir / "subdir").mkdir()

            # Wait for watcher to process
            time.sleep(0.2)

        # Callback should not have been called
        assert callback.call_count == 0

    def test_watcher_ignores_empty_files(self, tmp_path: Path) -> None:
        """Test watcher ignores empty .md files."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        with PlanFileWatcher(watch_dir, callback, debounce_seconds=0.01) as watcher:
            # Create an empty .md file
            (watch_dir / "empty.md").touch()

            # Wait for watcher to process
            time.sleep(0.2)

        # Callback should not have been called for empty file
        assert callback.call_count == 0

    def test_watcher_handles_multiple_files(self, tmp_path: Path) -> None:
        """Test watcher handles multiple file creations."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        with PlanFileWatcher(watch_dir, callback, debounce_seconds=0.01) as watcher:
            # Create multiple .md files
            (watch_dir / "plan1.md").write_text("# Plan 1")
            time.sleep(0.05)
            (watch_dir / "plan2.md").write_text("# Plan 2")

            # Wait for watcher to process
            time.sleep(0.3)

        # Callback should have been called for each file
        assert len(callback.call_args_list) == 2
        called_paths = {call[0][0].name for call in callback.call_args_list}
        assert called_paths == {"plan1.md", "plan2.md"}

    def test_watcher_double_start_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Test that starting watcher twice logs a warning."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        watcher = PlanFileWatcher(watch_dir, callback)

        try:
            watcher.start()
            watcher.start()  # Second start should warn

            assert "already started" in caplog.text.lower()
        finally:
            watcher.stop()

    def test_watcher_stop_without_start(self, tmp_path: Path) -> None:
        """Test that stopping watcher without starting doesn't error."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        watcher = PlanFileWatcher(watch_dir, callback)
        # Should not raise
        watcher.stop()

    def test_watcher_handles_callback_exception(self, tmp_path: Path) -> None:
        """Test watcher continues after callback exception."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()

        callback = MagicMock(side_effect=[Exception("Callback error"), None])

        with PlanFileWatcher(watch_dir, callback, debounce_seconds=0.01) as watcher:
            # Create first file (callback will raise)
            (watch_dir / "plan1.md").write_text("# Plan 1")
            time.sleep(0.15)

            # Watcher should still be running
            assert watcher.is_running

            # Create second file (callback will succeed)
            (watch_dir / "plan2.md").write_text("# Plan 2")
            time.sleep(0.15)

        # Both files should have triggered callbacks
        assert len(callback.call_args_list) == 2
        called_paths = {call[0][0].name for call in callback.call_args_list}
        assert called_paths == {"plan1.md", "plan2.md"}

    def test_watcher_prevents_duplicate_triggers(self, tmp_path: Path) -> None:
        """Test watcher doesn't trigger twice for same file."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        with PlanFileWatcher(watch_dir, callback, debounce_seconds=0.01) as watcher:
            # Create file
            test_file = watch_dir / "plan.md"
            test_file.write_text("# Plan")

            # Wait and update the file
            time.sleep(0.15)

            # Modify the same file (should not trigger again)
            test_file.write_text("# Plan Updated")

            time.sleep(0.15)

        # Callback should only have been called once
        assert callback.call_count == 1

    def test_watcher_file_stem_extraction(self, tmp_path: Path) -> None:
        """Test that file path passed to callback has correct stem."""
        watch_dir = tmp_path / "tasks"
        watch_dir.mkdir()
        callback = MagicMock()

        with PlanFileWatcher(watch_dir, callback, debounce_seconds=0.01) as watcher:
            test_file = watch_dir / "my-test-plan.md"
            test_file.write_text("# Test Plan")

            time.sleep(0.2)

        assert callback.called
        called_path = callback.call_args_list[0][0][0]
        assert called_path.stem == "my-test-plan"
        assert called_path.suffix == ".md"
