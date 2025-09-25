from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lw_coder.plan_validator import PlanMetadata, PlanValidationError, load_plan_metadata


def _write_plan(path: Path, data: dict, body: str = "# Plan Body") -> None:
    yaml_block = yaml.safe_dump(data, sort_keys=False).strip()
    content = "---\n" + yaml_block + "\n---\n\n" + body + "\n"
    path.write_text(content, encoding="utf-8")


def test_validate_plan_success(git_repo):
    repo = git_repo
    plan_path = repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": repo.latest_commit(),
            "evaluation_notes": ["All tests pass", "Docs updated"],
        },
        body="# Refactor API\n\nEnsure error handling is improved."
    )

    metadata = load_plan_metadata(plan_path)

    assert isinstance(metadata, PlanMetadata)
    assert metadata.plan_text.startswith("# Refactor API")
    assert metadata.git_sha == repo.latest_commit()
    assert metadata.evaluation_notes == ["All tests pass", "Docs updated"]
    assert metadata.plan_path == plan_path.resolve()
    assert metadata.repo_root == repo.path.resolve()


def test_missing_front_matter(git_repo):
    plan_path = git_repo.path / "plan.md"
    plan_path.write_text("# Plan without front matter", encoding="utf-8")

    with pytest.raises(PlanValidationError, match="front matter block"):
        load_plan_metadata(plan_path)


def test_missing_required_key(git_repo):
    plan_path = git_repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
        },
    )

    with pytest.raises(PlanValidationError, match="missing required key"):  # noqa: PT012
        load_plan_metadata(plan_path)


def test_extra_key_disallowed(git_repo):
    plan_path = git_repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "extra": "noop",
        },
    )

    with pytest.raises(PlanValidationError, match="unsupported key"):
        load_plan_metadata(plan_path)


def test_invalid_git_sha_pattern(git_repo):
    plan_path = git_repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": "123",
            "evaluation_notes": ["All tests pass"],
        },
    )

    with pytest.raises(PlanValidationError, match="40-character"):
        load_plan_metadata(plan_path)


def test_git_sha_not_commit(git_repo):
    repo = git_repo
    tree_sha = repo.run("rev-parse", "HEAD^{tree}").stdout.strip()
    plan_path = repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": tree_sha,
            "evaluation_notes": ["All tests pass"],
        },
    )

    with pytest.raises(PlanValidationError, match="expected a commit"):
        load_plan_metadata(plan_path)


def test_evaluation_notes_must_be_list(git_repo):
    plan_path = git_repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": "All tests pass",
        },
    )

    with pytest.raises(PlanValidationError, match="list of strings"):
        load_plan_metadata(plan_path)


def test_empty_evaluation_note(git_repo):
    plan_path = git_repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass", "  "],
        },
    )

    with pytest.raises(PlanValidationError, match="must not be empty"):
        load_plan_metadata(plan_path)


def test_plan_outside_git_repo(tmp_path):
    plan_path = tmp_path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": "f" * 40,
            "evaluation_notes": ["All tests pass"],
        },
    )

    with pytest.raises(PlanValidationError, match="Git repository"):
        load_plan_metadata(plan_path)


def test_nonexistent_git_sha(git_repo):
    plan_path = git_repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": "f" * 40,
            "evaluation_notes": ["All tests pass"],
        },
    )


def test_missing_plan_body(git_repo):
    plan_path = git_repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
        },
        body=" \n \n\t",
    )

    with pytest.raises(PlanValidationError, match="Plan body must contain"):
        load_plan_metadata(plan_path)
