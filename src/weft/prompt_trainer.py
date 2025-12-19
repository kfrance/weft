"""DSPy-based prompt trainer for generating improved prompts.

This module uses DSPy to analyze training data and generate
candidate prompt sets for the Claude Code CLI workflow.
"""

from __future__ import annotations

from pathlib import Path

import dspy

from .judge_executor import configure_dspy_cache, get_openrouter_api_key
from .logging_config import get_logger
from .training_types import (
    CandidatePrompts,
    PromptSnapshot,
    SubagentDefinition,
    TrainingSample,
)

logger = get_logger(__name__)


class PromptTrainerError(Exception):
    """Raised when prompt training fails."""

    pass


# Instructions for the prompt trainer DSPy signature
PROMPT_TRAINER_INSTRUCTIONS = """You are an expert prompt engineer specializing in AI coding assistants. Your task is to analyze training data from real coding sessions and generate improved prompts.

## How Claude Code CLI Works

Claude Code is a CLI tool that executes coding tasks. When given a task:
1. It receives a main prompt that defines its behavior and workflow
2. It can invoke subagents by name - these are specialized helpers with their own prompts
3. It has access to tools: Read (files), Grep (search), Bash (commands), Edit (modify files), etc.
4. Subagents inherit tool access from the parent agent

The main prompt typically defines:
- The overall workflow (read plan, implement, review loop)
- When and how to invoke subagents
- Operating principles and constraints

Subagents are invoked by name and return their analysis to the main agent. Each subagent has:
- A name (e.g., "code-review-auditor")
- A focused responsibility
- Its own prompt defining how it analyzes and responds

## Key Principles for Effective AI Coding Prompts

### 1. Verification is Easier Than Creation

LLMs, like humans, are better at evaluating work than producing it. It's easier to review code and identify issues than to write correct code from scratch. This has important implications:

- Build feedback loops into the workflow. Don't just write code—write, then verify, then fix.
- Subagents are excellent for verification roles (reviewers, checkers, validators) because they bring fresh, focused context to the judgment task.
- Multiple verification passes from different angles catch more issues than a single review.
- The main agent benefits from verification feedback to converge on the best result.

When designing prompts, ensure the workflow includes explicit verification steps. A prompt that says "implement and move on" will produce worse results than one that says "implement, then invoke reviewers, then address their feedback."

### 2. Context Preservation Through Delegation

The more context an AI accumulates, the more likely it is to make mistakes or lose focus. Context is a finite, precious resource. Prompts should actively preserve context through strategic delegation:

**When to use subagents:**
- Verification/review tasks (fresh context = better judgment)
- Exploration/research (use the Explore tool—it returns summaries without polluting your context with all files read)
- Focused analysis from a specific angle
- Any task that benefits from isolated, dedicated attention
- When you need to read many files or do extensive analysis—delegate and get back conclusions

**When NOT to split across subagents:**
- Implementation tasks that must coordinate (shared interfaces, naming conventions, function signatures)
- Work where one piece depends on decisions made in another piece
- Anything where the agents would need to "talk to each other" to succeed

**The principle:** Subagents are excellent for parallel, independent work. They struggle with tightly-coupled, interdependent work that requires coordination.

**Think of it like:** A lead developer who delegates investigation and review work to team members. They do the deep dive and report back findings. The lead makes decisions based on their summaries, not by reading everything themselves. After receiving subagent results, you get their insights without inheriting their context burden.

Proactively delegate to subagents to keep your own context clean. Don't wait until you're overwhelmed—plan for delegation from the start.

## Your Analysis Process

1. **Understand the Human Feedback First**
   This is the most critical input. The human who ran the coding session tells you what went wrong or right. Common issues include:
   - Agent skipped over problems instead of fixing them
   - Agent didn't complete all the work
   - Agent made changes that weren't requested
   - Agent got stuck in loops
   - Agent produced good results (learn from successes too)

2. **Examine the Code Trace**
   The trace shows the actual conversation: what the agent did, what tools it called, what it produced. Look for:
   - Where did the agent deviate from ideal behavior?
   - What patterns led to the issues mentioned in human feedback?
   - What worked well that should be reinforced?

3. **Review Judge Results**
   Judges score specific aspects (code reuse, plan compliance, etc.). Low scores indicate areas needing improvement. High scores indicate successful patterns.

4. **Review Test Results**
   Compare before/after test results. Did tests pass? Did new tests get added? Were existing tests broken?

5. **Synthesize Improvements**
   Based on your analysis:
   - Identify specific prompt weaknesses that led to problems
   - Design targeted improvements to address those weaknesses
   - Preserve what's working well in the current prompts
   - Consider whether new subagents could help (e.g., a "completion-checker" if work often goes unfinished)

## Output Requirements

Generate a candidate prompt set that:
1. Addresses the specific issues found in training data
2. Preserves successful patterns from current prompts
3. Defines up to the specified max_subagents (only create what's needed)
4. Uses clear, actionable language
5. Includes specific examples where helpful

**CRITICAL: Output Format**

You MUST provide the subagents as a JSON array in the subagents_json field. Each subagent object must have these exact fields:
- "name": A descriptive kebab-case name (e.g., "test-validator")
- "description": A brief description of its responsibility
- "prompt": The COMPLETE, FULL markdown prompt content (NOT a summary or "[unchanged]")

**IMPORTANT**: For EVERY subagent you include, you MUST output the COMPLETE prompt text in the "prompt" field. Do NOT write "[unchanged]" or summaries - write the actual full prompt content that should be saved to the file. If keeping an existing subagent, copy its full prompt. If modifying, output the complete modified version.

Example subagents_json output:
```json
[
  {
    "name": "code-review-auditor",
    "description": "Reviews code changes for quality and compliance",
    "prompt": "# Code Review Auditor\\n\\nYou are a code reviewer. Your job is to analyze code changes and provide structured feedback.\\n\\n## Review Process\\n\\n1. Read all changed files\\n2. Check code quality and style\\n3. Verify adherence to project patterns\\n4. Identify potential bugs or issues\\n\\n## Output Format\\n\\nProvide a structured report with:\\n- Summary of changes\\n- Issues found (HIGH/MEDIUM/LOW)\\n- Recommendations"
  },
  {
    "name": "test-validator",
    "description": "Validates test coverage and correctness",
    "prompt": "# Test Validator\\n\\nYou validate test coverage and correctness.\\n\\n## Process\\n\\n1. Run the test suite\\n2. Check coverage for new code\\n3. Verify tests are meaningful\\n\\n## Report\\n\\n- Test results summary\\n- Coverage gaps\\n- Recommendations"
  }
]
```

If no subagents are needed, output an empty array: `[]`

In your analysis_summary, explain:
- What issues you identified from the training data
- What specific changes you made to address them
- Why you chose the subagents you defined"""


