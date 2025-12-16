"""Integration tests for trace summarizer with real DSPy LLM calls.

These tests make real LLM API calls to external services (OpenRouter).
They require OPENROUTER_API_KEY to be configured and consume API credits.

Uses DSPy caching so subsequent runs reuse cached responses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lw_coder.judge_executor import JudgeExecutionError, get_openrouter_api_key
from lw_coder.trace_summarizer import (
    TraceSummarizationError,
    create_trace_summary,
    generate_narrative_summary,
)
from lw_coder.trace_parser import parse_subagent_sections


def _get_real_trace_path() -> Path:
    """Get the path to the real test trace file."""
    # Find the repo root by looking for pyproject.toml
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            break
        current = current.parent

    return current / ".lw_coder" / "training_data" / "test-planner-subagent" / "code_trace.md"


@pytest.fixture
def real_trace_path() -> Path:
    """Get path to real trace file."""
    trace_path = _get_real_trace_path()
    if not trace_path.exists():
        pytest.skip("Test trace file not available")
    return trace_path


@pytest.fixture
def real_trace_content(real_trace_path: Path) -> str:
    """Load the committed test-planner-subagent trace file."""
    return real_trace_path.read_text(encoding="utf-8")


def test_create_trace_summary_end_to_end(real_trace_path: Path, tmp_path: Path) -> None:
    """Test full workflow of creating a trace summary.

    This test:
    1. Copies the real trace file to a temp location
    2. Creates a summary using real LLM call
    3. Verifies summary structure and compression

    Uses DSPy caching, so first run hits API, subsequent runs use cache.
    """
    # Get API key (will fail with clear message if not available)
    try:
        get_openrouter_api_key()
    except JudgeExecutionError:
        pytest.skip(
            "OPENROUTER_API_KEY not found in ~/.lw_coder/.env. "
            "Add it to run this integration test."
        )

    # Copy trace file to temp location
    trace_content = real_trace_path.read_text(encoding="utf-8")
    test_trace_path = tmp_path / "code_trace.md"
    test_trace_path.write_text(trace_content, encoding="utf-8")

    original_size = len(trace_content)

    # Create summary
    summary_path = create_trace_summary(test_trace_path, model="x-ai/grok-4.1-fast")

    # Verify summary file was created
    assert summary_path.exists()
    assert summary_path.name == "code_trace_summary.md"
    assert summary_path.parent == tmp_path

    # Read summary content
    summary_content = summary_path.read_text(encoding="utf-8")
    summary_size = len(summary_content)

    # Verify significant compression
    compression_ratio = summary_size / original_size
    assert compression_ratio < 0.15, (
        f"Summary should be <15% of original size. "
        f"Got {compression_ratio:.1%} ({summary_size} / {original_size})"
    )

    # Verify summary structure
    assert "# Trace Summary" in summary_content
    assert "## Session Metadata" in summary_content
    assert "## Tool Usage" in summary_content
    assert "## Files Accessed" in summary_content
    assert "## Narrative Summary" in summary_content

    # Verify metadata is preserved
    assert "8f88f3a8-a30f-4065-be5f-63fb6e62b2b1" in summary_content  # Session ID
    assert "code" in summary_content  # Command
    assert "test-planner-subagent" in summary_content  # Git branch

    # Verify tool counts are present
    assert "Read:" in summary_content
    assert "Edit:" in summary_content
    assert "Bash:" in summary_content


def test_generate_narrative_summary_preserves_subagent_feedback(
    real_trace_content: str,
) -> None:
    """Verify narrative summary preserves subagent feedback.

    This is critical for prompt optimization - the narrative must
    include verbatim feedback from subagents.
    """
    # Get API key
    try:
        get_openrouter_api_key()
    except JudgeExecutionError:
        pytest.skip(
            "OPENROUTER_API_KEY not found in ~/.lw_coder/.env. "
            "Add it to run this integration test."
        )

    # Parse subagent sections
    subagent_sections = parse_subagent_sections(real_trace_content)

    # Generate narrative
    narrative = generate_narrative_summary(
        trace_content=real_trace_content,
        subagent_sections=subagent_sections,
        model="x-ai/grok-4.1-fast",
    )

    # Narrative should not be empty
    assert len(narrative) > 500, "Narrative should be substantial"

    # Narrative should be much smaller than original trace
    compression_ratio = len(narrative) / len(real_trace_content)
    assert compression_ratio < 0.10, (
        f"Narrative should be <10% of trace size. "
        f"Got {compression_ratio:.1%}"
    )

    # The narrative should contain references to subagents or code review
    # (The exact content depends on LLM output, but key topics should appear)
    narrative_lower = narrative.lower()
    assert (
        "subagent" in narrative_lower
        or "review" in narrative_lower
        or "feedback" in narrative_lower
        or "code" in narrative_lower
    ), "Narrative should reference code review or subagent feedback"


def test_summary_usable_in_training_loader(real_trace_path: Path, tmp_path: Path) -> None:
    """Verify generated summary can be loaded by training data loader.

    This is an end-to-end test that:
    1. Creates a minimal training sample directory
    2. Generates a trace summary
    3. Verifies the training loader uses the summary
    """
    # Get API key
    try:
        get_openrouter_api_key()
    except JudgeExecutionError:
        pytest.skip(
            "OPENROUTER_API_KEY not found in ~/.lw_coder/.env. "
            "Add it to run this integration test."
        )

    # Create training sample directory structure
    sample_dir = tmp_path / ".lw_coder" / "training_data" / "test-sample"
    sample_dir.mkdir(parents=True)

    # Copy trace file
    trace_content = real_trace_path.read_text(encoding="utf-8")
    trace_path = sample_dir / "code_trace.md"
    trace_path.write_text(trace_content, encoding="utf-8")

    # Create required files for training sample
    (sample_dir / "human_feedback.md").write_text("Agent performed well.")
    (sample_dir / "test_results_after.json").write_text('{"passed": 10, "failed": 0}')
    (sample_dir / "judge_test.json").write_text(
        '{"judge_name": "test", "score": 0.9, "weight": 0.5, "feedback": "Good work."}'
    )

    # Load training sample with model (triggers summary generation)
    from lw_coder.training_data_loader import load_training_sample

    sample = load_training_sample(
        tmp_path,
        "test-sample",
        model="x-ai/grok-4.1-fast",
    )

    # Verify summary was generated
    summary_path = sample_dir / "code_trace_summary.md"
    assert summary_path.exists(), "Summary should be generated"

    # Verify code_trace field contains the summary (shorter than original)
    assert len(sample.code_trace) < len(trace_content), (
        "Training sample should use summary, not full trace"
    )

    # Verify summary structure is in the loaded trace
    assert "# Trace Summary" in sample.code_trace
    assert "## Narrative Summary" in sample.code_trace


def test_summary_file_not_rewritten_when_trace_unchanged(real_trace_path: Path, tmp_path: Path) -> None:
    """Verify that existing up-to-date summaries are not regenerated.

    This test verifies the file-based caching by checking st_mtime equality:
    - First call creates the summary
    - Second call reuses existing summary (no file rewrite)
    """
    # Get API key
    try:
        get_openrouter_api_key()
    except JudgeExecutionError:
        pytest.skip(
            "OPENROUTER_API_KEY not found in ~/.lw_coder/.env. "
            "Add it to run this integration test."
        )

    # Setup
    trace_content = real_trace_path.read_text(encoding="utf-8")
    test_trace_path = tmp_path / "code_trace.md"
    test_trace_path.write_text(trace_content, encoding="utf-8")

    # First call - creates summary
    summary_path_1 = create_trace_summary(test_trace_path, model="x-ai/grok-4.1-fast")
    first_mtime = summary_path_1.stat().st_mtime

    # Read first summary content
    first_content = summary_path_1.read_text(encoding="utf-8")

    # Small delay to ensure mtime would change if file is rewritten
    import time
    time.sleep(0.1)

    # Use _get_or_create_summary to verify caching
    from lw_coder.training_data_loader import _get_or_create_summary

    cached_content = _get_or_create_summary(
        tmp_path,
        model="x-ai/grok-4.1-fast",
    )

    # Verify same content is returned
    assert cached_content == first_content

    # Verify file wasn't rewritten (mtime unchanged)
    second_mtime = summary_path_1.stat().st_mtime
    assert first_mtime == second_mtime, "Summary should not be regenerated when up-to-date"
