"""Validation logic for weft plan files."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .logging_config import get_logger
from .repo_utils import RepoUtilsError, find_repo_root

logger = get_logger(__name__)

_FRONT_MATTER_DELIM = "---"
_REQUIRED_KEYS = {"git_sha", "plan_id", "status"}
_OPTIONAL_KEYS = {"evaluation_notes", "linear_issue_id", "created_by", "created_at", "notes"}
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PLACEHOLDER_SHA = "0" * 40
_PLAN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{3,100}$")
_VALID_STATUSES = {"draft", "ready", "coding", "implemented", "done", "abandoned"}


class PlanValidationError(Exception):
    """Raised when a plan file fails validation."""


@dataclass(slots=True)
class PlanMetadata:
    """Parsed representation of a validated plan file."""

    plan_text: str
    git_sha: str
    evaluation_notes: list[str]
    plan_path: Path
    repo_root: Path
    plan_id: str
    status: str
    linear_issue_id: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    notes: str | None = None


def extract_front_matter(markdown: str) -> tuple[dict[str, Any], str]:
    """Extract YAML front matter from markdown content.

    Public API for extracting front matter from plan files.

    Args:
        markdown: Markdown content with YAML front matter.

    Returns:
        Tuple of (front_matter_dict, body_text).

    Raises:
        PlanValidationError: If front matter is malformed.
    """
    return _extract_front_matter(markdown)


def load_plan_id(plan_path: Path | str) -> tuple[str, Path]:
    """Load plan_id from a plan file (lightweight version of load_plan_metadata).

    Args:
        plan_path: Path to the plan file.

    Returns:
        Tuple of (plan_id, resolved_plan_path).

    Raises:
        PlanValidationError: If plan file is invalid or missing plan_id.
    """
    resolved_path = Path(plan_path).expanduser().resolve()
    if not resolved_path.exists():
        raise PlanValidationError(f"Plan file not found: {resolved_path}")

    try:
        content = resolved_path.read_text(encoding="utf-8")
        front_matter, _ = _extract_front_matter(content)
    except (OSError, PlanValidationError) as exc:
        raise PlanValidationError(f"Failed to read plan file: {exc}") from exc

    plan_id = front_matter.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise PlanValidationError("Plan file must have a valid 'plan_id' in front matter")

    return plan_id.strip(), resolved_path


def load_plan_metadata(plan_path: Path | str) -> PlanMetadata:
    """Parse and validate the plan file located at ``plan_path``.

    Args:
        plan_path: Path to the Markdown plan file containing YAML front matter.

    Returns:
        A :class:`PlanMetadata` instance containing the parsed metadata when validation succeeds.

    Raises:
        PlanValidationError: If the plan file is invalid.
    """

    path = Path(plan_path).expanduser().resolve()
    if not path.exists():
        raise PlanValidationError(f"Plan file not found: {path}")
    if not path.is_file():
        raise PlanValidationError(f"Plan path must be a file: {path}")

    logger.debug("Loading plan metadata from %s", path)

    content = path.read_text(encoding="utf-8")
    front_matter, body_text = _extract_front_matter(content)
    _enforce_exact_keys(front_matter, _REQUIRED_KEYS)

    # Validate required fields
    git_sha_value = _validate_git_sha(front_matter.get("git_sha"))
    evaluation_notes_value = _validate_evaluation_notes(front_matter.get("evaluation_notes"))
    plan_id_value = _validate_plan_id(front_matter.get("plan_id"), path)
    status_value = _validate_status(front_matter.get("status"))

    if git_sha_value == PLACEHOLDER_SHA and status_value != "draft":
        raise PlanValidationError(
            "Field 'git_sha' may use the all-zeros placeholder only when status is 'draft'."
        )
    plan_text_value = _validate_plan_body(body_text)

    # Validate optional fields if present
    created_at_value = None
    if "created_at" in front_matter:
        created_at_value = _validate_created_at(front_matter["created_at"])

    linear_issue_id_value = front_matter.get("linear_issue_id")
    created_by_value = front_matter.get("created_by")
    notes_value = front_matter.get("notes")

    try:
        repo_root = find_repo_root(path)
    except RepoUtilsError as exc:
        raise PlanValidationError("Plan file must reside inside a Git repository.") from exc

    _ensure_path_within_repo(path, repo_root)
    if git_sha_value != PLACEHOLDER_SHA:
        _ensure_commit_exists(repo_root, git_sha_value)

    logger.debug(
        "Plan validation succeeded for %s (plan_id=%s, git_sha=%s, status=%s)",
        path.name,
        plan_id_value,
        git_sha_value[:8],
        status_value,
    )

    return PlanMetadata(
        plan_text=plan_text_value,
        git_sha=git_sha_value,
        evaluation_notes=evaluation_notes_value,
        plan_path=path,
        repo_root=repo_root,
        plan_id=plan_id_value,
        status=status_value,
        linear_issue_id=linear_issue_id_value,
        created_by=created_by_value,
        created_at=created_at_value,
        notes=notes_value,
    )


def _extract_front_matter(markdown: str) -> tuple[dict[str, Any], str]:
    """Extract front matter from markdown content using regex parsing.

    Note: Uses regex instead of YAML for performance and simplicity.
    Plan files use simple format (key: value pairs, simple lists).
    If format becomes complex (nested structures, multiline values, etc.),
    migrate to full YAML parsing library.

    Args:
        markdown: Markdown content with front matter.

    Returns:
        Tuple of (front_matter_dict, body_text).

    Raises:
        PlanValidationError: If front matter is malformed.
    """
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != _FRONT_MATTER_DELIM:
        raise PlanValidationError("Plan file must begin with a YAML front matter block (---).")

    try:
        closing_index = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.strip() == _FRONT_MATTER_DELIM
        )
    except StopIteration as exc:
        raise PlanValidationError("Front matter block is missing the closing --- fence.") from exc

    # Parse front matter lines using regex
    front_matter_lines = lines[1:closing_index]
    parsed = _parse_front_matter_lines(front_matter_lines)

    body = "\n".join(lines[closing_index + 1 :])

    return parsed, body


# Regex patterns for parsing front matter
# Matches "key: value" or "key:" (value on next lines)
_KEY_VALUE_PATTERN = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$')
# Matches list items "- value" with optional leading whitespace
# yaml.safe_dump produces "- item" (no indent), but hand-written YAML often uses "  - item"
_LIST_ITEM_PATTERN = re.compile(r'^(\s*)-\s+(.*)$')


def _parse_front_matter_lines(lines: list[str]) -> dict[str, Any]:
    """Parse front matter lines into a dictionary.

    Handles:
    - Simple key: value pairs
    - Empty lists: key: []
    - Multi-line lists with - items

    Args:
        lines: Lines between the --- delimiters.

    Returns:
        Dictionary of parsed key-value pairs.

    Raises:
        PlanValidationError: If parsing fails.
    """
    parsed: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue

        # Check for list item first (indented with -)
        list_match = _LIST_ITEM_PATTERN.match(line)
        if list_match:
            if current_key is None or current_list is None:
                raise PlanValidationError(
                    "Front matter contains list item without preceding key."
                )
            item_value = list_match.group(2).strip()
            # Remove surrounding quotes if present
            if (item_value.startswith('"') and item_value.endswith('"')) or \
               (item_value.startswith("'") and item_value.endswith("'")):
                item_value = item_value[1:-1]
            current_list.append(item_value)
            continue

        # Check for key: value pattern
        key_match = _KEY_VALUE_PATTERN.match(line)
        if key_match:
            # Save previous list if any
            if current_key is not None and current_list is not None:
                parsed[current_key] = current_list

            key = key_match.group(1)
            value = key_match.group(2).strip()

            if value == "[]":
                # Empty list
                parsed[key] = []
                current_key = None
                current_list = None
            elif value == "":
                # Value will be a list on following lines
                current_key = key
                current_list = []
            else:
                # Simple string value - remove surrounding quotes if present
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                parsed[key] = value
                current_key = None
                current_list = None
        else:
            # Line doesn't match expected patterns
            raise PlanValidationError(
                f"Unable to parse front matter line: {line!r}"
            )

    # Save final list if any
    if current_key is not None and current_list is not None:
        parsed[current_key] = current_list

    return parsed


def _enforce_exact_keys(data: dict[str, Any], required_keys: Iterable[str]) -> None:
    keys = set(data.keys())
    allowed_keys = set(required_keys) | _OPTIONAL_KEYS
    missing = sorted(set(required_keys) - keys)
    extra = sorted(keys - allowed_keys)

    if missing:
        raise PlanValidationError(
            "Front matter is missing required key(s): " + ", ".join(missing)
        )
    if extra:
        raise PlanValidationError(
            "Front matter contains unsupported key(s): " + ", ".join(extra)
        )


def _validate_plan_body(body: str) -> str:
    if body is None:
        raise PlanValidationError("Plan body is missing.")

    stripped = body.strip()
    if not stripped:
        raise PlanValidationError("Plan body must contain non-empty Markdown content after front matter.")

    return stripped


def _validate_git_sha(value: Any) -> str:
    if not isinstance(value, str):
        raise PlanValidationError("Field 'git_sha' must be a string.")
    normalized = value.strip()
    if not _SHA_PATTERN.fullmatch(normalized.lower()):
        raise PlanValidationError("Field 'git_sha' must be a 40-character lowercase hex commit SHA.")
    return normalized.lower()


def _validate_evaluation_notes(value: Any) -> list[str]:
    # evaluation_notes is optional, so None or empty list is acceptable
    if value is None:
        return []

    if not isinstance(value, list):
        raise PlanValidationError("Field 'evaluation_notes' must be a list of strings.")

    # Empty list is now allowed
    if not value:
        return []

    cleaned_notes: list[str] = []
    for note in value:
        if not isinstance(note, str):
            raise PlanValidationError("Each evaluation note must be a string.")
        stripped = note.strip()
        if not stripped:
            raise PlanValidationError("Evaluation notes must not be empty strings.")
        cleaned_notes.append(stripped)

    return cleaned_notes


def _validate_plan_id(value: Any, plan_path: Path) -> str:
    if not isinstance(value, str):
        raise PlanValidationError("Field 'plan_id' must be a string.")

    stripped = value.strip()
    if not _PLAN_ID_PATTERN.fullmatch(stripped):
        raise PlanValidationError(
            "Field 'plan_id' must match pattern ^[a-zA-Z0-9._-]{3,100}$ (3-100 chars, alphanumeric/._- only)."
        )

    # Check uniqueness within plan directory
    tasks_dir = plan_path.parent
    for other_plan in tasks_dir.glob("*.md"):
        if other_plan.resolve() == plan_path.resolve():
            continue
        try:
            content = other_plan.read_text(encoding="utf-8")
            front_matter, _ = _extract_front_matter(content)
            other_id = front_matter.get("plan_id")
            if other_id == stripped:
                raise PlanValidationError(
                    f"Field 'plan_id' value '{stripped}' is not unique. Found duplicate in {other_plan.name}."
                )
        except PlanValidationError as e:
            # If the PlanValidationError is about duplicate plan_id, re-raise it
            if "not unique" in str(e):
                raise
            # Otherwise skip files with other validation errors
            continue
        except (KeyError, OSError):
            # Skip files that can't be read or parsed
            continue

    return stripped


def _validate_status(value: Any) -> str:
    if not isinstance(value, str):
        raise PlanValidationError("Field 'status' must be a string.")

    normalized = value.strip().lower()
    if normalized not in _VALID_STATUSES:
        valid_list = ", ".join(sorted(_VALID_STATUSES))
        raise PlanValidationError(
            f"Field 'status' must be one of: {valid_list} (case-insensitive)."
        )

    return normalized


def _validate_created_at(value: Any) -> str:
    if not isinstance(value, str):
        raise PlanValidationError("Field 'created_at' must be a string in ISO 8601 datetime format.")

    from datetime import datetime

    stripped = value.strip()
    try:
        datetime.fromisoformat(stripped)
    except ValueError as exc:
        raise PlanValidationError(
            f"Field 'created_at' must be a valid ISO 8601 datetime format: {exc}"
        ) from exc

    return stripped


def _ensure_path_within_repo(path: Path, repo_root: Path) -> None:
    try:
        path.resolve().relative_to(repo_root)
    except ValueError as exc:
        raise PlanValidationError(
            f"Plan file must be located inside the Git repository at {repo_root}."
        ) from exc


def _ensure_commit_exists(repo_root: Path, git_sha: str) -> None:
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "cat-file",
                "-t",
                git_sha,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise PlanValidationError(
            f"Git commit '{git_sha}' does not exist in repository {repo_root}."
        ) from exc

    object_type = result.stdout.strip()
    if object_type != "commit":
        raise PlanValidationError(
            f"Git object '{git_sha}' is of type '{object_type}', expected a commit."
        )
