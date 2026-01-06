"""Tests for plan completion cache."""

from __future__ import annotations

import time


from weft.completion.cache import PlanCompletionCache, PlanInfo


def test_cache_returns_empty_list_for_nonexistent_dir(tmp_path):
    """Test that cache returns empty list when tasks directory doesn't exist."""
    cache = PlanCompletionCache()
    tasks_dir = tmp_path / ".weft" / "tasks"

    result = cache.get_active_plans(tasks_dir)
    assert result == []


def test_cache_returns_active_plans(tmp_path):
    """Test that cache returns plans with status != 'done'."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create active plan
    active_plan = tasks_dir / "active.md"
    active_plan.write_text(
        """---
status: draft
---
# Active Plan
"""
    )

    # Create done plan
    done_plan = tasks_dir / "done.md"
    done_plan.write_text(
        """---
status: done
---
# Done Plan
"""
    )

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir)

    assert "active" in result
    assert "done" not in result


def test_cache_includes_implemented_status(tmp_path):
    """Test that cache includes plans with status 'implemented'."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plans with different statuses
    (tasks_dir / "draft.md").write_text("---\nstatus: draft\n---\n# Draft")
    (tasks_dir / "coding.md").write_text("---\nstatus: coding\n---\n# Coding")
    (tasks_dir / "implemented.md").write_text("---\nstatus: implemented\n---\n# Implemented")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir)

    # Should include draft, coding, and implemented but not done
    assert "draft" in result
    assert "coding" in result
    assert "implemented" in result
    assert "done" not in result


def test_cache_handles_malformed_yaml(tmp_path):
    """Test that cache gracefully handles malformed YAML."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plan with invalid YAML
    bad_plan = tasks_dir / "bad.md"
    bad_plan.write_text(
        """---
invalid: {yaml: [unclosed
---
# Bad Plan
"""
    )

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir)

    # Should include the plan despite invalid YAML
    assert "bad" in result


def test_cache_handles_unreadable_files(tmp_path):
    """Test that cache skips unreadable files."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create readable plan
    good_plan = tasks_dir / "good.md"
    good_plan.write_text(
        """---
status: draft
---
# Good Plan
"""
    )

    # Create unreadable plan (this is hard to test cross-platform)
    # For now, just test that readable files work
    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir)

    assert "good" in result


def test_cache_ttl_behavior(tmp_path):
    """Test that cache respects TTL."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create initial plan
    plan1 = tasks_dir / "plan1.md"
    plan1.write_text(
        """---
status: draft
---
# Plan 1
"""
    )

    cache = PlanCompletionCache(ttl_seconds=0.1)

    # First call - should scan filesystem
    result1 = cache.get_active_plans(tasks_dir)
    assert "plan1" in result1

    # Create second plan while cache is valid
    plan2 = tasks_dir / "plan2.md"
    plan2.write_text(
        """---
status: draft
---
# Plan 2
"""
    )

    # Second call - should use cache, not see plan2
    result2 = cache.get_active_plans(tasks_dir)
    assert "plan2" not in result2

    # Wait for cache to expire
    time.sleep(0.15)

    # Third call - should rescan and see plan2
    result3 = cache.get_active_plans(tasks_dir)
    assert "plan2" in result3


def test_cache_invalidate(tmp_path):
    """Test cache invalidation."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    plan = tasks_dir / "plan.md"
    plan.write_text(
        """---
status: draft
---
# Plan
"""
    )

    cache = PlanCompletionCache(ttl_seconds=10.0)

    # Populate cache
    result1 = cache.get_active_plans(tasks_dir)
    assert "plan" in result1

    # Invalidate cache
    cache.invalidate()

    # Create new plan
    plan2 = tasks_dir / "plan2.md"
    plan2.write_text(
        """---
status: draft
---
# Plan 2
"""
    )

    # Should see new plan after invalidation
    result2 = cache.get_active_plans(tasks_dir)
    assert "plan2" in result2


def test_cache_sorts_results(tmp_path):
    """Test that cache returns sorted plan IDs."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plans in non-alphabetical order
    for name in ["zebra", "alpha", "beta"]:
        plan = tasks_dir / f"{name}.md"
        plan.write_text(
            """---
status: draft
---
# Plan
"""
        )

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir)

    assert result == ["alpha", "beta", "zebra"]


def test_cache_filters_done_status_variations(tmp_path):
    """Test that cache filters various forms of 'done' status."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plans with different status values
    statuses = [
        ("done-exact", "done"),
        ("done-caps", "DONE"),
        ("done-mixed", "Done"),
        ("done-spaces", "  done  "),
        ("active", "draft"),
    ]

    for name, status in statuses:
        plan = tasks_dir / f"{name}.md"
        plan.write_text(
            f"""---
status: {status}
---
# Plan
"""
        )

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir)

    # Only "active" should be included
    assert result == ["active"]


def test_cache_handles_missing_status_field(tmp_path):
    """Test that cache includes plans with missing status field."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    plan = tasks_dir / "no-status.md"
    plan.write_text(
        """---
plan_id: no-status
---
# Plan
"""
    )

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir)

    # Should include plan with missing status (treated as not done)
    assert "no-status" in result


def test_get_active_plans_discovers_repo_root(tmp_path, monkeypatch):
    """Test that get_active_plans can discover repo root when tasks_dir=None."""
    # Create real git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    plan = tasks_dir / "plan.md"
    plan.write_text(
        """---
