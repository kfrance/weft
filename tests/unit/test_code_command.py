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
from lw_coder.plan_validator import PLACEHOLDER_SHA, PlanMetadata, PlanValidationError, extract_front_matter
from lw_coder.worktree_utils import WorktreeError

try:
    from tests.conftest import write_plan, GitRepo
except ImportError:
    # Fallback if conftest is not available
    import yaml

    def write_plan(path, data, body="# Plan Body"):
        """Write a test plan file with YAML front matter.

        Args:
            path: Path where the plan file will be written.
            data: Dictionary containing the YAML front matter data.
            body: Markdown body content for the plan. Defaults to "# Plan Body".
        """
        yaml_block = yaml.safe_dump(data, sort_keys=False).strip()
        content = f"---\n{yaml_block}\n---\n\n{body}\n"
        path.write_text(content, encoding="utf-8")

    class GitRepo:
        """Simple GitRepo mock."""
        pass


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
    monkeypatch.setattr(code_command, "create_session_directory", lambda repo_root, plan_id, session_type: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda repo_root, tool, model: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda repo_root, active_session_dir: 0)
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


def test_code_command_replaces_placeholder_git_sha(monkeypatch, git_repo, tmp_path: Path, mock_executor_factory) -> None:
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

    def fake_create_session_directory(repo_root: Path, received_plan_id: str, session_type: str) -> Path:
        assert repo_root == git_repo.path
        assert received_plan_id == plan_id
        assert session_type == "code"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    monkeypatch.setattr(code_command, "create_session_directory", fake_create_session_directory)
    monkeypatch.setattr(code_command, "load_prompts", lambda repo_root, tool, model: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)

    ensure_called = {}

    def fake_ensure_worktree(metadata: PlanMetadata) -> Path:
        front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
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
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")

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

    final_front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert final_front_matter["git_sha"] == head_sha
    assert final_front_matter["status"] == "implemented"


def test_code_command_status_implemented_on_success(monkeypatch, git_repo, tmp_path: Path, mock_executor_factory) -> None:
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

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda repo_root, tool, model: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)

    def fake_ensure_worktree(metadata: PlanMetadata) -> Path:
        front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
        assert front_matter["git_sha"] == head_sha
        assert front_matter["status"] == "coding"
        worktree_path = git_repo.path / "worktree-success"
        worktree_path.mkdir(exist_ok=True)
        return worktree_path

    monkeypatch.setattr(code_command, "ensure_worktree", fake_ensure_worktree)

    settings_dir = tmp_path / "src-success"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")
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

    front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == head_sha
    assert front_matter["status"] == "implemented"


def test_code_command_status_stays_coding_on_failure(
    monkeypatch, git_repo, tmp_path: Path, mock_executor_factory
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

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: git_repo.path / "worktree-failure",
    )

    settings_dir = tmp_path / "src-failure"
    (settings_dir / "droids").mkdir(parents=True)
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

    front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
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

    front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
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

    front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == PLACEHOLDER_SHA
    assert front_matter["status"] == "draft"


def test_code_command_warning_on_final_update_failure(
    monkeypatch, git_repo, tmp_path: Path, caplog
, mock_executor_factory) -> None:
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
        if updates.get("status") == "implemented":
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

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: git_repo.path / "worktree-final",
    )

    settings_dir = tmp_path / "src-final"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")
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
    assert "Failed to update plan status to 'implemented'" in caplog.text

    front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["status"] == "coding"


def test_code_command_interrupted_by_user(monkeypatch, git_repo, tmp_path: Path, mock_executor_factory) -> None:
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

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: git_repo.path / "worktree-interrupt",
    )

    settings_dir = tmp_path / "src-interrupt"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")
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

    front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["status"] == "coding"


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
    front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == PLACEHOLDER_SHA
    assert front_matter["status"] == "draft"


