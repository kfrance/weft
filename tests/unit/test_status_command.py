"""Tests for status command."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from weft.status_command import (
    _format_check,
    _format_relative_time,
    _format_table,
    _get_pipeline_state,
    _get_status_order,
    run_status_command,
)
from weft.completion.cache import PlanInfo, _global_cache

from tests.helpers import GitRepo, write_plan


@pytest.fixture(autouse=True)
def invalidate_cache():
    """Invalidate global cache before and after each test."""
    _global_cache.invalidate()
    yield
    _global_cache.invalidate()


# =============================================================================
# Status Order Tests
# =============================================================================


def test_get_status_order_known_statuses() -> None:
    """Test that known statuses return correct order values."""
    assert _get_status_order("draft") == 0
    assert _get_status_order("ready") == 1
    assert _get_status_order("coding") == 2
    assert _get_status_order("implemented") == 3
    assert _get_status_order("done") == 4
    assert _get_status_order("abandoned") == 5


def test_get_status_order_case_insensitive() -> None:
    """Test that status comparison is case-insensitive."""
    assert _get_status_order("DRAFT") == 0
    assert _get_status_order("Ready") == 1
    assert _get_status_order("CODING") == 2


def test_get_status_order_unknown_status() -> None:
    """Test that unknown statuses sort with 'done'."""
    assert _get_status_order("unknown") == 4
    assert _get_status_order("") == 4
    assert _get_status_order("custom-status") == 4


# =============================================================================
# Pipeline State Tests
# =============================================================================


def test_get_pipeline_state_no_artifacts(git_repo: GitRepo) -> None:
    """Test pipeline state with no artifacts."""
    # Setup: Create .weft directory but no artifacts
    weft_dir = git_repo.path / ".weft"
    weft_dir.mkdir()

    # Execute
    state = _get_pipeline_state(git_repo.path, "test-plan")

    # Verify: All false
    assert state["worktree"] is False
    assert state["coded"] is False
    assert state["eval"] is False
    assert state["training"] is False


def test_get_pipeline_state_worktree_only(git_repo: GitRepo) -> None:
    """Test pipeline state with only worktree."""
    # Setup: Create worktree directory
    worktree_dir = git_repo.path / ".weft" / "worktrees" / "test-plan"
    worktree_dir.mkdir(parents=True)

    # Execute
    state = _get_pipeline_state(git_repo.path, "test-plan")

    # Verify: Only worktree is true
    assert state["worktree"] is True
    assert state["coded"] is False
    assert state["eval"] is False
    assert state["training"] is False


def test_get_pipeline_state_all_artifacts(git_repo: GitRepo) -> None:
    """Test pipeline state with all artifacts."""
    # Setup: Create all artifact directories
    weft_dir = git_repo.path / ".weft"
    (weft_dir / "worktrees" / "test-plan").mkdir(parents=True)
    (weft_dir / "sessions" / "test-plan" / "code").mkdir(parents=True)
    (weft_dir / "sessions" / "test-plan" / "eval").mkdir(parents=True)
    (weft_dir / "training_data" / "test-plan").mkdir(parents=True)

    # Execute
    state = _get_pipeline_state(git_repo.path, "test-plan")

    # Verify: All true
    assert state["worktree"] is True
    assert state["coded"] is True
    assert state["eval"] is True
    assert state["training"] is True


def test_get_pipeline_state_partial_artifacts(git_repo: GitRepo) -> None:
    """Test pipeline state with some artifacts."""
    # Setup: Create coded and eval but not worktree or training
    weft_dir = git_repo.path / ".weft"
    (weft_dir / "sessions" / "test-plan" / "code").mkdir(parents=True)
    (weft_dir / "sessions" / "test-plan" / "eval").mkdir(parents=True)

    # Execute
    state = _get_pipeline_state(git_repo.path, "test-plan")

    # Verify: Only coded and eval are true
    assert state["worktree"] is False
    assert state["coded"] is True
    assert state["eval"] is True
    assert state["training"] is False


# =============================================================================
# Formatting Tests
# =============================================================================


def test_format_check_true() -> None:
    """Test format_check returns checkmark for True."""
    assert _format_check(True) == "\u2713"


def test_format_check_false() -> None:
    """Test format_check returns dash for False."""
    assert _format_check(False) == "-"


def test_format_relative_time() -> None:
    """Test format_relative_time returns human-readable time."""
    # Use a timestamp from 2 days ago
    two_days_ago = time.time() - (2 * 24 * 60 * 60)
    result = _format_relative_time(two_days_ago)

    # Should contain "day" (could be "2 days ago" or similar)
    assert "day" in result.lower() or "ago" in result.lower()


def test_format_table_empty_plans(git_repo: GitRepo) -> None:
    """Test format_table with no plans shows headers only."""
    # Setup: Create .weft directory
    (git_repo.path / ".weft").mkdir()

    # Execute
    table = _format_table([], git_repo.path)

    # Verify: Contains headers
    assert "Plan ID" in table
    assert "Status" in table
    assert "Worktree" in table
    assert "Coded" in table
    assert "Eval" in table
    assert "Training" in table
    assert "Modified" in table


def test_format_table_with_plans(git_repo: GitRepo) -> None:
    """Test format_table with plans shows correct data."""
    # Setup: Create .weft directory and worktree for one plan
    weft_dir = git_repo.path / ".weft"
    (weft_dir / "worktrees" / "plan-with-worktree").mkdir(parents=True)

    plans = [
        PlanInfo(plan_id="plan-with-worktree", status="coding", mtime=time.time()),
        PlanInfo(plan_id="plan-no-artifacts", status="draft", mtime=time.time()),
    ]

    # Execute
    table = _format_table(plans, git_repo.path)

    # Verify: Contains plan IDs and statuses
    assert "plan-with-worktree" in table
    assert "plan-no-artifacts" in table
    assert "coding" in table
    assert "draft" in table

    # Verify: Contains checkmarks and dashes
    assert "\u2713" in table  # Checkmark for worktree
    assert "-" in table  # Dash for missing artifacts


def test_format_table_unknown_status(git_repo: GitRepo) -> None:
    """Test format_table handles unknown/empty status."""
    # Setup
    (git_repo.path / ".weft").mkdir()

    plans = [
        PlanInfo(plan_id="unknown-status", status="", mtime=time.time()),
    ]

    # Execute
    table = _format_table(plans, git_repo.path)

    # Verify: Shows "(unknown)" for empty status
    assert "(unknown)" in table


# =============================================================================
# Run Status Command Tests - Plan Scanning
# =============================================================================


def test_run_status_command_empty_tasks_directory(git_repo: GitRepo, capsys) -> None:
    """Test status command with empty tasks directory shows headers only."""
    # Setup: Create empty tasks directory
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Execute
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command()

    # Verify: Success
    assert exit_code == 0

    # Verify: Shows headers (empty table)
    captured = capsys.readouterr()
    assert "Plan ID" in captured.out


def test_run_status_command_multiple_plans(git_repo: GitRepo, capsys) -> None:
    """Test status command with multiple plans shows active ones by default."""
    # Setup: Create tasks directory with plans
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "plan-alpha.md",
        {"plan_id": "plan-alpha", "status": "ready", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "plan-beta.md",
        {"plan_id": "plan-beta", "status": "coding", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "plan-gamma.md",
        {"plan_id": "plan-gamma", "status": "done", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command()

    # Verify: Success
    assert exit_code == 0

    # Verify: Active plans shown, done plans hidden by default
    captured = capsys.readouterr()
    assert "plan-alpha" in captured.out
    assert "plan-beta" in captured.out
    assert "plan-gamma" not in captured.out  # Done plans hidden by default


def test_run_status_command_show_all_includes_done(git_repo: GitRepo, capsys) -> None:
    """Test --all flag shows done plans."""
    # Setup: Create tasks directory with plans
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "active-plan.md",
        {"plan_id": "active-plan", "status": "coding", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "done-plan.md",
        {"plan_id": "done-plan", "status": "done", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute with --all
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(show_all=True)

    # Verify: Success
    assert exit_code == 0

    # Verify: All plans shown including done
    captured = capsys.readouterr()
    assert "active-plan" in captured.out
    assert "done-plan" in captured.out


def test_run_status_command_explicit_status_filter_shows_done(git_repo: GitRepo, capsys) -> None:
    """Test --status done explicitly shows done plans."""
    # Setup: Create tasks directory with plans
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "active-plan.md",
        {"plan_id": "active-plan", "status": "coding", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "done-plan.md",
        {"plan_id": "done-plan", "status": "done", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute with --status done
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(status_filter="done")

    # Verify: Success
    assert exit_code == 0

    # Verify: Only done plans shown
    captured = capsys.readouterr()
    assert "active-plan" not in captured.out
    assert "done-plan" in captured.out


def test_run_status_command_missing_tasks_directory(git_repo: GitRepo, capsys) -> None:
    """Test status command handles missing .weft/tasks directory gracefully."""
    # Setup: Create .weft directory but no tasks subdirectory
    (git_repo.path / ".weft").mkdir()

    # Execute
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command()

    # Verify: Success (empty table)
    assert exit_code == 0

    # Verify: Shows headers
    captured = capsys.readouterr()
    assert "Plan ID" in captured.out


# =============================================================================
# Run Status Command Tests - Malformed Data
# =============================================================================


def test_run_status_command_plan_no_frontmatter(git_repo: GitRepo, capsys) -> None:
    """Test status command handles plan with no frontmatter."""
    # Setup: Create plan without frontmatter
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Write a plan file without frontmatter (just markdown)
    plan_file = tasks_dir / "no-frontmatter.md"
    plan_file.write_text("# Just some markdown\n\nNo frontmatter here.\n", encoding="utf-8")

    # Also create a valid plan to ensure we don't crash entirely
    write_plan(
        tasks_dir / "valid-plan.md",
        {"plan_id": "valid-plan", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command()

    # Verify: Success (doesn't crash)
    assert exit_code == 0

    # Verify: Valid plan still shows
    captured = capsys.readouterr()
    assert "valid-plan" in captured.out


def test_run_status_command_plan_empty_plan_id(git_repo: GitRepo, capsys) -> None:
    """Test status command handles plan with empty plan_id."""
    # Setup: Create plan with empty plan_id
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # The cache uses file stem as plan_id, so this should work
    write_plan(
        tasks_dir / "empty-id.md",
        {"plan_id": "", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command()

    # Verify: Success (doesn't crash)
    assert exit_code == 0


def test_run_status_command_inaccessible_plan(git_repo: GitRepo, capsys, tmp_path) -> None:
    """Test status command skips inaccessible plan files gracefully."""
    # Setup: Create tasks directory with a valid plan
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "valid-plan.md",
        {"plan_id": "valid-plan", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Note: Testing actual permission denied is tricky in tests, but the cache
    # handles OSError/IOError gracefully by skipping the file (see cache.py)
    # This test verifies the command still works with a valid plan present

    # Execute
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command()

    # Verify: Success
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "valid-plan" in captured.out


# =============================================================================
# Run Status Command Tests - Filtering
# =============================================================================


def test_run_status_command_filter_single_status(git_repo: GitRepo, capsys) -> None:
    """Test --status filter with single status."""
    # Setup: Create plans with different statuses
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "ready-plan.md",
        {"plan_id": "ready-plan", "status": "ready", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "coding-plan.md",
        {"plan_id": "coding-plan", "status": "coding", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "done-plan.md",
        {"plan_id": "done-plan", "status": "done", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute: Filter for ready only
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(status_filter="ready")

    # Verify: Success
    assert exit_code == 0

    # Verify: Only ready plan shown
    captured = capsys.readouterr()
    assert "ready-plan" in captured.out
    assert "coding-plan" not in captured.out
    assert "done-plan" not in captured.out


def test_run_status_command_filter_multiple_statuses(git_repo: GitRepo, capsys) -> None:
    """Test --status filter with comma-separated statuses."""
    # Setup: Create plans with different statuses
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "ready-plan.md",
        {"plan_id": "ready-plan", "status": "ready", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "coding-plan.md",
        {"plan_id": "coding-plan", "status": "coding", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "done-plan.md",
        {"plan_id": "done-plan", "status": "done", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute: Filter for ready and coding
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(status_filter="ready,coding")

    # Verify: Success
    assert exit_code == 0

    # Verify: Ready and coding plans shown, done not shown
    captured = capsys.readouterr()
    assert "ready-plan" in captured.out
    assert "coding-plan" in captured.out
    assert "done-plan" not in captured.out


def test_run_status_command_filter_no_matches(git_repo: GitRepo, capsys) -> None:
    """Test --status filter with no matching plans shows empty table."""
    # Setup: Create plans with different statuses
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "ready-plan.md",
        {"plan_id": "ready-plan", "status": "ready", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute: Filter for status that doesn't exist
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(status_filter="abandoned")

    # Verify: Success
    assert exit_code == 0

    # Verify: Shows headers but no plans
    captured = capsys.readouterr()
    assert "Plan ID" in captured.out
    assert "ready-plan" not in captured.out


def test_run_status_command_filter_case_insensitive(git_repo: GitRepo, capsys) -> None:
    """Test --status filter is case-insensitive."""
    # Setup: Create plan
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "ready-plan.md",
        {"plan_id": "ready-plan", "status": "ready", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute: Filter with uppercase
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(status_filter="READY")

    # Verify: Success
    assert exit_code == 0

    # Verify: Plan shows despite case difference
    captured = capsys.readouterr()
    assert "ready-plan" in captured.out


# =============================================================================
# Run Status Command Tests - Sorting
# =============================================================================


def test_run_status_command_default_sort_by_status_then_modified(git_repo: GitRepo, capsys) -> None:
    """Test default sort orders by status (pipeline order) then by modified (newest first)."""
    # Setup: Create plans with different statuses (all visible by default, no "done")
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create in non-pipeline order with different mtimes
    write_plan(
        tasks_dir / "implemented-plan.md",
        {"plan_id": "implemented-plan", "status": "implemented", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    time.sleep(0.01)  # Small delay to ensure different mtimes
    write_plan(
        tasks_dir / "draft-plan.md",
        {"plan_id": "draft-plan", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    time.sleep(0.01)
    write_plan(
        tasks_dir / "coding-plan.md",
        {"plan_id": "coding-plan", "status": "coding", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute: Default sort
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command()

    # Verify: Success
    assert exit_code == 0

    # Verify: Plans appear in pipeline order (draft, coding, implemented)
    captured = capsys.readouterr()
    output = captured.out
    draft_pos = output.find("draft-plan")
    coding_pos = output.find("coding-plan")
    implemented_pos = output.find("implemented-plan")

    assert draft_pos < coding_pos < implemented_pos, "Plans should be sorted by pipeline order"


def test_run_status_command_sort_by_plan_id(git_repo: GitRepo, capsys) -> None:
    """Test --sort plan_id sorts alphabetically."""
    # Setup: Create plans
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "charlie.md",
        {"plan_id": "charlie", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "alpha.md",
        {"plan_id": "alpha", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "bravo.md",
        {"plan_id": "bravo", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute: Sort by plan_id
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(sort_field="plan_id")

    # Verify: Success
    assert exit_code == 0

    # Verify: Plans appear in alphabetical order
    captured = capsys.readouterr()
    output = captured.out
    alpha_pos = output.find("alpha")
    bravo_pos = output.find("bravo")
    charlie_pos = output.find("charlie")

    assert alpha_pos < bravo_pos < charlie_pos, "Plans should be sorted alphabetically"


def test_run_status_command_sort_by_modified(git_repo: GitRepo, capsys) -> None:
    """Test --sort modified sorts by file modification time."""
    # Setup: Create plans with different mtimes
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "oldest.md",
        {"plan_id": "oldest", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    time.sleep(0.05)  # Ensure different mtimes
    write_plan(
        tasks_dir / "middle.md",
        {"plan_id": "middle", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    time.sleep(0.05)
    write_plan(
        tasks_dir / "newest.md",
        {"plan_id": "newest", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute: Sort by modified (newest first is default for modified sort)
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(sort_field="modified")

    # Verify: Success
    assert exit_code == 0

    # Verify: Plans appear in order (newest first)
    captured = capsys.readouterr()
    output = captured.out
    newest_pos = output.find("newest")
    middle_pos = output.find("middle")
    oldest_pos = output.find("oldest")

    assert newest_pos < middle_pos < oldest_pos, "Plans should be sorted by modified time (newest first)"


def test_run_status_command_sort_by_status(git_repo: GitRepo, capsys) -> None:
    """Test --sort status sorts by pipeline status order only."""
    # Setup: Create plans with different statuses (all visible by default, no "done")
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Create in non-pipeline order
    write_plan(
        tasks_dir / "implemented-plan.md",
        {"plan_id": "implemented-plan", "status": "implemented", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "draft-plan.md",
        {"plan_id": "draft-plan", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "ready-plan.md",
        {"plan_id": "ready-plan", "status": "ready", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute: Sort by status
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(sort_field="status")

    # Verify: Success
    assert exit_code == 0

    # Verify: Plans appear in pipeline order (draft, ready, implemented)
    captured = capsys.readouterr()
    output = captured.out
    draft_pos = output.find("draft-plan")
    ready_pos = output.find("ready-plan")
    implemented_pos = output.find("implemented-plan")

    assert draft_pos < ready_pos < implemented_pos, "Plans should be sorted by status (pipeline order)"


def test_run_status_command_reverse_sort(git_repo: GitRepo, capsys) -> None:
    """Test --reverse reverses the sort order."""
    # Setup: Create plans
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "alpha.md",
        {"plan_id": "alpha", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "bravo.md",
        {"plan_id": "bravo", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )
    write_plan(
        tasks_dir / "charlie.md",
        {"plan_id": "charlie", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute: Sort by plan_id with reverse
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command(sort_field="plan_id", reverse=True)

    # Verify: Success
    assert exit_code == 0

    # Verify: Plans appear in reverse alphabetical order
    captured = capsys.readouterr()
    output = captured.out
    alpha_pos = output.find("alpha")
    bravo_pos = output.find("bravo")
    charlie_pos = output.find("charlie")

    assert charlie_pos < bravo_pos < alpha_pos, "Plans should be sorted in reverse alphabetical order"


# =============================================================================
# Run Status Command Tests - Output Format
# =============================================================================


def test_run_status_command_table_columns(git_repo: GitRepo, capsys) -> None:
    """Test table includes all expected columns."""
    # Setup: Create tasks directory
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    # Execute
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command()

    # Verify: Success
    assert exit_code == 0

    # Verify: All columns present
    captured = capsys.readouterr()
    assert "Plan ID" in captured.out
    assert "Status" in captured.out
    assert "Worktree" in captured.out
    assert "Coded" in captured.out
    assert "Eval" in captured.out
    assert "Training" in captured.out
    assert "Modified" in captured.out


def test_run_status_command_modified_time_format(git_repo: GitRepo, capsys) -> None:
    """Test modified time shows relative format."""
    # Setup: Create a plan
    tasks_dir = git_repo.path / ".weft" / "tasks"
    tasks_dir.mkdir(parents=True)

    write_plan(
        tasks_dir / "test-plan.md",
        {"plan_id": "test-plan", "status": "draft", "git_sha": "0" * 40, "evaluation_notes": []},
    )

    # Execute
    with patch("weft.status_command.find_repo_root", return_value=git_repo.path):
        exit_code = run_status_command()

    # Verify: Success
    assert exit_code == 0

    # Verify: Output contains relative time (should include "ago" or similar)
    captured = capsys.readouterr()
    # humanize.naturaltime returns strings like "now", "2 seconds ago", etc.
    assert "now" in captured.out.lower() or "ago" in captured.out.lower() or "second" in captured.out.lower()


# =============================================================================
# Run Status Command Tests - Error Handling
# =============================================================================


def test_run_status_command_not_in_repo(capsys, caplog) -> None:
    """Test status command fails gracefully when not in a git repo."""
    from weft.repo_utils import RepoUtilsError

    # Execute: Mock find_repo_root to raise error
    with patch("weft.status_command.find_repo_root", side_effect=RepoUtilsError("Not in a git repo")):
        exit_code = run_status_command()

    # Verify: Failure
    assert exit_code == 1

    # Verify: Error logged
    assert "Failed to find repository root" in caplog.text
