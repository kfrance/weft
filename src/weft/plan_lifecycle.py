"""Utilities for managing plan lifecycle metadata."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Mapping

import yaml

_FRONT_MATTER_DELIM = "---"


class PlanLifecycleError(Exception):
    """Raised when plan lifecycle mutations fail."""


def update_plan_fields(plan_path: str | Path, updates: Mapping[str, Any]) -> None:
    """Update specific YAML front matter fields in the plan file.

    Args:
        plan_path: Path to the plan file to update.
        updates: Mapping of field names to new values.

    Raises:
        PlanLifecycleError: If the plan file is missing or cannot be updated.
    """

    path = Path(plan_path).expanduser().resolve()
    if not path.exists():
        raise PlanLifecycleError(f"Plan file not found: {path}")
    if not path.is_file():
        raise PlanLifecycleError(f"Plan path must be a file: {path}")

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive
        raise PlanLifecycleError(f"Failed to read plan file: {exc}") from exc

    front_matter_text, body_text = _split_front_matter(content)

    try:
        front_matter = yaml.safe_load(front_matter_text) if front_matter_text.strip() else {}
    except yaml.YAMLError as exc:
        raise PlanLifecycleError(f"Unable to parse plan front matter: {exc}") from exc

    if not isinstance(front_matter, dict):
        raise PlanLifecycleError("Plan front matter must be a mapping.")

    updated_front_matter = dict(front_matter)
    updated_front_matter.update(updates)

    yaml_block = yaml.safe_dump(updated_front_matter, sort_keys=False).strip()
    new_content = f"{_FRONT_MATTER_DELIM}\n{yaml_block}\n{_FRONT_MATTER_DELIM}\n{body_text}"

    try:
        path.write_text(new_content, encoding="utf-8")
    except OSError as exc:  # pragma: no cover - defensive
        raise PlanLifecycleError(f"Failed to write plan file: {exc}") from exc


def get_current_head_sha(repo_root: str | Path) -> str:
    """Return the current Git HEAD commit SHA for the repository at ``repo_root``."""

    root = Path(repo_root).expanduser().resolve()
    if not root.exists():
        raise PlanLifecycleError(f"Repository root not found: {root}")

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise PlanLifecycleError("Failed to resolve current Git HEAD SHA.") from exc

    sha = result.stdout.strip()
    if len(sha) != 40:
        raise PlanLifecycleError(
            f"Resolved HEAD SHA has unexpected length {len(sha)}: {sha!r}"
        )

    return sha


def _split_front_matter(content: str) -> tuple[str, str]:
    """Split a Markdown document into YAML front matter and body content."""

    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONT_MATTER_DELIM:
        raise PlanLifecycleError("Plan file must begin with a YAML front matter block (---).")

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _FRONT_MATTER_DELIM:
            front_matter_lines = lines[1:index]
            body_lines = lines[index + 1 :]
            front_matter_text = "".join(front_matter_lines)
            body_text = "".join(body_lines)
            return front_matter_text, body_text

    raise PlanLifecycleError("Front matter block is missing the closing --- fence.")