def test_code_command_worktree_uses_updated_sha(monkeypatch, git_repo, tmp_path: Path, mock_executor_factory) -> None:
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

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)

    captured_metadata = {}

    def fake_ensure_worktree(metadata: PlanMetadata) -> Path:
        captured_metadata["git_sha"] = metadata.git_sha
        worktree_path = git_repo.path / "worktree-updated"
        worktree_path.mkdir(parents=True, exist_ok=True)
        return worktree_path

    monkeypatch.setattr(code_command, "ensure_worktree", fake_ensure_worktree)

    settings_dir = tmp_path / "src-worktree"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")
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
, mock_executor_factory) -> None:
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

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: git_repo.path / "worktree-match",
    )

    settings_dir = tmp_path / "src-match"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")
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

    front_matter, _ = extract_front_matter(plan_path.read_text(encoding="utf-8"))
    assert front_matter["git_sha"] == head_sha
    assert front_matter["status"] == "implemented"


def test_code_command_agents_cleanup(monkeypatch, git_repo, tmp_path: Path, mock_executor_factory) -> None:
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

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda *_args, **_kwargs: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)

    worktree_path = git_repo.path / "worktree-agents-cleanup"
    worktree_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        code_command,
        "ensure_worktree",
        lambda _metadata: worktree_path,
    )

    settings_dir = tmp_path / "src-agents-cleanup"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")
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


def test_code_command_with_droid_tool(monkeypatch, git_repo, tmp_path: Path) -> None:
    """Test code command with --tool droid."""
    plan_id = "plan-droid"
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

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_090000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)

    worktree_path = git_repo.path / "worktree-droid"
    worktree_path.mkdir(parents=True, exist_ok=True)

    captured_command = {}
    captured_tool = {}

    def fake_build_command(prompt_path, model):
        captured_command["path"] = str(prompt_path)
        captured_command["model"] = model
        return f'droid "$(cat {prompt_path})"'

    def fake_get_executor(cls, tool):
        captured_tool["value"] = tool
        return SimpleNamespace(
            check_auth=lambda: None,
            build_command=fake_build_command,
            get_env_vars=lambda factory_dir: None
        )

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "ensure_worktree", lambda _metadata: worktree_path)

    settings_dir = tmp_path / "src-droid"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "prompts" / "droid").mkdir(parents=True)
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(fake_get_executor))
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    # Run with droid tool
    exit_code = run_code_command(plan_path, tool="droid")
    assert exit_code == 0
    assert captured_tool["value"] == "droid"
    assert "droid_prompt.md" in captured_command["path"]
    # Model is None for droid
    assert captured_command["model"] is None


def test_code_command_with_claude_code_tool_explicit_model(monkeypatch, git_repo, tmp_path: Path) -> None:
    """Test code command with --tool claude-code and explicit model.

    With SDK integration, claude-code now runs SDK session first, then resumes with CLI.
    This test verifies the SDK is called with the correct model.
    """
    plan_id = "plan-claude-opus"
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

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_100000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)

    worktree_path = git_repo.path / "worktree-claude-opus"
    worktree_path.mkdir(parents=True, exist_ok=True)

    captured_sdk_call = {}
    captured_tool = {}
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    def fake_sdk_runner(**kwargs):
        captured_sdk_call["model"] = kwargs.get("model")
        captured_sdk_call["prompt_content"] = kwargs.get("prompt_content")
        return "mock-session-opus"

    def fake_get_executor(cls, tool):
        captured_tool["value"] = tool
        return SimpleNamespace(
            check_auth=lambda: None,
            build_command=lambda p, model: f'claude --model {model} "$(cat {p})"',
            get_env_vars=lambda factory_dir: None
        )

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda repo_root, tool, model: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "ensure_worktree", lambda _metadata: worktree_path)
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "run_sdk_session_sync", fake_sdk_runner)

    settings_dir = tmp_path / "src-claude-opus"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(fake_get_executor))
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    # Run with claude-code tool and opus model
    exit_code = run_code_command(plan_path, tool="claude-code", model="opus")
    assert exit_code == 0
    assert captured_tool["value"] == "claude-code"
    # SDK should be called with the opus model
    assert captured_sdk_call["model"] == "opus"
    assert captured_sdk_call["prompt_content"] == "Main prompt content"


