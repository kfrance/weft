"""Tests for code_command module."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import lw_coder.code_command as code_command
from lw_coder.code_command import _filter_env_vars, run_code_command
from lw_coder.executors import ExecutorRegistry
from lw_coder.plan_validator import PLACEHOLDER_SHA, PlanMetadata, PlanValidationError, _extract_front_matter
from lw_coder.worktree_utils import WorktreeError

try:
    from tests.conftest import write_plan, GitRepo
except ImportError:
    # Fallback if conftest is not available
    def write_plan(path, *args, **kwargs):
        """Write a test plan file."""
        plan_text = kwargs.get("body", "# Test Plan")
        git_sha = kwargs.get("git_sha", "a" * 40)
        plan_id = kwargs.get("plan_id", "test-plan")
        status = kwargs.get("status", "draft")

        content = f"""---
plan_id: {plan_id}
git_sha: {git_sha}
status: {status}
evaluation_notes: []
---

{plan_text}
"""
        path.write_text(content)

    class GitRepo:
        """Simple GitRepo mock."""
        pass


def mock_executor_factory():
    """Create a mock executor for testing."""
    return SimpleNamespace(
        check_auth=lambda: None,
        build_command=lambda p: f'claude "$(cat {p})"',
        get_env_vars=lambda factory_dir: None
    )


def test_run_code_command_validation_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with plan validation failure."""
    # Setup
    plan_path = tmp_path / "plan.md"

    # Mock load_plan_metadata to raise PlanValidationError
    def mock_load_plan_metadata(path):
        raise PlanValidationError("Invalid git_sha")

    # Apply monkeypatch
    monkeypatch.setattr(code_command, "load_plan_metadata", mock_load_plan_metadata)

    # Execute
    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    # Assert
    assert exit_code == 1
    assert "Plan validation failed" in caplog.text
    assert "Invalid git_sha" in caplog.text


def test_run_code_command_worktree_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with worktree preparation failure."""
    plan_path = tmp_path / "plan.md"
    run_dir = tmp_path / ".lw_coder" / "runs" / "test-plan" / "20250101_120000"

    mock_metadata = PlanMetadata(
        plan_text="# Test Plan",
        git_sha="b" * 40,
        evaluation_notes=["Test note"],
        plan_path=plan_path,
        repo_root=tmp_path,
        plan_id="test-plan-fail",
        status="draft",
    )

    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    def mock_ensure_worktree(metadata):
        raise WorktreeError("Failed to create worktree")

    monkeypatch.setattr(code_command, "load_plan_metadata", lambda path: mock_metadata)
    monkeypatch.setattr(code_command, "create_run_directory", lambda repo_root, plan_id: run_dir)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda run_dir: run_dir / "droids")
    monkeypatch.setattr(code_command, "load_prompts", lambda repo_root, tool, model: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda repo_root, active_run_dir: 0)
    monkeypatch.setattr(code_command, "ensure_worktree", mock_ensure_worktree)

    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "Plan validation succeeded" in caplog.text
    assert "Worktree preparation failed" in caplog.text
    assert "Failed to create worktree" in caplog.text


def test_filter_env_vars_with_patterns(monkeypatch) -> None:
    """Test _filter_env_vars with wildcard patterns."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "key123")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://api.openrouter.ai")
    monkeypatch.setenv("OTHER_VAR", "value")

    result = _filter_env_vars(["OPENROUTER_*"])

    assert "OPENROUTER_API_KEY" in result
    assert "OPENROUTER_BASE_URL" in result
    assert "OTHER_VAR" not in result


def test_filter_env_vars_with_star(monkeypatch) -> None:
    """Test _filter_env_vars with * pattern (all vars)."""
    monkeypatch.setenv("VAR1", "value1")
    monkeypatch.setenv("VAR2", "value2")

    result = _filter_env_vars(["*"])

    assert "VAR1" in result
    assert "VAR2" in result
    assert len(result) > 2  # Should include all env vars


def test_filter_env_vars_no_matches(monkeypatch) -> None:
    """Test _filter_env_vars when no vars match."""
    result = _filter_env_vars(["NONEXISTENT_*"])

    assert result == {}


