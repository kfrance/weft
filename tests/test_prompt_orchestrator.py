"""Tests for prompt_orchestrator module."""

from __future__ import annotations

import os
from pathlib import Path

import dspy
import pytest

from lw_coder.home_env import HomeEnvError
from lw_coder.dspy.prompt_orchestrator import (
    PromptArtifacts,
    _initialize_dspy_cache,
    _write_prompt_file,
    generate_code_prompts,
)
from lw_coder.plan_validator import PlanMetadata

from conftest import GitRepo, write_plan


@pytest.fixture(autouse=True)
def configure_dspy_for_tests():
    """Configure DSPy with OpenRouter for all tests in this module."""
    # Check if API key is available
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY not set - skipping tests that require LLM")

    # Configure DSPy with OpenRouter's grok-3-mini
    lm = dspy.LM("openrouter/x-ai/grok-3-mini", api_key=api_key)
    dspy.configure(lm=lm)

    yield

    # Reset DSPy configuration after tests
    dspy.configure(lm=None)


def test_initialize_dspy_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that DSPy cache directory is created correctly."""
    # Mock HOME to use tmp_path
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    cache_dir = _initialize_dspy_cache()

    expected_cache = home_dir / ".lw_coder" / "dspy_cache"
    assert cache_dir == expected_cache
    assert cache_dir.exists()
    assert cache_dir.is_dir()


def test_write_prompt_file(tmp_path: Path) -> None:
    """Test that prompt files are written correctly with proper formatting."""
    prompt_path = tmp_path / "prompts" / "test.md"
    content = "  This is a test prompt\n\n  "

    _write_prompt_file(prompt_path, content)

    assert prompt_path.exists()
    written_content = prompt_path.read_text(encoding="utf-8")

    # Should be trimmed and end with newline
    assert written_content == "This is a test prompt\n"


def test_write_prompt_file_creates_parent_dirs(tmp_path: Path) -> None:
    """Test that parent directories are created if they don't exist."""
    prompt_path = tmp_path / "deep" / "nested" / "path" / "prompt.md"
    content = "Test content"

    _write_prompt_file(prompt_path, content)

    assert prompt_path.exists()
    assert prompt_path.parent.exists()


