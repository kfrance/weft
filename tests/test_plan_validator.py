from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.plan_validator import PlanMetadata, PlanValidationError, load_plan_metadata
from tests.conftest import write_plan


def test_validate_plan_success(git_repo):
    repo = git_repo
    plan_path = repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": repo.latest_commit(),
            "evaluation_notes": ["All tests pass", "Docs updated"],
            "plan_id": "plan-refactor-api",
            "status": "draft",
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
    assert metadata.plan_id == "plan-refactor-api"
    assert metadata.status == "draft"
    assert metadata.linear_issue_id is None
    assert metadata.created_by is None
    assert metadata.created_at is None
    assert metadata.notes is None


def test_missing_front_matter(git_repo):
    plan_path = git_repo.path / "plan.md"
    plan_path.write_text("# Plan without front matter", encoding="utf-8")

    with pytest.raises(PlanValidationError, match="front matter block"):
        load_plan_metadata(plan_path)


def test_missing_required_key(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            # Missing required fields: plan_id and status
        },
    )

    with pytest.raises(PlanValidationError, match="missing required key"):  # noqa: PT012
        load_plan_metadata(plan_path)


def test_extra_key_disallowed(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-extra",
            "status": "draft",
            "extra": "noop",
        },
    )

    with pytest.raises(PlanValidationError, match="unsupported key"):
        load_plan_metadata(plan_path)


def test_invalid_git_sha_pattern(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": "123",
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-sha",
            "status": "draft",
        },
    )

    with pytest.raises(PlanValidationError, match="40-character"):
        load_plan_metadata(plan_path)


def test_git_sha_not_commit(git_repo):
    repo = git_repo
    tree_sha = repo.run("rev-parse", "HEAD^{tree}").stdout.strip()
    plan_path = repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": tree_sha,
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-tree",
            "status": "draft",
        },
    )

    with pytest.raises(PlanValidationError, match="expected a commit"):
        load_plan_metadata(plan_path)


def test_evaluation_notes_must_be_list(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": "All tests pass",
            "plan_id": "plan-test-notes",
            "status": "draft",
        },
    )

    with pytest.raises(PlanValidationError, match="list of strings"):
        load_plan_metadata(plan_path)


def test_empty_evaluation_note(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass", "  "],
            "plan_id": "plan-test-empty",
            "status": "draft",
        },
    )

    with pytest.raises(PlanValidationError, match="must not be empty"):
        load_plan_metadata(plan_path)


def test_evaluation_notes_optional_missing(git_repo):
    """Test that evaluation_notes field can be completely omitted."""
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "plan_id": "plan-test-no-notes",
            "status": "draft",
        },
        body="# Task\n\nImplement feature X"
    )

    metadata = load_plan_metadata(plan_path)
    assert metadata.evaluation_notes == []


def test_evaluation_notes_optional_empty_list(git_repo):
    """Test that evaluation_notes can be an empty list."""
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": [],
            "plan_id": "plan-test-empty-list",
            "status": "draft",
        },
        body="# Task\n\nImplement feature Y"
    )

    metadata = load_plan_metadata(plan_path)
    assert metadata.evaluation_notes == []


def test_plan_outside_git_repo(tmp_path):
    plan_path = tmp_path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": "f" * 40,
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-outside",
            "status": "draft",
        },
    )

    with pytest.raises(PlanValidationError, match="Git repository"):
        load_plan_metadata(plan_path)


def test_nonexistent_git_sha(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": "f" * 40,
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-nonexistent",
            "status": "draft",
        },
    )

    with pytest.raises(PlanValidationError, match="does not exist"):
        load_plan_metadata(plan_path)


def test_missing_plan_body(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-body",
            "status": "draft",
        },
        body=" \n \n\t",
    )

    with pytest.raises(PlanValidationError, match="Plan body must contain"):
        load_plan_metadata(plan_path)


# New field validation tests


def test_plan_id_invalid_pattern(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "ab",  # Too short
            "status": "draft",
        },
    )

    with pytest.raises(PlanValidationError, match="match pattern"):
        load_plan_metadata(plan_path)


def test_plan_id_invalid_characters(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan@invalid",  # Invalid character @
            "status": "draft",
        },
    )

    with pytest.raises(PlanValidationError, match="match pattern"):
        load_plan_metadata(plan_path)


def test_plan_id_duplicate(git_repo):
    # Create first plan
    plan_path_1 = git_repo.path / "plan1.md"
    write_plan(
        plan_path_1,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "duplicate-id",
            "status": "draft",
        },
    )

    # Create second plan with duplicate plan_id
    plan_path_2 = git_repo.path / "plan2.md"
    write_plan(
        plan_path_2,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "duplicate-id",
            "status": "draft",
        },
    )

    with pytest.raises(PlanValidationError, match="not unique"):
        load_plan_metadata(plan_path_2)


def test_status_invalid(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-status",
            "status": "invalid_status",
        },
    )

    with pytest.raises(PlanValidationError, match="must be one of"):
        load_plan_metadata(plan_path)


def test_status_case_insensitive(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-case",
            "status": "DRAFT",  # Uppercase
        },
    )

    metadata = load_plan_metadata(plan_path)
    assert metadata.status == "draft"  # Normalized to lowercase


def test_optional_fields_present(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-optional",
            "status": "draft",
            "linear_issue_id": "LW-123",
            "created_by": "test-user",
            "created_at": "2025-01-15T10:30:00",
            "notes": "Some notes here",
        },
    )

    metadata = load_plan_metadata(plan_path)
    assert metadata.linear_issue_id == "LW-123"
    assert metadata.created_by == "test-user"
    assert metadata.created_at == "2025-01-15T10:30:00"
    assert metadata.notes == "Some notes here"


def test_created_at_invalid_format(git_repo):
    plan_path = git_repo.path / "plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-test-datetime",
            "status": "draft",
            "created_at": "not-a-datetime",
        },
    )

    with pytest.raises(PlanValidationError, match="ISO 8601"):
        load_plan_metadata(plan_path)
