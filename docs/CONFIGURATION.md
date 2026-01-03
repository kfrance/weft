# Configuration Guide

This document describes the configuration for weft.

## Configuration Locations

weft uses two types of configuration:

1. **User-level secrets**: `~/.weft/.env` - API keys and credentials
2. **Repository-level config**: `.weft/config.toml` - Per-repository settings like worktree file sync

## Setup

1. Create the `.weft` directory in your home directory:
   ```bash
   mkdir -p ~/.weft
   ```

2. Create the `.env` file:
   ```bash
   touch ~/.weft/.env
   ```

3. Add your API keys to `~/.weft/.env`:
   ```bash
   # Required for DSPy to use OpenRouter
   OPENROUTER_API_KEY=your-api-key-here

   # Optional: Specify default model
   OPENROUTER_MODEL=x-ai/grok-4.1-fast

   # Optional: Your app name for OpenRouter analytics
   OPENROUTER_APP_NAME=weft
   ```

4. Run `weft code <plan_path>` to generate prompts and execute coding tasks

## Environment Variables for DSPy

weft uses DSPy for prompt generation and optimization. DSPy requires access to LLM providers via environment variables.

### OpenRouter Configuration

The recommended LLM provider is OpenRouter, which provides access to multiple models through a single API.

Set these variables in your `~/.weft/.env` file:

```bash
# Required for DSPy to use OpenRouter
OPENROUTER_API_KEY=your-api-key-here

# Optional: Specify default model
OPENROUTER_MODEL=x-ai/grok-4.1-fast

# Optional: Your app name for OpenRouter analytics
OPENROUTER_APP_NAME=weft
```

### DSPy Caching

DSPy caches LLM responses to improve performance and reduce API costs.

**Cache Location:**
- Global cache: `~/.weft/dspy_cache/`

**How It Works:**
- Cache is stored in a single global location accessible from all worktrees
- The SDK sandbox is configured to grant write access to the cache directory
- DSPy writes cache entries directly without any synchronization needed

**Cache behavior:**
- Initial runs that generate new prompts will call the LLM API
- Subsequent runs with the same plan will reuse cached responses
- Cache is keyed by prompt content, so plan changes trigger new API calls
- Cache persists across runs and is shared between all worktrees

**Manual Cache Management:**
- Clear cache: `rm -rf ~/.weft/dspy_cache`

**Troubleshooting:**
- If cache appears not to be working, verify the directory exists with `ls -la ~/.weft/dspy_cache`
- For permission issues, ensure write access to the cache directory

## Validation

Configuration is validated when loading:

- **Missing `~/.weft/.env`**: Error raised with instructions to create the file
- **Unreadable file**: Error if the file exists but cannot be read
- **Invalid path**: Error if `~/.weft/.env` is a directory instead of a file

### Error Messages

The configuration loader provides actionable error messages:

```
HomeEnvError: Environment file not found: /home/user/.weft/.env
Create ~/.weft/.env with required secrets (e.g., OPENROUTER_API_KEY).
```

```
HomeEnvError: Environment path is not a file: /home/user/.weft/.env
~/.weft/.env must be a regular file.
```

```
HomeEnvError: Cannot read environment file: /home/user/.weft/.env
Error: [Errno 13] Permission denied
```

## Security Considerations

- The `~/.weft/.env` file contains sensitive API keys and should not be committed to version control
- Environment variables are loaded into the process environment when weft runs
- The DSPy cache at `~/.weft/dspy_cache/` stores LLM responses in plaintext
- Standard filesystem permissions protect these files on single-user systems
- On shared systems, consider setting restrictive permissions: `chmod 600 ~/.weft/.env`

## Troubleshooting

**Error: Environment file not found**
- Ensure `~/.weft/.env` exists
- Check that you're running weft as the correct user
- Verify the path with `ls -la ~/.weft/`

**Environment variables not loading**
- Verify the `.env` file syntax (KEY=value format, one per line)
- Check for typos in variable names
- Ensure no extra spaces around the `=` sign
- Test by running `cat ~/.weft/.env`

**Permission denied errors**
- Check file permissions: `ls -l ~/.weft/.env`
- Ensure the file is readable: `chmod 644 ~/.weft/.env`
- Verify directory permissions: `chmod 755 ~/.weft`

## Host Execution Configuration

The `weft code` command executes coding agents directly on your Linux host using Git worktrees for isolated execution. No Docker setup is required.

### Prerequisites

- **Operating System**: Linux (Ubuntu 20.04+, Debian 11+, Fedora, etc.)
- **Tools**: Git, Python 3.11+, Droid CLI (installed separately)
- **Network**: Access to LLM provider APIs (OpenRouter, etc.)

### Platform Support

**Supported**: Linux (Ubuntu 20.04+, Debian 11+, Fedora, CentOS 8+, etc.)

**Not Supported**: macOS, Windows (coming soon with Claude Code CLI integration)

If you're running on an unsupported platform, `weft` will emit a warning on startup but may still function if you have the required tools available.

### Environment Variable Forwarding

By default, weft forwards environment variables matching the pattern `OPENROUTER_*` to the host execution context. This ensures that API credentials are available to the coding agents.

The forwarding behavior is hardcoded in `src/weft/code_command.py` and currently includes:
- `OPENROUTER_*` pattern (matches all OpenRouter-related variables)

### Git Worktree Isolation

Code execution occurs in isolated Git worktrees created under `.weft/runs/<plan_id>/`:

```
.weft/runs/
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

**Note**: If you need to preserve run artifacts long-term, copy them outside the `.weft/runs/` directory.

## Repository-Level Configuration

Repository-level settings are stored in `.weft/config.toml` at the root of your repository. This file is created automatically when you run `weft init`.

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

When running `weft code`, the coding agent executes in an isolated Git worktree. Files that are not tracked by Git (like `.env` files with secrets) won't be present in the worktree by default.

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
