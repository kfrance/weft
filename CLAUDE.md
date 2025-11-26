# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI coding platform that orchestrates self-optimizing multi-agent coding assistants through containerized executors. The system uses DSPy signatures and the GEPA optimizer to coordinate specialized subagents (coders, reviewers, testers) for improved code quality and delivery efficiency.

## Commands

### Development Commands
- **Install dependencies**: `uv sync`
- **Run tests**: `uv run pytest`
- **Run integration tests**: `uv run pytest -m integration` (makes real SDK calls)
- **Run all tests**: `uv run pytest -m ''`
- **Run CLI**: `uv run lw_coder <command>`
- **Run specific test**: `uv run pytest tests/test_<module>.py`

### CLI Usage
- **Initialize project**: `uv run lw_coder init` - Initialize lw_coder in git repository with baseline templates
- **Create/edit plan**: `uv run lw_coder plan --text "plan idea"` or `uv run lw_coder plan <plan_path>`
- **Validate plan file**: `uv run lw_coder code <plan_path>`
- **Quick fix mode**: `uv run lw_coder code --text "description"` - Bypasses interactive planning for simple fixes
- **Evaluate code changes**: `uv run lw_coder eval <plan_id>` - Run LLM judges on implemented changes
- **Finalize plan**: `uv run lw_coder finalize <plan_path>`
- **Install bash completion**: `uv run lw_coder completion install` (see `docs/COMPLETION.md` for setup)

#### Init Command
The `init` command bootstraps a new project with frozen baseline templates:
- **Command**: `uv run lw_coder init`
- **What it creates**:
  - `.lw_coder/judges/` - LLM judges for code evaluation (code-reuse, plan-compliance)
  - `.lw_coder/optimized_prompts/` - Optimized prompts for Claude Code CLI
  - `.lw_coder/VERSION` - Template version tracking file
- **Flags**:
  - `--force` - Reinitialize when `.lw_coder/` already exists (with confirmation)
  - `--yes` - Skip interactive prompts (for CI/CD automation)
- **Examples**:
  - `uv run lw_coder init` - Initialize new project
  - `uv run lw_coder init --force` - Reinitialize with prompts
  - `uv run lw_coder init --force --yes` - Reinitialize without prompts (CI/CD)

#### Quick Fix Mode
The `--text` flag allows you to quickly execute simple fixes without creating a full plan file:
- Creates plan files with pattern `quick-fix-YYYY.MM-NNN.md` in `.lw_coder/tasks/`
- Counter (NNN) resets monthly and increments from 001-999
- On overflow (>999 fixes/month), automatically falls back to timestamp format: `quick-fix-YYYY.MM.DD-HHMMSS`
- Works with `--tool` (claude-code, droid) and `--model` (sonnet, opus, haiku) flags
- Examples:
  - `uv run lw_coder code --text "Fix login button styling"`
  - `uv run lw_coder code --text "Update API endpoint" --tool droid`
  - `uv run lw_coder code --text "Refactor auth module" --model opus`

#### Eval Command
The `eval` command evaluates code changes using LLM judges:
- **Command**: `uv run lw_coder eval <plan_id>`
- **When to use**: After running `lw_coder code` to evaluate the implementation
- **What it does**: Runs all judges in `.lw_coder/judges/` against the code changes
- **Output**: Shows each judge's score (0.0-1.0) and detailed feedback
- **Judges included**:
  - `code-reuse`: Evaluates whether code properly reuses existing functionality
  - `plan-compliance`: Verifies implementation matches plan requirements
- **Requirements**: `OPENROUTER_API_KEY` in `~/.lw_coder/.env`

## Testing

Test files are located in `tests/` with pytest configuration in `pyproject.toml`:
- `pythonpath = ["src"]` allows importing from source without installation
- Tests cover plan validation logic and CLI behavior
- Use `conftest.py` for shared test fixtures and utilities
- **See `docs/BEST_PRACTICES.md` for testing guidelines** (pytest.fail vs skip, DSPy/LLM usage, etc.)