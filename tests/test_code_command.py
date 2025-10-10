"""Tests for code_command module."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lw_coder.code_command import _check_docker_image, _filter_env_vars, run_code_command
from lw_coder.plan_validator import PlanMetadata, PlanValidationError
from lw_coder.worktree_utils import WorktreeError

from tests.conftest import write_plan


def test_run_code_command_success(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test successful execution of run_code_command (legacy test, now redirects to full workflow)."""
    # This test is kept for backwards compatibility but now tests the full workflow
    # For the old simple behavior, see test_run_code_command_with_mocked_workflow
    pass


def test_run_code_command_validation_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with plan validation failure."""
    # Setup
    plan_path = tmp_path / "plan.md"

    # Mock load_plan_metadata to raise PlanValidationError
    def mock_load_plan_metadata(path):
        raise PlanValidationError("Invalid git_sha")

    # Apply monkeypatch
    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", mock_load_plan_metadata
    )

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

    from lw_coder.dspy.prompt_orchestrator import PromptArtifacts
    mock_artifacts = PromptArtifacts(
        main_prompt_path=run_dir / "prompts" / "main.md",
        review_prompt_path=run_dir / "droids" / "code-review-auditor.md",
        alignment_prompt_path=run_dir / "droids" / "plan-alignment-checker.md",
    )

    def mock_ensure_worktree(metadata):
        raise WorktreeError("Failed to create worktree")

    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", lambda path: mock_metadata
    )
    monkeypatch.setattr(
        lw_coder.code_command, "create_run_directory", lambda repo_root, plan_id: run_dir
    )
    monkeypatch.setattr(
        lw_coder.code_command, "copy_coding_droids", lambda run_dir: run_dir / "droids"
    )
    monkeypatch.setattr(
        lw_coder.code_command, "generate_code_prompts", lambda metadata, run_dir: mock_artifacts
    )
    monkeypatch.setattr(
        lw_coder.code_command, "prune_old_runs", lambda repo_root, active_run_dir: 0
    )
    monkeypatch.setattr(
        lw_coder.code_command, "ensure_worktree", mock_ensure_worktree
    )

    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path)

    assert exit_code == 1
    assert "Plan validation succeeded" in caplog.text
    assert "Worktree preparation failed" in caplog.text
    assert "Failed to create worktree" in caplog.text


def test_run_code_command_with_string_path(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command accepts string paths."""
    plan_path = tmp_path / "plan.md"
    plan_path_str = str(plan_path)
    run_dir = tmp_path / ".lw_coder" / "runs" / "test-plan-str" / "20250101_120000"
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    mock_metadata = PlanMetadata(
        plan_text="# Test Plan",
        git_sha="c" * 40,
        evaluation_notes=["Test note"],
        plan_path=plan_path,
        repo_root=tmp_path,
        plan_id="test-plan-str",
        status="draft",
    )

    from lw_coder.dspy.prompt_orchestrator import PromptArtifacts
    mock_artifacts = PromptArtifacts(
        main_prompt_path=run_dir / "prompts" / "main.md",
        review_prompt_path=run_dir / "droids" / "code-review-auditor.md",
        alignment_prompt_path=run_dir / "droids" / "plan-alignment-checker.md",
    )

    def mock_load_plan_metadata(path):
        # Verify it receives a Path object
        assert isinstance(path, Path)
        return mock_metadata

    # Mock subprocess.run for Docker execution
    mock_result = MagicMock()
    mock_result.returncode = 0

    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", mock_load_plan_metadata
    )
    monkeypatch.setattr(
        lw_coder.code_command, "create_run_directory", lambda repo_root, plan_id: run_dir
    )
    monkeypatch.setattr(
        lw_coder.code_command, "copy_coding_droids", lambda run_dir: run_dir / "droids"
    )
    monkeypatch.setattr(
        lw_coder.code_command, "generate_code_prompts", lambda metadata, run_dir: mock_artifacts
    )
    monkeypatch.setattr(
        lw_coder.code_command, "prune_old_runs", lambda repo_root, active_run_dir: 0
    )
    monkeypatch.setattr(
        lw_coder.code_command, "ensure_worktree", lambda metadata: worktree_path
    )
    monkeypatch.setattr(
        lw_coder.code_command, "_check_docker_image", lambda image_tag: True
    )
    monkeypatch.setattr(
        lw_coder.code_command, "_build_repo_image", lambda repo_root, build_args: "test:tag"
    )
    monkeypatch.setattr(
        lw_coder.code_command, "_filter_env_vars", lambda patterns: {}
    )
    monkeypatch.setattr(
        "subprocess.run", lambda *args, **kwargs: mock_result
    )

    # Mock patched_worktree_gitdir context manager
    from contextlib import contextmanager

    @contextmanager
    def mock_patched_git(worktree, repo_git_dir):
        yield "mock-worktree-name"

    monkeypatch.setattr(
        lw_coder.code_command, "patched_worktree_gitdir", mock_patched_git
    )

    # Mock build_docker_command
    monkeypatch.setattr(
        lw_coder.code_command, "build_docker_command", lambda config: ["docker", "run", "test"]
    )

    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path_str)

    assert exit_code == 0
    assert "Plan validation succeeded" in caplog.text


