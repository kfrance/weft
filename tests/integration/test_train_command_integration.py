"""Integration tests for train command with real DSPy LLM calls.

These tests make real LLM API calls to external services (OpenRouter).
They require OPENROUTER_API_KEY to be configured and consume API credits.
DSPy caching is used to minimize API costs on repeated runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from weft.candidate_writer import write_candidate
from weft.judge_executor import JudgeExecutionError, get_cache_dir, get_openrouter_api_key
from weft.prompt_loader import load_current_prompts_for_training
from weft.prompt_trainer import run_prompt_trainer
from weft.training_data_loader import load_training_batch


def create_test_training_data(repo_root: Path) -> None:
    """Create minimal training data structure for testing.

    Creates a single training sample with all required files.
    """
    training_dir = repo_root / ".weft" / "training_data" / "test-plan-001"
    training_dir.mkdir(parents=True)

    # Plan content
    (training_dir / "plan.md").write_text("""---
plan_id: test-plan-001
status: coding
---

## Objectives

Implement a simple calculator function.

## Requirements

1. Add function for addition
2. Add function for subtraction
3. Return correct results

## Work Items

### 1. Create calculator.py

Add basic arithmetic functions.
""")

    # Code trace (minimal)
    (training_dir / "code_trace.md").write_text("""## Tool Calls

1. Read: calculator.py
2. Write: calculator.py (added functions)
3. Bash: uv run pytest

## Result

Implementation completed successfully.
""")

    # Human feedback - the key training signal
    (training_dir / "human_feedback.md").write_text("""The agent performed well overall, but:

1. Agent skipped adding docstrings to functions
2. Agent didn't add type hints
3. Test coverage was incomplete - only tested happy path

Would be better if the agent:
- Added comprehensive documentation
- Used type hints consistently
- Created edge case tests
""")

    # Test results
    (training_dir / "test_results_before.json").write_text(json.dumps({
        "command": "uv run pytest",
        "exit_code": 0,
        "total_tests": 10,
        "passed_tests": 10,
        "failed_tests": 0,
        "summary": "All tests passed",
    }))

    (training_dir / "test_results_after.json").write_text(json.dumps({
        "command": "uv run pytest",
        "exit_code": 0,
        "total_tests": 12,
        "passed_tests": 11,
        "failed_tests": 1,
        "summary": "11 passed, 1 failed",
    }))

    # Judge results
    (training_dir / "judge_code-reuse.json").write_text(json.dumps({
        "judge_name": "code-reuse",
        "weight": 0.4,
        "score": 0.85,
        "feedback": "Good reuse of existing patterns. Minor opportunities for improvement.",
    }))
    (training_dir / "judge_code-reuse.md").write_text("""## Code Reuse Evaluation

Score: 0.85

The implementation shows good awareness of existing patterns.
However, could have reused the existing validation utilities.
""")

    (training_dir / "judge_plan-compliance.json").write_text(json.dumps({
        "judge_name": "plan-compliance",
        "weight": 0.6,
        "score": 0.7,
        "feedback": "Most requirements implemented. Missing documentation requirement.",
    }))
    (training_dir / "judge_plan-compliance.md").write_text("""## Plan Compliance Evaluation

Score: 0.7

The implementation addresses the core requirements but:
- Documentation was not added as specified
- Type hints were omitted
""")


def create_test_active_prompts(repo_root: Path) -> None:
    """Create minimal active prompts structure for testing."""
    prompts_dir = repo_root / ".weft" / "prompts" / "active" / "claude-code-cli" / "sonnet"
    prompts_dir.mkdir(parents=True)

    (prompts_dir / "main.md").write_text("""# Claude Code CLI Main Prompt (Sonnet)

You are the primary implementation agent for weft. Follow the plan in `plan.md` end-to-end.

## Implementation Phase

1. Use the **Read** tool to review `plan.md` and any referenced files.
2. Implement the required changes.
3. Run tests to verify.

## Operating Principles

- Write clean, well-documented code
- Follow existing patterns in the codebase
""")

    (prompts_dir / "code-review-auditor.md").write_text("""# Code Review Auditor

Review code changes for quality and compliance.

## Review Criteria

1. Code quality and style
2. Documentation completeness
3. Test coverage
""")

    (prompts_dir / "plan-alignment-checker.md").write_text("""# Plan Alignment Checker

Verify implementation aligns with the original plan.

## Verification Steps

