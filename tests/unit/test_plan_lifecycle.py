from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lw_coder.plan_lifecycle import (
    PlanLifecycleError,
    get_current_head_sha,
    update_plan_fields,
    _split_front_matter,
)
from lw_coder.plan_validator import _extract_front_matter
from tests.conftest import write_plan


def _load_front_matter(path: Path) -> dict[str, object]:
    content = path.read_text(encoding="utf-8")
    front_matter, _ = _extract_front_matter(content)
    return front_matter


def test_update_plan_fields_basic(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.md"
    write_plan(
        plan_path,
        {
            "plan_id": "plan-basic",
            "git_sha": "a" * 40,
            "status": "draft",
            "evaluation_notes": [],
        },
        body="# Objectives\n\n- First",
    )

    original_front_text, original_body = _split_front_matter(plan_path.read_text(encoding="utf-8"))
    original_front = yaml.safe_load(original_front_text)

    update_plan_fields(plan_path, {"status": "coding"})

    updated_front_text, updated_body = _split_front_matter(plan_path.read_text(encoding="utf-8"))
    updated_front = yaml.safe_load(updated_front_text)

    assert updated_front["status"] == "coding"
    assert updated_front["plan_id"] == original_front["plan_id"]
    assert updated_body == original_body


def test_update_plan_fields_multiple_fields(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.md"
    write_plan(
        plan_path,
        {
            "plan_id": "plan-multi",
            "git_sha": "0" * 40,
            "status": "draft",
            "evaluation_notes": [],
        },
    )

    update_plan_fields(plan_path, {"git_sha": "b" * 40, "status": "coding"})

    front_matter = _load_front_matter(plan_path)
    assert front_matter["git_sha"] == "b" * 40
    assert front_matter["status"] == "coding"
    assert front_matter["plan_id"] == "plan-multi"


def test_update_plan_fields_nonexistent_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.md"
    with pytest.raises(PlanLifecycleError, match="Plan file not found"):
        update_plan_fields(missing_path, {"status": "coding"})


def test_update_plan_fields_preserves_body_formatting(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.md"
    body = (
        "# Heading\n"
        "\n"
        "- Item 1\n"
        "- Item 2\n"
        "\n"
        "```python\nprint('hello')\n```\n"
    )
    write_plan(
        plan_path,
        {
            "plan_id": "plan-body",
            "git_sha": "c" * 40,
            "status": "draft",
            "evaluation_notes": [],
        },
        body=body,
    )

    original_front_text, original_body = _split_front_matter(plan_path.read_text(encoding="utf-8"))

    update_plan_fields(plan_path, {"status": "coding"})

    updated_front_text, updated_body = _split_front_matter(plan_path.read_text(encoding="utf-8"))
    assert updated_front_text is not None
    assert updated_body == original_body


def test_get_current_head_sha(git_repo) -> None:
    sha = get_current_head_sha(git_repo.path)
    assert isinstance(sha, str)
    assert len(sha) == 40
    assert sha == git_repo.latest_commit()


def test_get_current_head_sha_not_a_repo(tmp_path: Path) -> None:
    with pytest.raises(PlanLifecycleError):
        get_current_head_sha(tmp_path)