def test_code_command_replaces_placeholder_git_sha(monkeypatch, git_repo, tmp_path: Path) -> None:
    plan_id = "plan-placeholder"
    plan_path = git_repo.path / f"{plan_id}.md"
    write_plan(
        plan_path,
        {
            "git_sha": PLACEHOLDER_SHA,
            "plan_id": plan_id,
            "status": "draft",
        },
    )

    head_sha = git_repo.latest_commit()
    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_000000"
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)

    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    def fake_create_run_directory(repo_root: Path, received_plan_id: str) -> Path:
        assert repo_root == git_repo.path
        assert received_plan_id == plan_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    monkeypatch.setattr(code_command, "create_run_directory", fake_create_run_directory)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda _: droids_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda repo_root, tool, model: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)

    ensure_called = {}

    def fake_ensure_worktree(metadata: PlanMetadata) -> Path:
        front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
        assert front_matter["git_sha"] == head_sha
        assert front_matter["status"] == "coding"
        ensure_called["value"] = True
        worktree_path = git_repo.path / "worktree"
        worktree_path.mkdir(exist_ok=True)
        return worktree_path

    monkeypatch.setattr(code_command, "ensure_worktree", fake_ensure_worktree)

    settings_dir = tmp_path / "src"
    droids_template_dir = settings_dir / "droids"
    droids_template_dir.mkdir(parents=True)
    (settings_dir / "container_settings.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(lambda cls, tool: mock_executor_factory()))
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    exit_code = run_code_command(plan_path)

    assert exit_code == 0
    assert ensure_called.get("value") is True

    final_front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert final_front_matter["git_sha"] == head_sha
    assert final_front_matter["status"] == "done"


def test_code_command_status_done_on_success(monkeypatch, git_repo, tmp_path: Path) -> None:
    plan_id = "plan-success"
    plan_path = git_repo.path / f"{plan_id}.md"
    head_sha = git_repo.latest_commit()
    write_plan(
        plan_path,
        {
            "git_sha": head_sha,
            "plan_id": plan_id,
            "status": "coding",
        },
    )

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_010000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    main_prompt = prompts_dir / "main.md"
    main_prompt.write_text("prompt", encoding="utf-8")

    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)
    review_prompt = droids_dir / "code-review-auditor.md"
    alignment_prompt = droids_dir / "plan-alignment-checker.md"
    review_prompt.write_text("review", encoding="utf-8")
    alignment_prompt.write_text("alignment", encoding="utf-8")
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    monkeypatch.setattr(code_command, "create_run_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda _run_dir: droids_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda repo_root, tool, model: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda *_args, **_kwargs: None)

    def fake_ensure_worktree(metadata: PlanMetadata) -> Path:
        front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
        assert front_matter["git_sha"] == head_sha
        assert front_matter["status"] == "coding"
        worktree_path = git_repo.path / "worktree-success"
        worktree_path.mkdir(exist_ok=True)
        return worktree_path

    monkeypatch.setattr(code_command, "ensure_worktree", fake_ensure_worktree)

    settings_dir = tmp_path / "src-success"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "container_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(lambda cls, tool: mock_executor_factory()))
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    exit_code = run_code_command(plan_path)
    assert exit_code == 0

    front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == head_sha
    assert front_matter["status"] == "done"


def test_code_command_status_stays_coding_on_failure(
    monkeypatch, git_repo, tmp_path: Path
) -> None:
    plan_id = "plan-failure"
    plan_path = git_repo.path / f"{plan_id}.md"
    head_sha = git_repo.latest_commit()
    write_plan(
        plan_path,
        {
            "git_sha": head_sha,
            "plan_id": plan_id,
            "status": "coding",
        },
    )

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_020000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    main_prompt = prompts_dir / "main.md"
    main_prompt.write_text("prompt", encoding="utf-8")
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)
    review_prompt = droids_dir / "code-review-auditor.md"
    alignment_prompt = droids_dir / "plan-alignment-checker.md"
    review_prompt.write_text("review", encoding="utf-8")
    alignment_prompt.write_text("alignment", encoding="utf-8")
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    monkeypatch.setattr(code_command, "create_run_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda _: droids_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: git_repo.path / "worktree-failure",
    )

    settings_dir = tmp_path / "src-failure"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "container_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(lambda cls, tool: mock_executor_factory()))
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=1)),
    )

    # Create the worktree directory for the test
    worktree_path = git_repo.path / "worktree-failure"
    worktree_path.mkdir(parents=True, exist_ok=True)

    exit_code = run_code_command(plan_path)
    assert exit_code == 1

    front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == head_sha
    assert front_matter["status"] == "coding"


