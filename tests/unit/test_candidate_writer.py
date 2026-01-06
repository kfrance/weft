"""Tests for candidate_writer module."""

from __future__ import annotations

from pathlib import Path

import pytest

from weft.candidate_writer import (
    get_next_candidate_number,
    write_candidate,
)
from weft.training_types import CandidatePrompts, SubagentDefinition


class TestGetNextCandidateNumber:
    """Tests for get_next_candidate_number function."""

    def test_get_next_candidate_number_empty(self, tmp_path: Path) -> None:
        """Returns 1 when no candidates exist."""
        result = get_next_candidate_number(tmp_path, "claude-code-cli", "sonnet")
        assert result == 1

    def test_get_next_candidate_number_sequential(self, tmp_path: Path) -> None:
        """Returns next number after existing."""
        candidates_dir = (
            tmp_path / ".weft" / "prompts" / "candidates" / "claude-code-cli" / "sonnet"
        )
        candidates_dir.mkdir(parents=True)

        # Create existing candidates
        (candidates_dir / "candidate-001").mkdir()
        (candidates_dir / "candidate-002").mkdir()
        (candidates_dir / "candidate-003").mkdir()

        result = get_next_candidate_number(tmp_path, "claude-code-cli", "sonnet")
        assert result == 4

    def test_get_next_candidate_number_gaps(self, tmp_path: Path) -> None:
        """Returns number after highest, ignoring gaps."""
        candidates_dir = (
            tmp_path / ".weft" / "prompts" / "candidates" / "claude-code-cli" / "sonnet"
        )
        candidates_dir.mkdir(parents=True)

        # Create candidates with gaps
        (candidates_dir / "candidate-001").mkdir()
        (candidates_dir / "candidate-005").mkdir()

        result = get_next_candidate_number(tmp_path, "claude-code-cli", "sonnet")
        assert result == 6

    def test_get_next_candidate_number_ignores_non_matching(self, tmp_path: Path) -> None:
        """Ignores directories that don't match pattern."""
        candidates_dir = (
            tmp_path / ".weft" / "prompts" / "candidates" / "claude-code-cli" / "sonnet"
        )
        candidates_dir.mkdir(parents=True)

        (candidates_dir / "candidate-001").mkdir()
        (candidates_dir / "other-directory").mkdir()
        (candidates_dir / "candidate-bad").mkdir()

        result = get_next_candidate_number(tmp_path, "claude-code-cli", "sonnet")
        assert result == 2


class TestWriteCandidate:
    """Tests for write_candidate function."""

    @pytest.fixture
    def sample_candidate(self) -> CandidatePrompts:
        """Create a sample CandidatePrompts object."""
        return CandidatePrompts(
            main_prompt="# Main Prompt\n\nImproved content...",
            subagents=[
                SubagentDefinition(
                    name="code-review-auditor",
                    description="Reviews code quality",
                    prompt="You are a code review expert...",
                ),
                SubagentDefinition(
                    name="test-validator",
                    description="Validates test coverage",
                    prompt="You validate test quality...",
                ),
            ],
            analysis_summary="Improved code review and added test validation.",
        )

    def test_write_candidate_creates_directory(
        self, tmp_path: Path, sample_candidate: CandidatePrompts
    ) -> None:
        """Creates candidate-NNN directory."""
        result_path = write_candidate(
            tmp_path, "claude-code-cli", "sonnet", sample_candidate
        )

        assert result_path.exists()
        assert result_path.name == "candidate-001"
        assert result_path.parent.name == "sonnet"

    def test_write_candidate_writes_main_prompt(
        self, tmp_path: Path, sample_candidate: CandidatePrompts
    ) -> None:
        """Writes main.md."""
        result_path = write_candidate(
            tmp_path, "claude-code-cli", "sonnet", sample_candidate
        )

        main_path = result_path / "main.md"
        assert main_path.exists()
        assert main_path.read_text() == "# Main Prompt\n\nImproved content..."

    def test_write_candidate_writes_subagents(
        self, tmp_path: Path, sample_candidate: CandidatePrompts
    ) -> None:
        """Writes subagent .md files."""
        result_path = write_candidate(
            tmp_path, "claude-code-cli", "sonnet", sample_candidate
        )

        # Check code-review-auditor.md
        auditor_path = result_path / "code-review-auditor.md"
        assert auditor_path.exists()
        assert auditor_path.read_text() == "You are a code review expert..."

        # Check test-validator.md
        validator_path = result_path / "test-validator.md"
        assert validator_path.exists()
        assert validator_path.read_text() == "You validate test quality..."

    def test_write_candidate_writes_analysis(
        self, tmp_path: Path, sample_candidate: CandidatePrompts
    ) -> None:
        """Writes ANALYSIS.md with summary."""
        result_path = write_candidate(
            tmp_path, "claude-code-cli", "sonnet", sample_candidate
        )

        analysis_path = result_path / "ANALYSIS.md"
        assert analysis_path.exists()
        content = analysis_path.read_text()
        assert "candidate-001" in content
        assert "Improved code review" in content

    def test_write_candidate_returns_path(
        self, tmp_path: Path, sample_candidate: CandidatePrompts
    ) -> None:
        """Returns path to created directory."""
        result_path = write_candidate(
            tmp_path, "claude-code-cli", "sonnet", sample_candidate
        )

        expected = (
            tmp_path
            / ".weft"
            / "prompts"
            / "candidates"
            / "claude-code-cli"
            / "sonnet"
            / "candidate-001"
        )
        assert result_path == expected

    def test_write_candidate_sequential_numbering(
        self, tmp_path: Path, sample_candidate: CandidatePrompts
    ) -> None:
        """Creates sequentially numbered directories."""
        # Write first candidate
        path1 = write_candidate(tmp_path, "claude-code-cli", "sonnet", sample_candidate)
        assert path1.name == "candidate-001"

        # Write second candidate
        path2 = write_candidate(tmp_path, "claude-code-cli", "sonnet", sample_candidate)
        assert path2.name == "candidate-002"

        # Write third candidate
        path3 = write_candidate(tmp_path, "claude-code-cli", "sonnet", sample_candidate)
        assert path3.name == "candidate-003"

    def test_write_candidate_empty_subagents(self, tmp_path: Path) -> None:
        """Handles candidate with no subagents."""
        candidate = CandidatePrompts(
            main_prompt="Main only",
            subagents=[],
            analysis_summary="No subagents needed.",
        )

        result_path = write_candidate(
            tmp_path, "claude-code-cli", "sonnet", candidate
        )

        # Should only have main.md and ANALYSIS.md
        files = list(result_path.glob("*.md"))
        assert len(files) == 2
        assert (result_path / "main.md").exists()
        assert (result_path / "ANALYSIS.md").exists()

    def test_write_candidate_different_models(
        self, tmp_path: Path, sample_candidate: CandidatePrompts
    ) -> None:
        """Creates separate directories for different models."""
        path_sonnet = write_candidate(
            tmp_path, "claude-code-cli", "sonnet", sample_candidate
        )
        path_opus = write_candidate(
            tmp_path, "claude-code-cli", "opus", sample_candidate
        )

        assert "sonnet" in str(path_sonnet)
        assert "opus" in str(path_opus)
        assert path_sonnet != path_opus