def test_run_code_command_integration_with_real_functions(git_repo, caplog, tmp_path: Path, monkeypatch) -> None:
    """Integration test: run_code_command with real functions but mocked DSPy.

    This test verifies most of the workflow with real implementations,
    but mocks DSPy to avoid requiring OpenRouter credentials.
    """
    # Setup: Create a valid plan file in the git repo
    tasks_dir = git_repo.path / ".lw_coder" / "tasks"
    tasks_dir.mkdir(parents=True)
    plan_path = tasks_dir / "integration-test.md"

    write_plan(
        plan_path,
        {
            "git_sha": git_repo.latest_commit(),
            "evaluation_notes": ["Integration test note"],
            "plan_id": "integration-test",
            "status": "draft",
        },
        body="# Integration Test Plan\n\nThis tests the full workflow."
    )

    # Create dummy auth file so Docker validation passes
    auth_file = tmp_path / ".factory" / "auth.json"
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    auth_file.write_text('{"test": true}')

    # Mock Path.home() to use our tmp_path
    original_home = Path.home
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Mock DSPy prompt generation and Docker check
    from lw_coder.dspy.prompt_orchestrator import PromptArtifacts

    def mock_generate_prompts(metadata, run_dir):
        # Create actual prompt files
        (run_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (run_dir / "droids").mkdir(parents=True, exist_ok=True)

        main_path = run_dir / "prompts" / "main.md"
        review_path = run_dir / "droids" / "code-review-auditor.md"
        alignment_path = run_dir / "droids" / "plan-alignment-checker.md"

        main_path.write_text("# Main Prompt\nTest content")
        review_path.write_text("# Review Prompt\nTest content")
        alignment_path.write_text("# Alignment Prompt\nTest content")

        return PromptArtifacts(
            main_prompt_path=main_path,
            review_prompt_path=review_path,
            alignment_prompt_path=alignment_path,
        )

    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "generate_code_prompts", mock_generate_prompts
    )
    monkeypatch.setattr(
        lw_coder.code_command, "_check_docker_image", lambda image_tag: True
    )

    # Mock subprocess.run to avoid actually running Docker, but allow git commands
    import subprocess
    original_run = subprocess.run
    from unittest.mock import MagicMock

    def selective_mock_run(cmd, *args, **kwargs):
        # If it's a docker command, mock it
        if isinstance(cmd, list) and len(cmd) > 0 and cmd[0] == "docker":
            mock_result = MagicMock()
            mock_result.returncode = 0
            return mock_result
        # Otherwise, use the real subprocess.run
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr("subprocess.run", selective_mock_run)

    # Execute
    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path)

    # Assert: Verify success
    assert exit_code == 0

    # Verify log messages
    assert "Plan validation succeeded for" in caplog.text
    assert str(plan_path) in caplog.text
    assert "Worktree prepared at" in caplog.text
    assert "Run artifacts available at" in caplog.text

    # Verify worktree was actually created
    expected_worktree = git_repo.path / ".lw_coder" / "worktrees" / "integration-test"
    assert expected_worktree.exists()
    assert expected_worktree.is_dir()

    # Verify worktree has .git file
    git_file = expected_worktree / ".git"
    assert git_file.exists()
    assert "gitdir:" in git_file.read_text()

    # Verify worktree is at correct commit
    import subprocess
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=expected_worktree,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == git_repo.latest_commit()

    # Verify worktree contains actual repository content
    readme_file = expected_worktree / "README.md"
    assert readme_file.exists()
    assert readme_file.read_text() == "seed\n"

    # Verify run directory was created
    run_dir = git_repo.path / ".lw_coder" / "runs" / "integration-test"
    assert run_dir.exists()

    # Verify prompts were generated
    assert (run_dir / list(run_dir.iterdir())[0] / "prompts" / "main.md").exists()