def test_code_command_error_when_sha_mismatch(monkeypatch, git_repo, caplog) -> None:
    initial_sha = git_repo.latest_commit()
    extra_file = git_repo.path / "extra.txt"
    extra_file.write_text("extra", encoding="utf-8")
    git_repo.run("add", "extra.txt")
    git_repo.run("commit", "-m", "extra commit")
    head_sha = git_repo.latest_commit()
    assert head_sha != initial_sha

    plan_path = git_repo.path / "plan-mismatch.md"
    write_plan(
        plan_path,
        {
            "git_sha": initial_sha,
            "plan_id": "plan-mismatch",
            "status": "coding",
        },
    )

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "does not match repository HEAD" in caplog.text
    assert "uncommitted changes" in caplog.text or "rebasing" in caplog.text

    front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == initial_sha
    assert front_matter["status"] == "coding"


def test_code_command_error_on_initial_update_failure(monkeypatch, git_repo, caplog) -> None:
    plan_path = git_repo.path / "plan-initial-failure.md"
    write_plan(
        plan_path,
        {
            "git_sha": PLACEHOLDER_SHA,
            "plan_id": "plan-initial-failure",
            "status": "draft",
        },
    )

    def failing_update(*_args, **_kwargs):
        raise code_command.PlanLifecycleError("cannot write plan")

    monkeypatch.setattr(code_command, "update_plan_fields", failing_update)

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "Failed to update plan metadata before coding session" in caplog.text

    front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == PLACEHOLDER_SHA
    assert front_matter["status"] == "draft"


def test_code_command_warning_on_final_update_failure(
    monkeypatch, git_repo, tmp_path: Path, caplog
) -> None:
    plan_id = "plan-final-failure"
    plan_path = git_repo.path / f"{plan_id}.md"
    head_sha = git_repo.latest_commit()
    write_plan(
        plan_path,
        {
            "git_sha": head_sha,
            "plan_id": plan_id,
            "status": "coding",
        },
    )

    original_update = code_command.update_plan_fields

    def conditional_update(path, updates):
        if updates.get("status") == "done":
            raise code_command.PlanLifecycleError("final write failed")
        return original_update(path, updates)

    monkeypatch.setattr(code_command, "update_plan_fields", conditional_update)

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_030000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    main_prompt = prompts_dir / "main.md"
    main_prompt.write_text("prompt", encoding="utf-8")

    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)
    review_prompt = droids_dir / "code-review-auditor.md"
    alignment_prompt = droids_dir / "plan-alignment-checker.md"
    review_prompt.write_text("review", encoding="utf-8")
    alignment_prompt.write_text("alignment", encoding="utf-8")
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    monkeypatch.setattr(code_command, "create_run_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda _run_dir: droids_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: git_repo.path / "worktree-final",
    )

    settings_dir = tmp_path / "src-final"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "container_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(lambda cls, tool: mock_executor_factory()))
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    # Create the worktree directory for the test
    worktree_path = git_repo.path / "worktree-final"
    worktree_path.mkdir(parents=True, exist_ok=True)

    caplog.set_level(logging.WARNING)
    exit_code = run_code_command(plan_path)

    assert exit_code == 0
    assert "Failed to update plan status to 'done'" in caplog.text

    front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["status"] == "coding"


