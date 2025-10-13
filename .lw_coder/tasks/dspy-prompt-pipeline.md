---
plan_id: dspy-prompt-pipeline
git_sha: 8a87804ab65ba01b8eefcf6fa81e1fd9a1c96fc6
status: done
evaluation_notes:
  - Were any fallback prompts made or ways to skirt around using DSPy?
  - Confirm if your implementation provides a starting point for prompts in the Signature using one of these valid approaches (1) a docstring in a class-based Signature, (2) the with_instructions method on a Signature, or (3) the instructions parameter in the Signature constructor.
  - Did any tests mock out DSPy or the LLM that it uses? It should be making calls to openrouter or hit cached results if the tests have run before?

# Task Plan: Implement DSPy Prompt Pipeline & Configuration Layer

## Objectives
- Add a reusable DSPy signature and orchestrator that generate the main coding prompt and two subagent prompts directly from plan metadata.
- Parse `.lw_coder/config.toml` so the code command knows which `.env` file to load, which environment variables to forward, and what Docker arguments to apply.
- Write prompt artifacts into a provided run directory using the folder structure expected by later workflow steps (`prompts/main.md`, `droids/code-review-auditor.md`, `droids/plan-alignment-checker.md`).
- Ensure all new functionality is covered by unit tests plus an integration test that invokes the orchestrator with the real `.env` already present at the project root.

