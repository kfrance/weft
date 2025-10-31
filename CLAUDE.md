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
- **Create/edit plan**: `uv run lw_coder plan --text "plan idea"` or `uv run lw_coder plan <plan_path>`
- **Validate plan file**: `uv run lw_coder code <plan_path>`
- **Finalize plan**: `uv run lw_coder finalize <plan_path>`
- **Install bash completion**: `uv run lw_coder completion install` (see `docs/COMPLETION.md` for setup)

## Testing

Test files are located in `tests/` with pytest configuration in `pyproject.toml`:
- `pythonpath = ["src"]` allows importing from source without installation
- Tests cover plan validation logic and CLI behavior
- Use `conftest.py` for shared test fixtures and utilities
- **See `docs/BEST_PRACTICES.md` for testing guidelines** (pytest.fail vs skip, DSPy/LLM usage, etc.)