def test_code_command_interrupted_by_user(monkeypatch, git_repo, tmp_path: Path) -> None:
    plan_id = "plan-interrupt"
    plan_path = git_repo.path / f"{plan_id}.md"
    head_sha = git_repo.latest_commit()
    write_plan(
        plan_path,
        {
            "git_sha": head_sha,
            "plan_id": plan_id,
            "status": "coding",
        },
    )

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_040000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    main_prompt = prompts_dir / "main.md"
    main_prompt.write_text("prompt", encoding="utf-8")
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)
    review_prompt = droids_dir / "code-review-auditor.md"
    alignment_prompt = droids_dir / "plan-alignment-checker.md"
    review_prompt.write_text("review", encoding="utf-8")
    alignment_prompt.write_text("alignment", encoding="utf-8")
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    monkeypatch.setattr(code_command, "create_run_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda _run_dir: droids_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: git_repo.path / "worktree-interrupt",
    )

    settings_dir = tmp_path / "src-interrupt"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "container_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(lambda cls, tool: mock_executor_factory()))
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))

    def interrupting_run(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(code_command, "subprocess", SimpleNamespace(run=interrupting_run))

    # Create the worktree directory for the test
    worktree_path = git_repo.path / "worktree-interrupt"
    worktree_path.mkdir(parents=True, exist_ok=True)

    exit_code = run_code_command(plan_path)
    assert exit_code == 130

    front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["status"] == "coding"


def test_code_command_validation_failure_no_update(tmp_path: Path, git_repo) -> None:
    plan_path = git_repo.path / "invalid-plan.md"
    plan_path.write_text(
        "---\ninvalid: [\n",  # malformed YAML
        encoding="utf-8",
    )

    original_content = plan_path.read_text(encoding="utf-8")
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert plan_path.read_text(encoding="utf-8") == original_content


def test_code_command_validation_failure_rolls_back_initial_update(
    git_repo,
) -> None:
    plan_path = git_repo.path / "invalid-body-plan.md"
    write_plan(
        plan_path,
        {
            "git_sha": PLACEHOLDER_SHA,
            "plan_id": "plan-invalid-body",
            "status": "draft",
        },
        body="\n\t\n",
    )

    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == PLACEHOLDER_SHA
    assert front_matter["status"] == "draft"


def test_code_command_worktree_uses_updated_sha(monkeypatch, git_repo, tmp_path: Path) -> None:
    plan_id = "plan-worktree"
    plan_path = git_repo.path / f"{plan_id}.md"
    write_plan(
        plan_path,
        {
            "git_sha": PLACEHOLDER_SHA,
            "plan_id": plan_id,
            "status": "draft",
        },
    )

    head_sha = git_repo.latest_commit()
    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_050000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    main_prompt = prompts_dir / "main.md"
    main_prompt.write_text("prompt", encoding="utf-8")
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)
    review_prompt = droids_dir / "code-review-auditor.md"
    alignment_prompt = droids_dir / "plan-alignment-checker.md"
    review_prompt.write_text("review", encoding="utf-8")
    alignment_prompt.write_text("alignment", encoding="utf-8")
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    monkeypatch.setattr(code_command, "create_run_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda _run_dir: droids_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda *_args, **_kwargs: None)

    captured_metadata = {}

    def fake_ensure_worktree(metadata: PlanMetadata) -> Path:
        captured_metadata["git_sha"] = metadata.git_sha
        worktree_path = git_repo.path / "worktree-updated"
        worktree_path.mkdir(parents=True, exist_ok=True)
        return worktree_path

    monkeypatch.setattr(code_command, "ensure_worktree", fake_ensure_worktree)

    settings_dir = tmp_path / "src-worktree"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "container_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(lambda cls, tool: mock_executor_factory()))
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    exit_code = run_code_command(plan_path)

    assert exit_code == 0
    assert captured_metadata["git_sha"] == head_sha


def test_code_command_real_sha_matches_head_no_error(
    monkeypatch, git_repo, tmp_path: Path
) -> None:
    plan_id = "plan-match"
    plan_path = git_repo.path / f"{plan_id}.md"
    head_sha = git_repo.latest_commit()
    write_plan(
        plan_path,
        {
            "git_sha": head_sha,
            "plan_id": plan_id,
            "status": "draft",
        },
    )

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_060000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    main_prompt = prompts_dir / "main.md"
    main_prompt.write_text("prompt", encoding="utf-8")
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)
    review_prompt = droids_dir / "code-review-auditor.md"
    alignment_prompt = droids_dir / "plan-alignment-checker.md"
    review_prompt.write_text("review", encoding="utf-8")
    alignment_prompt.write_text("alignment", encoding="utf-8")
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    monkeypatch.setattr(code_command, "create_run_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda _run_dir: droids_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: git_repo.path / "worktree-match",
    )

    settings_dir = tmp_path / "src-match"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "container_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(lambda cls, tool: mock_executor_factory()))
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    # Create the worktree directory for the test
    worktree_path = git_repo.path / "worktree-match"
    worktree_path.mkdir(parents=True, exist_ok=True)

    exit_code = run_code_command(plan_path)
    assert exit_code == 0

    front_matter, _ = _extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == head_sha
    assert front_matter["status"] == "done"

