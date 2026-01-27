"""Tests for prompt_loader module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from weft.prompt_loader import PromptLoadingError, load_prompts, load_finalize_prompt


def test_load_prompts_success(tmp_path: Path) -> None:
    """Test successful loading of all three prompts."""
    # Create test prompt structure in project-relative path
    prompts_dir = tmp_path / ".weft" / "optimized_prompts" / "claude-code-cli" / "sonnet"
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
        prompts_dir = tmp_path / ".weft" / "optimized_prompts" / "claude-code-cli" / model
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


@pytest.mark.parametrize(
    "missing_file,other_files,model",
    [
        ("main.md", ["code-review-auditor.md", "plan-alignment-checker.md"], "sonnet"),
        ("code-review-auditor.md", ["main.md", "plan-alignment-checker.md"], "opus"),
        ("plan-alignment-checker.md", ["main.md", "code-review-auditor.md"], "haiku"),
    ],
    ids=["missing_main", "missing_code_review", "missing_alignment"]
)
def test_load_prompts_missing_file(tmp_path: Path, missing_file: str, other_files: list[str], model: str) -> None:
    """Test error when a required prompt file is missing."""
    prompts_dir = tmp_path / ".weft" / "optimized_prompts" / "claude-code-cli" / model
    prompts_dir.mkdir(parents=True)

    # Create only the other files, not the missing one
    for file in other_files:
        (prompts_dir / file).write_text("content")

    with pytest.raises(PromptLoadingError) as exc_info:
        load_prompts(repo_root=tmp_path, tool="claude-code-cli", model=model)

    assert "Prompt file not found" in str(exc_info.value)
    assert missing_file in str(exc_info.value)


def test_load_prompts_file_read_error(tmp_path: Path) -> None:
    """Test error handling when file cannot be read."""
    prompts_dir = tmp_path / ".weft" / "optimized_prompts" / "claude-code-cli" / "sonnet"
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
    prompts_dir = tmp_path / ".weft" / "optimized_prompts" / "claude-code-cli" / "sonnet"
    prompts_dir.mkdir(parents=True)

    (prompts_dir / "main.md").write_text("main")
    (prompts_dir / "code-review-auditor.md").write_text("review")
    (prompts_dir / "plan-alignment-checker.md").write_text("alignment")

    # Call with only repo_root to use defaults
    result = load_prompts(repo_root=tmp_path)

    assert result["main_prompt"] == "main"
    assert result["code_review_auditor"] == "review"
    assert result["plan_alignment_checker"] == "alignment"


# =============================================================================
# Tests for load_finalize_prompt
# =============================================================================


def test_load_finalize_prompt_from_repo_specific_location(tmp_path: Path) -> None:
    """Test loading finalize prompt from existing repo-specific location."""
    # Create repo-specific prompt
    prompt_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "finalize.md"
    prompt_content = "# Finalize for {PLAN_ID}\nCustom repo-specific content"
    prompt_file.write_text(prompt_content)

    result = load_finalize_prompt(tmp_path, "claude-code-cli")

    assert result == prompt_content


def test_load_finalize_prompt_auto_copy_from_bundled(tmp_path: Path) -> None:
    """Test auto-copy when repo-specific prompt is missing."""
    # No repo-specific prompt exists
    # Mock the bundled prompt location
    bundled_content = "# Bundled finalize prompt for {PLAN_ID}"

    with patch("weft.host_runner.get_weft_src_dir") as mock_src_dir:
        # Create a temp bundled location
        bundled_dir = tmp_path / "bundled" / "prompts" / "claude-code"
        bundled_dir.mkdir(parents=True)
        (bundled_dir / "finalize.md").write_text(bundled_content)
        mock_src_dir.return_value = tmp_path / "bundled"

        result = load_finalize_prompt(tmp_path, "claude-code-cli")

    assert result == bundled_content
    # Verify file was copied to repo location
    copied_file = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli" / "finalize.md"
    assert copied_file.exists()
    assert copied_file.read_text() == bundled_content


def test_load_finalize_prompt_auto_copy_is_idempotent(tmp_path: Path) -> None:
    """Test that calling auto-copy twice doesn't fail."""
    bundled_content = "# Bundled finalize prompt for {PLAN_ID}"

    with patch("weft.host_runner.get_weft_src_dir") as mock_src_dir:
        # Create a temp bundled location
        bundled_dir = tmp_path / "bundled" / "prompts" / "claude-code"
        bundled_dir.mkdir(parents=True)
        (bundled_dir / "finalize.md").write_text(bundled_content)
        mock_src_dir.return_value = tmp_path / "bundled"

        # First call triggers auto-copy
        result1 = load_finalize_prompt(tmp_path, "claude-code-cli")
        # Second call should load from repo-specific location
        result2 = load_finalize_prompt(tmp_path, "claude-code-cli")

    assert result1 == bundled_content
    assert result2 == bundled_content


