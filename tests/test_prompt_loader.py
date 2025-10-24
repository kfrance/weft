"""Tests for prompt_loader module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lw_coder.prompt_loader import PromptLoadingError, load_prompts


def test_load_prompts_success(tmp_path: Path) -> None:
    """Test successful loading of all three prompts."""
    # Create test prompt structure in project-relative path
    prompts_dir = tmp_path / ".lw_coder" / "optimized_prompts" / "claude-code-cli" / "sonnet"
    prompts_dir.mkdir(parents=True)

    main_content = "Main prompt for testing"
    review_content = "Code review auditor prompt"
    alignment_content = "Plan alignment checker prompt"

    (prompts_dir / "main.md").write_text(main_content)
    (prompts_dir / "code-review-auditor.md").write_text(review_content)
    (prompts_dir / "plan-alignment-checker.md").write_text(alignment_content)

    result = load_prompts(repo_root=tmp_path, tool="claude-code-cli", model="sonnet")

    assert result["main_prompt"] == main_content
    assert result["code_review_auditor"] == review_content
    assert result["plan_alignment_checker"] == alignment_content


def test_load_prompts_all_models(tmp_path: Path) -> None:
    """Test loading prompts for all three supported models."""
    models = ["sonnet", "opus", "haiku"]

    for model in models:
        prompts_dir = tmp_path / ".lw_coder" / "optimized_prompts" / "claude-code-cli" / model
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "main.md").write_text(f"Main for {model}")
        (prompts_dir / "code-review-auditor.md").write_text(f"Review for {model}")
        (prompts_dir / "plan-alignment-checker.md").write_text(f"Alignment for {model}")

    for model in models:
        result = load_prompts(repo_root=tmp_path, tool="claude-code-cli", model=model)
        assert result["main_prompt"] == f"Main for {model}"
        assert result["code_review_auditor"] == f"Review for {model}"
        assert result["plan_alignment_checker"] == f"Alignment for {model}"


def test_load_prompts_invalid_model(tmp_path: Path) -> None:
    """Test error when prompt is requested for invalid model."""
    with pytest.raises(PromptLoadingError) as exc_info:
        load_prompts(repo_root=tmp_path, tool="claude-code-cli", model="invalid-model")

    assert "Invalid model" in str(exc_info.value)
    assert "invalid-model" in str(exc_info.value)


def test_load_prompts_missing_main_file(tmp_path: Path) -> None:
    """Test error when main.md prompt file is missing."""
    prompts_dir = tmp_path / ".lw_coder" / "optimized_prompts" / "claude-code-cli" / "sonnet"
    prompts_dir.mkdir(parents=True)

    # Create only the sub-agent prompts, not the main prompt
    (prompts_dir / "code-review-auditor.md").write_text("review")
    (prompts_dir / "plan-alignment-checker.md").write_text("alignment")

    with pytest.raises(PromptLoadingError) as exc_info:
        load_prompts(repo_root=tmp_path, tool="claude-code-cli", model="sonnet")

    assert "Prompt file not found" in str(exc_info.value)
    assert "main.md" in str(exc_info.value)


def test_load_prompts_missing_code_review_file(tmp_path: Path) -> None:
    """Test error when code-review-auditor.md prompt file is missing."""
    prompts_dir = tmp_path / ".lw_coder" / "optimized_prompts" / "claude-code-cli" / "opus"
    prompts_dir.mkdir(parents=True)

    # Create only main and alignment prompts, not code-review
    (prompts_dir / "main.md").write_text("main")
    (prompts_dir / "plan-alignment-checker.md").write_text("alignment")

    with pytest.raises(PromptLoadingError) as exc_info:
        load_prompts(repo_root=tmp_path, tool="claude-code-cli", model="opus")

    assert "Prompt file not found" in str(exc_info.value)
    assert "code-review-auditor.md" in str(exc_info.value)


def test_load_prompts_missing_alignment_file(tmp_path: Path) -> None:
    """Test error when plan-alignment-checker.md prompt file is missing."""
    prompts_dir = tmp_path / ".lw_coder" / "optimized_prompts" / "claude-code-cli" / "haiku"
    prompts_dir.mkdir(parents=True)

    # Create only main and code-review prompts, not alignment
    (prompts_dir / "main.md").write_text("main")
    (prompts_dir / "code-review-auditor.md").write_text("review")

    with pytest.raises(PromptLoadingError) as exc_info:
        load_prompts(repo_root=tmp_path, tool="claude-code-cli", model="haiku")

    assert "Prompt file not found" in str(exc_info.value)
    assert "plan-alignment-checker.md" in str(exc_info.value)


def test_load_prompts_file_read_error(tmp_path: Path) -> None:
    """Test error handling when file cannot be read."""
    prompts_dir = tmp_path / ".lw_coder" / "optimized_prompts" / "claude-code-cli" / "sonnet"
    prompts_dir.mkdir(parents=True)

    # Create files but make the directory unreadable
    (prompts_dir / "main.md").write_text("main")
    (prompts_dir / "code-review-auditor.md").write_text("review")
    (prompts_dir / "plan-alignment-checker.md").write_text("alignment")

    # Patch read_text to simulate an I/O error
    with patch("pathlib.Path.read_text", side_effect=OSError("Permission denied")):
        with pytest.raises(PromptLoadingError) as exc_info:
            load_prompts(repo_root=tmp_path, tool="claude-code-cli", model="sonnet")

        assert "Failed to read prompt file" in str(exc_info.value)


def test_load_prompts_default_parameters(tmp_path: Path) -> None:
    """Test that load_prompts uses correct default parameters."""
    # Create structure for default tool and model
    prompts_dir = tmp_path / ".lw_coder" / "optimized_prompts" / "claude-code-cli" / "sonnet"
    prompts_dir.mkdir(parents=True)

    (prompts_dir / "main.md").write_text("main")
    (prompts_dir / "code-review-auditor.md").write_text("review")
    (prompts_dir / "plan-alignment-checker.md").write_text("alignment")

    # Call with only repo_root to use defaults
    result = load_prompts(repo_root=tmp_path)

    assert result["main_prompt"] == "main"
    assert result["code_review_auditor"] == "review"
    assert result["plan_alignment_checker"] == "alignment"


def test_load_prompts_correct_path_construction(tmp_path: Path) -> None:
    """Test that correct path is constructed for different models and tools."""
    # Create structure for multiple tools/models
    for tool in ["claude-code-cli"]:
        for model in ["sonnet", "opus", "haiku"]:
            prompts_dir = tmp_path / ".lw_coder" / "optimized_prompts" / tool / model
            prompts_dir.mkdir(parents=True)

            (prompts_dir / "main.md").write_text(f"main-{tool}-{model}")
            (prompts_dir / "code-review-auditor.md").write_text(f"review-{tool}-{model}")
            (prompts_dir / "plan-alignment-checker.md").write_text(f"alignment-{tool}-{model}")

    # Verify each combination loads from correct path
    result_sonnet = load_prompts(repo_root=tmp_path, tool="claude-code-cli", model="sonnet")
    assert "sonnet" in result_sonnet["main_prompt"]

    result_opus = load_prompts(repo_root=tmp_path, tool="claude-code-cli", model="opus")
    assert "opus" in result_opus["main_prompt"]

    result_haiku = load_prompts(repo_root=tmp_path, tool="claude-code-cli", model="haiku")
    assert "haiku" in result_haiku["main_prompt"]