def test_code_command_default_tool_and_model(monkeypatch, git_repo, tmp_path: Path) -> None:
    """Test code command with defaults uses claude-code with sonnet.

    With SDK integration, this verifies SDK is called with default sonnet model.
    """
    plan_id = "plan-defaults"
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

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_120000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)

    worktree_path = git_repo.path / "worktree-defaults"
    worktree_path.mkdir(parents=True, exist_ok=True)

    captured_tool = {}
    captured_sdk_call = {}
    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    def fake_sdk_runner(**kwargs):
        captured_sdk_call["model"] = kwargs.get("model")
        return "mock-session-defaults"

    def fake_get_executor(cls, tool):
        captured_tool["value"] = tool
        return SimpleNamespace(
            check_auth=lambda: None,
            build_command=lambda p, model: f'claude --model {model} "$(cat {p})"',
            get_env_vars=lambda factory_dir: None
        )

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda repo_root, tool, model: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "ensure_worktree", lambda _metadata: worktree_path)
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "run_sdk_session_sync", fake_sdk_runner)

    settings_dir = tmp_path / "src-defaults"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(code_command, "host_runner_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(fake_get_executor))
    monkeypatch.setattr(code_command, "build_host_command", lambda _config: (["cmd"], {}))
    monkeypatch.setattr(
        code_command,
        "subprocess",
        SimpleNamespace(run=lambda *args, **kwargs: SimpleNamespace(returncode=0)),
    )

    # Run with defaults (should use claude-code with sonnet)
    exit_code = run_code_command(plan_path)
    assert exit_code == 0
    assert captured_tool["value"] == "claude-code"
    # SDK should be called with default sonnet model
    assert captured_sdk_call["model"] == "sonnet"


def test_code_command_sdk_session_failure(monkeypatch, git_repo, tmp_path: Path, caplog) -> None:
    """Test code command handles SDK session failure gracefully."""
    from lw_coder.sdk_runner import SDKRunnerError

    plan_id = "plan-sdk-fail"
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

    run_dir = git_repo.path / ".lw_coder" / "runs" / plan_id / "20250101_130000"
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)

    worktree_path = git_repo.path / "worktree-sdk-fail"
    worktree_path.mkdir(parents=True, exist_ok=True)

    mock_prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    def failing_sdk_runner(*args, **kwargs):
        raise SDKRunnerError("SDK connection failed")

    monkeypatch.setattr(code_command, "create_session_directory", lambda *_args, **_kwargs: run_dir)
    monkeypatch.setattr(code_command, "load_prompts", lambda repo_root, tool, model: mock_prompts)
    monkeypatch.setattr(code_command, "prune_old_sessions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "ensure_worktree", lambda _metadata: worktree_path)
    monkeypatch.setattr(code_command, "_write_sub_agents", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(code_command, "run_sdk_session_sync", failing_sdk_runner)

    settings_dir = tmp_path / "src-sdk-fail"
    (settings_dir / "droids").mkdir(parents=True)
    (settings_dir / "sdk_settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(code_command, "get_lw_coder_src_dir", lambda: settings_dir)
    monkeypatch.setattr(ExecutorRegistry, "get_executor", classmethod(
        lambda cls, tool: SimpleNamespace(
            check_auth=lambda: None,
            build_command=lambda p, model: f'claude "$(cat {p})"',
            get_env_vars=lambda factory_dir: None
        )
    ))

    caplog.set_level(logging.ERROR)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "SDK session failed" in caplog.text
    assert "SDK connection failed" in caplog.text
