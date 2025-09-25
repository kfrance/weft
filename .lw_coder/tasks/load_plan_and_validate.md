---
git_sha: 17634532492117ac0dd0446f03bc137a4e3ff3f2
evaluation_notes:
  - Were any files that aren't being used generated?
  - Does the integration test create real repos, commits, and plans before invoking the CLI?
  - Were any features added that are outside the scope of the plan
---

# Task Plan: lw_coder Plan Validation CLI

## Objectives
- bootstrap the `lw_coder` Python package with a `code` CLI command using docopt-ng
- implement plan validation logic for Markdown files with YAML front matter containing required experiment metadata
- ensure validation covers required fields and verifies git SHA existence in the surrounding Git repo
- deliver automated tests (unit + integration) that exercise success and failure paths, including a temp Git repo scenario

## Requirements & Constraints
- Plan files are Markdown with a leading YAML front matter block
- Front matter must contain exactly the keys `git_sha`, `evaluation_notes`
  - `git_sha`: 40-character commit SHA that must resolve within the repository containing the plan file (short SHAs should be rejected for now)
  - `evaluation_notes`: list of non-empty strings describing post-run checks (reject other types)
- The Markdown body (content after front matter) must be non-empty and represents the plan description
- Validator must ensure the plan file resides inside a Git repository (does not have to be committed)
- Validation errors should print a descriptive message to stderr and exit with a non-zero status
- Successful validation should print a concise confirmation message

## Work Items
1. **Project setup**
   - Scaffold `src/lw_coder/` package with submodules for CLI entrypoint and validation logic
   - Configure CLI invocation via docopt-ng, wiring console script `lw_coder` target
   - Manage dependencies with `uv add` (docopt-ng, PyYAML) and ensure pytest is available for tests

2. **Validation core**
   - Implement Markdown front matter parser (reuse PyYAML after stripping the front matter fences)
   - Implement `load_plan_metadata(path: Path) -> PlanMetadata` that validates the front matter fields, ensures the Markdown body is non-empty, and raises custom exceptions for specific failures while returning parsed metadata for downstream use
   - Verify Git repo membership via `git rev-parse --show-toplevel`; use `git cat-file -e <sha>` (or lib equivalent) to confirm commit existence
   - Map validation exceptions to human-readable CLI error messages

3. **CLI wiring**
   - Implement `lw_coder code <plan-path>` using docopt-ng parsing
   - Call validator; on success print `Plan validation succeeded for <path>` and exit 0
   - On failure print `Plan validation failed: <reason>` to stderr and exit non-zero

4. **Testing**
   - Unit tests for validator edge cases (missing front matter, missing keys, wrong types, invalid Git SHA, not in repo)
   - Integration test using `tmp_path`: initialize Git repo, create commits, write plan files on the fly, run CLI via subprocess to assert exit codes and messages
   - Include negative integration test (bad SHA) to assert failure handling

5. **Sample plans & fixtures**
   - Generate valid and invalid plan content on the fly within tests instead of maintaining static fixture files

## Deliverables
- Source files under `src/lw_coder/` implementing CLI and validator
- Tests under `tests/` runnable with `pytest`
- Dependencies declared via `uv add`

## Out of Scope
- Implementing actual coding task execution, worktree management, or Docker orchestration
- Supporting additional CLI commands beyond `code`
- Auto-generating plans or modifying repository state beyond validation checks
- Accommodating alternative plan formats (JSON, plain YAML) or optional fields beyond the two required keys
- Performance optimizations or caching (validation runs synchronously per invocation)
