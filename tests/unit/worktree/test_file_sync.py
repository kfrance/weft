"""Tests for worktree file synchronization module."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest

from lw_coder.worktree.file_sync import (
    ConfigValidationError,
    CopyError,
    FileSyncConfig,
    FileSyncError,
    FileSyncOperation,
    FileSyncPattern,
    SizeLimitError,
    UnsafePatternError,
    WorktreeFileCleanup,
    load_repo_config,
    sync_files_to_worktree,
    validate_pattern_safety,
    validate_worktree_file_sync_config,
)


class TestPatternSafety:
    """Tests for pattern safety validation."""

    @pytest.mark.parametrize(
        "pattern,expected_error",
        [
            ("../secret", "parent directory reference"),
            ("foo/../bar", "parent directory reference"),
            ("/etc/passwd", "absolute path"),
            ("/home/user/.env", "absolute path"),
            ("~/.bashrc", "home directory reference"),
            ("~/secrets", "home directory reference"),
        ],
    )
    def test_rejects_unsafe_patterns(self, pattern: str, expected_error: str) -> None:
        """Test that unsafe patterns are rejected with appropriate error messages."""
        with pytest.raises(UnsafePatternError) as exc_info:
            validate_pattern_safety(pattern)
        assert expected_error in str(exc_info.value).lower()

    @pytest.mark.parametrize(
        "pattern",
        [
            ".env",
            ".env.*",
            "config/*.json",
            "**/*.env",
            "secrets/config.json",
            "deeply/nested/path/file.txt",
        ],
    )
    def test_allows_safe_patterns(self, pattern: str) -> None:
        """Test that safe patterns are allowed."""
        # Should not raise
        validate_pattern_safety(pattern)


class TestFileSyncPattern:
    """Tests for FileSyncPattern class."""

    def test_pattern_matching_glob(self, tmp_path: Path) -> None:
        """Test that glob patterns match files correctly."""
        # Create test files
        (tmp_path / ".env").write_text("test")
        (tmp_path / ".env.local").write_text("test")
        (tmp_path / ".env.production").write_text("test")
        (tmp_path / "other.txt").write_text("test")

        pattern = FileSyncPattern(".env*", tmp_path)
        matches = pattern.find_matches()

        assert len(matches) == 3
        assert Path(".env") in matches
        assert Path(".env.local") in matches
        assert Path(".env.production") in matches

    def test_pattern_matching_nested_directories(self, tmp_path: Path) -> None:
        """Test matching files in nested directories."""
        # Create nested structure
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "app.json").write_text("{}")
        (config_dir / "db.json").write_text("{}")
        (config_dir / "README.md").write_text("docs")

        pattern = FileSyncPattern("config/*.json", tmp_path)
        matches = pattern.find_matches()

        assert len(matches) == 2
        assert Path("config/app.json") in matches
        assert Path("config/db.json") in matches

    def test_pattern_matching_symlinks(self, tmp_path: Path) -> None:
        """Test that symlinks are included in matches."""
        # Create a file and symlink
        (tmp_path / "real.env").write_text("test")
        (tmp_path / ".env").symlink_to("real.env")

        pattern = FileSyncPattern(".env", tmp_path)
        matches = pattern.find_matches()

        assert len(matches) == 1
        assert Path(".env") in matches

    def test_pattern_matching_directories(self, tmp_path: Path) -> None:
        """Test matching directories."""
        # Create directory with contents
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "app.json").write_text("{}")

        pattern = FileSyncPattern("config", tmp_path)
        matches = pattern.find_matches()

        assert len(matches) == 1
        assert Path("config") in matches

    def test_no_matches_returns_empty_list(self, tmp_path: Path) -> None:
        """Test that no matches returns empty list."""
        pattern = FileSyncPattern("nonexistent.*", tmp_path)
        matches = pattern.find_matches()

        assert matches == []


class TestFileSyncOperation:
    """Tests for FileSyncOperation class."""

    def test_copy_file_preserves_metadata(self, tmp_path: Path) -> None:
        """Test that copying a file preserves permissions and timestamps."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        source_file = source_dir / "test.txt"
        source_file.write_text("test content")

        # Set specific permissions and get original metadata
        os.chmod(source_file, 0o644)
        source_stat = source_file.stat()

        dest_file = dest_dir / "test.txt"
        op = FileSyncOperation(
            source=source_file,
            dest=dest_file,
            rel_path=Path("test.txt"),
            max_file_size_bytes=100 * 1024 * 1024,
            max_total_size_bytes=500 * 1024 * 1024,
        )

        created = op.execute()

        assert dest_file.exists()
        assert dest_file.read_text() == "test content"

        # Verify metadata
        dest_stat = dest_file.stat()
        assert stat.S_IMODE(dest_stat.st_mode) == stat.S_IMODE(source_stat.st_mode)
        # Timestamps should be within 1 second (copy2 preserves them)
        assert abs(dest_stat.st_mtime - source_stat.st_mtime) < 1

        assert dest_file in created

    def test_copy_symlink(self, tmp_path: Path) -> None:
        """Test that symlinks are preserved as symlinks."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        # Create a real file and a symlink
        real_file = source_dir / "real.txt"
        real_file.write_text("real content")
        link_file = source_dir / "link.txt"
        link_file.symlink_to("real.txt")

        dest_link = dest_dir / "link.txt"
        op = FileSyncOperation(
            source=link_file,
            dest=dest_link,
            rel_path=Path("link.txt"),
            max_file_size_bytes=100 * 1024 * 1024,
            max_total_size_bytes=500 * 1024 * 1024,
        )

        created = op.execute()

        assert dest_link.is_symlink()
        assert os.readlink(dest_link) == "real.txt"
        assert dest_link in created

    def test_copy_directory(self, tmp_path: Path) -> None:
        """Test recursive directory copy with structure preservation."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        # Create a directory structure
        config_dir = source_dir / "config"
        config_dir.mkdir()
        (config_dir / "app.json").write_text('{"key": "value"}')

        subdir = config_dir / "nested"
        subdir.mkdir()
        (subdir / "deep.json").write_text('{"deep": true}')

        # Create a symlink inside the directory
        (config_dir / "link.json").symlink_to("app.json")

        dest_config = dest_dir / "config"
        op = FileSyncOperation(
            source=config_dir,
            dest=dest_config,
            rel_path=Path("config"),
            max_file_size_bytes=100 * 1024 * 1024,
            max_total_size_bytes=500 * 1024 * 1024,
        )

        created = op.execute()

        # Verify structure
        assert dest_config.exists()
        assert dest_config.is_dir()
        assert (dest_config / "app.json").exists()
        assert (dest_config / "app.json").read_text() == '{"key": "value"}'
        assert (dest_config / "nested" / "deep.json").exists()
        assert (dest_config / "nested" / "deep.json").read_text() == '{"deep": true}'

        # Verify symlink is preserved
        assert (dest_config / "link.json").is_symlink()
        assert os.readlink(dest_config / "link.json") == "app.json"

    @pytest.mark.parametrize(
        "file_size_mb,limit_mb,should_raise",
        [
            (50, 100, False),   # Under limit
            (100, 100, False),  # At limit
            (150, 100, True),   # Over per-file limit
        ],
    )
    def test_size_limits(
        self, tmp_path: Path, file_size_mb: int, limit_mb: int, should_raise: bool
    ) -> None:
        """Test per-file size limit enforcement."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # Create a file of specified size
        large_file = source_dir / "large.bin"
        large_file.write_bytes(b"x" * (file_size_mb * 1024 * 1024))

        op = FileSyncOperation(
            source=large_file,
            dest=tmp_path / "dest" / "large.bin",
            rel_path=Path("large.bin"),
            max_file_size_bytes=limit_mb * 1024 * 1024,
            max_total_size_bytes=1000 * 1024 * 1024,
        )

        if should_raise:
            with pytest.raises(SizeLimitError) as exc_info:
                op.calculate_size()
            assert "max_file_size_mb" in str(exc_info.value)
        else:
            size = op.calculate_size()
            assert size == file_size_mb * 1024 * 1024

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that parent directories are created as needed."""
        source_file = tmp_path / "source.txt"
        source_file.write_text("content")

        dest_file = tmp_path / "deep" / "nested" / "path" / "dest.txt"

        op = FileSyncOperation(
            source=source_file,
            dest=dest_file,
            rel_path=Path("dest.txt"),
            max_file_size_bytes=100 * 1024 * 1024,
            max_total_size_bytes=500 * 1024 * 1024,
        )

        op.execute()

        assert dest_file.exists()
        assert dest_file.read_text() == "content"


