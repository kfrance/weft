#!/usr/bin/env python3
"""Generate VERSION file for init_templates.

This script scans all template files in src/lw_coder/init_templates and generates
a VERSION file containing metadata and SHA256 hashes for each template.

Usage:
    python scripts/generate_template_version.py

The script should be run from the repository root directory.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

# Add src directory to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lw_coder.init_command import calculate_file_hash  # noqa: E402


def get_lw_coder_version() -> str:
    """Read lw_coder version from pyproject.toml.

    Returns:
        Version string from pyproject.toml.
    """
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        return "0.1.0"

    content = pyproject_path.read_text(encoding="utf-8")
    for line in content.split("\n"):
        if line.startswith("version"):
            # Parse version = "x.y.z"
            parts = line.split("=", 1)
            if len(parts) == 2:
                version = parts[1].strip().strip('"').strip("'")
                return version
    return "0.1.0"


# Only include these file extensions in VERSION hashing
# This prevents OS/editor artifacts from being included
ALLOWED_EXTENSIONS = {".md"}


def generate_version_file() -> None:
    """Generate VERSION file for init_templates."""
    templates_dir = Path("src/lw_coder/init_templates")

    if not templates_dir.exists():
        print(f"Error: Templates directory not found: {templates_dir}")
        return

    # Collect all template files (only allowed extensions)
    files_data: dict[str, dict[str, str]] = {}

    for file_path in sorted(templates_dir.rglob("*")):
        if (
            file_path.is_file()
            and file_path.name != "VERSION"
            and file_path.suffix in ALLOWED_EXTENSIONS
        ):
            # Get relative path from templates_dir
            relative_path = file_path.relative_to(templates_dir)
            file_hash = calculate_file_hash(file_path)
            files_data[str(relative_path)] = {"hash": file_hash}

    # Build VERSION content
    version_data = {
        "template_version": "1.0.0",
        "lw_coder_version": get_lw_coder_version(),
        "frozen_date": date.today().isoformat(),
        "description": "Initial frozen baseline templates",
        "files": files_data,
    }

    # Write VERSION file
    version_path = templates_dir / "VERSION"
    version_path.write_text(
        json.dumps(version_data, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    print(f"Generated {version_path}")
    print(f"  Template version: {version_data['template_version']}")
    print(f"  lw_coder version: {version_data['lw_coder_version']}")
    print(f"  Frozen date: {version_data['frozen_date']}")
    print(f"  Files indexed: {len(files_data)}")


if __name__ == "__main__":
    generate_version_file()
