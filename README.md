# AI Coding Platform

This project hosts a self-optimizing multi-agent coding assistant that orchestrates coding runs through containerized executors. Prompts are evolved with DSPy and the GEPA optimizer to coordinate specialized subagents—coders, reviewers, testers—for higher quality and faster delivery without reinventing the toolchain.

## Highlights
- Uses DSPy signatures to define the core coder and supporting review/test agents
- Integrates with CLI-based coding platforms and runs each experiment in isolated Docker worktrees
- Feeds GEPA with task/eval logs to iteratively improve prompt scaffolding, delegation order, and runtime efficiency

## Setup and Authentication

### Droid CLI Authentication

The `lw_coder plan` command uses Factory AI's Droid CLI tool for interactive plan development. Before using this command, you must authenticate with Droid:

1. **One-time authentication**: Run `droid` once to login via your browser:
   ```bash
   droid
   ```
   This will open a browser window for authentication and save credentials to `~/.factory/auth.json`.

2. **Verify authentication**: Ensure the auth file exists:
   ```bash
   ls ~/.factory/auth.json
   ```

3. **Build the Docker image**: The plan command runs Droid in a Docker container for isolation:
   ```bash
   docker build -t lw_coder_droid:latest docker/droid/
   ```

The Docker container (based on Debian Slim with glibc support for droid binary) includes comprehensive development tools that Droid uses for code analysis and editing:
- **Search/Analysis**: `ripgrep`, `fd`, `grep`, `tree`, `findutils`
- **Text Processing**: `sed`, `gawk`, `jq`, `diffutils`
- **Build Tools**: `make`, `gcc`, `g++`, `build-essential`
- **Languages**: `python3`, `pip`, Node.js (from base image)
- **Editors**: `vim`, `nano`
- **Version Control**: `git`

Once authenticated, you can use the plan command:
```bash
# Interactive plan creation from an idea file
lw_coder plan idea.md

# Or provide the idea directly
lw_coder plan --text "Create a feature to export user metrics"
```

## Logging

The CLI uses Python's built-in `logging` module for all output:

- **Console logging**: All messages are logged to stderr with INFO level by default
- **File logging**: Daily rotating log files are stored at `~/.lw_coder/logs/lw_coder.log` with 30 days retention
- **Debug mode**: Use the `--debug` flag to enable DEBUG-level logging for more verbose output:
  ```bash
  lw_coder code <plan_path> --debug
  ```

Log files rotate daily at midnight and maintain 30 days of history automatically.
