"""Home-level environment loader for lw_coder secrets.

Loads secrets exclusively from ~/.lw_coder/.env, providing
basic existence and readability validation.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from .logging_config import get_logger

logger = get_logger(__name__)


class HomeEnvError(Exception):
    """Raised when home-level .env file is missing or unreadable."""

    pass


def load_home_env() -> Path:
    """Load environment variables from ~/.lw_coder/.env.

    Returns:
        Path to the .env file that was loaded

    Raises:
        HomeEnvError: If ~/.lw_coder/.env is missing or unreadable
    """
    env_path = Path.home() / ".lw_coder" / ".env"

    if not env_path.exists():
        raise HomeEnvError(
            f"Environment file not found: {env_path}\n"
            "Create ~/.lw_coder/.env with required secrets (e.g., OPENROUTER_API_KEY)."
        )

    if not env_path.is_file():
        raise HomeEnvError(
            f"Environment path is not a file: {env_path}\n"
            "~/.lw_coder/.env must be a regular file."
        )

    # Check readability by attempting to open
    try:
        with open(env_path, "r") as f:
            # Just check if we can open it
            pass
    except (PermissionError, OSError) as e:
        raise HomeEnvError(
            f"Cannot read environment file: {env_path}\n" f"Error: {e}"
        ) from e

    logger.debug("Loading environment from %s", env_path)
    load_dotenv(env_path, override=False)

    return env_path