## Requirements & Constraints
- The DSPy signature module lives in `src/lw_coder/dspy/code_prompt_signature.py`. It must accept only the complete plan text (with metadata embedded) and produce three prompt strings (main, review subagent, plan-alignment subagent). The signature uses a class-based approach with a comprehensive docstring to instruct DSPy on what to generate. No fallback mechanisms or template-based generation are allowed—DSPy must be used directly.
- Provide an orchestrator module (e.g., `src/lw_coder/dspy/prompt_orchestrator.py`) that:
  - Loads configuration via the new `config_loader`.
  - Uses `python-dotenv` to load the configured `.env` file before initializing DSPy.
  - Enables DSPy disk caching (per https://dspy.ai/tutorials/cache/) stored under `~/.lw_coder/dspy_cache` so repeated runs reuse cached responses. Initial runs may hit OpenRouter; the on-disk cache keeps subsequent runs fast.
  - Builds complete plan text by embedding metadata (plan_id, git_sha, status, evaluation_notes) into the plan body text.
  - Calls the DSPy signature with only the complete plan text to obtain three prompt strings (no fallback mechanisms).
  - Writes files under `<run_dir>/prompts/main.md`, `<run_dir>/droids/code-review-auditor.md`, and `<run_dir>/droids/plan-alignment-checker.md`. Create parent folders as needed.
  - Returns a dataclass/typed object containing the written `Path`s so downstream workflow code can mount them in Docker.
- A new `src/lw_coder/config_loader.py` must parse `.lw_coder/config.toml` with the following behavior:
  - Require a `[code]` table. Fields: `env_file` (default `.env`, must exist when specified), optional `forward_env` list (default to `['OPENROUTER_*']`, allow `"*"` but log a warning), `docker_build_args` (list of strings, default empty), `docker_run_args` (list of strings, default empty).
  - Validate types and raise a custom `ConfigLoaderError` with actionable messages on failure (missing table, wrong type, unknown keys, missing env file, etc.).
  - Resolve the `.env` path relative to the repo root supplied by callers.
- For this repository, add a baseline `.lw_coder/config.toml` using default settings so the loader has concrete data to parse.
- Update `docs/configuration.md` to document the `[code]` table, defaults, examples for forwarding OpenRouter variables, and how DSPy uses the configured `.env` for OpenRouter credentials alongside disk caching.
- Update dependencies using `uv` commands (e.g., `uv pip install dspy-ai python-dotenv`) so `pyproject.toml` and lockfiles stay in sync while adding DSPy (latest release), python-dotenv, and any additional packages the orchestrator requires.
- The orchestrator should be callable from the existing `run_code_command` workflow (the foundation work already introduced `code_command.py` and `droid_session.py`), but wiring the full command happens in a later plan—here we just expose clean entry points.

## Work Items
1. **Add Configuration Loader**
   - Implement `src/lw_coder/config_loader.py` with `ConfigLoaderError` and `load_code_config(repo_root: Path) -> CodeConfig` (a dataclass capturing resolved paths and option lists).
   - Validate defaults and error cases as described; log a warning when `forward_env` contains `"*"`.

2. **Implement DSPy Signature**
   - Create `CodePromptSignature` in `code_prompt_signature.py` with a single input field `plan_text` (string containing complete plan with embedded metadata).
   - Use a comprehensive docstring in the class-based signature to instruct DSPy on generating three prompts.
   - Main prompt must instruct the agent to run both subagents IN PARALLEL for efficiency.
   - Review prompt must focus on test quality (no test cheating, proper mocking of dependencies/API/I/O, test appropriateness, test independence) and NOT include performance optimization checks.
   - Alignment prompt checks requirements coverage, scope adherence, and evaluation criteria.
   - Template constants may exist for documentation but must NOT be used as fallback mechanisms.

3. **Implement Prompt Orchestrator**
   - Add `generate_code_prompts(plan_metadata: PlanMetadata, run_dir: Path) -> PromptArtifacts` in `prompt_orchestrator.py`.
   - Load `.env` using `python-dotenv` based on the resolved config; initialize DSPy caching directory at `Path.home() / ".lw_coder" / "dspy_cache"` (create it if absent).
   - Build complete plan text by embedding metadata header (plan_id, git_sha, status, evaluation_notes) with the plan body text.
   - Call DSPy signature with only the complete plan text (no fallback error handling - let DSPy errors propagate).
   - Ensure files are written with newline termination and trimmed whitespace; return their `Path`s in `PromptArtifacts`.
   - Log where prompts were written.

4. **Documentation & Dependency Updates**
   - Update `docs/configuration.md` with `[code]` table details, default behaviors, example TOML, instructions for setting OpenRouter variables, and mention that DSPy writes cache data to `~/.lw_coder/dspy_cache`.
   - Use `uv` to add/upgrade dependencies (DSPy latest, python-dotenv, any supporting packages) so manifests and lockfiles remain consistent.

5. **Testing**
   - Unit tests for `config_loader` covering: happy path, missing `[code]`, missing env file, unknown keys, `forward_env = ['*']` (assert warning), non-list inputs raising `ConfigLoaderError`, path traversal protection.
   - Unit tests for `CodePromptSignature` verifying:
     - Signature has single `plan_text` input field and three output fields
     - Template constants exist and contain required content
     - Main template mentions running subagents in parallel
     - Review template focuses on test quality (mocking, no cheating, test appropriateness) and does NOT mention performance optimization
     - Alignment template covers requirements verification
   - Manual verification during implementation: ensure `~/.lw_coder/dspy_cache` does not exist before the first orchestrator run, execute the workflow, then confirm the directory exists afterward to prove caching is active.

## Deliverables
- `src/lw_coder/config_loader.py` with dataclasses, loader logic, path traversal protection, and tests.
- `src/lw_coder/dspy/code_prompt_signature.py` defining the signature with single `plan_text` input, comprehensive docstring instructions, and template constants (for documentation only, not used as fallbacks).
- `src/lw_coder/dspy/prompt_orchestrator.py` exposing `generate_code_prompts(plan_metadata, run_dir)` that builds complete plan text with metadata and calls DSPy directly (no fallback error handling).
- Updated `docs/configuration.md` and dependency manifests to cover new configuration and libraries.
- Unit tests in `tests/` (e.g., `tests/test_config_loader.py`, `tests/test_code_prompt_signature.py`).
- Baseline `.lw_coder/config.toml` for this repository with default `[code]` settings.

## Out of Scope
- Managing `.lw_coder/runs/` lifecycle or copying droid definitions (handled by a later "run artifacts" plan).
- Wiring the orchestrator into the CLI/Docker workflow (covered in subsequent plans).
- Modifying Dockerfiles or adding Docker build logic beyond documenting required arguments.
- Capturing or persisting agent feedback summaries beyond what the prompts instruct droid to do.
