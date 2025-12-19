"""Home-level environment loader for weft secrets.

Loads secrets exclusively from ~/.weft/.env, providing
basic existence and readability validation. Also handles OS detection
and emits warnings for unsupported platforms.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

from .logging_config import get_logger

logger = get_logger(__name__)

# Import OS detection functions from host_runner
from .host_runner import check_os_support


class HomeEnvError(Exception):
    """Raised when home-level .env file is missing or unreadable."""

    pass


def load_home_env() -> Path:
    """Load environment variables from ~/.weft/.env.

    Returns:
        Path to the .env file that was loaded

    Raises:
        HomeEnvError: If ~/.weft/.env is missing or unreadable
    """
    # Check OS support and emit warnings if needed
    check_os_support()

    env_path = Path.home() / ".weft" / ".env"

    if not env_path.exists():
        raise HomeEnvError(
            f"Environment file not found: {env_path}\n"
            "Create ~/.weft/.env with required secrets (e.g., OPENROUTER_API_KEY)."
        )

    if not env_path.is_file():
        raise HomeEnvError(
            f"Environment path is not a file: {env_path}\n"
            "~/.weft/.env must be a regular file."
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
