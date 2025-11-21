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

### Plan Command Setup

The `lw_coder plan` command supports multiple AI coding assistants for interactive plan development. By default, it uses **Claude Code CLI**, but you can also use Factory AI's Droid CLI.

#### Using Claude Code CLI (Default)

Claude Code CLI is the default executor and handles authentication automatically. No setup required.

```bash
# Interactive plan creation from an idea file
lw_coder plan idea.md

# Or provide the idea directly
lw_coder plan --text "Create a feature to export user metrics"
```

#### Using Droid CLI (Optional)

To use Droid instead of Claude Code CLI, add the `--tool droid` option:

```bash
lw_coder plan idea.md --tool droid
lw_coder plan --text "Create a feature" --tool droid
```

Before using Droid, you must authenticate once:

1. **One-time authentication**: Run `droid` once to login via your browser:
   ```bash
   droid
   ```
   This will open a browser window for authentication and save credentials to `~/.factory/auth.json`.

2. **Verify authentication**: Ensure the auth file exists:
   ```bash
   ls ~/.factory/auth.json
   ```

After authenticating, you can use Droid with `--tool droid` as shown above.

## Code Command

The `lw_coder code` command executes plans created with the `plan` command. It validates the plan, sets up a worktree, and runs the selected coding tool to implement the plan.

### Basic Usage

```bash
# Run with defaults (Claude Code CLI with sonnet model)
lw_coder code plan.md

# Use Droid instead of Claude Code CLI
lw_coder code plan.md --tool droid

# Use Claude Code CLI with a specific model
lw_coder code plan.md --model opus
lw_coder code plan.md --tool claude-code --model haiku
```

### Parameters

- `<plan_path>`: Path to the plan file to execute (required)
- `--tool <tool>`: Coding tool to use. Options: `claude-code` (default), `droid`
- `--model <model>`: Model variant for Claude Code CLI. Options: `sonnet` (default), `opus`, `haiku`
  - Note: The `--model` parameter only works with `claude-code` and cannot be used with `droid`
- `--debug`: Enable debug-level logging for troubleshooting

### Examples

```bash
# Execute a plan with default settings
lw_coder code .lw_coder/tasks/my-feature.md

# Use Droid for execution
lw_coder code .lw_coder/tasks/my-feature.md --tool droid

# Use Claude Code CLI with opus model
lw_coder code .lw_coder/tasks/my-feature.md --model opus

# Enable debug logging
lw_coder code .lw_coder/tasks/my-feature.md --debug
```

## Recover Plan Command

The `lw_coder recover-plan` command provides backup and recovery of plan files. Plan files are automatically backed up when created or modified during the `plan` command, and backups are automatically cleaned up when plans are finalized.

### What are Plan Backups?

- **Automatic creation**: Backups are created automatically when you run `lw_coder plan`
- **Durable storage**: Backups are stored as git orphan commits at `refs/plan-backups/<plan_id>`
- **Automatic cleanup**: Backups are automatically deleted when you run `lw_coder finalize`
- **Recovery**: Backups allow you to restore accidentally deleted plan files

### Basic Usage

```bash
# List all backed-up plans
lw_coder recover-plan

# Recover a specific plan
lw_coder recover-plan my-feature

# Force overwrite if plan file already exists
lw_coder recover-plan my-feature --force
```

### Parameters

- `<plan_id>`: Optional plan identifier to recover. If omitted, lists all backups
- `--force`: Overwrite existing plan file during recovery

### Examples

#### Listing All Backups

```bash
lw_coder recover-plan
```

Output:
```
Found 2 backed-up plan(s):

Plan ID          Backup Date          Status
----------------------------------------------------
feature-auth     2025-01-15 14:23:45  exists
feature-export   2025-01-14 09:12:30  missing

Use 'lw_coder recover-plan <plan_id>' to restore a plan.
```

The status column shows:
- `exists`: Plan file currently exists in `.lw_coder/tasks/`
- `missing`: Plan file has been deleted and can be recovered

#### Recovering a Plan

```bash
# Recover a deleted plan
lw_coder recover-plan feature-export

# Output:
# Successfully recovered plan to: /path/to/repo/.lw_coder/tasks/feature-export.md
# You can now continue working with: lw_coder code feature-export
```

#### Force Overwrite

If a plan file already exists and you want to restore it from backup:

```bash
lw_coder recover-plan my-feature --force
```

### Tab Completion

The recover-plan command supports tab completion for plan IDs. Press TAB after typing `lw_coder recover-plan` to see available backups with their status:

```bash
lw_coder recover-plan <TAB>
# Shows: feature-auth (exists)  feature-export (missing)
```

### Important: Backup Timing

**Backups are created when you run `lw_coder plan`, not when you manually edit files.** The backup timestamp shown in the listing indicates when the backup was created, which may be older than your current plan file if you've manually edited it since running the `plan` command.

⚠️ **Warning**: If you've manually edited a plan file after running `lw_coder plan`, recovering from backup with `--force` will overwrite your manual changes with the older backed-up version. Always verify the backup date before using `--force` to ensure you're not losing recent edits.

### Common Use Cases

1. **Accidentally deleted plan**: If you delete a plan file before finalizing it, use `recover-plan` to restore it
2. **View backup history**: Use `recover-plan` without arguments to see which plans have backups
3. **Revert plan changes**: If you modified a plan and want to go back to the backed-up version, use `--force` to overwrite

## Logging

The CLI uses Python's built-in `logging` module for all output:

- **Console logging**: All messages are logged to stderr with INFO level by default
- **File logging**: Daily rotating log files are stored at `~/.lw_coder/logs/lw_coder.log` with 30 days retention
- **Debug mode**: Use the `--debug` flag to enable DEBUG-level logging for more verbose output:
  ```bash
  lw_coder code <plan_path> --debug
  ```

Log files rotate daily at midnight and maintain 30 days of history automatically.
