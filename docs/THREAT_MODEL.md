# Threat Model & Security Assumptions

This document describes the threat model, trust boundaries, and security design decisions for lw_coder.

## System Classification

**lw_coder is a local developer CLI tool**, not a production web service or multi-tenant system. This classification fundamentally shapes our security posture.

## Trust Boundaries & Assumptions

### Trusted Entities
1. **Repository Owner** - Has full control over `.lw_coder/config.toml`, plan files, and codebase
2. **Local Environment** - The developer's machine and user account are trusted
3. **Local Filesystem** - Files within the repository are under user control
4. **Dependencies** - We trust dependencies from PyPI (DSPy, python-dotenv, etc.)

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

**Decision: No Docker argument validation**
- **Rationale:** Users control their own `.lw_coder/config.toml` and docker arguments
- **Risk Accepted:** Users could configure dangerous flags like `--privileged` or `--volume=/:/host`
- **Justification:** This is equivalent to users writing their own shell scripts - we trust them not to harm themselves
- **Mitigation:** Documentation clearly explains docker argument implications

**Decision: Allow wildcard environment variable forwarding**
- **Rationale:** Developers may legitimately need to forward many environment variables
- **Risk Accepted:** `forward_env = ["*"]` exposes all environment variables to Docker
- **Justification:** Users control their own environment and can see exactly what's being forwarded
- **Mitigation:** Log warning when `*` is used; document recommended patterns like `OPENROUTER_*`

### Path Security

**Decision: Path traversal protection with resolved paths**
- **Rationale:** Prevent accidental loading of unintended files
- **Risk Accepted:** Symlink bypass possible if user creates malicious symlinks in their own repo
- **Justification:** Users who can create symlinks already have full repository control
- **Implementation:** Use `Path.resolve()` and `relative_to()` checks for env_file validation
- **Note:** This protects against mistakes, not malicious repository owners

### Cache Security

**Decision: Disk-based DSPy cache at `~/.lw_coder/dspy_cache` without encryption**
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

## Security Boundary Summary

```
┌─────────────────────────────────────────────────────┐
│ TRUSTED: Developer's Local Machine                  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ TRUSTED: Repository (user controlled)        │  │
│  │  - .lw_coder/config.toml                     │  │
│  │  - .lw_coder/tasks/*.md                      │  │
│  │  - .env file                                 │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ TRUSTED: User's home directory               │  │
│  │  - ~/.lw_coder/dspy_cache                    │  │
│  │  - ~/.lw_coder/logs                          │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  UNTRUSTED EXTERNAL:                               │
│  - LLM API responses (handled by DSPy)             │
│  - Git repository contents (user controlled)       │
└─────────────────────────────────────────────────────┘
```

## Future Considerations

If lw_coder evolves into a different use case (multi-tenant service, production deployment, CI/CD integration), the following should be reconsidered:

1. **Docker argument allowlisting** - Prevent privilege escalation
2. **Cache encryption** - Protect sensitive data at rest
3. **Environment variable isolation** - Use `dotenv_values()` or context managers
4. **Symlink validation** - Check `is_symlink()` before path resolution
5. **XDG compliance** - Respect `XDG_CACHE_HOME` for cache location
6. **Error sanitization** - Redact sensitive paths in production logs
7. **Rate limiting** - Prevent API abuse
8. **Audit logging** - Track security-relevant operations

## References

- Code-bug-analyzer findings: See internal analysis reports
- DSPy security considerations: https://dspy.ai/
- Docker security best practices: https://docs.docker.com/engine/security/
