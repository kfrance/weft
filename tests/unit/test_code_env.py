"""Tests for code_env module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from weft.code_env import CodeEnvError, load_code_env
from weft.worktree.file_sync import FileSyncError


class TestLoadCodeEnv:
    """Tests for load_code_env function."""

    def test_valid_config_returns_dict(self, tmp_path: Path) -> None:
        """Test loading valid [code.env] section returns dict."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[code.env]
DATABASE_URL = "postgres://localhost:5432/dev"
DEBUG = "true"
MY_VAR = "value"
"""
        )

        result = load_code_env(tmp_path)

        assert result == {
            "DATABASE_URL": "postgres://localhost:5432/dev",
            "DEBUG": "true",
            "MY_VAR": "value",
        }

    def test_no_config_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """Test returns empty dict when no config file exists."""
        result = load_code_env(tmp_path)
        assert result == {}

    def test_no_code_section_returns_empty_dict(self, tmp_path: Path) -> None:
        """Test returns empty dict when no [code] section exists."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[worktree.file_sync]
patterns = [".env"]
"""
        )

        result = load_code_env(tmp_path)
        assert result == {}

    def test_no_env_section_returns_empty_dict(self, tmp_path: Path) -> None:
        """Test returns empty dict when [code] has no env section."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[code]
# No env section
"""
        )

        result = load_code_env(tmp_path)
        assert result == {}

    def test_empty_env_section_returns_empty_dict(self, tmp_path: Path) -> None:
        """Test returns empty dict when [code.env] is empty."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[code.env]
# No variables
"""
        )

        result = load_code_env(tmp_path)
        assert result == {}

    def test_invalid_key_starts_with_digit_raises_error(self, tmp_path: Path) -> None:
        """Test key starting with digit raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code.env]
1_INVALID = "value"
"""
        )

        with pytest.raises(CodeEnvError, match="invalid key '1_INVALID'"):
            load_code_env(tmp_path)

    def test_invalid_key_contains_hyphen_raises_error(self, tmp_path: Path) -> None:
        """Test key containing hyphen raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code.env]
MY-VAR = "value"
"""
        )

        with pytest.raises(CodeEnvError, match="invalid key 'MY-VAR'"):
            load_code_env(tmp_path)

    def test_invalid_key_contains_space_raises_error(self, tmp_path: Path) -> None:
        """Test key containing space raises error (TOML won't parse, but test for completeness)."""
        # Note: TOML actually won't allow unquoted keys with spaces, so we test with
        # an alternative invalid character
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code.env]
"MY VAR" = "value"
"""
        )

        with pytest.raises(CodeEnvError, match="invalid key 'MY VAR'"):
            load_code_env(tmp_path)

    def test_non_string_value_integer_raises_error(self, tmp_path: Path) -> None:
        """Test non-string value (integer) raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code.env]
PORT = 5432
"""
        )

        with pytest.raises(CodeEnvError, match="key 'PORT'.*must be a string.*got int"):
            load_code_env(tmp_path)

    def test_non_string_value_boolean_raises_error(self, tmp_path: Path) -> None:
        """Test non-string value (boolean) raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code.env]
DEBUG = true
"""
        )

        with pytest.raises(CodeEnvError, match="key 'DEBUG'.*must be a string.*got bool"):
            load_code_env(tmp_path)

    def test_non_string_value_array_raises_error(self, tmp_path: Path) -> None:
        """Test non-string value (array) raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code.env]
HOSTS = ["localhost", "127.0.0.1"]
"""
        )

        with pytest.raises(CodeEnvError, match="key 'HOSTS'.*must be a string.*got list"):
            load_code_env(tmp_path)

    def test_empty_string_value_succeeds(self, tmp_path: Path) -> None:
        """Test empty string value is valid."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code.env]
