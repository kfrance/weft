# AI Coding Platform

This project hosts a self-optimizing multi-agent coding assistant that orchestrates coding runs through containerized executors. Prompts are evolved with DSPy and the GEPA optimizer to coordinate specialized subagents—coders, reviewers, testers—for higher quality and faster delivery without reinventing the toolchain.

## Highlights
- Uses DSPy signatures to define the core coder and supporting review/test agents
- Integrates with CLI-based coding platforms and runs each experiment in isolated Docker worktrees
- Feeds GEPA with task/eval logs to iteratively improve prompt scaffolding, delegation order, and runtime efficiency

## Logging

The CLI uses Python's built-in `logging` module for all output:

- **Console logging**: All messages are logged to stderr with INFO level by default
- **File logging**: Daily rotating log files are stored at `~/.lw_coder/logs/lw_coder.log` with 30 days retention
- **Debug mode**: Use the `--debug` flag to enable DEBUG-level logging for more verbose output:
  ```bash
  lw_coder code <plan_path> --debug
  ```

Log files rotate daily at midnight and maintain 30 days of history automatically.
