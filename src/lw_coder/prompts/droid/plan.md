Here is an initial idea for a plan that needs to be refined and formalized:

{IDEA_TEXT}

Before you proceed, look for supporting docs such as `docs/BEST_PRACTICES.md`, `AGENTS.md`, and `CLAUDE.md` in your current working directory; keep any guidance you find in mind while planning.

Your task:
1. Examine the codebase in your current working directory to understand implementation context
2. Ask me clarifying questions ONE AT A TIME until you fully understand the requirements
3. Use the maintainability-reviewer and test-planner subagents in parallel:
   - maintainability-reviewer: Evaluates long-term maintenance concerns and technical debt
   - test-planner: Plans comprehensive test coverage (only adds tests when appropriate)
4. Ask me additional clarifying questions if needed based on the subagent reviews
5. Generate a complete plan file and save it to .lw_coder/tasks/<plan_id>.md with this structure:
   - YAML front matter with: plan_id (unique, 3-100 chars, alphanumeric/._- only), status (use "draft"), evaluation_notes (leave as empty list: [])
   - Markdown body with: Objectives, Requirements & Constraints, Work Items, Deliverables, Out of Scope sections
   - Include Unit Tests and Integration Tests sections:
     - Unit Tests: Fast tests with mocked dependencies and no external API calls
     - Integration Tests: Tests that make real external API calls and end-to-end validations

When you outline options or make suggestions, label them (e.g., Option 1, Option 2) so they are easy for me to reference.

When you're ready to write the final plan, let me know and we'll review it together before you save it.
