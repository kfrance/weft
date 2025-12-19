"""Tests for session_manager module."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from weft.session_manager import (
    SESSION_RETENTION_DAYS,
    SessionManagerError,
    create_session_directory,
    get_session_directory,
    prune_old_sessions,
)


class TestCreateSessionDirectory:
    """Tests for create_session_directory function."""

    def test_creates_code_session_directory(self, tmp_path: Path) -> None:
        """Test successful creation of code session directory."""
        repo_root = tmp_path
        plan_id = "test-plan"

        session_dir = create_session_directory(repo_root, plan_id, "code")

        assert session_dir.exists()
        assert session_dir.is_dir()
        assert ".weft/sessions" in str(session_dir)
        assert plan_id in str(session_dir)
        assert session_dir.name == "code"

    def test_creates_plan_session_directory(self, tmp_path: Path) -> None:
        """Test successful creation of plan session directory."""
        repo_root = tmp_path
        plan_id = "test-plan"

        session_dir = create_session_directory(repo_root, plan_id, "plan")

        assert session_dir.exists()
        assert session_dir.is_dir()
        assert session_dir.name == "plan"

    def test_creates_eval_session_directory(self, tmp_path: Path) -> None:
        """Test successful creation of eval session directory."""
        repo_root = tmp_path
        plan_id = "test-plan"

        session_dir = create_session_directory(repo_root, plan_id, "eval")

        assert session_dir.exists()
        assert session_dir.is_dir()
        assert session_dir.name == "eval"

    def test_rejects_invalid_session_type(self, tmp_path: Path) -> None:
        """Test that invalid session types are rejected."""
        repo_root = tmp_path
        plan_id = "test-plan"

        with pytest.raises(SessionManagerError, match="Invalid session type"):
            create_session_directory(repo_root, plan_id, "invalid")  # type: ignore

    def test_creates_existing_directory_without_error(self, tmp_path: Path) -> None:
        """Test that creating an existing directory doesn't raise an error."""
        repo_root = tmp_path
        plan_id = "test-plan"

        # Create twice - should succeed both times
        session_dir1 = create_session_directory(repo_root, plan_id, "code")
        session_dir2 = create_session_directory(repo_root, plan_id, "code")

        assert session_dir1 == session_dir2
        assert session_dir2.exists()

    def test_os_error_raises_exception(self, tmp_path: Path, monkeypatch) -> None:
        """Test that OSError is converted to SessionManagerError."""
        repo_root = tmp_path
        plan_id = "test-plan"

        original_mkdir = Path.mkdir

        def failing_mkdir(self, *args, **kwargs):
            if ".weft/sessions" in str(self):
                raise OSError("Permission denied")
            return original_mkdir(self, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", failing_mkdir)

        with pytest.raises(SessionManagerError, match="Failed to create session directory"):
            create_session_directory(repo_root, plan_id, "code")


class TestGetSessionDirectory:
    """Tests for get_session_directory function."""

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """Test that get_session_directory returns the correct path."""
        repo_root = tmp_path
        plan_id = "my-plan"

        path = get_session_directory(repo_root, plan_id, "eval")

        assert path == repo_root / ".weft" / "sessions" / "my-plan" / "eval"
        # Note: doesn't create the directory
        assert not path.exists()


class TestPruneOldSessions:
    """Tests for prune_old_sessions function."""

    def test_no_sessions_directory(self, tmp_path: Path) -> None:
        """Test pruning when sessions directory doesn't exist."""
        repo_root = tmp_path

        count = prune_old_sessions(repo_root)

        assert count == 0

    def test_removes_old_directories(self, tmp_path: Path) -> None:
        """Test that old session directories are pruned."""
        import os

        repo_root = tmp_path
        sessions_dir = repo_root / ".weft" / "sessions"

        # Create old plan directory
        old_plan_dir = sessions_dir / "old-plan"
        old_plan_dir.mkdir(parents=True)
        (old_plan_dir / "code").mkdir()
        old_timestamp = time.time() - (SESSION_RETENTION_DAYS + 1) * 24 * 60 * 60
        os.utime(old_plan_dir, (old_timestamp, old_timestamp))

        # Create recent plan directory
        recent_plan_dir = sessions_dir / "recent-plan"
        recent_plan_dir.mkdir(parents=True)
        (recent_plan_dir / "code").mkdir()

        count = prune_old_sessions(repo_root)

        assert count == 1
        assert not old_plan_dir.exists()
        assert recent_plan_dir.exists()

    def test_skips_active_session(self, tmp_path: Path) -> None:
        """Test that active session's plan directory is not pruned."""
        import os

        repo_root = tmp_path
        sessions_dir = repo_root / ".weft" / "sessions"

        # Create old plan directory
        old_plan_dir = sessions_dir / "old-plan"
        old_plan_dir.mkdir(parents=True)
        code_dir = old_plan_dir / "code"
        code_dir.mkdir()
        old_timestamp = time.time() - (SESSION_RETENTION_DAYS + 1) * 24 * 60 * 60
        os.utime(old_plan_dir, (old_timestamp, old_timestamp))

        # Mark it as active (via code session)
        count = prune_old_sessions(repo_root, active_session_dir=code_dir)

        assert count == 0
        assert old_plan_dir.exists()

    def test_handles_partial_failures(self, tmp_path: Path, monkeypatch) -> None:
        """Test that pruning continues even if some deletions fail."""
        import os
        import shutil

        repo_root = tmp_path
        sessions_dir = repo_root / ".weft" / "sessions"

        # Create two old plan directories
        old_plan1 = sessions_dir / "old-plan-1"
        old_plan1.mkdir(parents=True)
        old_plan2 = sessions_dir / "old-plan-2"
        old_plan2.mkdir(parents=True)

        old_timestamp = time.time() - (SESSION_RETENTION_DAYS + 1) * 24 * 60 * 60
        os.utime(old_plan1, (old_timestamp, old_timestamp))
        os.utime(old_plan2, (old_timestamp, old_timestamp))

        # Make deletion of first directory fail
        original_rmtree = shutil.rmtree

        def failing_rmtree(path, *args, **kwargs):
            if str(path) == str(old_plan1):
                raise OSError("Simulated failure")
            return original_rmtree(path, *args, **kwargs)

        monkeypatch.setattr("shutil.rmtree", failing_rmtree)

        count = prune_old_sessions(repo_root)

        assert count == 1
        assert old_plan1.exists()  # Failed to delete
        assert not old_plan2.exists()  # Successfully deleted

    def test_raises_on_all_failures(self, tmp_path: Path, monkeypatch) -> None:
        """Test that SessionManagerError is raised when all pruning operations fail."""
        import os

        repo_root = tmp_path
        sessions_dir = repo_root / ".weft" / "sessions"

        # Create old plan directory
        old_plan = sessions_dir / "old-plan"
        old_plan.mkdir(parents=True)
        old_timestamp = time.time() - (SESSION_RETENTION_DAYS + 1) * 24 * 60 * 60
        os.utime(old_plan, (old_timestamp, old_timestamp))

        def failing_rmtree(path, *args, **kwargs):
            raise OSError("Simulated failure")

        monkeypatch.setattr("shutil.rmtree", failing_rmtree)

        with pytest.raises(SessionManagerError, match="Pruning failed"):
            prune_old_sessions(repo_root)
