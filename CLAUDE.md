# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI coding platform that orchestrates self-optimizing multi-agent coding assistants through containerized executors. The system uses DSPy signatures and the GEPA optimizer to coordinate specialized subagents (coders, reviewers, testers) for improved code quality and delivery efficiency.

## Commands

### Development Commands
- **Install dependencies**: `uv sync`
- **Run tests**: `uv run pytest`
- **Run CLI**: `uv run lw_coder <command>`
- **Run specific test**: `uv run pytest tests/test_<module>.py`

### CLI Usage
- **Validate plan file**: `uv run lw_coder code <plan_path>`

## Architecture

### Core Components

**Plan Validation System** (`src/lw_coder/plan_validator.py`):
- Validates Markdown files with YAML front matter containing coding task metadata
- Required fields: `git_sha` (40-char hex commit SHA), `evaluation_notes` (list of strings)
- Ensures plan files exist within Git repositories and reference valid commits
- Returns `PlanMetadata` objects with parsed plan text, Git SHA, evaluation notes, and paths

**CLI Interface** (`src/lw_coder/cli.py`):
- Single command `code <plan_path>` that validates plan files using docopt
- Entry point defined in `pyproject.toml` as `lw_coder = "lw_coder.cli:main"`

**Plan File Format**:
Plans are Markdown files with YAML front matter:
```markdown
---
git_sha: "40-character-hex-sha"
evaluation_notes:
  - "Question about implementation requirement"
  - "Success criteria or test expectation"
---

# Plan content in Markdown
Task description and implementation details...
```

### Multi-Agent Workflow
The platform integrates with coding agents (Claude Code CLI, Goose) as execution engines:
- DSPy signatures define core coder and specialized subagents (code-reviewer, test-writer, plan-adherence-checker)
- GEPA optimizer evolves prompts and agent orchestration patterns
- All executions run in isolated Docker containers with Git worktrees for reproducible environments
- Agent registry provides context about available subagents and their capabilities

### Key Design Patterns
- Git worktrees created from specific SHAs ensure consistent codebase states
- Docker isolation prevents system interference during coding runs
- GEPA training loop uses task/evaluation logs to improve prompt scaffolding and delegation patterns
- Evaluation metrics combine automated testing, human-defined criteria, and execution time optimization

## Testing

Test files are located in `tests/` with pytest configuration in `pyproject.toml`:
- `pythonpath = ["src"]` allows importing from source without installation
- Tests cover plan validation logic and CLI behavior
- Use `conftest.py` for shared test fixtures and utilities