def test_generate_code_prompts_success(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test successful prompt generation using real DSPy with OpenRouter."""
    # Setup: Mock home directory with .env
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    lw_coder_dir = home_dir / ".lw_coder"
    lw_coder_dir.mkdir()
    env_file = lw_coder_dir / ".env"
    env_file.write_text("OPENROUTER_API_KEY=test\n")

    # Mock Path.home() to return our test home directory
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    # Create a plan file
    tasks_dir = git_repo.path / "tasks"
    tasks_dir.mkdir()
    plan_file = tasks_dir / "test-plan.md"
    git_sha = git_repo.latest_commit()

    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "git_sha": git_sha,
            "evaluation_notes": ["Test note 1", "Test note 2"],
            "status": "ready",
        },
        "# Implementation Plan\n\nBuild a feature.",
    )

    # Create PlanMetadata
    plan_metadata = PlanMetadata(
        plan_text="# Implementation Plan\n\nBuild a feature.",
        git_sha=git_sha,
        evaluation_notes=["Test note 1", "Test note 2"],
        plan_path=plan_file,
        repo_root=git_repo.path,
        plan_id="test-plan",
        status="ready",
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # Execute with real DSPy (configured by fixture)
    artifacts = generate_code_prompts(plan_metadata, run_dir)

    # Assert
    assert isinstance(artifacts, PromptArtifacts)
    assert artifacts.main_prompt_path == run_dir / "prompts" / "main.md"
    assert artifacts.review_prompt_path == run_dir / "droids" / "code-review-auditor.md"
    assert artifacts.alignment_prompt_path == run_dir / "droids" / "plan-alignment-checker.md"

    # Check files were written
    assert artifacts.main_prompt_path.exists()
    assert artifacts.review_prompt_path.exists()
    assert artifacts.alignment_prompt_path.exists()

    # Check content contains expected prompts (non-empty and reasonable length)
    main_content = artifacts.main_prompt_path.read_text()
    review_content = artifacts.review_prompt_path.read_text()
    alignment_content = artifacts.alignment_prompt_path.read_text()

    assert len(main_content) > 50, "Main prompt should be substantial"
    assert len(review_content) > 50, "Review prompt should be substantial"
    assert len(alignment_content) > 50, "Alignment prompt should be substantial"


def test_generate_code_prompts_missing_config(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that missing home .env raises HomeEnvError."""
    # Mock home directory without .env
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    plan_file = git_repo.path / "plan.md"
    git_sha = git_repo.latest_commit()

    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "git_sha": git_sha,
            "evaluation_notes": ["Note"],
            "status": "ready",
        },
    )

    plan_metadata = PlanMetadata(
        plan_text="# Plan",
        git_sha=git_sha,
        evaluation_notes=["Note"],
        plan_path=plan_file,
        repo_root=git_repo.path,
        plan_id="test-plan",
        status="ready",
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # Should raise because ~/.lw_coder/.env doesn't exist
    with pytest.raises(HomeEnvError, match="Environment file not found"):
        generate_code_prompts(plan_metadata, run_dir)


def test_generate_code_prompts_loads_env_variables(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that environment variables are loaded from ~/.lw_coder/.env."""
    # Setup: Mock home directory with .env
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    lw_coder_dir = home_dir / ".lw_coder"
    lw_coder_dir.mkdir()
    env_file = lw_coder_dir / ".env"
    env_file.write_text("TEST_ENV_VAR=test_value\n")

    # Mock Path.home() to return our test home directory
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    plan_file = git_repo.path / "plan.md"
    git_sha = git_repo.latest_commit()

    write_plan(
        plan_file,
        {
            "plan_id": "test-plan",
            "git_sha": git_sha,
            "evaluation_notes": ["Note"],
            "status": "ready",
        },
    )

    plan_metadata = PlanMetadata(
        plan_text="# Plan",
        git_sha=git_sha,
        evaluation_notes=["Note"],
        plan_path=plan_file,
        repo_root=git_repo.path,
        plan_id="test-plan",
        status="ready",
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    # Clear the env var first
    monkeypatch.delenv("TEST_ENV_VAR", raising=False)

    # Execute with real DSPy
    generate_code_prompts(plan_metadata, run_dir)

    # Check that env var was loaded
    assert os.getenv("TEST_ENV_VAR") == "test_value"


def test_generate_code_prompts_with_multiple_plans(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that DSPy caching works across multiple prompt generations."""
    # Setup: Mock home directory with .env
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    lw_coder_dir = home_dir / ".lw_coder"
    lw_coder_dir.mkdir()
    env_file = lw_coder_dir / ".env"
    env_file.write_text("TEST=1\n")

    # Mock Path.home() to return our test home directory
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    tasks_dir = git_repo.path / "tasks"
    tasks_dir.mkdir()
    git_sha = git_repo.latest_commit()

    # Generate prompts for first plan
    plan_file_1 = tasks_dir / "plan1.md"
    write_plan(
        plan_file_1,
        {
            "plan_id": "plan-1",
            "git_sha": git_sha,
            "evaluation_notes": ["Note 1"],
            "status": "ready",
        },
        "# Plan 1",
    )

    plan_metadata_1 = PlanMetadata(
        plan_text="# Plan 1",
        git_sha=git_sha,
        evaluation_notes=["Note 1"],
        plan_path=plan_file_1,
        repo_root=git_repo.path,
        plan_id="plan-1",
        status="ready",
    )

    run_dir_1 = tmp_path / "run1"
    run_dir_1.mkdir()

    artifacts_1 = generate_code_prompts(plan_metadata_1, run_dir_1)
    assert artifacts_1.main_prompt_path.exists()

    # Generate prompts for second plan
    plan_file_2 = tasks_dir / "plan2.md"
    write_plan(
        plan_file_2,
        {
            "plan_id": "plan-2",
            "git_sha": git_sha,
            "evaluation_notes": ["Note 2"],
            "status": "ready",
        },
        "# Plan 2",
    )

    plan_metadata_2 = PlanMetadata(
        plan_text="# Plan 2",
        git_sha=git_sha,
        evaluation_notes=["Note 2"],
        plan_path=plan_file_2,
        repo_root=git_repo.path,
        plan_id="plan-2",
        status="ready",
    )

    run_dir_2 = tmp_path / "run2"
    run_dir_2.mkdir()

    artifacts_2 = generate_code_prompts(plan_metadata_2, run_dir_2)
    assert artifacts_2.main_prompt_path.exists()

    # Both should have succeeded
    assert artifacts_1.main_prompt_path != artifacts_2.main_prompt_path
