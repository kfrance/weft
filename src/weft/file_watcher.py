"""File watcher for detecting plan file creation.

This module provides a file watcher that monitors the .weft/tasks/ directory
for new plan files during interactive sessions, triggering the plan_file_created hook.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class PlanFileEventHandler(FileSystemEventHandler):
    """Event handler for plan file creation detection.

    Filters for .md files, applies debouncing, and triggers callback.
    Handles both direct file creation and rename/move operations (Claude Code
    creates .tmp files and renames them to .md).
    """

    def __init__(
        self,
        callback: Callable[[Path], None],
        debounce_seconds: float = 0.1,
    ) -> None:
        """Initialize the event handler.

        Args:
            callback: Function to call when a plan file is created.
            debounce_seconds: Time to wait after file creation before triggering.
        """
        super().__init__()
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._lock = threading.Lock()
        self._triggered_files: set[str] = set()

    def _handle_new_file(self, path: Path) -> None:
        """Handle a new .md file (from creation or move/rename).

        Args:
            path: Path to the new file.
        """
        # Only process .md files
        if path.suffix.lower() != ".md":
            return

        # Prevent duplicate triggering for the same file
        with self._lock:
            if str(path) in self._triggered_files:
                return
            self._triggered_files.add(str(path))

        # Debounce: wait for file to be fully written
        time.sleep(self._debounce_seconds)

        # Verify file exists and has content
        try:
            if not path.exists():
                logger.debug("File no longer exists after debounce: %s", path)
                return

            if path.stat().st_size == 0:
                logger.debug("File is empty, skipping: %s", path)
                return
        except OSError as exc:
            logger.debug("Error checking file status: %s", exc)
            return

        # Trigger callback
        try:
            logger.debug("Triggering callback for new plan file: %s", path)
            self._callback(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Callback failed for %s: %s", path, exc)

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation event.

        Args:
            event: The file system event.
        """
        if event.is_directory:
            return

        path = Path(event.src_path)
        logger.debug("on_created event: %s", path)
        self._handle_new_file(path)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename event.

        Claude Code creates .tmp files and renames them to .md, so we need
        to watch for move events to detect plan file creation.

        Args:
            event: The file system event with src_path and dest_path.
        """
        if event.is_directory:
            return

        # For move events, dest_path is the new location
        dest_path = Path(event.dest_path)
        logger.debug("on_moved event: %s -> %s", event.src_path, dest_path)
        self._handle_new_file(dest_path)


class PlanFileWatcher:
    """Watches for plan file creation in a directory.

    Uses watchdog library for cross-platform file watching.
    """

    def __init__(
        self,
        watch_dir: Path,
        on_file_created: Callable[[Path], None],
        debounce_seconds: float = 0.1,
    ) -> None:
        """Initialize the file watcher.

        Args:
            watch_dir: Directory to watch for new files.
            on_file_created: Callback function when a .md file is created.
            debounce_seconds: Time to wait after file creation before triggering.
        """
        self._watch_dir = watch_dir
        self._on_file_created = on_file_created
        self._debounce_seconds = debounce_seconds
        self._observer: Observer | None = None
        self._event_handler: PlanFileEventHandler | None = None
        self._started = False

    def start(self) -> None:
        """Start watching the directory.

        Creates the watch directory if it doesn't exist.
        """
        if self._started:
            logger.warning("File watcher already started")
            return

        # Ensure directory exists
        try:
            self._watch_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Failed to create watch directory %s: %s", self._watch_dir, exc)
            return

        self._event_handler = PlanFileEventHandler(
            callback=self._on_file_created,
            debounce_seconds=self._debounce_seconds,
        )

        self._observer = Observer()
        self._observer.schedule(
            self._event_handler,
            str(self._watch_dir),
            recursive=False,
        )

        try:
            self._observer.start()
            self._started = True
            logger.debug("Started watching %s for plan files", self._watch_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to start file watcher: %s", exc)
            self._observer = None

    def stop(self) -> None:
        """Stop watching the directory and clean up."""
        if not self._started or self._observer is None:
            return

        try:
            self._observer.stop()
            self._observer.join(timeout=5)
            logger.debug("Stopped file watcher for %s", self._watch_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error stopping file watcher: %s", exc)
        finally:
            self._observer = None
            self._event_handler = None
            self._started = False

    def __enter__(self) -> "PlanFileWatcher":
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.stop()

    @property
    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._started and self._observer is not None and self._observer.is_alive()
