"""Human feedback collection via interactive Claude Code session.

This module handles collecting human feedback after evaluation using an
interactive Claude Code session. The feedback is free-form markdown
structured however the user prefers.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from .claude_session import ClaudeSessionError, run_interactive_session
from .host_runner import get_lw_coder_src_dir
from .logging_config import get_logger

logger = get_logger(__name__)


class FeedbackCollectionError(Exception):
    """Raised when feedback collection fails."""

    pass


def build_feedback_prompt(
    plan_id: str,
    judge_results: list[dict],
    test_results_before: Optional[dict] = None,
    test_results_after: Optional[dict] = None,
) -> str:
    """Build the feedback collection prompt with evaluation results.

    Args:
        plan_id: Plan identifier being evaluated
        judge_results: List of judge result dictionaries
        test_results_before: Optional before-test results
        test_results_after: Optional after-test results

    Returns:
        Complete prompt string for feedback collection
    """
    # Format judge results
    judge_summary_lines = []
    for result in judge_results:
        judge_summary_lines.append(
            f"- **{result.get('judge_name', 'Unknown')}**: "
            f"{result.get('score', 0):.2f}/1.00 (weight: {result.get('weight', 0):.2f})"
        )
    judge_summary = "\n".join(judge_summary_lines) if judge_summary_lines else "No judge results available"

    # Calculate weighted score
    total_weight = sum(r.get("weight", 0) for r in judge_results)
    if total_weight > 0:
        weighted_score = sum(
            r.get("score", 0) * r.get("weight", 0) for r in judge_results
        ) / total_weight
        weighted_score_line = f"**Overall Weighted Score**: {weighted_score:.2f}/1.00"
    else:
        weighted_score_line = "**Overall Weighted Score**: N/A"

    # Format test results
    def format_test_summary(results: Optional[dict], label: str) -> str:
        if not results:
            return f"**{label}**: Not available"
        total = results.get("total_tests", 0)
        passed = results.get("passed_tests", 0)
        failed = results.get("failed_tests", 0)
        exit_code = results.get("exit_code", "N/A")
        return f"**{label}**: {passed}/{total} passed, {failed} failed (exit code: {exit_code})"

    test_before_summary = format_test_summary(test_results_before, "Before Implementation")
    test_after_summary = format_test_summary(test_results_after, "After Implementation")

    # Format detailed judge feedback
    detailed_feedback_lines = []
    for result in judge_results:
        detailed_feedback_lines.append(f"### {result.get('judge_name', 'Unknown')}")
        detailed_feedback_lines.append(f"**Score**: {result.get('score', 0):.2f}/1.00")
        detailed_feedback_lines.append(f"**Weight**: {result.get('weight', 0):.2f}")
        detailed_feedback_lines.append("")
        detailed_feedback_lines.append(result.get("feedback", "No feedback provided"))
        detailed_feedback_lines.append("")
        detailed_feedback_lines.append("---")
        detailed_feedback_lines.append("")

    detailed_feedback = "\n".join(detailed_feedback_lines) if detailed_feedback_lines else "No detailed feedback available"

    prompt = f"""# Evaluation Feedback Collection

You are helping the user provide feedback on a code implementation that was just evaluated. Your role is to help them compose thoughtful feedback based on the evaluation results.

## Context

The user just ran an evaluation on plan: **{plan_id}**

The evaluation included:
- LLM judge scores assessing code quality and plan compliance
- Test results before implementation (baseline)
- Test results after implementation (current state)

## Your Task

Help the user compose feedback about the implementation. This feedback will be used as training data for improving future code implementations.

1. **Present the evaluation results**: Show the user the judge scores and test results so they can review them.

2. **Gather their feedback**: Ask the user what feedback they have about the implementation. This is free-form - they can structure it however they want. Some users might organize feedback into sections like "Strengths" and "Issues", others might write narrative feedback, and others might use bullet points. Let them decide.

3. **Help refine**: Offer to help them compose or refine their feedback if they want assistance. You can suggest improvements to clarity, help them articulate concerns, or add details they might have missed.

4. **Create the file**: When the user is satisfied with their feedback, write it to `human_feedback.md` in the current directory.

## Important Notes

- This is their feedback, not yours. Don't insert your own analysis unless they ask for it.
- There's no required structure - respect however they want to organize their thoughts.
- Don't ask for approval after creating the file - when it's written, you're done.
- The file will be automatically copied to the training data when this session ends.

## Evaluation Results

### Judge Scores

{judge_summary}

{weighted_score_line}

### Test Results

{test_before_summary}
{test_after_summary}

### Detailed Judge Feedback

{detailed_feedback}

---

Now please present these results to the user and help them compose their feedback.
"""

    return prompt


def collect_human_feedback(
    plan_id: str,
    repo_root: Path,
    output_dir: Path,
    model: str,
    judge_results: list[dict],
    test_results_before: Optional[dict] = None,
    test_results_after: Optional[dict] = None,
) -> Optional[Path]:
    """Collect human feedback via interactive Claude Code session.

    Args:
        plan_id: Plan identifier
        repo_root: Repository root directory
        output_dir: Directory where human_feedback.md should be saved
        model: Model to use for Claude Code
        judge_results: List of judge result dictionaries
        test_results_before: Optional before-test results
        test_results_after: Optional after-test results

    Returns:
        Path to saved feedback file, or None if user cancelled

    Raises:
        FeedbackCollectionError: If session fails
    """
    src_dir = get_lw_coder_src_dir()
    sdk_settings_path = src_dir / "sdk_settings.json"

    if not sdk_settings_path.exists():
        raise FeedbackCollectionError(
            f"SDK settings file not found at {sdk_settings_path}. "
            "Ensure the package is properly installed."
        )

    # Get worktree path
    worktree_path = repo_root / ".lw_coder" / "worktrees" / plan_id

    if not worktree_path.exists():
        raise FeedbackCollectionError(
            f"Worktree not found: {worktree_path}. "
            f"Run 'lw_coder code {plan_id}' first to create the worktree."
        )

    # Build prompt with evaluation results
    prompt = build_feedback_prompt(
        plan_id=plan_id,
        judge_results=judge_results,
        test_results_before=test_results_before,
        test_results_after=test_results_after,
    )

    # Expected output file in worktree
    expected_output = worktree_path / "human_feedback.md"

    try:
        logger.info("Launching interactive feedback collection session...")
        session_id, output_path = run_interactive_session(
            worktree_path=worktree_path,
            prompt=prompt,
            model=model,
            sdk_settings_path=sdk_settings_path,
            expected_output=expected_output,
        )
    except ClaudeSessionError as exc:
        raise FeedbackCollectionError(f"Feedback collection failed: {exc}") from exc

    # Copy feedback file to output directory if it was created
    if output_path and output_path.exists():
        final_path = output_dir / "human_feedback.md"
        try:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output_path, final_path)
            # Clean up the worktree copy
            output_path.unlink(missing_ok=True)
            logger.info("Human feedback saved to: %s", final_path)
            return final_path
        except OSError as exc:
            raise FeedbackCollectionError(
                f"Failed to save feedback file: {exc}"
            ) from exc
    else:
        logger.warning(
            "Feedback file was not created. User may have cancelled the session."
        )
        return None
