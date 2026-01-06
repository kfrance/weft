"""Tests for judge file loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from weft.judge_loader import (
    JudgeLoaderError,
    discover_judges,
    parse_judge_file,
)


def test_parse_valid_judge_file(tmp_path: Path) -> None:
    """Test parsing a valid judge file."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text(
        """---
weight: 0.5
model: x-ai/grok-4.1-fast
---

This is the judge instruction.
It can be multiple lines.
"""
    )

    config = parse_judge_file(judge_file)

    assert config.name == "test-judge"
    assert config.weight == 0.5
    assert config.model == "x-ai/grok-4.1-fast"
    assert "This is the judge instruction" in config.instructions
    assert config.file_path == judge_file


def test_parse_judge_file_missing_weight(tmp_path: Path) -> None:
    """Test parsing judge file with missing weight field."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text(
        """---
model: x-ai/grok-4.1-fast
---

Instructions here.
"""
    )

    with pytest.raises(JudgeLoaderError, match="Missing required field 'weight'"):
        parse_judge_file(judge_file)


def test_parse_judge_file_missing_model(tmp_path: Path) -> None:
    """Test parsing judge file with missing model field."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text(
        """---
weight: 0.5
---

Instructions here.
"""
    )

    with pytest.raises(JudgeLoaderError, match="Missing required field 'model'"):
        parse_judge_file(judge_file)


def test_parse_judge_file_invalid_weight_type(tmp_path: Path) -> None:
    """Test parsing judge file with invalid weight type."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text(
        """---
weight: invalid
model: x-ai/grok-4.1-fast
---

Instructions here.
"""
    )

    with pytest.raises(JudgeLoaderError, match="Invalid 'weight'.*Expected number"):
        parse_judge_file(judge_file)


def test_parse_judge_file_weight_out_of_range(tmp_path: Path) -> None:
    """Test parsing judge file with weight out of valid range."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text(
        """---
weight: 1.5
model: x-ai/grok-4.1-fast
---

Instructions here.
"""
    )

    with pytest.raises(JudgeLoaderError, match="Invalid 'weight'.*between 0.0 and 1.0"):
        parse_judge_file(judge_file)


def test_parse_judge_file_empty_model(tmp_path: Path) -> None:
    """Test parsing judge file with empty model string."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text(
        """---
weight: 0.5
model: ""
---

Instructions here.
"""
    )

    with pytest.raises(JudgeLoaderError, match="Invalid 'model'.*Cannot be empty"):
        parse_judge_file(judge_file)


def test_parse_judge_file_empty_instructions(tmp_path: Path) -> None:
    """Test parsing judge file with empty instructions."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text(
        """---
weight: 0.5
model: x-ai/grok-4.1-fast
---

"""
    )

    with pytest.raises(JudgeLoaderError, match="Empty instructions"):
        parse_judge_file(judge_file)


def test_parse_judge_file_no_frontmatter(tmp_path: Path) -> None:
    """Test parsing judge file without frontmatter."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text("Just some instructions without frontmatter")

    with pytest.raises(JudgeLoaderError, match="Invalid judge file format.*Expected YAML frontmatter"):
        parse_judge_file(judge_file)


def test_parse_judge_file_invalid_yaml(tmp_path: Path) -> None:
    """Test parsing judge file with invalid YAML."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text(
        """---
weight: 0.5
model: [invalid yaml structure
---

Instructions here.
"""
    )

    with pytest.raises(JudgeLoaderError, match="Invalid YAML frontmatter"):
        parse_judge_file(judge_file)


def test_parse_judge_file_not_found(tmp_path: Path) -> None:
    """Test parsing non-existent judge file."""
    judge_file = tmp_path / "nonexistent.md"

    with pytest.raises(JudgeLoaderError, match="Judge file not found"):
        parse_judge_file(judge_file)


def test_discover_judges(tmp_path: Path) -> None:
    """Test discovering multiple judge files."""
    judges_dir = tmp_path / "judges"
    judges_dir.mkdir()

    # Create multiple judge files
    (judges_dir / "judge-a.md").write_text(
        """---
weight: 0.3
model: x-ai/grok-4.1-fast
---

Judge A instructions.
"""
    )

    (judges_dir / "judge-b.md").write_text(
        """---
weight: 0.7
model: x-ai/grok-4.1-fast
---

Judge B instructions.
"""
    )

    judges = discover_judges(judges_dir)

    assert len(judges) == 2
    assert judges[0].name == "judge-a"
    assert judges[1].name == "judge-b"
    assert judges[0].weight == 0.3
    assert judges[1].weight == 0.7


def test_discover_judges_empty_directory(tmp_path: Path) -> None:
    """Test discovering judges in empty directory."""
    judges_dir = tmp_path / "judges"
    judges_dir.mkdir()

    with pytest.raises(JudgeLoaderError, match="No judge files found"):
        discover_judges(judges_dir)


def test_discover_judges_directory_not_found(tmp_path: Path) -> None:
    """Test discovering judges in non-existent directory."""
    judges_dir = tmp_path / "nonexistent"

    with pytest.raises(JudgeLoaderError, match="Judges directory not found"):
        discover_judges(judges_dir)


def test_discover_judges_invalid_judge_file(tmp_path: Path) -> None:
    """Test discovering judges with one invalid file."""
    judges_dir = tmp_path / "judges"
    judges_dir.mkdir()

    # Valid judge
    (judges_dir / "valid.md").write_text(
        """---
weight: 0.5
model: x-ai/grok-4.1-fast
---

Valid instructions.
"""
    )

    # Invalid judge (missing model)
    (judges_dir / "invalid.md").write_text(
        """---
weight: 0.5
---

Invalid instructions.
"""
    )

    with pytest.raises(JudgeLoaderError, match="Failed to load some judge files"):
        discover_judges(judges_dir)


def test_parse_judge_file_integer_weight(tmp_path: Path) -> None:
    """Test parsing judge file with integer weight (should be converted to float)."""
    judge_file = tmp_path / "test-judge.md"
    judge_file.write_text(
        """---
weight: 1
model: x-ai/grok-4.1-fast
---

Instructions here.
"""
    )

    config = parse_judge_file(judge_file)
    assert config.weight == 1.0
    assert isinstance(config.weight, float)
