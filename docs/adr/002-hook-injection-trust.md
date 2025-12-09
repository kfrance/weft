# ADR 002: Hook Command Injection Trust Model

## Status

Accepted

## Context

lw_coder needs a hook system to execute user-configured commands at key workflow points (e.g., opening an editor after plan creation, sending notifications after code completion). The question is how to handle command execution securely.

Traditional web applications must sanitize all user input to prevent command injection attacks. However, lw_coder is a local CLI tool where the "user" configuring hooks is the same developer who will be affected by any commands executed.

## Decision

**Trust developer-controlled hook configurations and use `shell=True` for command execution.**

The hook system will:
1. Load commands from `~/.lw_coder/config.toml` (developer's home directory)
2. Execute commands using `subprocess.Popen(..., shell=True)`
3. Use `string.Template` for `${variable}` substitution
4. Not attempt to sanitize, escape, or restrict commands

## Rationale

### Developer is the user, not an attacker

The developer creates their own `~/.lw_coder/config.toml` on their own machine. Any "malicious" command would only affect themselves. This is identical to:

- **Git hooks**: `.git/hooks/` scripts run arbitrary code
- **Shell aliases**: `~/.bashrc` aliases execute any command
- **npm scripts**: `package.json` scripts run arbitrary code
- **Makefile targets**: `Makefile` targets execute any command
- **VS Code tasks**: `.vscode/tasks.json` runs arbitrary commands

All of these are trusted without sanitization because the developer controls the configuration.

### No untrusted input

The hook command comes from:
1. The developer's home directory config file
2. Variable values (paths) from lw_coder internals

There is no external, untrusted input that could inject malicious commands. The developer would have to intentionally write a malicious config to attack themselves.

### Usability over defense-in-depth

Using `shell=True` provides several benefits:
- Commands work exactly as typed in a shell
- Shell features (pipes, redirects, globs) work naturally
- No complex argument parsing or escaping needed
- Matches developer expectations from other CLI tools

The alternative (argument list parsing with `shlex.split`) adds complexity without providing security benefits in this trust model.

## Consequences

### Positive

- Simple implementation using `string.Template` and `shell=True`
- Commands behave identically to shell execution
- Developers can use full shell syntax in hooks
- Clear trust boundary: home directory config is trusted

### Negative

- If a developer misconfigures a hook, it could cause unintended effects
- Mitigation: Detailed logging shows exactly what commands execute
- Mitigation: `--no-hooks` flag allows disabling hooks when needed

### Security Boundary

```
TRUSTED BOUNDARY
├── ~/.lw_coder/config.toml (developer-created)
├── Variable values (lw_coder internal paths)
└── Result: Commands execute with developer's permissions

UNTRUSTED (not applicable in this system)
├── Network input
├── User-submitted data
└── Third-party content
```

## Alternatives Considered

### 1. Argument list parsing with shlex.split

- Rejected: Adds complexity without security benefit
- Shell features wouldn't work (pipes, redirects)
- Still executes arbitrary commands, just with more friction

### 2. Command whitelist

- Rejected: Too restrictive for legitimate use cases
- Would prevent custom scripts, notification tools, etc.
- Developers would work around it anyway

### 3. Webhook-only integration

- Rejected: HTTP webhooks are more complex to set up
- Requires running a local server
- Less flexible than shell commands

### 4. No project-level config (accepted limitation)

- Project-level `.lw_coder/config.toml` could be malicious
- Clone repo, run lw_coder, execute attacker's commands
- Solution: Only support global `~/.lw_coder/config.toml`
- Future: Could add project config with explicit approval workflow

## References

- [OWASP Command Injection](https://owasp.org/www-community/attacks/Command_Injection) - describes the threat model for untrusted input (not applicable here)
- Git hooks documentation - example of trusted local code execution
- npm scripts documentation - example of trusted package.json commands