def test_load_finalize_prompt_error_when_bundled_missing(tmp_path: Path) -> None:
    """Test error when both repo-specific and bundled prompts are missing."""
    with patch("weft.host_runner.get_weft_src_dir") as mock_src_dir:
        # Point to a directory without the finalize prompt
        empty_dir = tmp_path / "empty_src"
        empty_dir.mkdir(parents=True)
        mock_src_dir.return_value = empty_dir

        with pytest.raises(PromptLoadingError) as exc_info:
            load_finalize_prompt(tmp_path, "claude-code-cli")

    assert "Bundled finalize prompt not found" in str(exc_info.value)


def test_load_finalize_prompt_error_when_get_weft_src_dir_fails(tmp_path: Path) -> None:
    """Test error when get_weft_src_dir raises RuntimeError."""
    with patch("weft.host_runner.get_weft_src_dir") as mock_src_dir:
        mock_src_dir.side_effect = RuntimeError("Could not determine source directory")

        with pytest.raises(PromptLoadingError) as exc_info:
            load_finalize_prompt(tmp_path, "claude-code-cli")

    assert "Failed to locate source directory" in str(exc_info.value)
    assert "Could not determine source directory" in str(exc_info.value)


def test_load_finalize_prompt_error_on_empty_repo_prompt(tmp_path: Path) -> None:
    """Test error when repo-specific prompt file is empty."""
    # Create empty repo-specific prompt
    prompt_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "finalize.md").write_text("")

    with pytest.raises(PromptLoadingError) as exc_info:
        load_finalize_prompt(tmp_path, "claude-code-cli")

    assert "is empty" in str(exc_info.value)


def test_load_finalize_prompt_for_droid_tool(tmp_path: Path) -> None:
    """Test loading finalize prompt for droid tool."""
    # Create repo-specific prompt for droid
    prompt_dir = tmp_path / ".weft" / "prompts" / "active" / "droid"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "finalize.md"
    prompt_content = "# Droid finalize for {PLAN_ID}"
    prompt_file.write_text(prompt_content)

    result = load_finalize_prompt(tmp_path, "droid")

    assert result == prompt_content


def test_load_finalize_prompt_placeholder_preserved(tmp_path: Path) -> None:
    """Test that {PLAN_ID} placeholder is preserved for later substitution."""
    # Create repo-specific prompt with multiple placeholders
    prompt_dir = tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli"
    prompt_dir.mkdir(parents=True)
    prompt_content = "Plan: {PLAN_ID}\nRef: {PLAN_ID}\nAnother: {PLAN_ID}"
    (prompt_dir / "finalize.md").write_text(prompt_content)

    result = load_finalize_prompt(tmp_path, "claude-code-cli")

    # Placeholder should still be present (not replaced yet)
    assert "{PLAN_ID}" in result
    assert result.count("{PLAN_ID}") == 3


def test_load_finalize_prompt_creates_parent_directories(tmp_path: Path) -> None:
    """Test that auto-copy creates parent directories when they don't exist."""
    bundled_content = "# Bundled prompt"

    with patch("weft.host_runner.get_weft_src_dir") as mock_src_dir:
        bundled_dir = tmp_path / "bundled" / "prompts" / "claude-code"
        bundled_dir.mkdir(parents=True)
        (bundled_dir / "finalize.md").write_text(bundled_content)
        mock_src_dir.return_value = tmp_path / "bundled"

        # Ensure .weft directory doesn't exist
        assert not (tmp_path / ".weft").exists()

        result = load_finalize_prompt(tmp_path, "claude-code-cli")

    assert result == bundled_content
    # Verify the entire directory hierarchy was created
    assert (tmp_path / ".weft" / "prompts" / "active" / "claude-code-cli" / "finalize.md").exists()
