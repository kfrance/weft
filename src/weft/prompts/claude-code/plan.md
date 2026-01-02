Here is an initial idea for a plan that needs to be refined and formalized:

{IDEA_TEXT}

Before you proceed, look for supporting docs such as `AGENTS.md` and `CLAUDE.md` in your current working directory; keep any guidance you find in mind while planning.

Your task:
1. Examine the codebase in your current working directory to understand implementation context
2. Ask me clarifying questions ONE AT A TIME until you fully understand the requirements
   - Focus on understanding what needs to be built and why
   - Clarify scope, constraints, and expected behavior
3. Once requirements are clear, invoke the `test-discovery` subagent to analyze existing tests relevant to the proposed changes
4. Ask any testing-related questions based on the discovery results (e.g., "Should we extend existing test X or create new tests?")
5. Draft your plan and use the evaluation subagents in parallel to review it:
   - maintainability-reviewer: Evaluates long-term maintenance concerns and technical debt
   - test-reviewer: Reviews the plan's test coverage and identifies gaps
6. Ask me additional clarifying questions if needed based on the subagent reviews
7. Generate a complete plan file and save it to .weft/tasks/<plan_id>.md with this structure:
   - YAML front matter with: plan_id (unique, 3-100 chars, alphanumeric/._- only), status (use "draft"), evaluation_notes (leave as empty list: [])
   - Markdown body with: Objectives, Requirements & Constraints, Work Items, Deliverables, Out of Scope sections
   - Work Items section must include:
     - Unit Tests: Fast tests with mocked dependencies and no external API calls
     - Integration Tests: Tests that make real external API calls (identified by test-discovery as relevant to the changes)
   - Integration tests listed in the plan are required to pass for the task to be complete

## Using test-discovery (Step 3)

The `test-discovery` subagent helps you understand the existing test landscape BEFORE finalizing your plan. Invoke it after requirements are clear (step 3) when:
- You understand the scope of changes (which files/modules will be affected)
- You're ready to ask informed questions about testing approach
- You need to know what test patterns and fixtures already exist

When invoking test-discovery, provide context about:
- The proposed changes and affected modules
- The types of functionality being added or modified
- Any specific areas where test coverage concerns exist

Example invocation context:
"The plan involves adding a new validation function to the plan_command module and modifying the existing file copier. Affected files include plan_command.py and plan_file_copier.py."

test-discovery will report:
- Existing integration tests that must pass (these go in the plan's Work Items)
- Existing unit tests that may need modification
- Reusable fixtures and test patterns
- Coverage gaps to consider

## Using Evaluation Subagents (Step 5)

After drafting your plan, invoke these subagents in parallel:
- **maintainability-reviewer**: Reviews architectural decisions, code organization, and long-term maintenance implications
- **test-reviewer**: Reviews the plan's test coverage, identifies gaps, and flags problematic tests

When invoking test-reviewer, provide:
- A summary of the proposed changes (what functionality is being added/modified)
- The draft Unit Tests section from your plan
- The draft Integration Tests section from your plan
- The list of required integration tests identified by test-discovery (so the reviewer can verify they're included)

When you outline options or make suggestions, label them (e.g., Option 1, Option 2) so they are easy for me to reference.

Focus on *what* needs to be built, not *how* to implement it. Avoid detailed code implementations—leave those to the developer. Code snippets are appropriate only when they define interfaces, schemas, or data layouts that constrain the design.

When you're ready to write the final plan, let me know and we'll review it together before you save it.
