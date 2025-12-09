# Configurable Hooks

lw_coder supports configurable hooks that execute commands at key workflow points. This allows you to automate actions like opening editors, sending notifications, or running custom scripts.

## Configuration

Hooks are configured in `~/.lw_coder/config.toml` in your home directory. This is a global configuration file that applies to all repositories.

### Basic Structure

```toml
[hooks.hook_name]
command = "your-command ${variable}"
enabled = true
```

### Example Configuration

```toml
# Open VS Code when a plan file is created
[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = true

# Send desktop notification when code generation completes
[hooks.code_sdk_complete]
command = "notify-send 'lw_coder' 'Code complete for ${plan_id}'"
enabled = true

# Open file manager after evaluation
[hooks.eval_complete]
command = "nautilus ${training_data_dir}"
enabled = true
```

## Available Hooks

### plan_file_created

**Triggered:** When a plan file is created during an interactive `lw_coder plan` session.

**Timing:** During the plan session, when Claude creates a `.md` file in the tasks directory.

**Available Variables:**
| Variable | Description |
|----------|-------------|
| `${worktree_path}` | Path to the temporary worktree |
| `${plan_path}` | Path to the plan file in the main repository |
| `${plan_id}` | The plan ID (filename without .md extension) |
| `${repo_root}` | Path to the repository root |

**Common Use Cases:**
```toml
# Open the worktree in VS Code
[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = true

# Open the plan file specifically
[hooks.plan_file_created]
command = "code-oss ${plan_path}"
enabled = true

# Send notification
[hooks.plan_file_created]
command = "notify-send 'Plan Created' '${plan_id}'"
enabled = true
```

### code_sdk_complete

**Triggered:** After the SDK session completes during `lw_coder code`, before the CLI resume session starts.

**Timing:** Between the initial SDK code generation and the interactive CLI session.

**Available Variables:**
| Variable | Description |
|----------|-------------|
| `${worktree_path}` | Path to the code worktree |
| `${plan_path}` | Path to the plan file |
| `${plan_id}` | The plan ID |
| `${repo_root}` | Path to the repository root |

**Common Use Cases:**
```toml
# Open worktree in editor
[hooks.code_sdk_complete]
command = "code-oss ${worktree_path}"
enabled = true

# Play a sound
[hooks.code_sdk_complete]
command = "paplay /usr/share/sounds/freedesktop/stereo/complete.oga"
enabled = true

# Run custom script
[hooks.code_sdk_complete]
command = "~/scripts/on-code-complete.sh ${plan_id}"
enabled = true
```

### eval_complete

**Triggered:** After evaluation completes and training data is created.

**Note:** This hook requires the round-out-eval-command feature to be implemented.

**Available Variables:**
| Variable | Description |
|----------|-------------|
| `${training_data_dir}` | Path to the training data output directory |
| `${worktree_path}` | Path to the worktree |
| `${plan_path}` | Path to the plan file |
| `${plan_id}` | The plan ID |
| `${repo_root}` | Path to the repository root |

## Variable Substitution

Variables use the `${variable}` syntax, similar to shell variables.

- All paths are absolute
- Path objects are converted to strings
- Undefined variables will cause an error (logged, doesn't fail main command)

### Example with Multiple Variables

```toml
[hooks.code_sdk_complete]
command = "echo 'Plan ${plan_id} in ${repo_root}' | tee -a ~/lw_coder.log"
enabled = true
```

## Execution Model

- **Asynchronous:** Hooks run in the background and don't block the main workflow
- **Non-blocking:** Hook failures don't fail the main command
- **Logged:** Hook executions are logged via the standard lw_coder logging system
- **Shell execution:** Commands are executed with `shell=True` for full shell syntax support

### Console Feedback

When a hook runs, you'll see:
```
→ Running plan_file_created hook in background
```

If a hook fails:
```
⚠ Hook 'plan_file_created' failed: <error message>
```

## Disabling Hooks

### Temporarily (per command)

Use the `--no-hooks` flag:

```bash
lw_coder plan --text "my idea" --no-hooks
lw_coder code my-plan --no-hooks
```

### Permanently (per hook)

Set `enabled = false` in the config:

```toml
[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = false
```

### Completely

Remove or rename `~/.lw_coder/config.toml`.

## Troubleshooting

### Test Commands Manually

Before adding a hook, test the command manually:

```bash
# Test with actual paths
code-oss /path/to/worktree

# Check the command syntax
which code-oss
```

### Common Issues

**Command not found:**
- Ensure the command is in your PATH
- Use absolute paths if needed: `/usr/bin/notify-send`

**Variable substitution failed:**
- Check that you're using the correct variable names
- Verify the variable is available for that hook

**Hook not triggering:**
- Check that `enabled = true` is set
- Verify the config file syntax with a TOML validator
- Run lw_coder with `--verbose` to see debug output

## Security Considerations

Hooks execute commands from your `~/.lw_coder/config.toml` file. This is similar to shell aliases, git hooks, or npm scripts - developer-controlled configurations that are inherently trusted.

**Important:** There is no project-level hook configuration. This prevents malicious repositories from executing commands when you run lw_coder.

For detailed security rationale, see [ADR 002: Hook Command Injection Trust Model](adr/002-hook-injection-trust.md).

## Examples

### Open Editor on Plan Creation

```toml
# For VS Code
[hooks.plan_file_created]
command = "code-oss ${worktree_path}"
enabled = true

# For Neovim in terminal
[hooks.plan_file_created]
command = "gnome-terminal -- nvim ${plan_path}"
enabled = true

# For JetBrains IDEs
[hooks.plan_file_created]
command = "idea ${worktree_path}"
enabled = true
```

### Desktop Notifications

```toml
# Linux (notify-send)
[hooks.code_sdk_complete]
command = "notify-send 'lw_coder' 'Code generation complete for ${plan_id}'"
enabled = true

# macOS (osascript)
[hooks.code_sdk_complete]
command = "osascript -e 'display notification \"Code complete\" with title \"lw_coder\"'"
enabled = true
```

### Custom Scripts

```toml
# Run a custom script with context
[hooks.code_sdk_complete]
command = "~/scripts/on-code-complete.sh '${plan_id}' '${worktree_path}'"
enabled = true
```

### Logging

```toml
# Append to a log file
[hooks.plan_file_created]
command = "echo \"$(date): Plan ${plan_id} created\" >> ~/.lw_coder/activity.log"
enabled = true
```
