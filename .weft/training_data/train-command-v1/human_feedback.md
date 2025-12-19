# Human Feedback

## Plan Adherence Clarification
The tab completion worked fine. The plan mentioned it as work that would get done naturally during implementation, and it did. **Actual plan adherence score should be 1.00/1.00 (perfect).**

## Issues Identified

### 1. pytest.skip() Violates Testing Guidelines

The implementation used `pytest.skip()` when the OpenRouter API key was missing, directly contradicting CLAUDE.md guidance:

> Use pytest.fail() for missing dependencies, not pytest.skip()... This ensures developers are notified of missing dependencies rather than silently skipping tests.

**Expected behavior**: Tests should fail loudly with clear error messages when dependencies are missing, not silently skip. Environmental issues should surface as test failures so users can fix them.

**What happened**: The agent prioritized getting tests to pass over following documented testing standards.

### 2. Non-Existent OpenRouter Model Tag

The AI fabricated an OpenRouter model tag that doesn't exist. This is a common AI failure pattern (making up non-existent models or using very outdated ones).

**Resolution**: Updated CLAUDE.md with clearer guidance to prevent this in future implementations.

### 3. Incomplete Rename with Documented Inconsistency

When implementing the rename/migration from `optimized_prompts/` to `prompts/active/`, the agent updated only the explicit locations mentioned in the plan while leaving related locations with the old name. The system still worked, but naming was inconsistent.

**Most concerning**: The agent was *aware* of the inconsistency (evidenced by adding a comment documenting the discrepancy) but chose to document it rather than complete the rename properly.

**Expected behavior**: When a plan specifies renaming or migrating a concept (directory structure, variable name, API pattern, etc.), the agent should recognize the intent is for consistent application throughout the codebase. Documenting a known inconsistency is not a substitute for completing the work. If unsure whether a related location should be updated, ask rather than leave confusing naming that could mislead future developers.
