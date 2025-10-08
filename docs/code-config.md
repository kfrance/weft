# Configuration Guide

This document describes the configuration options for lw_coder.

## Configuration File Location

Configuration is stored in `.lw_coder/config.toml` at the root of your repository.

## `[code]` Table

The `[code]` table configures the `lw_coder code` command, which orchestrates AI coding agents to implement plans.

### Fields

#### `env_file` (string, default: `".env"`)

Path to the environment file containing credentials and configuration variables, relative to the repository root.

The specified file must exist or configuration loading will fail.

**Example:**
```toml
[code]
env_file = ".env"  # Load from .env in repo root
```

```toml
[code]
env_file = "config/production.env"  # Load from subdirectory
```

#### `forward_env` (list of strings, default: `["OPENROUTER_*"]`)

List of environment variable patterns to forward from the `.env` file to the Docker container where coding agents run.

Patterns support wildcards:
- `"OPENROUTER_*"` matches all variables starting with `OPENROUTER_`
- `"*"` matches all environment variables (not recommended, logs a warning)

**Example:**
```toml
[code]
forward_env = ["OPENROUTER_*"]  # Forward only OpenRouter credentials
```

```toml
[code]
forward_env = ["OPENROUTER_*", "ANTHROPIC_API_KEY", "DEBUG"]  # Forward multiple patterns
```

**Warning:** Using `forward_env = ["*"]` will forward ALL environment variables, which may expose sensitive information. This configuration will log a warning.

#### `docker_build_args` (list of strings, default: `[]`)

Arguments to pass to `docker build` when building the container image for coding agents.

**Example:**
```toml
[code]
docker_build_args = ["--build-arg", "PYTHON_VERSION=3.11"]
```

#### `docker_run_args` (list of strings, default: `[]`)

Arguments to pass to `docker run` when starting the container for coding agents.

**Example:**
```toml
[code]
docker_run_args = ["--memory", "4g", "--cpus", "2"]
```

### Complete Example

```toml
# .lw_coder/config.toml

[code]
# Environment configuration
env_file = ".env"
forward_env = ["OPENROUTER_*"]

# Docker configuration
docker_build_args = []
docker_run_args = ["--memory", "4g"]
```

## Environment Variables for DSPy

lw_coder uses DSPy for prompt generation and optimization. DSPy requires access to LLM providers via environment variables.

### OpenRouter Configuration

The recommended LLM provider is OpenRouter, which provides access to multiple models through a single API.

Set these variables in your `.env` file:

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

- **Missing `[code]` table**: Error raised with instructions to add required section
- **Unknown keys**: Error lists unrecognized keys and valid options
- **Missing env file**: Error if specified `.env` file doesn't exist
- **Invalid types**: Error if fields have wrong types (e.g., string instead of list)
- **Wildcard warning**: Warning logged if `forward_env = ["*"]` is used

### Error Messages

The configuration loader provides actionable error messages:

```
ConfigLoaderError: Configuration file not found: /path/to/.lw_coder/config.toml
Create .lw_coder/config.toml with a [code] section.
```

```
ConfigLoaderError: Missing required [code] table in /path/to/.lw_coder/config.toml
Add a [code] section with env_file and optional forward_env, docker_build_args, docker_run_args.
```

```
ConfigLoaderError: Unknown keys in [code] section: unknown_field
Valid keys are: docker_build_args, docker_run_args, env_file, forward_env
```

## Quick Start

1. Create `.lw_coder/config.toml` in your repository:
   ```toml
   [code]
   env_file = ".env"
   forward_env = ["OPENROUTER_*"]
   docker_build_args = []
   docker_run_args = []
   ```

2. Create `.env` in your repository root:
   ```bash
   OPENROUTER_API_KEY=your-key-here
   ```

3. Run `lw_coder code <plan_path>` to generate prompts and execute coding tasks

The first run will call the OpenRouter API and cache responses. Subsequent runs with the same plan will use the cache.
