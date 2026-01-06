# Threat Model & Security Assumptions

This document describes the threat model, trust boundaries, and security design decisions for weft.

## System Classification

**weft is a local developer CLI tool**, not a production web service or multi-tenant system. This classification fundamentally shapes our security posture.

## Trust Boundaries & Assumptions

### Trusted Entities
1. **Repository Owner** - Has full control over plan files and codebase
2. **Local Environment** - The developer's machine and user account are trusted
3. **Local Filesystem** - Files within the repository and home directory are under user control
4. **Dependencies** - We trust dependencies from PyPI (DSPy, python-dotenv, etc.)
5. **Home Directory Configuration** - `~/.weft/config.toml` is developer-controlled

### Threat Model Scope

**IN SCOPE:**
- Accidental misconfiguration by developers
- Clear error messages for debugging
- Protection against common mistakes
- Data leakage through logs or cache

**OUT OF SCOPE:**
- Malicious repository owners attacking themselves
- Multi-tenant security boundaries
- Untrusted user input (all input comes from repo owner)
- Production deployment security
- Network-based attacks

## Security Design Decisions

### Configuration Security

**Decision: Home-level configuration only**
- **Rationale:** Secrets should be stored once in the user's home directory, not per-repository
- **Risk Accepted:** All repositories using weft share the same credentials
- **Justification:** This matches standard CLI tool patterns (e.g., `~/.aws/credentials`, `~/.gitconfig`)
- **Implementation:** Load from `~/.weft/.env` with existence and readability validation
- **Benefit:** Prevents accidental credential commits to repositories

### Path Security

**Decision: Fixed home directory path**
- **Rationale:** Using a single, predictable location simplifies configuration and reduces misconfiguration risk
- **Risk Accepted:** Users cannot customize the configuration location
- **Justification:** Standard home directory locations are well-understood and secure
- **Implementation:** Use `Path.home() / ".weft" / ".env"` with validation
- **Note:** No path traversal concerns since path is fixed

### Cache Security

**Decision: Disk-based DSPy cache at `~/.weft/dspy_cache` without encryption**
- **Rationale:** Caching improves developer experience and reduces API costs
- **Risk Accepted:** Cached LLM responses stored in plaintext on local filesystem
- **Justification:** Local filesystem is trusted; cache data doesn't contain secrets if used properly
- **Mitigation:** Documentation warns not to include secrets in plan files; cache location clearly documented

**Decision: Standard filesystem permissions for cache**
- **Rationale:** Operating system user isolation is sufficient for single-developer machines
- **Risk Accepted:** Other users on the same machine could read cache
- **Justification:** Shared developer machines are increasingly rare; users can set permissions manually if needed
- **Note:** Consider adding `chmod 0700` in future if users request it

### Environment Variable Handling

**Decision: Global environment variable loading via `load_dotenv()`**
- **Rationale:** Standard pattern for CLI tools; simple and well-understood
- **Risk Accepted:** Environment variables persist in global `os.environ` for process lifetime
- **Justification:** Each CLI invocation is a separate process; no cross-execution leakage risk
- **Alternative Considered:** `dotenv_values()` for isolation - rejected as over-engineering for CLI tool

**Decision: No sanitization of plan content before DSPy**
- **Rationale:** Trust users to not put secrets in plan files
- **Risk Accepted:** If users include API keys in plans, they'll be sent to LLM and cached
- **Justification:** This would be equivalent to committing secrets to git - user error
- **Mitigation:** Documentation and best practices guide

### Error Handling

**Decision: Allow DSPy/LLM errors to propagate with full details**
- **Rationale:** Developers need complete error information for debugging
- **Risk Accepted:** Stack traces may include API endpoints, request details, or partial paths
- **Justification:** Errors only visible to developer on their own machine; helpful for troubleshooting
- **Implementation:** No try-except around DSPy predictor calls per plan requirements

**Decision: Detailed error messages with full file paths**
- **Rationale:** Debugging is primary use case; specificity helps developers fix issues
- **Risk Accepted:** Error messages reveal absolute paths, directory structure, file existence
- **Justification:** Developer already knows their own filesystem structure
- **Alternative Considered:** Verbose/debug flags - rejected as unnecessary complexity

### SDK Network Access

**Decision: Enable unrestricted network access for SDK sessions via `NO_PROXY="*"`**
- **Rationale:** SDK sessions need network access for WebFetch and similar tools to function correctly
- **Risk Accepted:** SDK sessions can make requests to any domain without audit trail or allowlist
  - Potential for injection attacks if malicious code is executed
  - No visibility into what external resources are accessed
- **Justification:** Local developer CLI tool with trusted codebase; external attack surface is low
  - Repository code is under developer control (same trust boundary as rest of system)
  - Not a multi-tenant or production system
  - Developer controls what code is executed
