"""Tests for exploration resolver module."""

from __future__ import annotations

from weft.exploration_resolver import ExplorationResolver
from weft.exploration_store import save_exploration

from tests.helpers import GitRepo


def test_resolve_found(git_repo: GitRepo) -> None:
    """Verify resolver returns content for existing exploration."""
    save_exploration(git_repo.path, "cache-bug", "## Findings\n\nCache TTL too low.")

    content = ExplorationResolver.resolve("cache-bug", git_repo.path)
    assert content == "## Findings\n\nCache TTL too low."


def test_resolve_not_found(git_repo: GitRepo) -> None:
    """Verify resolver returns None for missing exploration."""
    content = ExplorationResolver.resolve("nonexistent", git_repo.path)
    assert content is None


def test_resolve_plan_file_takes_priority(git_repo: GitRepo) -> None:
    """Verify plan file resolution takes priority over exploration.

    This test documents the expected behavior in cli.py: PlanResolver.resolve()
    is called first; only on FileNotFoundError does the code try
    ExplorationResolver.resolve(). So a plan file named 'foo' would be found
    first and the exploration never consulted.
    """
    from weft.plan_resolver import PlanResolver

    # Create a plan file
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_file = tasks_dir / "my-plan.md"
    plan_file.write_text(
        "---\nplan_id: my-plan\nstatus: draft\ngit_sha: \"0000000000000000000000000000000000000000\"\nevaluation_notes: []\n---\n\n# Plan Body\n",
        encoding="utf-8",
    )

    # Also create an exploration with same name
    save_exploration(git_repo.path, "my-plan", "Exploration findings")

    # PlanResolver should find the plan file
    import os
    old_cwd = os.getcwd()
    try:
        os.chdir(git_repo.path)
        resolved = PlanResolver.resolve("my-plan")
        assert resolved.exists()
        assert "tasks" in str(resolved)
    finally:
        os.chdir(old_cwd)
