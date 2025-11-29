# AI Coding Platform

This project hosts a self-optimizing multi-agent coding assistant that orchestrates coding runs on your Linux development environment. Prompts are evolved with DSPy and the GEPA optimizer to coordinate specialized subagents—coders, reviewers, testers—for higher quality and faster delivery without reinventing the toolchain.

**Supported Platforms**: Linux (Ubuntu 20.04+, Debian 11+, Fedora, etc.)
**Not Supported**: macOS, Windows (coming soon with Claude Code CLI integration)

## Highlights
- Uses DSPy signatures to define the core coder and supporting review/test agents
- Runs directly on Linux hosts with Git worktrees for isolated code experiments
- Feeds GEPA with task/eval logs to iteratively improve prompt scaffolding, delegation order, and runtime efficiency

## Requirements

- Python 3.10+
- Git
- `rsync` command (for DSPy cache synchronization in worktrees)
  - Linux/macOS: Usually pre-installed
  - Windows: Install via WSL, Cygwin, or `choco install rsync`
  - Verify installation: `rsync --version`

If `rsync` is not available, commands will run but cache synchronization will be disabled.

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

## Quick Start

Get started with lw_coder in a new project:

1. **Install lw_coder** (see Installation above)
2. **Configure credentials** in `~/.lw_coder/.env` (see Configuration below)
3. **Initialize your project**:
   ```bash
   cd your-project
   lw_coder init
   ```
4. **Create a plan**:
   ```bash
   lw_coder plan --text "your feature idea"
   ```
5. **Implement it**:
   ```bash
   lw_coder code <plan_id>
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

## Init Command

The `lw_coder init` command initializes a new project with frozen baseline templates. This is the recommended first step when adopting lw_coder in a new repository.

### What It Does

Running `lw_coder init` creates a `.lw_coder/` directory at your repository root containing:

- **Judges** (`.lw_coder/judges/`): LLM judges for evaluating code changes
  - `code-reuse.md`: Evaluates proper reuse of existing functionality
  - `plan-compliance.md`: Verifies implementation matches plan requirements
- **Optimized Prompts** (`.lw_coder/optimized_prompts/`): Pre-optimized prompts for Claude Code CLI
  - Includes prompts for sonnet, opus, and haiku models
- **VERSION**: Tracks template version and file hashes for customization detection

### Basic Usage

```bash
# Initialize in a new project
cd your-project
lw_coder init

# Reinitialize with prompts (when .lw_coder already exists)
lw_coder init --force

# Reinitialize without prompts (CI/CD automation)
lw_coder init --force --yes
```

### Customization Detection

When reinitializing with `--force`, lw_coder detects which files you've customized by comparing current file hashes against the VERSION file. You'll see warnings before overwriting customized files:

```
WARNING: 1 judges have been customized from baseline:
  - judges/code-reuse.md
Overwrite existing judges? (y/n):
```

### Parameters

- `--force`: Allow initialization when `.lw_coder/` already exists (asks for confirmation)
- `--yes`: Skip interactive prompts and overwrite everything (for CI/CD)

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

## Eval Command

The `lw_coder eval` command evaluates code changes using LLM judges. After implementing a plan with the `code` command, use `eval` to get automated feedback on code quality and plan compliance.

### Basic Usage

```bash
# Evaluate changes for a plan
lw_coder eval <plan_id>

# Examples
lw_coder eval my-feature
lw_coder eval quick-fix-2025.01-001
```

### How It Works

The eval command:
1. Discovers all judge files in `.lw_coder/judges/` directory
2. Gathers the plan content and git changes from the worktree
3. Executes all judges in parallel using DSPy and OpenRouter
4. Displays each judge's score (0.0-1.0) and detailed feedback
5. Shows an overall weighted score combining all judge results

### Built-in Judges

Two judges are included by default:

#### Code Reuse Judge
- **Weight**: 0.4
- **Purpose**: Evaluates whether code properly reuses existing functionality
- **Checks**: Looks for reimplemented logic that should have called existing functions
- **File**: `.lw_coder/judges/code-reuse.md`

#### Plan Compliance Judge
- **Weight**: 0.6
- **Purpose**: Verifies implementation matches plan requirements
- **Checks**: Ensures all requirements are implemented and no out-of-scope additions
- **File**: `.lw_coder/judges/plan-compliance.md`

### Example Output

```
================================================================================
Evaluation Results for: my-feature
Worktree: .lw_coder/worktrees/my-feature
================================================================================

Judge: code-reuse
Weight: 0.40
Score: 0.85 / 1.00
--------------------------------------------------------------------------------
Feedback:
Good code reuse overall. The implementation properly uses existing utility
functions in most cases. Minor issue: function validate_input() at line 42
reimplements logic similar to validation.check_format()...

================================================================================

Judge: plan-compliance
Weight: 0.60
Score: 0.92 / 1.00
--------------------------------------------------------------------------------
Feedback:
Excellent plan compliance. All requirements from the plan are implemented:
✓ User authentication module
✓ Session management
✓ Password reset flow...

================================================================================

Overall Weighted Score: 0.89 / 1.00
================================================================================
```

### Requirements

- `OPENROUTER_API_KEY` must be set in `~/.lw_coder/.env`
- Worktree must exist (run `lw_coder code <plan_id>` first)
- At least one judge file in `.lw_coder/judges/`

### When to Use

- **During development**: Run eval while coding to get early feedback
- **Before finalize**: Run eval before `lw_coder finalize` to ensure quality
- **After changes**: Run eval after making fixes to verify improvements
- **Code review**: Use eval output to supplement manual code review

### Creating Custom Judges

Judges are markdown files with YAML frontmatter. Create new judges in `.lw_coder/judges/`:

```markdown
---
weight: 0.5
model: x-ai/grok-4.1-fast
---

# Your Judge Name

You are evaluating code changes for [specific criteria].

## Evaluation Criteria
- [Criterion 1]
- [Criterion 2]

## Scoring Guidelines
**Score: 0.9-1.0** - [Description]
**Score: 0.7-0.8** - [Description]
...
```

Required frontmatter fields:
- `weight`: Float between 0.0 and 1.0 for weighted scoring
- `model`: OpenRouter model tag (e.g., "x-ai/grok-4.1-fast")

The judge instructions in the markdown body are loaded dynamically into DSPy using the `.with_instructions()` pattern.

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