1. Compare implemented features against plan requirements
2. Identify any deviations
3. Report alignment status
""")


def test_train_command_end_to_end(tmp_path: Path) -> None:
    """Full workflow test covering the complete happy path.

    No mocks for the DSPy/LLM call - uses real API calls with caching.
    """
    # Get API key (will fail with clear message if not available)
    try:
        api_key = get_openrouter_api_key()
    except JudgeExecutionError:
        pytest.fail(
            "OPENROUTER_API_KEY not found in ~/.weft/.env. "
            "Add it to run integration tests."
        )

    # Set up test directory structure
    create_test_training_data(tmp_path)
    create_test_active_prompts(tmp_path)

    # Get cache directory for DSPy
    cache_dir = get_cache_dir()

    # Step 1: Load training batch
    training_samples = load_training_batch(tmp_path, batch_size=1)
    assert len(training_samples) == 1
    assert training_samples[0].plan_id == "test-plan-001"

    # Step 2: Load current prompts
    current_prompts = load_current_prompts_for_training(
        tmp_path, tool="claude-code-cli", model="sonnet"
    )
    assert current_prompts.main_prompt is not None
    assert len(current_prompts.subagents) == 2

    # Step 3: Run prompt trainer (real API call, cached)
    candidate, token_usage = run_prompt_trainer(
        training_samples=training_samples,
        current_prompts=current_prompts,
        max_subagents=3,
        model="x-ai/grok-4.1-fast",
        cache_dir=cache_dir,
    )

    # Assertion 1: Candidate has valid structure
    assert candidate.main_prompt is not None
    assert len(candidate.main_prompt) > 0
    assert isinstance(candidate.main_prompt, str)

    # Assertion 2: Subagents within bounds
    assert len(candidate.subagents) >= 0
    assert len(candidate.subagents) <= 3  # respects max_subagents

    # Assertion 3: Each subagent has required fields
    for subagent in candidate.subagents:
        assert subagent.name is not None
        assert len(subagent.name) > 0
        assert subagent.description is not None
        assert subagent.prompt is not None
        assert len(subagent.prompt) > 0

    # Assertion 4: Analysis summary exists and is non-empty
    assert candidate.analysis_summary is not None
    assert len(candidate.analysis_summary) > 0

    # Assertion 5: Token usage is reported
    assert "input_tokens" in token_usage
    assert "output_tokens" in token_usage
    assert "total_tokens" in token_usage
    # Note: token counts may be 0 if caching doesn't track usage
    assert isinstance(token_usage["input_tokens"], int)
    assert isinstance(token_usage["output_tokens"], int)
    assert isinstance(token_usage["total_tokens"], int)

    # Step 4: Write candidate (verify it can be written successfully)
    candidate_dir = write_candidate(
        repo_root=tmp_path,
        tool="claude-code-cli",
        model="sonnet",
        candidate=candidate,
    )

    # Assertion 6: Candidate directory created
    assert candidate_dir.exists()
    assert candidate_dir.name == "candidate-001"

    # Assertion 7: Main prompt written
    main_path = candidate_dir / "main.md"
    assert main_path.exists()
    assert len(main_path.read_text()) > 0

    # Assertion 8: Subagent files written (if any)
    subagent_files = [f for f in candidate_dir.glob("*.md") if f.name not in ("main.md", "ANALYSIS.md")]
    assert len(subagent_files) == len(candidate.subagents)

    # Assertion 9: ANALYSIS.md written
    analysis_path = candidate_dir / "ANALYSIS.md"
    assert analysis_path.exists()
    assert "candidate-001" in analysis_path.read_text()


def test_train_command_multiple_samples(tmp_path: Path) -> None:
    """Test training with multiple samples."""
    try:
        api_key = get_openrouter_api_key()
    except JudgeExecutionError:
        pytest.fail(
            "OPENROUTER_API_KEY not found in ~/.weft/.env. "
            "Add it to run integration tests."
        )

    # Create multiple training samples
    create_test_training_data(tmp_path)

    # Create second sample
    training_dir2 = tmp_path / ".weft" / "training_data" / "test-plan-002"
    training_dir2.mkdir(parents=True)
    (training_dir2 / "human_feedback.md").write_text("Agent completed task successfully.")
    (training_dir2 / "test_results_after.json").write_text('{"passed": 20, "failed": 0}')
    (training_dir2 / "judge_test.json").write_text(json.dumps({
        "judge_name": "test",
        "weight": 1.0,
        "score": 0.95,
        "feedback": "Excellent work.",
    }))

    create_test_active_prompts(tmp_path)
    cache_dir = get_cache_dir()

    # Load batch with multiple samples
    training_samples = load_training_batch(tmp_path, batch_size=2)
    assert len(training_samples) == 2

    current_prompts = load_current_prompts_for_training(
        tmp_path, tool="claude-code-cli", model="sonnet"
    )

    # Should work with multiple samples
    candidate, token_usage = run_prompt_trainer(
        training_samples=training_samples,
        current_prompts=current_prompts,
        max_subagents=2,
        model="x-ai/grok-4.1-fast",
        cache_dir=cache_dir,
    )

    assert candidate.main_prompt is not None
    assert len(candidate.subagents) <= 2
