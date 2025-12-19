# Configuration Guide

This document describes the configuration for weft.

## Configuration Location

weft loads secrets and credentials from `~/.weft/.env` in your home directory.

**This is the only configuration location.** There is no repository-level configuration file.

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
   OPENROUTER_MODEL=anthropic/claude-3-5-sonnet

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
OPENROUTER_MODEL=anthropic/claude-3-5-sonnet

# Optional: Your app name for OpenRouter analytics
OPENROUTER_APP_NAME=weft
```

### DSPy Caching

DSPy caches LLM responses to improve performance and reduce API costs.

**Cache Locations:**
- Global cache: `~/.weft/dspy_cache/`
- Worktree cache: `<worktree>/.weft/dspy_cache/`

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
- Clear cache: `rm -rf ~/.weft/dspy_cache`
- Verify rsync: `which rsync`

**Troubleshooting:**
- If cache sync fails, check rsync installation with `rsync --version`
- Cache sync failures are logged as warnings but don't block command execution
- For permission issues, ensure write access to both cache directories

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