class PromptTrainerSignature(dspy.Signature):
    """Analyze training data to generate improved prompts."""

    training_samples_json: str = dspy.InputField(
        desc="JSON-encoded list of training samples with plan, trace, feedback, judges, tests"
    )
    current_prompts_json: str = dspy.InputField(
        desc="JSON-encoded current prompts including main prompt and subagents"
    )
    max_subagents: int = dspy.InputField(
        desc="Maximum number of subagents to generate"
    )

    main_prompt: str = dspy.OutputField(
        desc="Improved main prompt content (markdown)"
    )
    subagents: list[SubagentDefinition] = dspy.OutputField(
        desc="List of subagent definitions. Each must have name (kebab-case), description, and full prompt content."
    )
    analysis_summary: str = dspy.OutputField(
        desc="Summary of what issues were found and what improvements were made"
    )


def _serialize_training_samples(samples: list[TrainingSample]) -> str:
    """Serialize training samples to JSON string."""
    import json
    return json.dumps([s.model_dump() for s in samples], indent=2)


def _serialize_current_prompts(prompts: PromptSnapshot) -> str:
    """Serialize current prompts to JSON string."""
    import json
    return json.dumps(prompts.model_dump(), indent=2)


def run_prompt_trainer(
    training_samples: list[TrainingSample],
    current_prompts: PromptSnapshot,
    max_subagents: int,
    model: str,
    cache_dir: Path,
) -> tuple[CandidatePrompts, dict[str, int]]:
    """Run the prompt trainer and return candidate + token usage.

    Args:
        training_samples: List of training samples to analyze
        current_prompts: Current prompts (PromptSnapshot) to improve upon
        max_subagents: Maximum number of subagents to generate
        model: OpenRouter model tag (e.g., x-ai/grok-4.1-fast)
        cache_dir: Directory for DSPy cache

    Returns:
        Tuple of (CandidatePrompts, token_usage_dict)

    Raises:
        PromptTrainerError: If training fails
    """
    logger.info(
        "Running prompt trainer with %d samples, max %d subagents",
        len(training_samples),
        max_subagents,
    )

    try:
        # Get API key
        api_key = get_openrouter_api_key()

        # Configure DSPy cache
        configure_dspy_cache(cache_dir)

        # Create LM with specified OpenRouter model
        # Enable reasoning for models that support it (like Grok, GPT-5)
        # Disable cache - we want fresh responses for training
        lm = dspy.LM(
            f"openrouter/{model}",
            api_key=api_key,
            max_tokens=64000,
            temperature=1.0,
            extra_body={"reasoning": {"effort": "high"}},
            cache=False,
        )

        # Create signature with instructions
        InstructedSignature = PromptTrainerSignature.with_instructions(
            PROMPT_TRAINER_INSTRUCTIONS
        )

        # Serialize inputs
        training_samples_json = _serialize_training_samples(training_samples)
        current_prompts_json = _serialize_current_prompts(current_prompts)

        # Create predictor and run with JSONAdapter for structured output
        predictor = dspy.Predict(InstructedSignature)
        with dspy.context(lm=lm, adapter=dspy.JSONAdapter()):
            result = predictor(
                training_samples_json=training_samples_json,
                current_prompts_json=current_prompts_json,
                max_subagents=max_subagents,
            )

        # Parse outputs - subagents are now directly returned as list[SubagentDefinition]
        main_prompt = str(result.main_prompt)
        subagents = result.subagents if result.subagents else []
        # Ensure subagents are SubagentDefinition instances
        if subagents and not isinstance(subagents[0], SubagentDefinition):
            # Convert dicts to SubagentDefinition if needed
            subagents = [
                SubagentDefinition(**s) if isinstance(s, dict) else s
                for s in subagents
            ]
        analysis_summary = str(result.analysis_summary)

        # Ensure we don't exceed max_subagents
        if len(subagents) > max_subagents:
            logger.warning(
                "DSPy returned %d subagents, limiting to %d",
                len(subagents),
                max_subagents,
            )
            subagents = subagents[:max_subagents]

        candidate = CandidatePrompts(
            main_prompt=main_prompt,
            subagents=subagents,
            analysis_summary=analysis_summary,
        )

        # Get token usage from LM history
        token_usage = _extract_token_usage(lm)

        logger.info(
            "Prompt training complete. Generated %d subagents.",
            len(subagents),
        )

        return candidate, token_usage

    except Exception as exc:
        raise PromptTrainerError(f"Prompt training failed: {exc}") from exc


