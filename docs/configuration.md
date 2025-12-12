# Configuration Guide

This document describes the configuration for lw_coder.

## Configuration Locations

lw_coder uses two types of configuration:

1. **User-level secrets**: `~/.lw_coder/.env` - API keys and credentials
2. **Repository-level config**: `.lw_coder/config.toml` - Per-repository settings like worktree file sync

## Setup

1. Create the `.lw_coder` directory in your home directory:
   ```bash
   mkdir -p ~/.lw_coder
   ```

2. Create the `.env` file:
   ```bash
   touch ~/.lw_coder/.env
   ```

3. Add your API keys to `~/.lw_coder/.env`:
   ```bash
   # Required for DSPy to use OpenRouter
   OPENROUTER_API_KEY=your-api-key-here

   # Optional: Specify default model
   OPENROUTER_MODEL=anthropic/claude-3-5-sonnet

   # Optional: Your app name for OpenRouter analytics
   OPENROUTER_APP_NAME=lw_coder
   ```

4. Run `lw_coder code <plan_path>` to generate prompts and execute coding tasks

## Environment Variables for DSPy

lw_coder uses DSPy for prompt generation and optimization. DSPy requires access to LLM providers via environment variables.

### OpenRouter Configuration

The recommended LLM provider is OpenRouter, which provides access to multiple models through a single API.

Set these variables in your `~/.lw_coder/.env` file:

```bash
# Required for DSPy to use OpenRouter
OPENROUTER_API_KEY=your-api-key-here

# Optional: Specify default model
OPENROUTER_MODEL=anthropic/claude-3-5-sonnet

# Optional: Your app name for OpenRouter analytics
OPENROUTER_APP_NAME=lw_coder
```

### DSPy Caching

DSPy caches LLM responses to improve performance and reduce API costs.

**Cache Locations:**
- Global cache: `~/.lw_coder/dspy_cache/`
- Worktree cache: `<worktree>/.lw_coder/dspy_cache/`

**How It Works:**
- Cache entries are automatically synced to worktrees before command execution
- Cache entries created in worktrees sync back to global cache after execution
- This allows worktrees to benefit from existing cache while running in sandbox environments

**Cache behavior:**
- Initial runs that generate new prompts will call the LLM API
- Subsequent runs with the same plan will reuse cached responses
- Cache is keyed by prompt content, so plan changes trigger new API calls
- Cache persists across runs and is shared between worktrees

**Requirements:**
- `rsync` command must be available for cache synchronization
- If rsync is not available, you'll see a warning and cache sync will be disabled
- Commands continue to work without cache sync, just without worktree cache sharing

**Manual Cache Management:**
- Clear cache: `rm -rf ~/.lw_coder/dspy_cache`
- Verify rsync: `which rsync`

**Troubleshooting:**
- If cache sync fails, check rsync installation with `rsync --version`
- Cache sync failures are logged as warnings but don't block command execution
- For permission issues, ensure write access to both cache directories

## Validation

Configuration is validated when loading:

- **Missing `~/.lw_coder/.env`**: Error raised with instructions to create the file
- **Unreadable file**: Error if the file exists but cannot be read
- **Invalid path**: Error if `~/.lw_coder/.env` is a directory instead of a file

### Error Messages

The configuration loader provides actionable error messages:

```
HomeEnvError: Environment file not found: /home/user/.lw_coder/.env
Create ~/.lw_coder/.env with required secrets (e.g., OPENROUTER_API_KEY).
```

```
HomeEnvError: Environment path is not a file: /home/user/.lw_coder/.env
~/.lw_coder/.env must be a regular file.
```

```
HomeEnvError: Cannot read environment file: /home/user/.lw_coder/.env
Error: [Errno 13] Permission denied
```

## Security Considerations

- The `~/.lw_coder/.env` file contains sensitive API keys and should not be committed to version control
- Environment variables are loaded into the process environment when lw_coder runs
- The DSPy cache at `~/.lw_coder/dspy_cache/` stores LLM responses in plaintext
- Standard filesystem permissions protect these files on single-user systems
- On shared systems, consider setting restrictive permissions: `chmod 600 ~/.lw_coder/.env`

## Troubleshooting

**Error: Environment file not found**
- Ensure `~/.lw_coder/.env` exists
- Check that you're running lw_coder as the correct user
- Verify the path with `ls -la ~/.lw_coder/`

**Environment variables not loading**
- Verify the `.env` file syntax (KEY=value format, one per line)
- Check for typos in variable names
- Ensure no extra spaces around the `=` sign
- Test by running `cat ~/.lw_coder/.env`

**Permission denied errors**
- Check file permissions: `ls -l ~/.lw_coder/.env`
- Ensure the file is readable: `chmod 644 ~/.lw_coder/.env`
- Verify directory permissions: `chmod 755 ~/.lw_coder`

## Host Execution Configuration

The `lw_coder code` command executes coding agents directly on your Linux host using Git worktrees for isolated execution. No Docker setup is required.

