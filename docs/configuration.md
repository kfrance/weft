# Configuration Guide

This document describes how to configure `lw_coder` for the code command workflow.

## Configuration File

The code command reads configuration from `.lw_coder/config.toml` in your repository root.

### `[code]` Section

The `[code]` table controls environment loading, variable forwarding, and Docker settings for the coding workflow.

#### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `env_file` | string | `".env"` | Path to environment file (relative to repo root) |
| `forward_env` | list of strings | `["OPENROUTER_*"]` | Environment variable patterns to forward to container |
| `docker_build_args` | list of strings | `[]` | Arguments to pass to `docker build` |
| `docker_run_args` | list of strings | `[]` | Arguments to pass to `docker run` |

#### Example Configuration

```toml
[code]
# Path to .env file (relative to repo root)
env_file = ".env"

# Environment variables to forward to Docker container
# Supports wildcard patterns using fnmatch syntax
forward_env = ["OPENROUTER_*", "DEBUG"]

# Arguments to pass to docker build
docker_build_args = []

# Arguments to pass to docker run
# WARNING: Avoid dangerous options like --privileged, --cap-add, --security-opt
docker_run_args = ["--cpus=2", "--memory=4g"]
```

## Environment Variables

### OpenRouter Configuration

The code command uses DSPy with OpenRouter for prompt generation. Set these variables in your `.env` file:

```bash
# OpenRouter API Key (required)
OPENROUTER_API_KEY=your-api-key-here

# OpenRouter Base URL (optional, uses default if not specified)
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### Environment Variable Forwarding

The `forward_env` option controls which environment variables are passed to the Docker container:

- **Wildcard patterns**: Use `*` as a wildcard (e.g., `OPENROUTER_*` matches `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`)
- **Specific variables**: List exact variable names (e.g., `["DEBUG", "LOG_LEVEL"]`)
- **Forward all** (not recommended): Use `["*"]` to forward all variables, but this will log a security warning

**Security Note**: Be cautious about forwarding sensitive environment variables. Only forward what's necessary for your coding workflow.

## Docker Configuration

### Build Arguments

Use `docker_build_args` to pass arguments during Docker image building:

```toml
[code]
docker_build_args = [
  "--build-arg", "NODE_VERSION=20",
  "--build-arg", "PYTHON_VERSION=3.12"
]
```

### Runtime Arguments

Use `docker_run_args` to pass additional arguments when running the Docker container:

```toml
[code]
docker_run_args = [
  "--cpus=4",
  "--memory=8g",
  "--tmpfs=/tmp:size=2g"
]
```

**Security Warning**: The following Docker arguments are flagged as potentially dangerous and will trigger warnings:
- `--privileged`: Grants extended privileges to container
- `--cap-add`: Adds Linux capabilities
- `--security-opt`: Modifies security options
- `--pid=host`, `--network=host`, `--ipc=host`, `--userns=host`: Share host namespaces

Use these options only if absolutely necessary and understand the security implications.

## DSPy Caching

DSPy uses disk caching to speed up repeated prompt generations. Cache data is stored at:

```
~/.lw_coder/dspy_cache/
```

### Cache Behavior

- **First run**: DSPy makes API calls to OpenRouter, responses are cached to disk
- **Subsequent runs**: Cached responses are reused for identical inputs
- **Cache invalidation**: Changing the plan content or metadata will result in cache misses

### Managing the Cache

To clear the cache:

```bash
rm -rf ~/.lw_coder/dspy_cache/
```

**Note**: Clearing the cache will cause DSPy to make fresh API calls on the next run, which may incur OpenRouter usage costs.

## Run Artifacts

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

## Troubleshooting

### DSPy LM Not Configured

**Error**: `No LM is loaded. Please configure the LM using dspy.configure(lm=dspy.LM(...))`

**Solution**: Ensure your `.env` file contains `OPENROUTER_API_KEY` and is specified correctly in `config.toml`.

### Missing Configuration File

**Error**: `Configuration file not found: .lw_coder/config.toml`

**Solution**: Create `.lw_coder/config.toml` with at minimum a `[code]` section:

```toml
[code]
env_file = ".env"
```

### Missing Environment File

**Error**: `Environment file not found: /path/to/.env`

**Solution**: Create the `.env` file at the specified location (relative to repo root), or update `env_file` in `config.toml` to point to an existing file.

### Docker Image Not Found

**Error**: `Docker image 'lw_coder_droid:latest' not found`

**Solution**: Build the Docker image first:

```bash
cd docker/droid
docker build -t lw_coder_droid:latest .
```

### OpenRouter API Errors

If you encounter OpenRouter API errors:

1. **Check API key**: Verify `OPENROUTER_API_KEY` in your `.env` file
2. **Check network**: Ensure you can reach `https://openrouter.ai`
3. **Check quota**: Verify your OpenRouter account has available credits
4. **Clear cache**: If cached responses are corrupted, remove `~/.lw_coder/dspy_cache/`

## Best Practices

1. **Version control**: Add `.lw_coder/config.toml` to version control, but keep `.env` in `.gitignore`
2. **Environment isolation**: Use separate `.env` files for different environments (dev, staging, production)
3. **Security**: Only forward necessary environment variables using specific patterns rather than `["*"]`
4. **Docker resources**: Set appropriate CPU and memory limits via `docker_run_args` based on your workload
5. **Cache management**: Monitor `~/.lw_coder/dspy_cache/` size if running many different plans

## Example: Minimal Setup

Here's a minimal working configuration:

**.lw_coder/config.toml**:
```toml
[code]
env_file = ".env"
forward_env = ["OPENROUTER_*"]
```

**.env**:
```bash
OPENROUTER_API_KEY=sk-or-your-key-here
```

With this setup, run:

```bash
uv run lw_coder code .lw_coder/tasks/my-plan.md
```

The command will:
1. Validate the plan
2. Load configuration and environment
3. Generate prompts using DSPy (with caching)
4. Create a worktree for the specified Git SHA
5. Prepare run artifacts

For complete workflow documentation, see the README.