def _extract_token_usage(lm: dspy.LM) -> dict[str, int]:
    """Extract token usage from DSPy LM history.

    Args:
        lm: DSPy LM instance

    Returns:
        Dictionary with input_tokens, output_tokens, reasoning_tokens, total_tokens
    """
    try:
        history = lm.history
        if not history:
            return {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0}

        input_tokens = 0
        output_tokens = 0
        reasoning_tokens = 0

        for entry in history:
            if not hasattr(entry, "get"):
                continue

            usage = entry.get("usage")
            if not usage:
                continue

            # Get tokens - usage might be dict or object
            if hasattr(usage, "get"):
                # Dict-like access
                input_tokens += usage.get("prompt_tokens", 0) or 0
                output_tokens += usage.get("completion_tokens", 0) or 0
            else:
                # Object attribute access
                input_tokens += getattr(usage, "prompt_tokens", 0) or 0
                output_tokens += getattr(usage, "completion_tokens", 0) or 0

            # Get reasoning tokens from completion_tokens_details
            # This can be a dict or a wrapper object
            details = None
            if hasattr(usage, "get"):
                details = usage.get("completion_tokens_details")
            else:
                details = getattr(usage, "completion_tokens_details", None)

            if details:
                # Try dict access first, then attribute access
                if hasattr(details, "get"):
                    reasoning_tokens += details.get("reasoning_tokens", 0) or 0
                else:
                    reasoning_tokens += getattr(details, "reasoning_tokens", 0) or 0

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
    except Exception as exc:
        logger.debug("Failed to extract token usage: %s", exc)
        return {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0}