### Prerequisites

- **Operating System**: Linux (Ubuntu 20.04+, Debian 11+, Fedora, etc.)
- **Tools**: Git, Python 3.11+, Droid CLI (installed separately)
- **Network**: Access to LLM provider APIs (OpenRouter, etc.)

### Platform Support

**Supported**: Linux (Ubuntu 20.04+, Debian 11+, Fedora, CentOS 8+, etc.)

**Not Supported**: macOS, Windows (coming soon with Claude Code CLI integration)

If you're running on an unsupported platform, `lw_coder` will emit a warning on startup but may still function if you have the required tools available.

### Environment Variable Forwarding

By default, lw_coder forwards environment variables matching the pattern `OPENROUTER_*` to the host execution context. This ensures that API credentials are available to the coding agents.

The forwarding behavior is hardcoded in `src/lw_coder/code_command.py` and currently includes:
- `OPENROUTER_*` pattern (matches all OpenRouter-related variables)

### Git Worktree Isolation

Code execution occurs in isolated Git worktrees created under `.lw_coder/runs/<plan_id>/`:

```
.lw_coder/runs/
└── my-plan/
    └── 20251009_143000/
        ├── prompts/
        │   └── main.md              # Main coding prompt
        ├── droids/
        │   ├── code-review-auditor.md    # Code review subagent prompt
        │   └── plan-alignment-checker.md  # Plan alignment subagent prompt
        └── .git                     # Worktree git directory
```

Each worktree is a separate Git repository state, allowing safe experimentation without affecting your main working directory.

### Retention Policy

Run directories are automatically pruned after **30 days**. The pruning logic:
- Checks directory modification time
- Skips the currently active run
- Removes empty plan directories after all runs are pruned

**Note**: If you need to preserve run artifacts long-term, copy them outside the `.lw_coder/runs/` directory.

## Repository-Level Configuration

Repository-level settings are stored in `.lw_coder/config.toml` at the root of your repository. This file is created automatically when you run `lw_coder init`.

### Configuration Schema

```toml
# Required: Schema version for forward compatibility
schema_version = "1.0"

# Worktree file synchronization (optional)
[worktree.file_sync]
enabled = true                    # Enable/disable file sync (default: true)
patterns = [                      # Glob patterns for files to sync
    ".env",
    ".env.*",
    "config/*.json",
]
max_file_size_mb = 100           # Max size per file in MB (default: 100)
max_total_size_mb = 500          # Max total size in MB (default: 500)
```

### Worktree File Synchronization

When running `lw_coder code`, the coding agent executes in an isolated Git worktree. Files that are not tracked by Git (like `.env` files with secrets) won't be present in the worktree by default.

The worktree file sync feature copies specified untracked files from your main repository to the worktree before execution, ensuring tests and code have access to necessary configuration files.

#### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | boolean | `true` | Enable or disable file synchronization |
| `patterns` | list[string] | `[]` | Glob patterns relative to repo root |
| `max_file_size_mb` | integer | `100` | Maximum size per individual file (MB) |
| `max_total_size_mb` | integer | `500` | Maximum total size of all synced files (MB) |

#### Pattern Syntax

Patterns use standard glob syntax relative to the repository root:

- `".env"` - Matches `.env` file in repo root
- `".env.*"` - Matches `.env.local`, `.env.test`, etc.
- `"config/*.json"` - Matches all JSON files in config directory
- `"**/*.env"` - Matches `.env` files in any subdirectory

#### Security Constraints

For security, patterns cannot:

- Reference parent directories (`..`)
- Use absolute paths (`/etc/passwd`)
- Use home directory expansion (`~/.bashrc`)

#### File Handling

- **Regular files**: Copied with metadata preserved (permissions, timestamps)
- **Directories**: Recursively copied maintaining structure
- **Symlinks**: Preserved as symlinks (not dereferenced)

#### Size Limits

Size limits prevent accidentally copying large files like build artifacts:

- **Per-file limit**: Rejects any single file exceeding `max_file_size_mb`
- **Total limit**: Rejects if cumulative size exceeds `max_total_size_mb`

#### Error Behavior

- **Pattern matches nothing**: Error with message suggesting to check the pattern
- **Size limit exceeded**: Error identifying the problematic file
- **Config validation error**: Error with specific fix guidance

#### Cleanup

Synced files are automatically removed from the worktree after the coding session ends, whether it completes successfully, fails, or is interrupted.

#### Example Use Cases

**Syncing environment files:**
```toml
[worktree.file_sync]
patterns = [".env", ".env.local", ".env.test"]
```

**Syncing configuration directory:**
```toml
[worktree.file_sync]
patterns = ["config/"]
```

**Multiple patterns with custom limits:**
```toml
[worktree.file_sync]
patterns = [
    ".env*",
    "secrets/*.json",
    "certs/*.pem",
]
max_file_size_mb = 10
max_total_size_mb = 50
```