def test_check_docker_image_exists(monkeypatch) -> None:
    """Test _check_docker_image when image exists."""
    mock_result = MagicMock()
    mock_result.stdout = "abc123def456\n"

    def mock_run(*args, **kwargs):
        return mock_result

    monkeypatch.setattr("subprocess.run", mock_run)

    assert _check_docker_image("test:latest") is True


def test_check_docker_image_not_exists(monkeypatch) -> None:
    """Test _check_docker_image when image doesn't exist."""
    mock_result = MagicMock()
    mock_result.stdout = ""

    def mock_run(*args, **kwargs):
        return mock_result

    monkeypatch.setattr("subprocess.run", mock_run)

    assert _check_docker_image("test:latest") is False


def test_check_docker_image_docker_error(monkeypatch) -> None:
    """Test _check_docker_image when docker command fails."""
    import subprocess

    def mock_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "docker")

    monkeypatch.setattr("subprocess.run", mock_run)

    assert _check_docker_image("test:latest") is False


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


def test_run_code_command_with_mocked_workflow(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test run_code_command with complete mocked workflow."""
    plan_path = tmp_path / "plan.md"
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    run_dir = tmp_path / ".lw_coder" / "runs" / "test-plan" / "20250101_120000"

    mock_metadata = PlanMetadata(
        plan_text="# Test Plan",
        git_sha="a" * 40,
        evaluation_notes=["Test note"],
        plan_path=plan_path,
        repo_root=tmp_path,
        plan_id="test-plan",
        status="draft",
    )

    from lw_coder.dspy.prompt_orchestrator import PromptArtifacts

    mock_artifacts = PromptArtifacts(
        main_prompt_path=run_dir / "prompts" / "main.md",
        review_prompt_path=run_dir / "droids" / "code-review-auditor.md",
        alignment_prompt_path=run_dir / "droids" / "plan-alignment-checker.md",
    )

    # Mock subprocess.run for Docker execution
    mock_result = MagicMock()
    mock_result.returncode = 0

    # Mock all dependencies
    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", lambda path: mock_metadata
    )
    monkeypatch.setattr(
        lw_coder.code_command, "create_run_directory", lambda repo_root, plan_id: run_dir
    )
    monkeypatch.setattr(
        lw_coder.code_command, "copy_coding_droids", lambda run_dir: run_dir / "droids"
    )
    monkeypatch.setattr(
        lw_coder.code_command, "generate_code_prompts", lambda metadata, run_dir: mock_artifacts
    )
    monkeypatch.setattr(
        lw_coder.code_command, "prune_old_runs", lambda repo_root, active_run_dir: 0
    )
    monkeypatch.setattr(
        lw_coder.code_command, "ensure_worktree", lambda metadata: worktree_path
    )
    monkeypatch.setattr(
        lw_coder.code_command, "_check_docker_image", lambda image_tag: True
    )
    monkeypatch.setattr(
        lw_coder.code_command, "_build_repo_image", lambda repo_root, build_args: "test:tag"
    )
    monkeypatch.setattr(
        lw_coder.code_command, "_filter_env_vars", lambda patterns: {}
    )
    monkeypatch.setattr(
        "subprocess.run", lambda *args, **kwargs: mock_result
    )

    # Mock patched_worktree_gitdir context manager
    from contextlib import contextmanager

    @contextmanager
    def mock_patched_git(worktree, repo_git_dir):
        yield "mock-worktree-name"

    monkeypatch.setattr(
        lw_coder.code_command, "patched_worktree_gitdir", mock_patched_git
    )

    # Mock build_docker_command
    monkeypatch.setattr(
        lw_coder.code_command, "build_docker_command", lambda config: ["docker", "run", "test"]
    )

    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path)

    assert exit_code == 0
    assert "Plan validation succeeded" in caplog.text
    assert "Generating prompts using DSPy" in caplog.text
    assert "DSPy prompt generation completed" in caplog.text
    assert "Worktree prepared at" in caplog.text
    assert "Run artifacts available at" in caplog.text
    assert "Launching interactive droid session" in caplog.text


def test_build_base_image_timeout(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test _build_base_image when docker build times out."""
    import subprocess
    from lw_coder.code_command import _build_base_image

    # Create dockerfile to satisfy the exists check
    dockerfile_path = tmp_path / "docker" / "droid" / "Dockerfile"
    dockerfile_path.parent.mkdir(parents=True)
    dockerfile_path.write_text("FROM ubuntu:22.04\n")

    # Change to temp directory so dockerfile is found
    import os
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        def mock_run(*args, **kwargs):
            raise subprocess.TimeoutExpired("docker build", 600)

        monkeypatch.setattr("subprocess.run", mock_run)

        caplog.set_level(logging.INFO)
        with pytest.raises(RuntimeError, match="Docker build timed out after 10 minutes"):
            _build_base_image()

        assert "Building base Docker image" in caplog.text
    finally:
        os.chdir(original_cwd)


def test_build_base_image_missing_dockerfile(caplog, tmp_path: Path) -> None:
    """Test _build_base_image when Dockerfile doesn't exist."""
    import os
    from lw_coder.code_command import _build_base_image

    # Change to temp directory where Dockerfile doesn't exist
    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        with pytest.raises(RuntimeError, match="Base Dockerfile not found"):
            _build_base_image()
    finally:
        os.chdir(original_cwd)


def test_build_repo_image_build_failure(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test _build_repo_image when docker build fails with CalledProcessError."""
    import subprocess
    from lw_coder.code_command import _build_repo_image

    # Create repo Dockerfile
    dockerfile_path = tmp_path / ".lw_coder" / "code.Dockerfile"
    dockerfile_path.parent.mkdir(parents=True)
    dockerfile_path.write_text("FROM lw_coder_droid:latest\n")

    def mock_run(*args, **kwargs):
        error = subprocess.CalledProcessError(1, "docker build")
        error.stderr = "Build failed: invalid instruction"
        raise error

    monkeypatch.setattr("subprocess.run", mock_run)

    caplog.set_level(logging.INFO)
    with pytest.raises(RuntimeError, match="Docker build failed for repo image"):
        _build_repo_image(tmp_path, [])

    assert "Building repo-specific Docker image" in caplog.text
    assert "Failed to build repo image" in caplog.text


def test_build_repo_image_missing_dockerfile(tmp_path: Path) -> None:
    """Test _build_repo_image when repo Dockerfile doesn't exist."""
    from lw_coder.code_command import _build_repo_image

    with pytest.raises(RuntimeError, match="Repo Dockerfile not found"):
        _build_repo_image(tmp_path, [])


def test_build_repo_image_skips_existing(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test _build_repo_image skips build when image already exists."""
    from lw_coder.code_command import _build_repo_image

    # Create repo Dockerfile
    dockerfile_path = tmp_path / ".lw_coder" / "code.Dockerfile"
    dockerfile_path.parent.mkdir(parents=True)
    dockerfile_path.write_text("FROM lw_coder_droid:latest\n")

    # Mock docker images to return existing image
    monkeypatch.setattr(
        "lw_coder.code_command._check_docker_image", lambda tag: True
    )

    caplog.set_level(logging.INFO)
    result = _build_repo_image(tmp_path, [])

    # Should skip build and return tag
    assert result.startswith("lw_coder_droid:")
    assert "already exists, skipping build" in caplog.text


def test_docker_command_construction_with_real_build(monkeypatch, caplog, tmp_path: Path) -> None:
    """Test that Docker command is constructed correctly without mocking build_docker_command."""
    plan_path = tmp_path / "plan.md"
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    run_dir = tmp_path / ".lw_coder" / "runs" / "test-plan" / "20250101_120000"

    # Create droids directory that build_docker_command expects
    droids_dir = run_dir / "droids"
    droids_dir.mkdir(parents=True)

    # Create prompts directory and main prompt file
    prompts_dir = run_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    main_prompt_file = prompts_dir / "main.md"
    main_prompt_file.write_text("# Test Prompt")

    mock_metadata = PlanMetadata(
        plan_text="# Test Plan",
        git_sha="a" * 40,
        evaluation_notes=["Test note"],
        plan_path=plan_path,
        repo_root=tmp_path,
        plan_id="test-plan",
        status="draft",
    )

    from lw_coder.dspy.prompt_orchestrator import PromptArtifacts
    mock_artifacts = PromptArtifacts(
        main_prompt_path=main_prompt_file,
        review_prompt_path=run_dir / "droids" / "code-review-auditor.md",
        alignment_prompt_path=run_dir / "droids" / "plan-alignment-checker.md",
    )

    # Set environment variables that should be forwarded
    # Note: With sensible defaults in code_command, we forward OPENROUTER_* by default
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")
    monkeypatch.setenv("TEST_VAR", "test-value")
    monkeypatch.setenv("IGNORED_VAR", "ignored")

    # Capture subprocess.run calls
    docker_commands_executed = []

    def mock_run(cmd, **kwargs):
        docker_commands_executed.append(cmd)
        mock_result = MagicMock()
        mock_result.returncode = 0
        return mock_result

    # Mock all dependencies except build_docker_command
    import lw_coder.code_command
    monkeypatch.setattr(
        lw_coder.code_command, "load_plan_metadata", lambda path: mock_metadata
    )
    monkeypatch.setattr(
        lw_coder.code_command, "create_run_directory", lambda repo_root, plan_id: run_dir
    )
    monkeypatch.setattr(
        lw_coder.code_command, "copy_coding_droids", lambda run_dir: droids_dir
    )
    monkeypatch.setattr(
        lw_coder.code_command, "generate_code_prompts", lambda metadata, run_dir: mock_artifacts
    )
    monkeypatch.setattr(
        lw_coder.code_command, "prune_old_runs", lambda repo_root, active_run_dir: 0
    )
    monkeypatch.setattr(
        lw_coder.code_command, "ensure_worktree", lambda metadata: worktree_path
    )
    monkeypatch.setattr(
        lw_coder.code_command, "_check_docker_image", lambda image_tag: True
    )
    monkeypatch.setattr(
        lw_coder.code_command, "_build_repo_image", lambda repo_root, build_args: "lw_coder_droid:test123"
    )
    monkeypatch.setattr("subprocess.run", mock_run)

    # Mock patched_worktree_gitdir context manager
    from contextlib import contextmanager

    @contextmanager
    def mock_patched_git(worktree, repo_git_dir):
        yield "mock-worktree-name"

    monkeypatch.setattr(
        lw_coder.code_command, "patched_worktree_gitdir", mock_patched_git
    )

    # Execute
    caplog.set_level(logging.INFO)
    exit_code = run_code_command(plan_path)

    # Verify success
    assert exit_code == 0

    # Verify Docker command was executed
    assert len(docker_commands_executed) == 1
    docker_cmd = docker_commands_executed[0]

    # Verify key Docker arguments
    assert "docker" in docker_cmd
    assert "run" in docker_cmd
    assert "lw_coder_droid:test123" in docker_cmd

    # Verify environment variables are forwarded
    # With sensible defaults, we forward OPENROUTER_* variables only
    env_args = [docker_cmd[i+1] for i, arg in enumerate(docker_cmd) if arg == "-e"]
    assert any("OPENROUTER_API_KEY=test-key-123" in arg for arg in env_args)
    # TEST_VAR and IGNORED_VAR should NOT be present (only OPENROUTER_* forwarded by default)
    assert not any("TEST_VAR" in arg for arg in env_args)
    assert not any("IGNORED_VAR" in arg for arg in env_args)

    # Verify workspace mount
    assert any("/workspace" in arg for arg in docker_cmd)
