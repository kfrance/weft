---
plan_id: "lwc-home-env-migration"
git_sha: "6136da44a8cb52e3e529a5db7d35d06cd372adf0"
status: "done"
evaluation_notes: []
---

## Objectives
- Load lw_coder secrets exclusively from `~/.lw_coder/.env`, applying basic existence/readability validation and presenting this as the canonical behavior.
- Remove all dependencies on repository-level `.lw_coder/config.toml`, keeping the codebase ready for future extensibility without repo overrides.

## Requirements & Constraints
- No runtime or documentation references to `.lw_coder/config.toml` may remain.
- Error messaging must describe the home-level `.env` as the standard configuration without implying a recent change.
- Automated tests must isolate home-directory usage (e.g., via monkeypatching) to avoid touching the real user environment.

## Work Items
1. **Home Environment Loader** – Resolve `Path.home() / ".lw_coder" / ".env"`, validate presence/readability, and load secrets with `dotenv`.
2. **Remove Config Loader Module** – Delete `src/lw_coder/config_loader.py` and replace its usage in `src/lw_coder/dspy/prompt_orchestrator.py` with the home-based loader.
3. **Purge Legacy Config References** – Excise imports, exceptions, and helpers tied to `.lw_coder/config.toml` across the codebase.
4. **Rebuild Test Coverage** – Add tests that monkeypatch `Path.home()` (or equivalent) to temp directories, covering success and failure flows without touching the actual home folder.
5. **Update Documentation & Messaging** – Rewrite setup guidance and inline comments to reference only the home-level `.env`, avoiding any mention of deprecated behavior.

## Deliverables
- Updated lw_coder implementation sourcing secrets solely from the home-level `.env`.
- Revised automated tests validating the new loader within isolated temp-home environments.
- Documentation/help text aligned with the single-source secret configuration.

## Out of Scope
- Any compatibility or migration support for existing `.lw_coder/config.toml` files.
- Repo-specific overrides, Docker configuration hooks, or alternate secret locations.
- Broader changes to DSPy caching or agent orchestration settings.

## Test Cases
```gherkin
Feature: Home-level secret loading
  Scenario: Missing ~/.lw_coder/.env
    Given Path.home is patched to a temp directory lacking .lw_coder/.env
    When the user runs lw_coder code
    Then the CLI exits with an error instructing creation of ~/.lw_coder/.env

  Scenario: Valid secrets in ~/.lw_coder/.env
    Given Path.home is patched to a temp directory containing .lw_coder/.env with OPENROUTER_API_KEY=test-key
    When the user runs lw_coder code
    Then the command succeeds without referencing repo-level configuration

  Scenario: Prompt orchestrator uses home env
    Given Path.home is patched to a temp directory containing .lw_coder/.env with OPENROUTER_API_KEY=test-key
    And a valid plan is provided
    When generate_code_prompts executes
    Then secret loading succeeds without accessing .lw_coder/config.toml
```

## AI Appendix
- **Loader Implementation:** Create a helper (e.g., `src/lw_coder/home_env.py`) that resolves `Path.home() / ".lw_coder" / ".env"`, checks existence/readability, and invokes `load_dotenv`, raising a dedicated exception when missing.
- **Orchestrator Refactor:** Update `src/lw_coder/dspy/prompt_orchestrator.py` to call the new helper, removing `CodeConfig` usage and any handling of `forward_env`, `docker_build_args`, or `docker_run_args`.
- **Code Removal:** Delete `src/lw_coder/config_loader.py`, remove associated exports/imports, and drop `tests/test_config_loader.py` along with any fixtures referencing the old loader.
- **Test Strategy:** Introduce tests that monkeypatch `Path.home()` (via `monkeypatch` or context managers) to temporary directories, verifying both missing and present `.env` scenarios while leaving the actual user home untouched.
- **Documentation Updates:** Purge `.lw_coder/config.toml` instructions from README, `docs/code-config.md`, threat modeling, and any other references, replacing them with steps for preparing `~/.lw_coder/.env` containing `OPENROUTER_API_KEY`.
- **Error Messaging:** Standardize exceptions to instruct users to create `~/.lw_coder/.env` with required keys, avoiding language that suggests a recent behavioral change.
