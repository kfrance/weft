"""Unit tests for cache synchronization utilities.

Tests cache sync functions in isolation using mocks and temporary directories.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.cache_sync import (
    check_rsync_available,
    get_global_cache_dir,
    get_worktree_cache_dir,
    sync_cache_from_worktree,
    sync_cache_to_worktree,
)


class TestCheckRsyncAvailable:
    """Tests for check_rsync_available function."""

    def test_rsync_available(self) -> None:
        """Test returns True when rsync is installed."""
        with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = check_rsync_available()
            assert result is True
            mock_run.assert_called_once_with(
                ["rsync", "--version"],
                capture_output=True,
                check=True,
            )

    def test_rsync_not_found(self) -> None:
        """Test returns False when rsync is not installed."""
        with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            result = check_rsync_available()
            assert result is False

    def test_rsync_command_failed(self) -> None:
        """Test returns False when rsync command fails."""
        with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "rsync")
            result = check_rsync_available()
            assert result is False


class TestSyncCacheToWorktree:
    """Tests for sync_cache_to_worktree function."""

    def test_sync_success(self, tmp_path: Path) -> None:
        """Test successful sync from global to worktree cache."""
        source = tmp_path / "source_cache"
        dest = tmp_path / "dest_cache"

        # Create source with some files
        source.mkdir()
        (source / "cache_file.db").write_text("cached data")
        (source / "subdir").mkdir()
        (source / "subdir" / "nested.db").write_text("nested data")

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                result = sync_cache_to_worktree(source, dest)

                assert result is True
                mock_run.assert_called_once()
                # Verify rsync command includes -a and --delete
                call_args = mock_run.call_args[0][0]
                assert "rsync" in call_args
                assert "-a" in call_args
                assert "--delete" in call_args

    def test_sync_when_source_does_not_exist(self, tmp_path: Path) -> None:
        """Test sync returns True when source doesn't exist (nothing to sync)."""
        source = tmp_path / "nonexistent"
        dest = tmp_path / "dest"

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            result = sync_cache_to_worktree(source, dest)
            assert result is True  # Nothing to sync is not an error

    def test_sync_when_rsync_not_available(self, tmp_path: Path) -> None:
        """Test sync returns False when rsync is not available."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=False):
            result = sync_cache_to_worktree(source, dest)
            assert result is False

    def test_sync_creates_dest_directory(self, tmp_path: Path) -> None:
        """Test sync creates destination directory if it doesn't exist."""
        source = tmp_path / "source"
        dest = tmp_path / "nested" / "dest"
        source.mkdir()
        (source / "file.db").write_text("data")

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                sync_cache_to_worktree(source, dest)
                assert dest.exists()

    def test_sync_handles_rsync_failure(self, tmp_path: Path) -> None:
        """Test sync returns False when rsync fails."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="rsync error")
                result = sync_cache_to_worktree(source, dest)
                assert result is False


class TestSyncCacheFromWorktree:
    """Tests for sync_cache_from_worktree function."""

    def test_sync_success(self, tmp_path: Path) -> None:
        """Test successful sync from worktree to global cache."""
        source = tmp_path / "worktree_cache"
        dest = tmp_path / "global_cache"

        source.mkdir()
        (source / "new_cache.db").write_text("new cached data")

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                result = sync_cache_from_worktree(source, dest)

                assert result is True
                mock_run.assert_called_once()
                # Verify rsync command includes -a but NOT --delete
                call_args = mock_run.call_args[0][0]
                assert "rsync" in call_args
                assert "-a" in call_args
                assert "--delete" not in call_args

    def test_sync_when_source_does_not_exist(self, tmp_path: Path) -> None:
        """Test sync returns True when worktree cache doesn't exist."""
        source = tmp_path / "nonexistent"
        dest = tmp_path / "global"

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            result = sync_cache_from_worktree(source, dest)
            assert result is True  # Nothing to sync is not an error

    def test_sync_when_rsync_not_available(self, tmp_path: Path) -> None:
        """Test sync returns False when rsync is not available."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=False):
            result = sync_cache_from_worktree(source, dest)
            assert result is False

    def test_sync_creates_dest_directory(self, tmp_path: Path) -> None:
        """Test sync creates global cache directory if it doesn't exist."""
        source = tmp_path / "worktree"
        dest = tmp_path / "global"
        source.mkdir()
        (source / "file.db").write_text("data")

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                sync_cache_from_worktree(source, dest)
                assert dest.exists()

    def test_sync_handles_rsync_failure(self, tmp_path: Path) -> None:
        """Test sync returns False when rsync fails."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="rsync error")
                result = sync_cache_from_worktree(source, dest)
                assert result is False


class TestGetGlobalCacheDir:
    """Tests for get_global_cache_dir function."""

    def test_returns_home_cache_path(self) -> None:
        """Test returns ~/.lw_coder/dspy_cache."""
        result = get_global_cache_dir()
        assert result == Path.home() / ".lw_coder" / "dspy_cache"
        assert isinstance(result, Path)


class TestGetWorktreeCacheDir:
    """Tests for get_worktree_cache_dir function."""

    def test_returns_worktree_cache_path(self, tmp_path: Path) -> None:
        """Test returns worktree/.lw_coder/dspy_cache."""
        worktree_path = tmp_path / "my_worktree"
        result = get_worktree_cache_dir(worktree_path)
        assert result == worktree_path / ".lw_coder" / "dspy_cache"
        assert isinstance(result, Path)


class TestSyncGracefulHandling:
    """Tests for graceful error handling in sync functions."""

    def test_sync_to_worktree_handles_exception(self, tmp_path: Path) -> None:
        """Test sync_cache_to_worktree handles unexpected exceptions gracefully."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
                mock_run.side_effect = Exception("Unexpected error")
                result = sync_cache_to_worktree(source, dest)
                assert result is False

    def test_sync_from_worktree_handles_exception(self, tmp_path: Path) -> None:
        """Test sync_cache_from_worktree handles unexpected exceptions gracefully."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()

        with patch("lw_coder.cache_sync.check_rsync_available", return_value=True):
            with patch("lw_coder.cache_sync.subprocess.run") as mock_run:
                mock_run.side_effect = Exception("Unexpected error")
                result = sync_cache_from_worktree(source, dest)
                assert result is False