EMPTY_VAR = ""
"""
        )

        result = load_code_env(tmp_path)
        assert result == {"EMPTY_VAR": ""}

    def test_special_characters_in_value_succeeds(self, tmp_path: Path) -> None:
        """Test values with special characters are valid."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            '''
[code.env]
URL = "postgres://user:p@ssw0rd!@localhost:5432/db?ssl=true"
JSON = "{\\"key\\": \\"value\\"}"
MULTILINE = """line1
line2
line3"""
SPECIAL = "!@#$%^&*()[]{}|;:,.<>?/~`"
'''
        )

        result = load_code_env(tmp_path)
        assert result["URL"] == "postgres://user:p@ssw0rd!@localhost:5432/db?ssl=true"
        assert result["JSON"] == '{"key": "value"}'
        # Use exact comparison for multiline to catch truncation/corruption issues
        assert result["MULTILINE"] == "line1\nline2\nline3"
        assert result["SPECIAL"] == "!@#$%^&*()[]{}|;:,.<>?/~`"

    def test_valid_key_with_underscore_prefix(self, tmp_path: Path) -> None:
        """Test key starting with underscore is valid."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code.env]
_PRIVATE = "secret"
__DUNDER = "value"
"""
        )

        result = load_code_env(tmp_path)
        assert result == {
            "_PRIVATE": "secret",
            "__DUNDER": "value",
        }

    def test_valid_key_with_numbers(self, tmp_path: Path) -> None:
        """Test key containing numbers (not at start) is valid."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code.env]
VAR1 = "value1"
MY_VAR_2 = "value2"
V123 = "v123"
"""
        )

        result = load_code_env(tmp_path)
        assert result == {
            "VAR1": "value1",
            "MY_VAR_2": "value2",
            "V123": "v123",
        }

    def test_code_section_not_table_raises_error(self, tmp_path: Path) -> None:
        """Test [code] section that is not a table raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
code = "not a table"
"""
        )

        with pytest.raises(CodeEnvError, match="\\[code\\] section must be a table"):
            load_code_env(tmp_path)

    def test_env_section_not_table_raises_error(self, tmp_path: Path) -> None:
        """Test [code.env] that is not a table raises error."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
[code]
env = "not a table"
"""
        )

        with pytest.raises(CodeEnvError, match="\\[code.env\\] must be a table"):
            load_code_env(tmp_path)

    def test_multiple_valid_keys(self, tmp_path: Path) -> None:
        """Test loading multiple valid environment variables."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[code.env]
DATABASE_URL = "postgres://localhost:5432/dev"
REDIS_URL = "redis://localhost:6379"
API_KEY = "secret123"
DEBUG = "true"
LOG_LEVEL = "debug"
"""
        )

        result = load_code_env(tmp_path)

        assert len(result) == 5
        assert result["DATABASE_URL"] == "postgres://localhost:5432/dev"
        assert result["REDIS_URL"] == "redis://localhost:6379"
        assert result["API_KEY"] == "secret123"
        assert result["DEBUG"] == "true"
        assert result["LOG_LEVEL"] == "debug"

    def test_mixed_with_other_config_sections(self, tmp_path: Path) -> None:
        """Test [code.env] works alongside other config sections."""
        config_path = tmp_path / ".weft" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """
schema_version = "1.0"

[worktree.file_sync]
enabled = true
patterns = [".env"]

[code.env]
MY_VAR = "value"

[[code.setup]]
name = "test"
command = "echo $MY_VAR"
"""
        )

        result = load_code_env(tmp_path)
        assert result == {"MY_VAR": "value"}

    def test_file_sync_error_propagates_as_code_env_error(self, tmp_path: Path) -> None:
        """Test FileSyncError from load_repo_config is wrapped as CodeEnvError."""
        with patch("weft.code_env.load_repo_config") as mock_load:
            mock_load.side_effect = FileSyncError("Config file corrupted")

            with pytest.raises(CodeEnvError, match="Failed to load repository config"):
                load_code_env(tmp_path)
