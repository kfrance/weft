---
plan_id: plan-switch-to-logging
branch_name: lw/logging/switch-to-logging
git_sha: 6488c0e47c1e773607a2176afda6057c71157a0f
status: done
evaluation_notes:
  - Does the CLI respect the new --debug flag by adjusting only the logging level?
  - Are both console and rotating file handlers covered by tests or verified through integration behavior?
  - Do we document the new logging behavior and ensure existing prints are removed or migrated?
---

# Task Plan: Adopt Python Logging Infrastructure

## Objectives
- Replace direct stdout/stderr messaging with the `logging` module while preserving user-visible behavior.
- Configure a rotating daily log file at `~/.lw_coder/logs/lw_coder.log` retaining 30 days of history alongside console logging.
- Expose a `--debug` CLI flag that enables DEBUG-level verbosity without changing the default INFO level.

## Requirements & Constraints
- Logging must initialize once, ideally during CLI bootstrapping, to avoid duplicate handlers in tests or repeat invocations.
- File handler should ensure the `~/.lw_coder/logs` directory exists, rotating daily (`TimedRotatingFileHandler` with 30 backups).
- Console output remains human-friendly; error paths still exit with appropriate status codes.
- Debug flag only alters logging level (no other side effects) and should be testable through CLI invocation.
- Avoid introducing third-party dependencies; rely on Python's standard logging components.
- Update or add tests ensuring CLI success/failure scenarios capture logging changes without polluting test output.

## Work Items
1. **Logging Infrastructure**
   - Introduce a logging utility (module or helper) that configures console + timed rotating file handlers.
   - Ensure directory creation for `~/.lw_coder/logs` is handled safely (idempotent).
   - Remove existing `print` usage in favor of `logger` calls with appropriate levels.
2. **CLI Enhancements**
   - Extend CLI usage help to document `--debug` flag and wire it to logging level configuration.
   - Ensure CLI exit codes remain unchanged; logging messages should mirror prior user-facing strings where applicable.
3. **Testing & Documentation**
   - Adjust CLI tests to accommodate logging (e.g., capturing stdout/stderr expectations).
   - Add targeted tests for logging configuration (e.g., verifying handlers or log level toggling).
   - Update README or project docs to describe logging behavior, log file location, and debug usage.

## Deliverables
- Updated source introducing configured logging and CLI flag support.
- Tests demonstrating the new logging behavior without regressions.
- Documentation updates reflecting logging setup and usage.

## Out of Scope
- Multi-process logging coordination or remote log aggregation.
- Configurable log paths beyond the fixed `~/.lw_coder/logs` directory.
- Structured logging or JSON log output.
