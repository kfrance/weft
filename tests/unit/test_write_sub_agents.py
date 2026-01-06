"""Tests for _write_sub_agents function in code_command module."""

from __future__ import annotations

from pathlib import Path


from weft.code_command import _write_sub_agents, AGENT_DESCRIPTIONS


def test_write_sub_agents_creates_both_files(tmp_path: Path) -> None:
    """Test that both sub-agent files are created."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    prompts = {
        "main_prompt": "Main prompt content",
        "code_review_auditor": "Code review prompt",
        "plan_alignment_checker": "Plan alignment prompt",
    }

    _write_sub_agents(prompts, worktree_path, "sonnet")

    assert (worktree_path / ".claude" / "agents" / "code-review-auditor.md").exists()
    assert (worktree_path / ".claude" / "agents" / "plan-alignment-checker.md").exists()


def test_write_sub_agents_correct_yaml_frontmatter(tmp_path: Path) -> None:
    """Test that YAML frontmatter is correctly formatted without tools: field."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    prompts = {
        "main_prompt": "Main prompt",
        "code_review_auditor": "Review prompt",
        "plan_alignment_checker": "Alignment prompt",
    }

    model = "opus"
    _write_sub_agents(prompts, worktree_path, model)

    # Check code-review-auditor frontmatter
    review_file = worktree_path / ".claude" / "agents" / "code-review-auditor.md"
    review_content = review_file.read_text(encoding="utf-8")

    assert "---" in review_content
    assert "name: code-review-auditor" in review_content
    assert f"description: {AGENT_DESCRIPTIONS['code-review-auditor']}" in review_content
    # Verify tools: is not declared (enables inheritance from parent agent)
    assert "tools:" not in review_content
    assert f"model: {model}" in review_content

    # Check plan-alignment-checker frontmatter
    alignment_file = worktree_path / ".claude" / "agents" / "plan-alignment-checker.md"
    alignment_content = alignment_file.read_text(encoding="utf-8")

    assert "---" in alignment_content
    assert "name: plan-alignment-checker" in alignment_content
    assert f"description: {AGENT_DESCRIPTIONS['plan-alignment-checker']}" in alignment_content
    # Verify tools: is not declared (enables inheritance from parent agent)
    assert "tools:" not in alignment_content
    assert f"model: {model}" in alignment_content


def test_write_sub_agents_content_after_frontmatter(tmp_path: Path) -> None:
    """Test that prompt content appears correctly after frontmatter."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    review_prompt = "This is the review prompt content"
    alignment_prompt = "This is the alignment prompt content"

    prompts = {
        "main_prompt": "Main",
        "code_review_auditor": review_prompt,
        "plan_alignment_checker": alignment_prompt,
    }

    _write_sub_agents(prompts, worktree_path, "haiku")

    # Verify review content
    review_file = worktree_path / ".claude" / "agents" / "code-review-auditor.md"
    review_content = review_file.read_text(encoding="utf-8")
    assert review_prompt in review_content
    # Verify content appears after frontmatter
    parts = review_content.split("---")
    assert len(parts) >= 3  # Opening ---, closing ---, and content
    assert review_prompt in parts[2]

    # Verify alignment content
    alignment_file = worktree_path / ".claude" / "agents" / "plan-alignment-checker.md"
    alignment_content = alignment_file.read_text(encoding="utf-8")
    assert alignment_prompt in alignment_content
    # Verify content appears after frontmatter
    parts = alignment_content.split("---")
    assert len(parts) >= 3
    assert alignment_prompt in parts[2]


def test_write_sub_agents_creates_directory_structure(tmp_path: Path) -> None:
    """Test that .claude/agents/ directory structure is created."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Initially .claude/agents doesn't exist
    agents_dir = worktree_path / ".claude" / "agents"
    assert not agents_dir.exists()

    prompts = {
        "main_prompt": "Main",
        "code_review_auditor": "Review",
        "plan_alignment_checker": "Alignment",
    }

    _write_sub_agents(prompts, worktree_path, "sonnet")

    # After calling _write_sub_agents, directory and files should exist
    assert agents_dir.exists()
    assert agents_dir.is_dir()
    assert (agents_dir / "code-review-auditor.md").exists()
    assert (agents_dir / "plan-alignment-checker.md").exists()


def test_write_sub_agents_different_models(tmp_path: Path) -> None:
    """Test that different model values are correctly written to frontmatter."""
    models = ["sonnet", "opus", "haiku"]

    for model in models:
        worktree_path = tmp_path / f"worktree-{model}"
        worktree_path.mkdir()

        prompts = {
            "main_prompt": "Main",
            "code_review_auditor": f"Review for {model}",
            "plan_alignment_checker": f"Alignment for {model}",
        }

        _write_sub_agents(prompts, worktree_path, model)

        review_file = worktree_path / ".claude" / "agents" / "code-review-auditor.md"
        content = review_file.read_text(encoding="utf-8")

        assert f"model: {model}" in content


def test_write_sub_agents_overwrites_existing_files(tmp_path: Path) -> None:
    """Test that existing agent files are overwritten."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()
    agents_dir = worktree_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)

    # Create existing files with old content
    review_file = agents_dir / "code-review-auditor.md"
    alignment_file = agents_dir / "plan-alignment-checker.md"
    review_file.write_text("Old review content")
    alignment_file.write_text("Old alignment content")

    prompts = {
        "main_prompt": "Main",
        "code_review_auditor": "New review content",
        "plan_alignment_checker": "New alignment content",
    }

    _write_sub_agents(prompts, worktree_path, "sonnet")

    # Verify files were overwritten with new content
    assert "New review content" in review_file.read_text(encoding="utf-8")
    assert "New alignment content" in alignment_file.read_text(encoding="utf-8")
    assert "Old review content" not in review_file.read_text(encoding="utf-8")
    assert "Old alignment content" not in alignment_file.read_text(encoding="utf-8")


def test_write_sub_agents_preserves_prompt_formatting(tmp_path: Path) -> None:
    """Test that multi-line prompts and special characters are preserved."""
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()

    # Prompt with multiple lines, special characters, etc.
    multiline_prompt = """
# Code Review Guidelines

- Check for:
  1. Security issues
  2. Performance problems
  3. Code style violations

Special chars: $, @, %, &, etc.
"""

    prompts = {
        "main_prompt": "Main",
        "code_review_auditor": multiline_prompt,
        "plan_alignment_checker": "Alignment",
    }

    _write_sub_agents(prompts, worktree_path, "opus")

    review_file = worktree_path / ".claude" / "agents" / "code-review-auditor.md"
    content = review_file.read_text(encoding="utf-8")

    # Verify formatting is preserved
    assert multiline_prompt in content
    assert "# Code Review Guidelines" in content
    assert "Security issues" in content
    assert "Special chars: $, @, %, &" in content