- **Mitigation:** Environment variable is scoped to SDK session only (restored after completion)
- **Reference:** NO_PROXY documented at https://code.claude.com/docs/en/settings

### Hook Execution Security

**Decision: Trust developer-controlled hook configurations**
- **Rationale:** Hooks configured in `~/.weft/config.toml` by developer on their own machine
- **Risk Accepted:** Hooks execute arbitrary commands with developer's permissions
- **Justification:** Developer creates their own config on their own machine
  - Similar trust model to git hooks, shell aliases, npm scripts
  - No untrusted input - developer would be attacking themselves
  - Standard pattern for CLI developer tools
- **Implementation:** Use `shell=True` with `string.Template` substitution
- **Mitigation:**
  - Global config only (no project-level hooks to prevent malicious repos)
  - `--no-hooks` flag to disable if needed
  - Logs show exactly what commands execute
- **Note:** Project-level command execution is now available via setup commands (see below)
- **Reference:** See [ADR 002: Hook Command Injection Trust Model](adr/002-hook-injection-trust.md)

### Setup Command Execution Security

**Decision: Trust repository-level setup command configurations**
- **Rationale:** Setup commands configured in repository's `.weft/config.toml` via `[[code.setup]]` sections
- **Risk Accepted:** Commands execute arbitrary shell commands with developer's permissions when `weft code` is run
  - Cloning and running `weft code` on an untrusted repository could execute malicious commands
  - Commands run on the host system before sandbox isolation begins
- **Justification:** User explicitly invokes `weft code` in their repository, opting into the repo's setup commands
  - Same trust model as npm scripts (`npm install`, `npm run`), Makefiles, git hooks in repos
  - Developer has already cloned the repository and is choosing to run weft on it
  - Standard practice for developer tooling that operates on repository code
- **Implementation:** Use `subprocess.run()` with `shell=True` for shell feature support
- **Mitigation:**
  - Commands only run when user explicitly invokes `weft code`
  - Working directory constrained to within repository (prevents path traversal)
  - Command names logged at info level (not full commands for security)
  - `continue_on_failure` flag allows non-critical commands to fail gracefully
- **Important:** Unlike hooks (which are user-level in `~/.weft/config.toml`), setup commands are project-level
  - Users should exercise caution when running `weft code` on untrusted repositories
  - Same level of caution as running `npm install` or `make` on untrusted code
- **Reference:** See [Configuration Guide](CONFIGURATION.md#setup-commands)

## Non-Security Quality Decisions

These aren't security issues but are documented for completeness:

**Decision: Single input field (`plan_text`) for DSPy signature**
- **Rationale:** Simplifies signature; metadata embedded in plan text
- **Implementation:** Orchestrator builds complete plan text with metadata header

**Decision: No fallback prompt generation**
- **Rationale:** DSPy must be properly configured; fallbacks hide configuration issues
- **Risk:** Tool fails if DSPy/LLM not configured
- **Justification:** Clear failure is better than degraded silent operation

**Decision: Template constants exist but are unused**
- **Rationale:** Documentation only; show example prompt structure
- **Note:** Tests verify templates exist but they're not used in code

**Decision: Non-atomic quick-fix ID generation (TOCTOU race condition accepted)**
- **Risk Accepted:** Concurrent `weft code --text` invocations (~20ms window) could generate duplicate IDs, causing silent file overwrite
- **Justification:** Single-developer CLI tool; race requires near-simultaneous execution; user can re-run if collision occurs

## Security Boundary Summary

```
┌─────────────────────────────────────────────────────┐
│ TRUSTED: Developer's Local Machine                  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ TRUSTED: Repository (user controlled)        │  │
│  │  - .weft/tasks/*.md (plan files)             │  │
│  │  - .weft/config.toml (setup commands)        │  │
│  │  - Source code                               │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ TRUSTED: User's home directory               │  │
│  │  - ~/.weft/.env (secrets)                    │  │
│  │  - ~/.weft/config.toml (hook config)         │  │
│  │  - ~/.weft/dspy_cache                        │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  UNTRUSTED EXTERNAL:                               │
│  - LLM API responses (handled by DSPy)             │
│  - Git repository contents (user controlled)       │
└─────────────────────────────────────────────────────┘
```

## Future Considerations

If weft evolves into a different use case (multi-tenant service, production deployment, CI/CD integration), the following should be reconsidered:

1. **Cache encryption** - Protect sensitive data at rest
2. **Environment variable isolation** - Use `dotenv_values()` or context managers
3. **XDG compliance** - Respect `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` for configuration and cache locations
4. **Error sanitization** - Redact sensitive paths in production logs
5. **Rate limiting** - Prevent API abuse
6. **Audit logging** - Track security-relevant operations
7. **Per-repository credentials** - Support different API keys for different projects

## References

- Code-bug-analyzer findings: See internal analysis reports
- DSPy security considerations: https://dspy.ai/
- Host execution security: Standard Unix file permissions and environment isolation
