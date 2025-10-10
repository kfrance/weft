---
plan_id: implement-dspy-code-command
git_sha: de528997b23028fdd0732ae6d17a8c11ad6c6348
status: done
evaluation_notes:
  - Did the DSPy signature generate prompts with placeholder text (e.g., `{plan_text}`) instead of embedding the actual plan content? Was the signature docstring explicit enough to instruct the LLM to directly embed the complete plan text rather than creating a template?
  - Were the droid configuration files written with proper YAML frontmatter (name, model, tools fields) as required by Factory.ai custom droids? Did the implementation correctly distinguish between plain prompt files (main.md) and droid configuration files (subagent .md files)?
---

# Task Plan: Integrate DSPy Prompts into the `lw_coder code` Workflow

## Objectives
- Wire the existing DSPy prompt pipeline into `lw_coder code` so each coding run materializes prompts, prepares run assets, and launches the interactive droid session end-to-end.
- Persist run-scoped artifacts under `.lw_coder/runs/<plan_id>/<timestamp>/` while pruning stale directories and keeping plan-only subagents out of coding sessions.
- Ensure the command validates plan metadata, operates from a durable worktree, and streams droid feedback summaries back to the user before exit.

## Requirements & Constraints
- Reuse the implemented DSPy signature and prompt orchestrator in `src/lw_coder/dspy/` to produce the main and subagent prompts; callers must pass validated `PlanMetadata` and plan body text.
- Write prompts to the run directory structure expected by downstream tooling (`prompts/main.md`, `droids/code-review-auditor.md`, `droids/plan-alignment-checker.md`) and log their locations; maintain ASCII encoding.
- Treat `.lw_coder/config.toml` as the single source of truth for the code workflow: respect the `[code]` table fields (`env_file`, `forward_env`, `docker_build_args`, `docker_run_args`) and surface actionable errors when configuration is invalid or referenced `.env` files are missing.
- Manage `.lw_coder/runs/` lifecycle so new sessions create timestamped directories, copy the baseline coding droids (excluding `src/lw_coder/droids/plan/`), and prune directories older than 30 days without touching active runs.
- Ensure the coding worktree comes from `ensure_worktree` and is left on disk after the session; update the shared droid session helper so plan/code share mount logic, gitdir patching, and Docker invocation assembly.
- Docker requirements:
  - Verify `lw_coder_droid:latest` exists, building from `docker/droid/Dockerfile` when necessary, then build/tag a repo-scoped image (e.g., `lw_coder_droid:<repo_hash>`) using `.lw_coder/code.Dockerfile` with `--ignorefile .lw_coder/.dockerignore`.
  - Mount run prompt files at `/tmp/lw_coder/main_prompt.md` and coding droids under `/home/droiduser/.factory/droids`; mount shared assets used by `lw_coder plan` (auth, settings, tasks, git metadata) so session parity is preserved.
  - Install the `context7` MCP inside the repo-specific image via `droid mcp add --transport http context7 https://mcp.context7.com/mcp`.
- DSPy/LiteLLM must use OpenRouter settings from the loaded `.env` and leverage the on-disk cache configured by the prompt orchestrator; command output should make it clear when cached prompt generations are reused.
- Maintain current logging structure (e.g., “Plan validation succeeded”, “Worktree prepared”) and propagate exceptions with clear remediation guidance; do not swallow original tracebacks.

## Work Items
1. **Orchestrate Prompt Generation & Run Asset Setup**
   - Invoke the prompt orchestrator after plan validation, create the timestamped run directory, copy coding droids, and emit log statements with artifact paths.
   - Implement pruning logic for `.lw_coder/runs/` (30-day retention) with safeguards against deleting the active run or non-run directories.
2. **Enhance Shared Droid Session Helper**
   - Extend the helper to compose Docker mounts for prompts, droids, config assets, and the worktree while patching git metadata for the run.
   - Ensure container teardown leaves the worktree intact and logs follow-up instructions for resuming the session if needed.
3. **Extend `lw_coder code` Command**
   - Load code configuration, prepare/build Docker images, and launch the interactive container while streaming droid output.
   - Surface subagent feedback summaries reported by the droid before exit and leave the worktree path visible to the user.
4. **Testing & Verification**
   - Unit tests covering run directory creation/pruning, config-driven environment forwarding, Docker command assembly, and MCP installation hooks.
   - Integration test (or CLI-level test) that simulates a full code run with mocked Docker/DSPy layers, asserting prompts are generated and mounted as expected.
5. **Documentation & UX Polish**
   - Update CLI usage docs and `docs/configuration.md` with coding workflow behavior, run-directory retention policy, Docker image lifecycle, and troubleshooting tips for OpenRouter or caching issues.
   - Provide user-facing log or status messages indicating when prompt assets are ready, when Docker builds start, and how to locate run artifacts post-session.

## Deliverables
- Updated `lw_coder code` workflow and supporting helpers integrating the DSPy prompt pipeline, run asset management, and Docker session launch.
- Automated pruning of stale `.lw_coder/runs/` directories with tests validating retention boundaries.
- Extended tests covering configuration wiring, prompt generation invocation, Docker command composition, and droid session launch behavior.
- Documentation updates detailing the end-to-end coding command flow, run artifact locations, caching expectations, and required project configuration files.

## Out of Scope
- Re-implementing the DSPy prompt pipeline, configuration loader, or documentation already delivered by `dspy-prompt-pipeline`.
- GEPA optimization routines, automatic prompt tuning, or additional subagent types beyond the existing set.
- Supporting non-droid execution modes or remote repository operations.
- Automating cleanup of archived worktrees beyond logging their locations.
