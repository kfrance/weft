"""Validation logic for lw_coder plan files."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

_FRONT_MATTER_DELIM = "---"
_REQUIRED_KEYS = {"git_sha", "evaluation_notes"}
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


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

    git_sha_value = _validate_git_sha(front_matter.get("git_sha"))
    evaluation_notes_value = _validate_evaluation_notes(front_matter.get("evaluation_notes"))
    plan_text_value = _validate_plan_body(body_text)

    repo_root = _find_repo_root(path)
    _ensure_path_within_repo(path, repo_root)
    _ensure_commit_exists(repo_root, git_sha_value)

    return PlanMetadata(
        plan_text=plan_text_value,
        git_sha=git_sha_value,
        evaluation_notes=evaluation_notes_value,
        plan_path=path,
        repo_root=repo_root,
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
    missing = sorted(set(required_keys) - keys)
    extra = sorted(keys - set(required_keys))

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