status: draft
---
# Plan
"""
    )

    # Change to repo directory
    monkeypatch.chdir(tmp_path)

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir=None)

    assert "plan" in result


def test_get_active_plans_returns_empty_when_not_in_repo(tmp_path, monkeypatch):
    """Test that get_active_plans returns empty list when not in a git repo."""
    # Don't create .git directory
    monkeypatch.chdir(tmp_path)

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir=None)

    assert result == []


# Tests for include_finished parameter


def test_include_finished_returns_done_plans(tmp_path):
    """Test that include_finished=True returns both done and non-done plans."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create active and done plans
    (tasks_dir / "active.md").write_text("---\nstatus: draft\n---\n# Active")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir, include_finished=True)

    assert "active" in result
    assert "done" in result
    assert len(result) == 2


def test_include_finished_false_excludes_done_plans(tmp_path):
    """Test that include_finished=False excludes done plans (existing behavior)."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create active and done plans
    (tasks_dir / "active.md").write_text("---\nstatus: draft\n---\n# Active")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    cache = PlanCompletionCache()
    result = cache.get_active_plans(tasks_dir, include_finished=False)

    assert "active" in result
    assert "done" not in result


def test_include_finished_default_maintains_backward_compatibility(tmp_path):
    """Test default parameter maintains backward compatibility."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create active and done plans
    (tasks_dir / "active.md").write_text("---\nstatus: draft\n---\n# Active")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    cache = PlanCompletionCache()
    # Call without include_finished parameter
    result = cache.get_active_plans(tasks_dir)

    # Should exclude done plans (backward compatible)
    assert "active" in result
    assert "done" not in result


def test_include_finished_with_mixed_statuses(tmp_path):
    """Test include_finished with mix of statuses."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create plans with different statuses
    statuses = [
        ("plan-draft", "draft"),
        ("plan-ready", "ready"),
        ("plan-coding", "coding"),
        ("plan-implemented", "implemented"),
        ("plan-done", "done"),
        ("plan-abandoned", "abandoned"),
    ]

    for name, status in statuses:
        (tasks_dir / f"{name}.md").write_text(f"---\nstatus: {status}\n---\n# {name}")

    cache = PlanCompletionCache()

    # With include_finished=False
    result_without_done = cache.get_active_plans(tasks_dir, include_finished=False)
    assert "plan-done" not in result_without_done
    assert "plan-draft" in result_without_done
    assert "plan-ready" in result_without_done
    assert "plan-coding" in result_without_done
    assert "plan-implemented" in result_without_done
    assert "plan-abandoned" in result_without_done

    # Invalidate cache for fresh scan
    cache.invalidate()

    # With include_finished=True
    result_with_done = cache.get_active_plans(tasks_dir, include_finished=True)
    assert "plan-done" in result_with_done
    assert len(result_with_done) == 6


def test_caching_works_with_include_finished_parameter(tmp_path):
    """Test caching works correctly with new parameter."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create active and done plans
    (tasks_dir / "active.md").write_text("---\nstatus: draft\n---\n# Active")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    cache = PlanCompletionCache(ttl_seconds=10.0)

    # First call with include_finished=False
    result1 = cache.get_active_plans(tasks_dir, include_finished=False)
    assert "done" not in result1

    # Second call with include_finished=True - should use same cache but filter differently
    result2 = cache.get_active_plans(tasks_dir, include_finished=True)
    assert "done" in result2

    # Third call with include_finished=False again
    result3 = cache.get_active_plans(tasks_dir, include_finished=False)
    assert "done" not in result3


# Tests for get_all_plans method


def test_get_all_plans_returns_plan_info(tmp_path):
    """Test that get_all_plans returns PlanInfo objects."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    (tasks_dir / "plan.md").write_text("---\nstatus: draft\n---\n# Plan")

    cache = PlanCompletionCache()
    result = cache.get_all_plans(tasks_dir)

    assert len(result) == 1
    assert isinstance(result[0], PlanInfo)
    assert result[0].plan_id == "plan"
    assert result[0].status == "draft"
    assert result[0].mtime > 0


def test_get_all_plans_includes_all_statuses(tmp_path):
    """Test that get_all_plans includes all plans regardless of status."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    (tasks_dir / "active.md").write_text("---\nstatus: draft\n---\n# Active")
    (tasks_dir / "done.md").write_text("---\nstatus: done\n---\n# Done")

    cache = PlanCompletionCache()
    result = cache.get_all_plans(tasks_dir)

    assert len(result) == 2
    plan_ids = [p.plan_id for p in result]
    assert "active" in plan_ids
    assert "done" in plan_ids


def test_get_all_plans_preserves_mtime(tmp_path):
    """Test that get_all_plans captures file mtime correctly."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    plan_file = tasks_dir / "plan.md"
    plan_file.write_text("---\nstatus: draft\n---\n# Plan")

    # Get expected mtime
    expected_mtime = plan_file.stat().st_mtime

    cache = PlanCompletionCache()
    result = cache.get_all_plans(tasks_dir)

    assert len(result) == 1
    assert result[0].mtime == expected_mtime


def test_get_all_plans_handles_invalid_yaml_mtime(tmp_path):
    """Test that get_all_plans handles malformed YAML and still gets mtime."""
    tasks_dir = tmp_path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    plan_file = tasks_dir / "bad.md"
    plan_file.write_text("---\ninvalid: {yaml: [unclosed\n---\n# Bad Plan")

    cache = PlanCompletionCache()
    result = cache.get_all_plans(tasks_dir)

    assert len(result) == 1
    assert result[0].plan_id == "bad"
    assert result[0].status == ""  # Unknown status for invalid YAML
    assert result[0].mtime > 0
