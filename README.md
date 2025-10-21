# AI Coding Platform

This project hosts a self-optimizing multi-agent coding assistant that orchestrates coding runs on your Linux development environment. Prompts are evolved with DSPy and the GEPA optimizer to coordinate specialized subagents—coders, reviewers, testers—for higher quality and faster delivery without reinventing the toolchain.

**Supported Platforms**: Linux (Ubuntu 20.04+, Debian 11+, Fedora, etc.)
**Not Supported**: macOS, Windows (coming soon with Claude Code CLI integration)

## Highlights
- Uses DSPy signatures to define the core coder and supporting review/test agents
- Runs directly on Linux hosts with Git worktrees for isolated code experiments
- Feeds GEPA with task/eval logs to iteratively improve prompt scaffolding, delegation order, and runtime efficiency

## Installation

To install `lw_coder` as a system-wide command that works from any directory:

```bash
cd /home/kfrance/lw_coder
uv tool install --force .
```

The `--force` flag ensures the tool is reinstalled with all current dependencies. After installation, you can run `lw_coder` from anywhere.

For an editable install (where code changes are immediately reflected without reinstalling):

```bash
uv tool install --force --editable .
```

## Setup and Authentication

### Configuration

lw_coder loads credentials from `~/.lw_coder/.env` in your home directory:

1. Create the configuration directory:
   ```bash
   mkdir -p ~/.lw_coder
   ```

2. Create the environment file with your API credentials:
   ```bash
   cat > ~/.lw_coder/.env << EOF
   OPENROUTER_API_KEY=your-api-key-here
   EOF
   ```

See [docs/code-config.md](docs/code-config.md) for detailed configuration options.

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

Once authenticated, you can use the plan command directly (no Docker setup needed):
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
