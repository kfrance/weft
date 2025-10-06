"""Validation logic for lw_coder plan files."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

_FRONT_MATTER_DELIM = "---"
_REQUIRED_KEYS = {"git_sha", "evaluation_notes", "plan_id", "branch_name", "status"}
_OPTIONAL_KEYS = {"linear_issue_id", "created_by", "created_at", "notes"}
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_PLAN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{3,100}$")
_VALID_STATUSES = {"draft", "ready", "coding", "review", "done", "abandoned"}


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
    branch_name: str
    status: str
    linear_issue_id: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    notes: str | None = None


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

    content = path.read_text(encoding="utf-8")
    front_matter, body_text = _extract_front_matter(content)
    _enforce_exact_keys(front_matter, _REQUIRED_KEYS)

    # Validate required fields
    git_sha_value = _validate_git_sha(front_matter.get("git_sha"))
    evaluation_notes_value = _validate_evaluation_notes(front_matter.get("evaluation_notes"))
    plan_id_value = _validate_plan_id(front_matter.get("plan_id"), path)
    branch_name_value = _validate_branch_name(front_matter.get("branch_name"))
    status_value = _validate_status(front_matter.get("status"))
    plan_text_value = _validate_plan_body(body_text)

    # Validate optional fields if present
    created_at_value = None
    if "created_at" in front_matter:
        created_at_value = _validate_created_at(front_matter["created_at"])

    linear_issue_id_value = front_matter.get("linear_issue_id")
    created_by_value = front_matter.get("created_by")
    notes_value = front_matter.get("notes")

    repo_root = _find_repo_root(path)
    _ensure_path_within_repo(path, repo_root)
    _ensure_commit_exists(repo_root, git_sha_value)

    return PlanMetadata(
        plan_text=plan_text_value,
        git_sha=git_sha_value,
        evaluation_notes=evaluation_notes_value,
        plan_path=path,
        repo_root=repo_root,
        plan_id=plan_id_value,
        branch_name=branch_name_value,
        status=status_value,
        linear_issue_id=linear_issue_id_value,
        created_by=created_by_value,
        created_at=created_at_value,
        notes=notes_value,
    )


def _extract_front_matter(markdown: str) -> tuple[dict[str, Any], str]:
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

    yaml_block = "\n".join(lines[1:closing_index])
    try:
        parsed = yaml.safe_load(yaml_block) if yaml_block.strip() else {}
    except yaml.YAMLError as exc:  # pragma: no cover - exercised in tests
        raise PlanValidationError(f"Unable to parse YAML front matter: {exc}") from exc

    if not isinstance(parsed, dict):
        raise PlanValidationError("Front matter must be a mapping of keys to values.")

    body = "\n".join(lines[closing_index + 1 :])

    return parsed, body


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
    if not isinstance(value, list):
        raise PlanValidationError("Field 'evaluation_notes' must be a list of strings.")
    if not value:
        raise PlanValidationError("Field 'evaluation_notes' must not be empty.")

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
        except (yaml.YAMLError, KeyError, OSError):
            # Skip files that can't be read or parsed
            continue

    return stripped


def _validate_branch_name(value: Any) -> str:
    if not isinstance(value, str):
        raise PlanValidationError("Field 'branch_name' must be a string.")

    stripped = value.strip()
    if not stripped:
        raise PlanValidationError("Field 'branch_name' must not be empty.")

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


def _find_repo_root(path: Path) -> Path:
    directory = path.parent
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive
        raise PlanValidationError(
            "Plan file must reside inside a Git repository."
        ) from exc

    repo_root = Path(result.stdout.strip()).resolve()
    if not repo_root.exists():  # pragma: no cover - defensive
        raise PlanValidationError("Git repository root could not be determined.")
    return repo_root


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