def test_code_command_plan_md_cleanup(monkeypatch, git_repo, tmp_path: Path) -> None:
    plan_id = "plan-cleanup"
    plan_path = git_repo.path / f"{plan_id}.md"
    head_sha = git_repo.latest_commit()
    write_plan(
        plan_path,
        {
            "git_sha": head_sha,
            "plan_id": plan_id,
            "status": "coding",
        },
    )

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_070000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    main_prompt = prompts_dir / "main.md"
    main_prompt.write_text("prompt", encoding="utf-8")
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)
    review_prompt = droids_dir / "code-review-auditor.md"
    alignment_prompt = droids_dir / "plan-alignment-checker.md"
    review_prompt.write_text("review", encoding="utf-8")
    alignment_prompt.write_text("alignment", encoding="utf-8")
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    monkeypatch.setattr(code_command, "create_run_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda _: droids_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda *_args, **_kwargs: None)

    worktree_path = git_repo.path / "worktree-cleanup"
    worktree_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: worktree_path,
    )

    settings_dir = tmp_path / "src-cleanup"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "container_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(lambda cls, tool: mock_executor_factory()))
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    # Verify plan.md doesn't exist before execution
    plan_md_path = worktree_path / "plan.md"
    assert not plan_md_path.exists()

    exit_code = run_code_command(plan_path)
    assert exit_code == 0

    # Verify plan.md was cleaned up after execution
    assert not plan_md_path.exists()


def test_code_command_agents_cleanup(monkeypatch, git_repo, tmp_path: Path) -> None:
    plan_id = "plan-agents-cleanup"
    plan_path = git_repo.path / f"{plan_id}.md"
    head_sha = git_repo.latest_commit()
    write_plan(
        plan_path,
        {
            "git_sha": head_sha,
            "plan_id": plan_id,
            "status": "coding",
        },
    )

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_080000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    main_prompt = prompts_dir / "main.md"
    main_prompt.write_text("prompt", encoding="utf-8")
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)
    review_prompt = droids_dir / "code-review-auditor.md"
    alignment_prompt = droids_dir / "plan-alignment-checker.md"
    review_prompt.write_text("review", encoding="utf-8")
    alignment_prompt.write_text("alignment", encoding="utf-8")
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    monkeypatch.setattr(code_command, "create_run_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "copy_coding_droids", lambda _: droids_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_runs", lambda *_args, **_kwargs: None)

    worktree_path = git_repo.path / "worktree-agents-cleanup"
    worktree_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: worktree_path,
    )

    settings_dir = tmp_path / "src-agents-cleanup"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "container_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(lambda cls, tool: mock_executor_factory()))
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    # Verify .claude/agents directory doesn't exist before execution
    agents_dir = worktree_path / ".claude" / "agents"
    assert not agents_dir.exists()

    exit_code = run_code_command(plan_path)
    assert exit_code == 0

    # Verify .claude/agents directory was cleaned up after execution
    assert not agents_dir.exists()
    # Also verify .claude directory is gone since we created it
    assert not (worktree_path / ".claude").exists()
