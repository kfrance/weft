# Configuration Guide

This document describes the configuration for lw_coder.

## Configuration Location

lw_coder loads secrets and credentials from `~/.lw_coder/.env` in your home directory.

**This is the only configuration location.** There is no repository-level configuration file.

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

DSPy automatically caches LLM responses to disk at `~/.lw_coder/dspy_cache/`. This cache:

- Reduces API costs by reusing responses for identical prompts
- Speeds up development by avoiding redundant API calls
- Persists across runs

The cache directory is created automatically on first use. You can safely delete it to clear the cache.

**Cache behavior:**
- Initial runs that generate new prompts will call the LLM API
- Subsequent runs with the same plan will reuse cached responses
- Cache is keyed by prompt content, so plan changes trigger new API calls

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

## Docker Configuration

The `lw_coder code` command uses Docker to run coding agents in isolated environments. Docker configuration is handled automatically with sensible defaults.

### Environment Variable Forwarding

By default, lw_coder forwards environment variables matching the pattern `OPENROUTER_*` to the Docker container. This ensures that API credentials are available to the coding agents.

The forwarding behavior is hardcoded in `src/lw_coder/code_command.py` and currently includes:
- `OPENROUTER_*` pattern (matches all OpenRouter-related variables)

### Run Artifacts

The code command creates run-scoped artifacts under `.lw_coder/runs/<plan_id>/<timestamp>/`:

```
.lw_coder/runs/
└── my-plan/
    └── 20251009_143000/
        ├── prompts/
        │   └── main.md              # Main coding prompt
        └── droids/
            ├── code-review-auditor.md    # Code review subagent prompt
            └── plan-alignment-checker.md  # Plan alignment subagent prompt
```

### Retention Policy

Run directories are automatically pruned after **30 days**. The pruning logic:
- Checks directory modification time
- Skips the currently active run
- Removes empty plan directories after all runs are pruned

**Note**: If you need to preserve run artifacts long-term, copy them outside the `.lw_coder/runs/` directory.