class TestWorktreeFileCleanup:
    """Tests for WorktreeFileCleanup class."""

    def test_cleanup_files_and_directories(self, tmp_path: Path) -> None:
        """Test that files and directories are removed in correct order."""
        # Create files and directories
        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        file1 = dir1 / "file1.txt"
        file1.write_text("content")
        file2 = tmp_path / "file2.txt"
        file2.write_text("content")

        cleanup = WorktreeFileCleanup()
        cleanup.register_copied_path(dir1)
        cleanup.register_copied_path(file1)
        cleanup.register_copied_path(file2)

        cleanup.cleanup()

        # All paths should be removed - files first, then empty directories
        assert not file1.exists()
        assert not file2.exists()
        assert not dir1.exists()  # Directory should be removed after file1 is removed

    def test_cleanup_handles_nonexistent_paths_gracefully(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that cleanup errors are logged as warnings, not raised."""
        import logging

        # Register a path that doesn't exist
        nonexistent = tmp_path / "nonexistent.txt"

        cleanup = WorktreeFileCleanup()
        cleanup.register_copied_path(nonexistent)

        caplog.set_level(logging.DEBUG)

        # Should not raise
        cleanup.cleanup()


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_valid_config_accepted(self) -> None:
        """Test that a valid configuration is accepted."""
        config = {
            "schema_version": "1.0",
            "worktree": {
                "file_sync": {
                    "enabled": True,
                    "patterns": [".env", "config/*.json"],
                    "max_file_size_mb": 50,
                    "max_total_size_mb": 200,
                }
            }
        }

        result = validate_worktree_file_sync_config(config)

        assert result.enabled is True
        assert result.patterns == [".env", "config/*.json"]
        assert result.max_file_size_mb == 50
        assert result.max_total_size_mb == 200

    def test_defaults_when_file_sync_section_missing(self) -> None:
        """Test defaults are used when [worktree.file_sync] section is missing."""
        config = {"schema_version": "1.0"}

        result = validate_worktree_file_sync_config(config)

        assert result.enabled is True
        assert result.patterns == []
        assert result.max_file_size_mb == 100
        assert result.max_total_size_mb == 500

    @pytest.mark.parametrize(
        "config,error_message",
        [
            # Wrong schema version
            (
                {"schema_version": "2.0", "worktree": {"file_sync": {}}},
                "Invalid schema_version '2.0'",
            ),
            # Unknown keys
            (
                {"worktree": {"file_sync": {"unknown_key": True}}},
                "Unknown keys in [worktree.file_sync]",
            ),
            # Wrong type for enabled
            (
                {"worktree": {"file_sync": {"enabled": "yes"}}},
                "enabled must be a boolean",
            ),
            # Wrong type for patterns
            (
                {"worktree": {"file_sync": {"patterns": ".env"}}},
                "patterns must be a list",
            ),
            # Pattern is not a string
            (
                {"worktree": {"file_sync": {"patterns": [123]}}},
                "patterns[0] must be a string",
            ),
            # Negative max_file_size_mb
            (
                {"worktree": {"file_sync": {"max_file_size_mb": -1}}},
                "max_file_size_mb must be positive",
            ),
            # Zero max_total_size_mb
            (
                {"worktree": {"file_sync": {"max_total_size_mb": 0}}},
                "max_total_size_mb must be positive",
            ),
            # max_file_size_mb is a boolean (special case since bool is subclass of int)
            (
                {"worktree": {"file_sync": {"max_file_size_mb": True}}},
                "max_file_size_mb must be an integer",
            ),
        ],
    )
    def test_invalid_configs(self, config: dict[str, Any], error_message: str) -> None:
        """Test that invalid configurations are rejected with appropriate errors."""
        with pytest.raises(ConfigValidationError) as exc_info:
            validate_worktree_file_sync_config(config)
        assert error_message in str(exc_info.value)


class TestSyncFilesToWorktree:
    """Tests for sync_files_to_worktree function."""

    def test_no_config_skips_silently(self, tmp_path: Path) -> None:
        """Test that missing config results in silent skip."""
        repo_root = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo_root.mkdir()
        worktree.mkdir()

        # No .lw_coder/config.toml exists
        result = sync_files_to_worktree(repo_root, worktree)

        assert result == 0

    def test_disabled_skips_sync(self, tmp_path: Path) -> None:
        """Test that disabled sync is skipped."""
        repo_root = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo_root.mkdir()
        worktree.mkdir()

        # Create config with sync disabled
        config_dir = repo_root / ".lw_coder"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            """
schema_version = "1.0"
[worktree.file_sync]
enabled = false
patterns = [".env"]
"""
        )

        # Create .env file
        (repo_root / ".env").write_text("SECRET=value")

        result = sync_files_to_worktree(repo_root, worktree)

        assert result == 0
        # .env should NOT be copied
        assert not (worktree / ".env").exists()

    def test_empty_patterns_skips_sync(self, tmp_path: Path) -> None:
        """Test that empty patterns list results in no files copied."""
        repo_root = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo_root.mkdir()
        worktree.mkdir()

        # Create config with empty patterns list
        config_dir = repo_root / ".lw_coder"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            """
schema_version = "1.0"
[worktree.file_sync]
enabled = true
patterns = []
"""
        )

        # Create a file that would be synced if patterns weren't empty
        (repo_root / ".env").write_text("SECRET=value")

        result = sync_files_to_worktree(repo_root, worktree)

        assert result == 0
        # .env should NOT be copied because patterns is empty
        assert not (worktree / ".env").exists()

    def test_end_to_end(self, tmp_path: Path) -> None:
        """Test end-to-end sync: copy files, preserve structure, register cleanup, log summary."""
        repo_root = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo_root.mkdir()
        worktree.mkdir()

        # Create config
        config_dir = repo_root / ".lw_coder"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            """
schema_version = "1.0"
[worktree.file_sync]
enabled = true
patterns = [".env", "config/*.json"]
"""
        )

        # Create files to sync
        (repo_root / ".env").write_text("SECRET=value")
        config_subdir = repo_root / "config"
        config_subdir.mkdir()
        (config_subdir / "app.json").write_text('{"key": "value"}')
        (config_subdir / "db.json").write_text('{"host": "localhost"}')

        cleanup = WorktreeFileCleanup()
        result = sync_files_to_worktree(repo_root, worktree, cleanup)

        # Should have copied 3 files
        assert result == 3

        # Verify files exist
        assert (worktree / ".env").exists()
        assert (worktree / ".env").read_text() == "SECRET=value"
        assert (worktree / "config" / "app.json").exists()
        assert (worktree / "config" / "db.json").exists()

        # Cleanup should remove the files
        cleanup.cleanup()
        assert not (worktree / ".env").exists()

    def test_pattern_match_nothing_errors(self, tmp_path: Path) -> None:
        """Test that a pattern matching no files raises an error."""
        repo_root = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo_root.mkdir()
        worktree.mkdir()

        # Create config with pattern that won't match
        config_dir = repo_root / ".lw_coder"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            """
schema_version = "1.0"
[worktree.file_sync]
enabled = true
patterns = [".env.nonexistent"]
"""
        )

        with pytest.raises(FileSyncError) as exc_info:
            sync_files_to_worktree(repo_root, worktree)

        assert "matched no files" in str(exc_info.value)


class TestFilesystemOperations:
    """Filesystem tests with real file operations."""

    def test_sync_workflow(self, tmp_path: Path) -> None:
        """Test complete workflow: create files, sync, verify, cleanup."""
        repo_root = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo_root.mkdir()
        worktree.mkdir()

        # Create config
        config_dir = repo_root / ".lw_coder"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            """
schema_version = "1.0"
[worktree.file_sync]
enabled = true
patterns = [".env"]
"""
        )

        # Create .env
        (repo_root / ".env").write_text("KEY=value")

        cleanup = WorktreeFileCleanup()

        # Sync
        count = sync_files_to_worktree(repo_root, worktree, cleanup)
        assert count == 1
        assert (worktree / ".env").exists()

        # Cleanup
        cleanup.cleanup()
        assert not (worktree / ".env").exists()

    def test_sync_symlink_handling(self, tmp_path: Path) -> None:
        """Test that symlinks are copied as symlinks to worktree."""
        repo_root = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo_root.mkdir()
        worktree.mkdir()

        # Create config
        config_dir = repo_root / ".lw_coder"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            """
schema_version = "1.0"
[worktree.file_sync]
enabled = true
patterns = [".env"]
"""
        )

        # Create a real file and symlink to it
        (repo_root / ".env.real").write_text("SECRET=value")
        (repo_root / ".env").symlink_to(".env.real")

        cleanup = WorktreeFileCleanup()
        sync_files_to_worktree(repo_root, worktree, cleanup)

        # Verify symlink was preserved
        assert (worktree / ".env").is_symlink()
        assert os.readlink(worktree / ".env") == ".env.real"

    @pytest.mark.parametrize(
        "scenario,config_content,file_setup,expected_error",
        [
            (
                "size_limit_exceeded",
                """
schema_version = "1.0"
[worktree.file_sync]
enabled = true
patterns = ["large.bin"]
max_file_size_mb = 1
""",
                {"large.bin": b"x" * (2 * 1024 * 1024)},  # 2MB file, 1MB limit
                "max_file_size_mb",
            ),
            (
                "invalid_config",
                """
schema_version = "1.0"
[worktree.file_sync]
enabled = "yes"
""",
                {},
                "enabled must be a boolean",
            ),
            (
                "unsafe_pattern",
                """
schema_version = "1.0"
[worktree.file_sync]
enabled = true
patterns = ["../outside"]
""",
                {},
                "parent directory reference",
            ),
        ],
    )
    def test_sync_error_cases(
        self,
        tmp_path: Path,
        scenario: str,
        config_content: str,
        file_setup: dict[str, bytes],
        expected_error: str,
    ) -> None:
        """Test various error scenarios during sync."""
        repo_root = tmp_path / "repo"
        worktree = tmp_path / "worktree"
        repo_root.mkdir()
        worktree.mkdir()

        # Create config
        config_dir = repo_root / ".lw_coder"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(config_content)

        # Create any required files
        for filename, content in file_setup.items():
            (repo_root / filename).write_bytes(content)

        with pytest.raises(FileSyncError) as exc_info:
            sync_files_to_worktree(repo_root, worktree)

        assert expected_error in str(exc_info.value)


class TestLoadRepoConfig:
    """Tests for load_repo_config function."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        """Test loading a valid config file."""
        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text(
            """
schema_version = "1.0"
[worktree.file_sync]
patterns = [".env"]
"""
        )

        config = load_repo_config(tmp_path)

        assert config["schema_version"] == "1.0"
        assert config["worktree"]["file_sync"]["patterns"] == [".env"]

    def test_missing_config_returns_empty_dict(self, tmp_path: Path) -> None:
        """Test that missing config returns empty dict."""
        config = load_repo_config(tmp_path)
        assert config == {}

    def test_invalid_toml_raises_error(self, tmp_path: Path) -> None:
        """Test that invalid TOML raises FileSyncError."""
        config_dir = tmp_path / ".lw_coder"
        config_dir.mkdir()
        (config_dir / "config.toml").write_text("invalid [ toml")

        with pytest.raises(FileSyncError) as exc_info:
            load_repo_config(tmp_path)

        assert "Failed to parse config file" in str(exc_info.value)
