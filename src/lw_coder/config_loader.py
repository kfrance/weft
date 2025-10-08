"""Configuration loader for lw_coder code command.

Loads and validates configuration from .lw_coder/config.toml.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


class ConfigLoaderError(Exception):
    """Raised when configuration loading or validation fails."""

    pass


@dataclass
class CodeConfig:
    """Configuration for the code command.

    Attributes:
        env_file: Resolved absolute path to the .env file
        forward_env: List of environment variable patterns to forward to Docker
        docker_build_args: List of arguments to pass to docker build
        docker_run_args: List of arguments to pass to docker run
    """

    env_file: Path
    forward_env: list[str]
    docker_build_args: list[str]
    docker_run_args: list[str]


def load_code_config(repo_root: Path) -> CodeConfig:
    """Load and validate code configuration from .lw_coder/config.toml.

    Args:
        repo_root: Absolute path to the repository root directory

    Returns:
        CodeConfig with validated and resolved settings

    Raises:
        ConfigLoaderError: If configuration is missing, invalid, or references missing files
    """
    config_path = repo_root / ".lw_coder" / "config.toml"

    if not config_path.exists():
        raise ConfigLoaderError(
            f"Configuration file not found: {config_path}\n"
            "Create .lw_coder/config.toml with a [code] section."
        )

    try:
        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigLoaderError(
            f"Failed to parse configuration file {config_path}: {e}"
        ) from e

    if "code" not in config_data:
        raise ConfigLoaderError(
            f"Missing required [code] table in {config_path}\n"
            "Add a [code] section with env_file and optional forward_env, "
            "docker_build_args, docker_run_args."
        )

    code_section = config_data["code"]

    # Check for unknown keys
    known_keys = {"env_file", "forward_env", "docker_build_args", "docker_run_args"}
    unknown_keys = set(code_section.keys()) - known_keys
    if unknown_keys:
        raise ConfigLoaderError(
            f"Unknown keys in [code] section: {', '.join(sorted(unknown_keys))}\n"
            f"Valid keys are: {', '.join(sorted(known_keys))}"
        )

    # Load env_file (required, defaults to ".env")
    env_file_str = code_section.get("env_file", ".env")
    if not isinstance(env_file_str, str):
        raise ConfigLoaderError(
            f"env_file must be a string, got {type(env_file_str).__name__}"
        )

    env_file = (repo_root / env_file_str).resolve()

    # Validate that env_file is within repo_root (prevent path traversal)
    try:
        env_file.relative_to(repo_root.resolve())
    except ValueError as e:
        raise ConfigLoaderError(
            f"env_file path '{env_file_str}' resolves outside repository: {env_file}\n"
            f"Repository root: {repo_root}"
        ) from e

    if not env_file.exists():
        raise ConfigLoaderError(
            f"Environment file not found: {env_file}\n"
            f"Specified by env_file = '{env_file_str}' in {config_path}"
        )

    # Load forward_env (optional, defaults to ["OPENROUTER_*"])
    forward_env = code_section.get("forward_env", ["OPENROUTER_*"])
    if not isinstance(forward_env, list):
        raise ConfigLoaderError(
            f"forward_env must be a list, got {type(forward_env).__name__}"
        )
    if not all(isinstance(item, str) for item in forward_env):
        raise ConfigLoaderError("forward_env must be a list of strings")

    # Warn if forwarding all environment variables
    if "*" in forward_env:
        logger.warning(
            "forward_env contains '*' which will forward ALL environment variables. "
            "This may expose sensitive information. Consider using specific patterns instead."
        )

    # Load docker_build_args (optional, defaults to [])
    docker_build_args = code_section.get("docker_build_args", [])
    if not isinstance(docker_build_args, list):
        raise ConfigLoaderError(
            f"docker_build_args must be a list, got {type(docker_build_args).__name__}"
        )
    if not all(isinstance(item, str) for item in docker_build_args):
        raise ConfigLoaderError("docker_build_args must be a list of strings")

    # Load docker_run_args (optional, defaults to [])
    docker_run_args = code_section.get("docker_run_args", [])
    if not isinstance(docker_run_args, list):
        raise ConfigLoaderError(
            f"docker_run_args must be a list, got {type(docker_run_args).__name__}"
        )
    if not all(isinstance(item, str) for item in docker_run_args):
        raise ConfigLoaderError("docker_run_args must be a list of strings")

    return CodeConfig(
        env_file=env_file,
        forward_env=forward_env,
        docker_build_args=docker_build_args,
        docker_run_args=docker_run_args,
    )
