"""Path utilities for weft.

This module provides centralized path resolution functions to eliminate
duplication and ensure consistent path handling across the codebase.
"""

from __future__ import annotations

from pathlib import Path


def get_weft_src_dir() -> Path:
    """Get the weft source directory (where package files are located).

    Returns:
        Path to the weft source directory.

    Raises:
        RuntimeError: If the source directory cannot be determined.
    """
    # The source directory is where this module is located
    src_dir = Path(__file__).resolve().parent
    if not src_dir.exists():
        raise RuntimeError(
            f"weft source directory not found at {src_dir}. "
            "Ensure the package is properly installed."
        )
    return src_dir


def get_sdk_settings_path() -> Path:
    """Get the path to the SDK settings JSON file.

    Returns:
        Path to src/weft/sdk_settings.json

    Raises:
        RuntimeError: If the source directory cannot be determined.
    """
    return get_weft_src_dir() / "sdk_settings.json"
