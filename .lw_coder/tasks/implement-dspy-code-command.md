---
plan_id: implement-dspy-code-command
git_sha: de528997b23028fdd0732ae6d17a8c11ad6c6348
status: draft
evaluation_notes: []
---

# Task Plan: Implement DSPy-Driven Code Command Workflow

## Objectives
- Extend the `lw_coder code` command to drive an interactive droid coding session that first generates main and subagent prompts via a DSPy signature.
- Persist DSPy-generated prompt assets inside run-scoped directories under `.lw_coder/runs/` so GEPA can later optimize them without polluting tracked sources.
- Ensure the workflow consumes validated plan metadata, executes within a dedicated worktree that remains after the run, and surfaces the droid feedback summary to the user during the session (without host-side persistence).

## Requirements & Constraints
- DSPy signature lives at `src/lw_coder/dspy/code_prompt_signature.py` (or package) and accepts `PlanMetadata`; it returns three prompts (main, review subagent, plan-alignment subagent) plus a structured feedback summary slot.
- Generated prompts are written under the active repo’s `.lw_coder/runs/<plan_id>/<timestamp>/` directory (e.g., `prompts/main.md`, `droids/code-review-auditor.md`, `droids/plan-alignment-checker.md`) so each coding run keeps isolated artifacts. Plan-only subagents continue to live in `src/lw_coder/droids/plan/` (mounted only by the plan command) and must not be copied into the coding run directory; run-specific directories older than 30 days should be pruned when new runs are added.
- Each repository must supply a `.lw_coder/config.toml` and `.lw_coder/code.Dockerfile` that drive the code command: the config exposes a `[code]` table with `env_file` (default `.env`, required when set), optional `forward_env` (defaults to `OPENROUTER_*`, supports `"*"` with a warning), plus `docker_build_args` and `docker_run_args` arrays; the Dockerfile extends the base droid image to install project dependencies. Validation must raise actionable errors for missing keys, absent env files, or unknown options.
- Main prompt must instruct droid to (1) follow the coding plan, (2) run both subagents, and (3) present a detailed summary of each subagent’s feedback and the actions taken directly to the interactive user before finishing.
- Ensure the droid Docker image has the `context7` MCP installed via `droid mcp add --transport http context7 https://mcp.context7.com/mcp` (no API key required) so the agent can access that tool during coding runs.
- Configure DSPy/LiteLLM to route through OpenRouter using `.env` configuration (e.g., `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_MODEL`), defaulting to the Sonnet 4.5 model for droid runs; load the `.env` using `python-dotenv` and enable DSPy caching (see https://dspy.ai/tutorials/cache/) so repeated invocations reuse cached responses during development and tests.
- `lw_coder code` reuses plan validation, prepares (and leaves behind) the plan worktree via `ensure_worktree`, manages prompt temp files securely, and—together with the plan command—invokes a shared "droid session" helper that patches the worktree `.git` pointer and composes the Docker invocation (mounts, security opts) from a common code path.
- Interactive Docker session mirrors the plan command pattern but mounts the run-specific prompt file at `/tmp/lw_coder/main_prompt.md` and a synthesized coding subagents directory at `/home/droiduser/.factory/droids`, keeping plan-only assets unmounted; user exits manually (`exit`/Ctrl+C). Before launching the container, the CLI copies the required baseline droids from the lw_coder repo into the run-specific directory (excluding plan-only subagents) so only the intended coding droids are available. The container must also mount the shared assets that `lw_coder plan` depends on today (`auth.json`, `container_settings.json`, repo tasks directory, git metadata) so authentication and settings continue to work. The docker image tag should encode repository identity (e.g., `lw_coder_droid:<repo_hash>`). Before every coding run, the CLI ensures the base image `lw_coder_droid:latest` exists (building `docker/droid/Dockerfile` if necessary), then invokes `docker build` for the repo-scoped tag (passing `--ignorefile .lw_coder/.dockerignore` so repo-specific ignore rules apply); Docker/BuildKit caching handles no-op builds, and the CLI simply notifies the user that the image build is running.
- Use the latest DSPy release (bringing LiteLLM) when adding dependencies.
- Maintain ASCII files and respect existing logging and error-handling conventions.

## Work Items
1. **Baseline Refactor & Command Skeleton**
   - Introduce a new `code_command.py` (or equivalent) that will orchestrate plan validation, worktree preparation via `ensure_worktree`, DSPy invocation, Docker image builds, and the interactive session, returning an exit code.
   - Update `cli.py` so it simply dispatches to `run_plan_command` or the new `run_code_command`, keeping the entry point thin.

2. **Define DSPy Integration & Configuration**
    - Add dependency notes (latest DSPy, bundled LiteLLM); specify OpenRouter env vars, `.env` placement, and leveraging `python-dotenv` in code.
    - Update the droid Docker image build to install the Context7 MCP once (`droid mcp add --transport http context7 https://mcp.context7.com/mcp`) so every container has the tool preconfigured.
    - Implement the DSPy signature module (`CodePromptSignature`), including schema for inputs/outputs and initial prompt templates.
    - Prepare a small orchestrator that loads `.env`, initializes DSPy caching, calls the signature, writes the three prompt files into `.lw_coder/runs/<plan_id>/<timestamp>/`, prunes runs older than 30 days, and returns file paths plus the feedback summary structure.
    - Document the `.lw_coder/config.toml` contract in `docs/configuration.md`: required `[code]` table, field defaults (including the implicit `OPENROUTER_*` pass-through when `forward_env` is omitted), type checking, handling of the wildcard `"*"` option, and validation errors for missing env files or unknown keys.
    - Add a `config_loader.py` (or similar) module that parses `.lw_coder/config.toml`, applies defaults, emits warnings for `"*"`, and returns a typed configuration object used by the code command.
    - For this repository, scaffold `.lw_coder/config.toml` with the chosen env file path, forwarded OpenRouter variables, and any docker options (e.g., cache mounts) required for uv.

3. **Persist Prompt Assets & Docker Templates**
    - Introduce a `runs_manager.py` (or similar) module that creates timestamped run directories under `.lw_coder/runs/<plan_id>/<timestamp>/`, prunes entries older than 30 days when new runs start, copies baseline coding droids from `src/lw_coder/droids` (excluding anything under `src/lw_coder/droids/plan/`), and surfaces prompt/droid paths back to the CLI.
    - Use the runs manager so the DSPy orchestrator writes the main prompt and both subagent prompts atomically into the run directory, keeping artifacts auditable without polluting tracked source files.
    - For this repository, create `.lw_coder/code.Dockerfile` that installs uv, syncs dependencies, ensures `uv run pytest` is available inside the container, and installs the context7 MCP during the build.

4. **Wire Up `lw_coder code` & Docker Builds**
    - Extend the command to load `PlanMetadata`, invoke the DSPy orchestrator (which uses `python-dotenv` to load `.env` and returns run directory paths), and log the per-run artifact directory.
    - Build the Docker command via the shared droid session helper, mounting the generated main prompt to `/tmp/lw_coder/main_prompt.md` and the generated subagents directory to `/home/droiduser/.factory/droids`, avoiding plan-only assets, while preserving the existing mounts for auth/settings/tasks/git metadata.
    - Extract the `.git` pointer rewrite/restore logic into the shared session helper so containerised runs consistently reference `/repo-git/worktrees/<name>`.
    - Ensure the droid run operates inside the plan’s worktree via `ensure_worktree`, leaves the worktree untouched after the container exits, and keeps plan temp-worktree helpers clearly separated in code structure/documentation.
    - Ensure the base image `lw_coder_droid:latest` exists by building `docker/droid/Dockerfile` when missing or out of date, keeping parity with the existing test suite.
    - Always invoke `docker build --tag lw_coder_droid:<repo_hash> --file .lw_coder/code.Dockerfile --ignorefile .lw_coder/.dockerignore .` (or equivalent) after the base image check so repo-provided ignore rules trim the build context; log that the image build is running and rely on BuildKit to short-circuit unchanged inputs.
    - Respect the env file path defined in `.lw_coder/config.toml` when forwarding secrets into the container (e.g., load `.env.local` if configured) and surface errors if the file is missing.
    - When `forward_env` is omitted, automatically forward environment variables matching `OPENROUTER_*`; when it contains `"*"`, forward all host variables and emit a warning to the user about broad exposure.
    - Ensure the new `code_command` module wires together plan validation, config loading, DSPy prompt generation, run directory management, Docker image builds, env forwarding, and the shared droid session helper into a cohesive execution path that returns an exit status.

5. **Surface Feedback Summary**
   - Ensure the generated main prompt explicitly tells droid to display the subagent feedback summary interactively before exit; no additional host-side capture required.

6. **Testing & Tooling**
   - Add unit tests for DSPy orchestration that run against the real DSPy signature with caching enabled (no mocking) to verify run-directory creation, pruning of stale runs, file writes, and metadata usage.
   - Provide integration tests that execute the live `lw_coder code` command, inspect the running docker container, and confirm mounts and worktree usage without monkeypatching subprocesses.
   - Add a smoke integration test that builds the repo-specific image and runs `uv run pytest` inside the container to prove the template supports test execution.
   - Provide additional integration smoke tests

## Test Scenarios (Gherkin, Level: Normal)
```gherkin
Feature: DSPy-driven code command workflow

  Background:
    Given a repository with a valid plan file at .lw_coder/tasks/sample-plan.md
    And the plan references git_sha de528997b23028fdd0732ae6d17a8c11ad6c6348
    And .env defines OPENROUTER_API_KEY, OPENROUTER_BASE_URL, and OPENROUTER_MODEL
    And the DSPy cache directory is empty

  Scenario: Run directory is created with cached prompts
    When I execute `lw_coder code .lw_coder/tasks/sample-plan.md`
    Then a new directory appears under `.lw_coder/runs/sample-plan/<timestamp>/`
    And `prompts/main.md` and `droids/code-review-auditor.md` and `droids/plan-alignment-checker.md` exist inside that directory
    And rerunning the command reuses cached DSPy responses without additional API calls

  Scenario: Old run directories are pruned on new run
    Given `.lw_coder/runs/sample-plan/` contains runs older than 30 days
    When I execute `lw_coder code .lw_coder/tasks/sample-plan.md`
    Then run directories older than 30 days are deleted
    And the new run directory remains

  Scenario: Docker container sees only code assets
    When I execute `lw_coder code .lw_coder/tasks/sample-plan.md`
    Then inside the droid container `/tmp/lw_coder/main_prompt.md` exists and matches the generated prompt
    And `/home/droiduser/.factory/droids` contains only the run-specific code subagents
    And no plan subagent files are present in the container

  Scenario: Configurable env file path is honored
    Given `.lw_coder/config.toml` specifies `env_file = ".env.local"`
    And `.env.local` defines OPENROUTER_API_KEY
    When I execute `lw_coder code .lw_coder/tasks/sample-plan.md`
    Then the container receives OPENROUTER_API_KEY from `.env.local`
    And the command succeeds without referencing `.env`

  Scenario: Repository-specific Docker image reuse
    Given `.lw_coder/code.Dockerfile` and `.lw_coder/config.toml` have not changed since the last run
    When I execute `lw_coder code .lw_coder/tasks/sample-plan.md`
    Then the command runs `docker build` for `lw_coder_droid:<repo_hash>`
    And Docker reuses cached layers so the build completes quickly
    And the logs show the image build invocation before the interactive session starts

  Scenario: Repository Docker image rebuild rationale
    Given `.lw_coder/code.Dockerfile` was modified since the last run
    When I execute `lw_coder code .lw_coder/tasks/sample-plan.md`
    Then the command rebuilds the docker image `lw_coder_droid:<repo_hash>`
    And the logs note that the image build is running before launching droid

  Scenario: Base image built on demand
    Given `lw_coder_droid:latest` is not present locally
    When I execute `lw_coder code .lw_coder/tasks/sample-plan.md`
    Then the CLI builds `docker/droid/Dockerfile` into `lw_coder_droid:latest`
    And the subsequent repo-specific build succeeds using that base tag

  Scenario: Context7 MCP available inside droid container
    When the docker image is built
    Then the `droid mcp list` command inside the container includes `context7`
    And running `droid mcp describe context7` succeeds without additional setup

  Scenario: Pytest executable available in repo image
    When I build the repo-specific docker image
    And I run `uv run pytest --version` inside the container
    Then the command exits successfully and prints the pytest version

  Scenario: Worktree separation is preserved
    When I execute `lw_coder code .lw_coder/tasks/sample-plan.md`
    Then the command uses `ensure_worktree` to prepare the coding worktree
    And no temporary worktree created by `create_temp_worktree` is removed
    And the worktree path remains after the command exits

  Scenario: Missing OpenRouter configuration fails fast
    Given `.env` is missing `OPENROUTER_API_KEY`
    When I execute `lw_coder code .lw_coder/tasks/sample-plan.md`
    Then the command exits with a non-zero status
    And it logs guidance for configuring OpenRouter credentials

  Scenario: DSPy caching active during tests
    Given the DSPy cache directory is pre-populated for sample-plan
    When I run the unit test suite
    Then the tests execute without making external OpenRouter calls
    And they assert the cached responses were utilized
```

- DSPy signature module and supporting orchestration code in `src/lw_coder/dspy/`.
- Run-specific prompt artifacts written beneath `.lw_coder/runs/<plan_id>/<timestamp>/` (main prompt and coding subagents only) with logging that surfaces their locations, explicit exclusion of `src/lw_coder/droids/plan/` assets, and automatic pruning of outdated runs.
- Enhanced `lw_coder code` command with interactive droid execution, context7 MCP availability, Docker mount clarity, config-driven env forwarding, and clear separation between temporary plan worktrees and persistent coding worktrees.
- Shared droid session helper (including gitdir patching) plus typed config loader and runs manager modules so plan/code share mount logic, config parsing, and `.lw_coder/runs/` lifecycle management.
- Documentation covering OpenRouter `.env` configuration (Sonnet 4.5 default with `python-dotenv`), `.lw_coder/config.toml` schema (fields, defaults, validation rules) in `docs/configuration.md`, Docker tagging rules, rebuild notifications, dependency installation steps, and new CLI usage, including how the base image `lw_coder_droid:latest` is maintained.
- Checked-in `.lw_coder/config.toml` and `.lw_coder/code.Dockerfile` for this repository, configured for uv dependency sync, `uv run pytest`, and context7 MCP installation during image build.
- Test coverage for the new DSPy integration, run-directory management (including pruning), Docker invocation path, config handling, and repository image rebuild logic.

## Out of Scope
- GEPA training loop changes or automatic prompt optimization.
- Non-droid coding tools (`--tool` values other than `droid`).
- Automating plan creation or plan subagent updates.
- Remote repo interactions (push/pull) or automated git commit flows.
- Cleanup automation for residual prompt artifacts or worktrees beyond logging their locations.
- Authoring or maintaining repository `.lw_coder/.dockerignore` files.
