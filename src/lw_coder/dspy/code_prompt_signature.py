"""DSPy signature for generating coding prompts from plan metadata.

This module defines the signature for generating the main coding prompt
and two subagent prompts (code review auditor and plan alignment checker)
from plan metadata using DSPy.
"""

import dspy


class CodePromptSignature(dspy.Signature):
    """Generate three specialized prompts for implementing a coding plan.

    You will receive the complete plan text and must generate three complete, detailed prompts:

    1. MAIN PROMPT: Instructions for the primary coding agent that includes:
       - IMPORTANT: Directly embed the COMPLETE plan text that was provided as input (do NOT use placeholders like {plan_text} - copy the actual plan text verbatim into the prompt)
       - Required workflow: read plan, implement, run code-review-auditor and plan-alignment-checker subagents IN PARALLEL, address feedback, run tests, summarize
       - Important guidelines: follow plan exactly, no test cheating, document assumptions, consult both subagents, run subagents in parallel when possible
       - Success criteria: all requirements implemented, tests passing, no critical subagent issues, evaluation criteria addressed

    2. REVIEW PROMPT: Instructions for the code review auditor subagent that includes:
       - Role: Review code for quality, correctness, documentation, security
       - Special focus on testing: verify no test cheating, proper mocking of dependencies/API calls/I/O, tests appropriately validate functionality, test independence
       - Guidelines: Focus on significant issues, distinguish critical vs suggestions, provide specific feedback with locations, be constructive
       - Output format: Critical Issues, Suggestions, Positive Notes sections
       - What NOT to report: Style preferences, trivial naming, performance optimizations, out-of-scope issues

    3. ALIGNMENT PROMPT: Instructions for the plan alignment checker subagent that includes:
       - Role: Verify implementation covers all requirements, stays in scope, addresses evaluation criteria, follows constraints
       - Guidelines: Cross-reference requirements, flag missing items, flag scope creep, check tests validate requirements
       - Output format: Requirements Coverage, Scope Verification, Evaluation Criteria Check, Missing Items sections
       - What NOT to flag: Code quality (reviewer's job), unspecified details, testing strategies beyond plan

    Each prompt must be comprehensive and self-contained with all necessary instructions.
    """

    # Input fields
    plan_text: str = dspy.InputField(desc="Full text of the plan in Markdown format including all metadata, evaluation criteria, and implementation details")

    # Output fields
    main_prompt: str = dspy.OutputField(
        desc="Complete prompt for the main coding agent including task, workflow, and guidelines"
    )
    review_prompt: str = dspy.OutputField(
        desc="Prompt for the code review auditor subagent defining its role and review criteria"
    )
    alignment_prompt: str = dspy.OutputField(
        desc="Prompt for the plan alignment checker subagent defining its verification role"
    )


