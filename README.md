# Weft

In weaving, the **weft** is the thread that passes back and forth through the warp, binding separate threads into fabric. Without weft, you just have parallel strings. The weft is what creates something whole.

**Weft** is a self-optimizing coding assistant that weaves specialized AI agents—coders, reviewers, testers—into production-ready software. Like the weft thread in a loom, it's the cross-cutting intelligence that binds individual capabilities into something useful.

**Supported Platforms**: Linux

## Highlights
- Orchestrates specialized AI agents for coding, review, and testing
- Runs directly on Linux hosts with Git worktrees for isolated code experiments
- Collects evaluation data to iteratively improve prompts and agent coordination

## Requirements

- **uv** (Python package installer and manager)
  - Install with: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - uv will automatically manage Python 3.12+ installation
- **Git** (2.7.0 or later for worktree support)
  - Verify version: `git --version`
- **Claude Code CLI**
  - Website: [claude.ai/code](https://claude.ai/code)
  - Install with: `curl -fsSL https://claude.ai/install.sh | bash`

## Installation

To install `weft` as a system-wide command that works from any directory:

```bash
# Clone the repository (if you haven't already)
git clone https://github.com/kfrance/weft.git
cd weft

# Install the tool
uv tool install --force .
```

The `--force` flag ensures the tool is reinstalled with all current dependencies. After installation, you can run `weft` from anywhere.

For an editable install (where code changes are immediately reflected without reinstalling):

```bash
uv tool install --force --editable .
```

## Tab Completion

Weft supports intelligent tab completion for all commands, making it faster to work with plans, files, and options.

### Enabling Tab Completion

**For Bash:**

```bash
weft completion install
```

This automatically configures tab completion by creating `~/.bash_completion.d/weft` and updating your `~/.bashrc`.

**For Zsh:**

```bash
# Add to ~/.zshrc
autoload -U bashcompinit
bashcompinit
eval "$(register-python-argcomplete weft)"
```

### What Gets Completed

- **Commands**: `weft <TAB>` shows all available commands
- **Plan IDs**: Commands like `code`, `eval`, `abandon`, and `recover-plan` complete plan identifiers
- **File paths**: Arguments expecting files complete from your filesystem
- **Options**: `--<TAB>` shows available flags for each command
- **Model names**: `--model <TAB>` completes with `sonnet`, `opus`, `haiku`

### Examples

```bash
# Complete command names
weft <TAB>
# Shows: code  eval  plan  init  train  abandon  recover-plan  ...

# Complete plan IDs
weft code <TAB>
# Shows plan files from .weft/tasks/

# Complete with status information
weft recover-plan <TAB>
# Shows: feature-auth (exists)  feature-export (missing)

# Complete model options
weft code plan.md --model <TAB>
# Shows: sonnet  opus  haiku
```

## Quick Start

Get started with weft in a new project:

1. **Install weft** (see Installation above)
2. **Configure credentials** in `~/.weft/.env` (see Configuration below)
3. **Initialize your project**:
   ```bash
   cd your-project
   weft init
   ```
4. **Create a plan**:
   ```bash
   weft plan --text "your feature idea"
   ```
5. **Implement it**:
   ```bash
   weft code <plan_id>
   ```
6. **Merge to main**:
   ```bash
   weft finalize <plan_id>
   ```

## Workflow: Plan → Code → Finalize

Weft uses a three-stage workflow for implementing features:

1. **Plan** (`weft plan`): Interactively create an implementation plan with Claude. The plan is saved to `.weft/tasks/<plan_id>.md` and defines what will be built.

2. **Code** (`weft code`): Execute the plan in an isolated Git worktree. Claude implements the plan, making changes in the worktree without affecting your main branch.

3. **Finalize** (`weft finalize`): Commit, rebase onto main, and merge. This completes the workflow by integrating your changes and cleaning up the worktree.

Each stage is independent—you can pause between stages, review changes, or abandon a plan at any point.

## Commands Overview

Weft provides a suite of commands for the complete development lifecycle:

| Command | Purpose | Details |
|---------|---------|---------|
| `plan` | Interactively create implementation plans | [Plan Command](#plan-command-setup) |
| `code` | Execute a plan using Claude Code CLI | [Code Command](#code-command) |
| `judge` | Quick judge feedback while coding | [Judge Command](#judge-command) |
| `finalize` | Commit, rebase, and merge completed plan | [Finalize Command](#finalize-command) |
| `eval` | Evaluate code quality and create training data | [Eval Command](#eval-command) |
| `train` | Generate improved prompt candidates from training data | [Train Command](#train-command) |
| `init` | Initialize weft in a new project | [Init Command](#init-command) |
| `abandon` | Clean up failed or unwanted plans | [Abandon Command](#abandon-command) |
| `recover-plan` | Restore backed-up plan files | [Recover Plan Command](#recover-plan-command) |
| `completion` | Install shell tab completion | [Tab Completion](#tab-completion) |

## Setup and Authentication

### Prerequisites

Before configuring weft, ensure you have:

1. **Claude Code CLI installed** (see [Requirements](#requirements))
2. **Authenticated with Claude Code CLI**:
   ```bash
   # Run claude to authenticate (opens browser for login)
   claude
   ```
   This creates your Claude authentication in `~/.claude/` which weft will use.

### Weft Configuration

weft also requires OpenRouter API credentials for judges and training. Configure them in `~/.weft/.env`:

1. Create the configuration directory:
   ```bash
   mkdir -p ~/.weft
   ```

2. Create the environment file with your API credentials:
   ```bash
   cat > ~/.weft/.env << EOF
   OPENROUTER_API_KEY=your-api-key-here

   # Optional: Default model for DSPy operations (judges, training)
   OPENROUTER_MODEL=x-ai/grok-4.1-fast
   EOF
   ```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for detailed configuration options.

## Plan Command Setup

The `weft plan` command uses Claude Code CLI for interactive plan development. Once you've authenticated with Claude Code CLI (see [Prerequisites](#prerequisites)), you can create plans:

```bash
# Interactive plan creation from an idea file
weft plan idea.md

# Or provide the idea directly
weft plan --text "Create a feature to export user metrics"

# Use a specific model
weft plan --text "Create a feature" --model opus

# Disable hooks for this run
weft plan idea.md --no-hooks
```

The plan command opens an interactive Claude Code CLI session where you can discuss and refine your implementation plan. The resulting plan is saved to `.weft/tasks/<plan-id>.md`.

### Parameters

- `<plan_path>`: Path to idea file (optional if using `--text`)
- `--text <text>`: Provide idea text directly instead of a file
- `--model <model>`: Model variant to use. Options: `sonnet` (default), `opus`, `haiku`
- `--no-hooks`: Disable hooks for this command

## Init Command

The `weft init` command initializes a new project with frozen baseline templates. This is the recommended first step when adopting weft in a new repository.

### What It Does

Running `weft init` creates a `.weft/` directory at your repository root containing:

- **Judges** (`.weft/judges/`): LLM judges for evaluating code changes
  - `code-reuse.md`: Evaluates proper reuse of existing functionality
  - `plan-compliance.md`: Verifies implementation matches plan requirements
- **Active Prompts** (`.weft/prompts/active/`): Pre-optimized prompts for Claude Code CLI
  - Includes prompts for sonnet, opus, and haiku models
- **Config Template** (`.weft/config.toml`): Repository-level settings (e.g., worktree file sync)
- **VERSION**: Tracks template version and file hashes for customization detection

### Basic Usage

```bash
# Initialize in a new project
cd your-project
weft init

# Reinitialize with prompts (when .weft already exists)
weft init --force

# Reinitialize without prompts (CI/CD automation)
weft init --force --yes
```

### Customization Detection

When reinitializing with `--force`, weft detects which files you've customized by comparing current file hashes against the VERSION file. You'll see warnings before overwriting customized files:

```
WARNING: 1 judges have been customized from baseline:
  - judges/code-reuse.md
Overwrite existing judges? (y/n):
```

### Parameters

- `--force`: Allow initialization when `.weft/` already exists (asks for confirmation)
- `--yes`: Skip interactive prompts and overwrite everything (for CI/CD)

## Code Command

The `weft code` command executes plans created with the `plan` command. It validates the plan, sets up a worktree, and uses Claude Code CLI to implement the plan.

### Basic Usage

```bash
# Run with defaults (Claude Code CLI with sonnet model)
weft code plan.md

# Use a specific model
weft code plan.md --model opus
weft code plan.md --model haiku

# Provide plan text directly (creates plan inline)
weft code --text "Add error handling to the API endpoints"

# Disable hooks for this run
weft code plan.md --no-hooks
```

### Parameters

- `<plan_path>`: Path to the plan file to execute (optional if using `--text`)
- `--text <text>`: Provide plan text directly instead of a file
- `--model <model>`: Model variant to use. Options: `sonnet` (default), `opus`, `haiku`
- `--no-hooks`: Disable hooks for this command
- `--debug`: Enable debug-level logging for troubleshooting

### Examples

```bash
# Execute a plan with default settings
weft code .weft/tasks/my-feature.md

# Use opus model
weft code .weft/tasks/my-feature.md --model opus

# Enable debug logging
weft code .weft/tasks/my-feature.md --debug
```

### Worktree File Synchronization

When running `weft code`, your code executes in an isolated Git worktree. By default, untracked files like `.env` aren't present in the worktree.

To automatically copy untracked configuration files to the worktree, configure `.weft/config.toml`:

```toml
schema_version = "1.0"

[worktree.file_sync]
patterns = [".env", ".env.*", "config/*.json"]
```

Files are copied before execution and cleaned up after. See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for full configuration options.

## Judge Command

The `weft judge` command provides quick feedback on code changes during the coding phase. Unlike `weft eval`, it only runs LLM judges without executing tests, collecting human feedback, or generating training data.

### When to Use Judge vs Eval

| Use Case | Command | What It Does |
|----------|---------|--------------|
| **Quick feedback while coding** | `weft judge` | Runs judges only, displays results |
| **Full evaluation for training** | `weft eval` | Runs judges + tests + feedback + training data |

**Recommended workflow:**

```bash
# 1. Create and implement a plan
weft code my-feature

# 2. Get quick feedback during iteration
weft judge my-feature     # Fast - judges only
# ... make improvements based on feedback ...
weft judge my-feature     # Check again

# 3. When ready, run full evaluation
weft eval my-feature      # Full pipeline for training data

# 4. Finalize and merge
weft finalize my-feature
```

### Basic Usage

```bash
# Run judges and display results
weft judge <plan_id>

# Save results as markdown to a directory
weft judge <plan_id> --output ./results

# Examples
weft judge my-feature
weft judge quick-fix-2025.01-001 --output ./judge-results
```

### Parameters

- `<plan_id>`: Plan identifier (from `.weft/tasks/<plan_id>.md`)
- `--output <dir>`: Optional directory to save results as markdown file

**Note**: The `--debug` flag is a global option available for all weft commands.

### Output Format

Results are displayed to stdout in this format:

```
Judge Results:

code-reuse (score: 0.85, weight: 0.4)
  The implementation properly reuses the existing validation
  utilities rather than reimplementing them...

plan-compliance (score: 0.92, weight: 0.6)
  The changes align well with the plan requirements...

Weighted average: 0.89
```

### Understanding the Output

- **Score**: Each judge rates the code from 0.0 to 1.0
- **Weight**: Relative importance of this judge (configured in judge file)
- **Feedback**: Detailed analysis and recommendations
- **Weighted average**: Overall score considering judge weights

### Requirements

- Must be run from within a weft-initialized repository
- Worktree must exist (run `weft code <plan_id>` first)
- `OPENROUTER_API_KEY` must be set in `~/.weft/.env`
- At least one judge file in `.weft/judges/`

## Finalize Command

The `weft finalize` command completes the workflow by committing changes, rebasing onto main, and merging. It uses Claude Code CLI to handle the git operations automatically.

### What It Does

Running `weft finalize <plan_id>` will:
1. Verify uncommitted changes exist in the worktree
2. Move the plan file into the worktree (so it's included in the commit)
3. Launch Claude Code to commit, rebase onto main, and merge
4. Verify the merge succeeded
5. Clean up the worktree and branch
6. Remove the plan backup reference

### Basic Usage

```bash
# Finalize a completed plan
weft finalize my-feature

# Use a specific model (default: haiku)
weft finalize my-feature --model sonnet
```

### Parameters

- `<plan_path>`: Path to plan file or plan ID (required)
- `--model <model>`: Model variant to use. Options: `sonnet`, `opus`, `haiku` (default)
- `--tool <tool>`: Coding tool to use (default: claude-code)

### Example Workflow

```bash
# 1. Create a plan
weft plan --text "Add user authentication"

# 2. Implement the plan
weft code add-user-authentication

# 3. (Optional) Evaluate the implementation
weft eval add-user-authentication

# 4. Finalize and merge to main
weft finalize add-user-authentication
```

### Notes

- **Requires uncommitted changes**: The command fails if there are no changes to commit
- **Automatic cleanup**: On success, the worktree and branch are removed automatically
- **Plan file moves**: The plan file is moved into the worktree and committed with your changes
- **Runs outside sandbox**: Git operations run without sandbox restrictions (no permission prompts)

## Eval Command

The `weft eval` command evaluates code changes and creates training data for prompt optimization. After implementing a plan with the `code` command, use `eval` to get automated feedback on code quality, run tests, and collect human feedback.

### Basic Usage

```bash
# Evaluate changes for a plan
weft eval <plan_id>

# Use a specific model for test execution and feedback
weft eval <plan_id> --model opus

# Force re-run all steps (skip idempotency checks)
weft eval <plan_id> --force

# Disable hooks for this run
weft eval <plan_id> --no-hooks

# Examples
weft eval my-feature
weft eval quick-fix-2025.01-001
```

### What It Does

The eval command runs a comprehensive evaluation workflow:

1. **Run LLM Judges**: Executes all judges in `.weft/judges/` to evaluate code quality and plan compliance
2. **Run Before Tests**: Uses Claude Code SDK to run tests at the plan's original git commit (baseline)
3. **Run After Tests**: Uses Claude Code SDK to run tests in the current worktree (after implementation)
4. **Collect Human Feedback**: Opens an interactive Claude Code session to gather your feedback
5. **Create Training Data**: Saves all evaluation artifacts to `.weft/training_data/<plan_id>/`
6. **Trigger Hooks**: Runs the `eval_complete` hook after training data is created

### Parameters

- `<plan_id>`: Plan identifier (from `.weft/tasks/<plan_id>.md`)
- `--model <model>`: Model for test execution and feedback. Options: `sonnet` (default), `opus`, `haiku`
- `--force`: Re-run all steps and overwrite existing results (skips idempotency checks)
- `--no-hooks`: Disable hooks for this command
- `--debug`: Enable debug-level logging

### Idempotency

The eval command is idempotent and can be safely re-run:
- Judges: Only runs judges whose output files don't exist
- Tests: Skips if `test_results_before.json` or `test_results_after.json` exist
- Feedback: Skips if `human_feedback.md` exists
- Training Data: Skips if `training_data/<plan_id>/` exists

Use `--force` to re-run all steps and overwrite existing results.

### Test Execution

Tests are run using the Claude Code SDK in headless mode. Claude Code reads your project's CLAUDE.md file to understand how to run tests for your specific project.

**Requirements for test execution:**
- Your project's CLAUDE.md must contain test instructions
- The plan file should have a `git_sha` field for before-tests

Test results are saved as JSON with this structure:
```json
{
  "command": "uv run pytest",
  "exit_code": 0,
  "total_tests": 45,
  "passed_tests": 45,
  "failed_tests": 0,
  "summary": "All tests passed",
  "analysis": "Test analysis..."
}
```

**Note**: Test failures are DATA, not errors. The eval command succeeds even if tests fail.

### Human Feedback Collection

After judges and tests complete, an interactive Claude Code session opens to help you compose feedback. This feedback is used as training data for prompt optimization.

The session presents:
- Judge scores and detailed feedback
- Test results (before and after)
- Prompts to help you articulate your feedback

Your feedback is saved to `human_feedback.md` and can be free-form (no required structure).

### Training Data

After all steps complete, training data is created at `.weft/training_data/<plan_id>/`:

```
.weft/training_data/<plan_id>/
├── plan.md                     # Copy of the plan
├── code_trace.md               # Trace from code session
├── test_results_before.json    # Baseline test results
├── test_results_after.json     # Post-implementation test results
├── human_feedback.md           # Your feedback
├── judge_code-reuse.json       # Per-judge JSON results
├── judge_code-reuse.md         # Per-judge markdown feedback
├── judge_plan-compliance.json
└── judge_plan-compliance.md
```

**Important**: Training data is PERMANENT and expected to be committed to git. It is never pruned.

### Built-in Judges

Two judges are included by default:

#### Code Reuse Judge
- **Weight**: 0.4
- **Purpose**: Evaluates whether code properly reuses existing functionality
- **Checks**: Looks for reimplemented logic that should have called existing functions
- **File**: `.weft/judges/code-reuse.md`

#### Plan Compliance Judge
- **Weight**: 0.6
- **Purpose**: Verifies implementation matches plan requirements
- **Checks**: Ensures all requirements are implemented and no out-of-scope additions
- **File**: `.weft/judges/plan-compliance.md`

### Example Output

```
================================================================================
Evaluation Results for: my-feature
Worktree: .weft/worktrees/my-feature
================================================================================

Judge: code-reuse (weight: 0.40)
Score: 0.85 / 1.00

Judge: plan-compliance (weight: 0.60)
Score: 0.92 / 1.00

================================================================================
Overall Weighted Score: 0.89 / 1.00
================================================================================

Judge result files saved to: .weft/sessions/my-feature/eval/
```

### Requirements

- `OPENROUTER_API_KEY` must be set in `~/.weft/.env`
- Worktree must exist (run `weft code <plan_id>` first)
- At least one judge file in `.weft/judges/`
- CLAUDE.md with test instructions (for test execution)

### When to Use

- **After code command**: Run eval immediately after implementing a plan
- **Before finalize**: Always run eval before `weft finalize` to generate training data
- **After fixes**: Re-run with `--force` after making improvements
- **Code review**: Use eval output to supplement manual code review

### Creating Custom Judges

Judges are markdown files with YAML frontmatter. Create new judges in `.weft/judges/`:

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

The judge instructions in the markdown body are used to configure the LLM evaluation.

## Train Command

The `weft train` command analyzes training data from the `eval` command and generates improved prompt candidates. This is the first step toward self-optimizing prompts.

### Basic Usage

```bash
# Generate candidate prompts for sonnet variant
weft train sonnet

# Train opus prompts with custom parameters
weft train opus --batch-size 5 --max-subagents 3

# Use a different OpenRouter model for generation
weft train sonnet --model openai/gpt-5.2
```

### What It Does

The train command:

1. **Loads training data** from `.weft/training_data/<plan_id>/`
2. **Loads current active prompts** from `.weft/prompts/active/claude-code-cli/<variant>/`
3. **Analyzes patterns** using the specified OpenRouter model
4. **Generates candidate prompts** saved to `.weft/prompts/candidates/claude-code-cli/<variant>/`

### Parameters

- `VARIANT`: Required. Prompt variant to train: `sonnet`, `opus`, or `haiku`. Determines which prompt set to load and where candidates are saved.
- `--batch-size N`: Number of training samples to analyze per batch (default: 3, max: 10)
- `--max-subagents N`: Maximum number of subagents to generate (default: 5, max: 10)
- `--model MODEL`: OpenRouter model for generating candidates (default: x-ai/grok-4.1-fast)
- `--regenerate-summaries`: Regenerate training data summaries even if they already exist
- `--debug`: Enable debug-level logging

### Prerequisites

Before running `train`, you need:

1. **Training data**: Run `weft eval <plan_id>` on completed plans to generate training data
2. **Active prompts**: Run `weft init` to install baseline prompts at `.weft/prompts/active/`
3. **API key**: `OPENROUTER_API_KEY` must be set in `~/.weft/.env`

### Output

Candidates are saved to:
```
.weft/prompts/candidates/claude-code-cli/<model>/candidate-NNN/
├── main.md              # Improved main prompt
├── code-review-auditor.md  # Generated subagent (if applicable)
├── test-validator.md       # Generated subagent (if applicable)
├── ...                     # Additional subagents
└── ANALYSIS.md          # Summary of improvements made
```

### Example Output

```
========================================================================
Training Complete
========================================================================

Candidate saved to: .weft/prompts/candidates/claude-code-cli/sonnet/candidate-001/

Generated 3 subagent(s):
  - code-review-auditor
  - test-validator
  - completion-checker

Token Usage:
  Input tokens:  45,231
  Output tokens: 12,847
  Total tokens:  58,078

Analysis Summary:
------------------------------------------------------------------------
Based on training data analysis, the following improvements were made:
1. Added explicit completion verification steps to address incomplete work
2. Enhanced test validation instructions based on test failures
3. Improved code review focus on reusing existing functionality
------------------------------------------------------------------------

Next steps:
  1. Review the generated prompts in the candidate directory
  2. Test the candidate prompts manually
  3. If satisfactory, copy to prompts/active/ to use
```

### Workflow

The recommended workflow for prompt optimization:

1. **Implement plans**: `weft code <plan_id>`
2. **Evaluate results**: `weft eval <plan_id>` (creates training data)
3. **Train on data**: `weft train sonnet` (generates candidates for sonnet variant)
4. **Review candidates**: Manually inspect generated prompts
5. **Promote if good**: Copy candidate files to `prompts/active/`
6. **Repeat**: Continue the feedback loop to improve prompts

## Abandon Command

The `weft abandon` command cleans up failed or unwanted plans by removing the worktree, branch, and plan file while preserving the backup reference in a separate "abandoned" namespace for potential future recovery.

### What It Does

Running `weft abandon <plan>` will:
1. Force-delete the worktree (regardless of uncommitted changes)
2. Force-delete the branch (regardless of unmerged commits)
3. Delete the plan file
4. Move backup reference to `refs/plan-abandoned/` namespace
5. Optionally log the abandonment reason

### Basic Usage

```bash
# Abandon a plan with confirmation prompt
weft abandon my-feature

# Abandon with a reason (logged to abandoned-plans.log)
weft abandon my-feature --reason "Decided on different approach"

# Skip confirmation prompt (for automation)
weft abandon quick-fix-001 --yes
```

### Parameters

- `<plan_path>`: Path to plan file or plan ID (required)
- `--reason "text"`: Record why the plan was abandoned
- `--yes`: Skip confirmation prompt (useful for automation)

### Confirmation Prompt

When run interactively, the command shows what will be cleaned up:

```
Plan 'my-feature' will be abandoned:
  - Worktree will be force-deleted (has uncommitted changes)
  - Branch will be force-deleted (has 3 unmerged commits)
  - Plan file will be deleted
  - Backup moved to refs/plan-abandoned/my-feature

Continue? (y/n)
```

### Abandoned Plans Log

When using the `--reason` flag, the reason is appended to `.weft/abandoned-plans.log`:

```markdown
## my-feature - 2025-12-08 15:30:45 -0800
Decided on different approach.

## another-plan - 2025-12-08 16:22:10 -0800
Bug was already fixed in another PR
```

### Recovering Abandoned Plans

Abandoned plans can be recovered using the recover-plan command:

```bash
# List abandoned plans
weft recover-plan --abandoned

# Recover an abandoned plan
weft recover-plan --abandoned my-feature
```

When recovered, the backup reference is moved back to `refs/plan-backups/`.

## Recover Plan Command

The `weft recover-plan` command provides backup and recovery of plan files. Plan files are automatically backed up when created or modified during the `plan` command, and backups are automatically cleaned up when plans are finalized.

### What are Plan Backups?

- **Automatic creation**: Backups are created automatically when you run `weft plan`
- **Durable storage**: Backups are stored as git orphan commits at `refs/plan-backups/<plan_id>`
- **Automatic cleanup**: Backups are automatically deleted when you run `weft finalize`
- **Abandoned storage**: When plans are abandoned, backups move to `refs/plan-abandoned/<plan_id>`
- **Recovery**: Backups allow you to restore accidentally deleted plan files

### Basic Usage

```bash
# List all backed-up plans
weft recover-plan

# List only abandoned plans
weft recover-plan --abandoned

# List all plans (both active and abandoned)
weft recover-plan --all

# Recover a specific plan
weft recover-plan my-feature

# Recover an abandoned plan
weft recover-plan --abandoned my-feature

# Force overwrite if plan file already exists
weft recover-plan my-feature --force
```

### Parameters

- `<plan_id>`: Optional plan identifier to recover. If omitted, lists all backups
- `--force`: Overwrite existing plan file during recovery
- `--abandoned`: Show or recover from abandoned plans (refs/plan-abandoned/)
- `--all`: Show both active backups and abandoned plans

### Examples

#### Listing All Backups

```bash
weft recover-plan
```

Output:
```
Found 2 backed-up plan(s):

Plan ID          Backup Date          Status
----------------------------------------------------
feature-auth     2025-01-15 14:23:45  exists
feature-export   2025-01-14 09:12:30  missing

Use 'weft recover-plan <plan_id>' to restore a plan.
```

The status column shows:
- `exists`: Plan file currently exists in `.weft/tasks/`
- `missing`: Plan file has been deleted and can be recovered

#### Recovering a Plan

```bash
# Recover a deleted plan
weft recover-plan feature-export

# Output:
# Successfully recovered plan to: /path/to/repo/.weft/tasks/feature-export.md
# You can now continue working with: weft code feature-export
```

#### Force Overwrite

If a plan file already exists and you want to restore it from backup:

```bash
weft recover-plan my-feature --force
```

### Important: Backup Timing

**Backups are created when you run `weft plan`, not when you manually edit files.** The backup timestamp shown in the listing indicates when the backup was created, which may be older than your current plan file if you've manually edited it since running the `plan` command.

**Warning**: If you've manually edited a plan file after running `weft plan`, recovering from backup with `--force` will overwrite your manual changes with the older backed-up version. Always verify the backup date before using `--force` to ensure you're not losing recent edits.

### Common Use Cases

1. **Accidentally deleted plan**: If you delete a plan file before finalizing it, use `recover-plan` to restore it
2. **View backup history**: Use `recover-plan` without arguments to see which plans have backups
3. **Revert plan changes**: If you modified a plan and want to go back to the backed-up version, use `--force` to overwrite

## Configurable Hooks

You can configure commands to run automatically at key workflow points by creating `~/.weft/config.toml` in your home directory.

### Quick Start

Create `~/.weft/config.toml`:

```toml
[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = true

[hooks.code_sdk_complete]
command = "notify-send 'Code Complete' 'Ready for review'"
enabled = true

[hooks.eval_complete]
command = "echo 'Training data ready at ${training_data_dir}'"
enabled = true
```

### Hook Points

- **plan_file_created**: Triggered when plan file is created during interactive session
- **code_sdk_complete**: Triggered after SDK session completes, before CLI resume
- **eval_complete**: Triggered after eval completes and training data is created

### Available Variables

Use `${variable}` syntax in commands:
- All hooks: `${worktree_path}`, `${plan_path}`, `${plan_id}`, `${repo_root}`
- `eval_complete` only: `${training_data_dir}`

### Common Examples

```toml
# Open editor when plan is created
[hooks.plan_file_created]
command = "code-oss ${worktree_path} --new-window"
enabled = true

# Desktop notification when code completes
[hooks.code_sdk_complete]
command = "notify-send 'weft' 'Code generation complete for ${plan_id}'"
enabled = true

# Notification when eval completes
[hooks.eval_complete]
command = "notify-send 'weft' 'Evaluation complete for ${plan_id}'"
enabled = true
```

### Disabling Hooks

Use the `--no-hooks` flag to disable all hooks for a single command:

```bash
weft plan idea.md --no-hooks
weft code plan.md --no-hooks
weft eval my-feature --no-hooks
```

For complete documentation, see [docs/HOOKS.md](docs/HOOKS.md).

### Model Defaults

Configure default models for commands in the same config file:

```toml
[defaults]
plan_model = "opus"      # Most capable for planning
code_model = "sonnet"    # Balanced for implementation
finalize_model = "haiku" # Fast for finalization

[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = true
```

Available models:
- `sonnet`: Balanced capability and speed (default for plan and code)
- `opus`: Most capable, slower, more expensive
- `haiku`: Fast and economical (default for finalize)

**Precedence**: CLI flags override config defaults. For example:
```bash
weft code plan.md --model opus
```

## Logging

The CLI uses Python's built-in `logging` module for all output:

- **Console logging**: All messages are logged to stderr with INFO level by default
- **File logging**: Daily rotating log files are stored at `~/.weft/logs/weft.log` with 30 days retention
- **Debug mode**: Use the `--debug` flag to enable DEBUG-level logging for more verbose output:
  ```bash
  weft code <plan_path> --debug
  ```

Log files rotate daily at midnight and maintain 30 days of history automatically.

## Further Documentation

For more detailed information, see:

- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) - Complete configuration guide including environment variables, DSPy caching, and worktree file sync
- [docs/HOOKS.md](docs/HOOKS.md) - Detailed hook configuration and examples
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) - Security considerations and threat analysis
