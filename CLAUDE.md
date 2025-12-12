# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Note**: For user-facing documentation on how to use lw_coder commands, see [README.md](README.md).

## Project Overview

This is an AI coding platform that orchestrates self-optimizing multi-agent coding assistants through containerized executors. The system uses DSPy signatures and the GEPA optimizer to coordinate specialized subagents (coders, reviewers, testers) for improved code quality and delivery efficiency.

## Development Commands

- **Install dependencies**: `uv sync`
- **Run tests**: `uv run pytest` (runs unit tests only by default via testpaths)
- **Run integration tests**: `uv run pytest tests/integration/` (makes real API calls)
- **Run all tests**: `uv run pytest tests/`
- **Run CLI**: `uv run lw_coder <command>`
- **Run specific test**: `uv run pytest tests/unit/test_<module>.py`

## Best Practices

### Testing Guidelines

- **Keep tests in the default run**: Avoid adding `pytest` markers whose only purpose is to skip tests because a dependency might be missing or the test could be slow. Keep those tests in the normal `pytest` run instead.

- **Use pytest.fail() for missing dependencies, not pytest.skip()**: When a test requires an external dependency that might not be available, use `pytest.fail()` with a clear error message instead of `pytest.skip()`. This ensures developers are notified of missing dependencies rather than silently skipping tests. Example: `pytest.fail("Required dependency 'droid' not found. Install it first with: pip install droid-cli")`.

- **Avoid mocking DSPy and LLMs**: Use real DSPy components with real LLM API calls in tests. Configure tests with actual LLM providers (e.g., OpenRouter) rather than creating mock LLM objects or stub responses. DSPy's caching ensures the first test run hits the API while subsequent runs retrieve cached results, making tests both fast and representative of production behavior.

- **Documentation is verified manually**: Avoid writing tests whose only purpose is to check for the existence of documentation pages or sections—keep effort focused on code behavior.

- **Don't test interactive commands**: Avoid writing automated tests that run `lw_coder code` or `lw_coder plan` commands, as these launch interactive Claude Code sessions. Instead, test the underlying modules and functions directly with mock data or controlled inputs.

### Test Organization

Tests are organized into two directories based on whether they make external API calls:

#### Directory Structure
- `tests/unit/` - Fast tests with mocked dependencies, no external API calls
- `tests/integration/` - Tests that make real external API calls (Claude SDK, OpenRouter, etc.)
- `tests/conftest.py` - Shared fixtures available to both directories

#### Test Categorization Rules
- **Unit Test**: Tests internal logic using mocks, no external network calls
  - Place in `tests/unit/`
- **Integration Test**: Makes real API calls to Claude SDK, OpenRouter, or other external services
  - Place in `tests/integration/`

#### Running Tests
- `pytest` - Runs unit tests only (default via testpaths)
- `pytest tests/integration/` - Runs integration tests
- `pytest tests/` - Runs all tests (unit + integration)

> **When to run integration tests**: Only run integration tests relevant to the code you changed. For example, if you modified `judge_executor.py`, run `pytest tests/integration/test_judge_executor_api.py` rather than all integration tests.

### DSPy and OpenRouter

- **Default model**: When writing code that uses DSPy with OpenRouter and no specific model is required, use `x-ai/grok-4.1-fast` as the default model tag.

### Test Optimization

- **Avoid redundant tests**: Before adding a new test, check if similar test coverage already exists. Duplicate tests increase maintenance burden without adding value.
- **Use parametrization for similar test cases**: When testing the same code path with different inputs, use `@pytest.mark.parametrize` instead of writing separate test functions. This keeps tests DRY and makes it easier to add new test cases.
- **Keep parametrized tests focused**: Each parametrized test should verify a single concern or behavior. Don't mix unrelated test scenarios in one parametrized function—this makes failures harder to diagnose.
- **Write descriptive test names**: Test function names should clearly document the behavior being tested. For parametrized tests, use the `ids` parameter to provide clear labels for each test case.
- **Integrate related assertions**: When multiple tests check different aspects of the same error condition, consider combining them into a single parametrized test that verifies all relevant properties (e.g., error type, message content, and paths).

## Architecture Decision Records (ADRs)

Architecture Decision Records document significant architectural choices, trade-offs, and technical decisions. They provide context for future maintainers and help evaluate whether past decisions still make sense.

### When to Create an ADR

Create an ADR for:
- **Significant architectural choices**: Design patterns, system structure, technology selection
- **External dependencies on undocumented APIs**: Relying on internal implementation details of third-party tools
- **Trade-off decisions**: Choosing between competing approaches with clear pros/cons
- **Breaking changes**: Changes that affect how components interact or how the system is used
- **Security decisions**: Authentication, authorization, data handling choices
- **Performance trade-offs**: Accepting reduced performance for other benefits (or vice versa)

Do NOT create ADRs for:
- Routine code changes or refactoring
- Bug fixes (unless they reveal a design flaw worth documenting)
- Trivial dependency additions
- Configuration changes

### ADR Format and Location

- **Location**: `docs/adr/NNN-title-with-dashes.md`
- **Numbering**: Sequential starting from 001
- **Template**:

```markdown
# ADR NNN: Title

## Status
[Proposed | Accepted | Deprecated | Superseded by ADR-XXX]

## Context
What is the issue that we're seeing? What factors are influencing this decision?

## Decision
What decision have we made? Be specific and concrete.

## Consequences
What becomes easier or harder as a result? Include positive, negative, and neutral consequences.

## Alternatives Considered
What other options were evaluated? Why were they rejected?

## References
Links to related documents, tickets, or discussions.
```

### Example ADR

See `docs/adr/001-trace-capture-claude-dependency.md` for a complete example documenting the decision to rely on Claude Code's undocumented internal file format for conversation trace capture.
