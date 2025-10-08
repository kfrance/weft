---
plan_id: code-command-foundation
git_sha: 3572e48544fdff29f517a0122ede462ad4a4a6c0
status: done
evaluation_notes: []
---

# Task Plan: Establish Code Command Foundation & Shared Droid Session Helper

## Objectives
- Split the CLI so `lw_coder.cli` delegates to a new `run_code_command` function, keeping `main` free of business logic.
- Introduce `src/lw_coder/code_command.py` that performs plan validation, prepares the persistent worktree via `ensure_worktree`, and centralizes logging/exit-code handling for future code workflows.
- Factor shared droid-session utilities into `src/lw_coder/droid_session.py` (context management, Docker command assembly, lw_coder source discovery) and migrate `plan_command` to use them so the forthcoming code command can reuse the same logic.
- Add unit tests to lock in the refactor: CLI dispatch, code command behavior, and the git-pointer/Docker helper mechanics.

## Requirements & Constraints
- Keep the current CLI usage string and argument parsing identical; only the dispatch path may change.
- `run_code_command(plan_path: Path | str) -> int` must:
  1. Resolve the plan path and call `load_plan_metadata`.
  2. Return exit code `1` if validation raises `PlanValidationError`, logging the error via `logger.error`.
  3. Call `ensure_worktree(metadata)` on success, log the resulting path, and return `0`.
  4. Preserve the existing info-level logs (`"Plan validation succeeded for %s"` and `"Worktree prepared at: %s"`) so CLI integration tests stay green.
  5. Catch `WorktreeError`, log the message, and return `1`.
- The new module must initialize a module-level logger using `get_logger(__name__)` and avoid side effects at import time.
- Move the following responsibilities out of `plan_command.py` into `droid_session.py`:
  - Determining the lw_coder source directory (currently `_get_lw_coder_src_dir`).
  - Patching a worktree’s `.git` pointer to `/repo-git/worktrees/<name>` and restoring it after use.
  - Building the Docker command list; encode mounts for auth, container settings, prompt path, repo tasks directory, lw_coder droids, repo git dir, and worktree just as the current implementation does.
- `droid_session.py` should expose:
  - `get_lw_coder_src_dir() -> Path` (raises `RuntimeError` with actionable text if it cannot resolve).
  - `@dataclass class DroidSessionConfig` capturing all mount paths, prompt file, image tag, the derived `worktree_name`, and command string to run.
  - `def build_docker_command(config: DroidSessionConfig) -> list[str]` that mirrors today’s `_build_docker_command` behavior (still invokes `bash -c "droid \"$(cat /tmp/prompt.txt)\""`) and ensures the tasks directory exists before returning.
  - `@contextmanager def patched_worktree_gitdir(worktree: Path, repo_git_dir: Path) -> Iterator[str]` that rewrites the `.git` file on entry, yields the derived worktree name, and restores the original pointer on exit (even on error).
- Update `plan_command.py` to import and use these helpers; ensure the Docker invocation (prompt creation, `subprocess.run`, cleanup) executes inside the `patched_worktree_gitdir` context so the container always sees `/repo-git/worktrees/<name>` while running, translate `RuntimeError` from `get_lw_coder_src_dir` into `PlanCommandError`, and eliminate any duplicated business logic.
- Ensure refactor preserves current behavior: existing CLI integration tests (`tests/test_cli.py`) must continue to pass without altering expectations.

## Work Items
1. **Create `code_command.py`**
   - Implement `run_code_command` per the requirements, including logging, exception handling, and docstring.
   - Add type hints, leverage `Path` from `pathlib`, and keep implementation free of future DSPy logic (return after the worktree log).
   - Provide a dedicated logger (`get_logger(__name__)`).

2. **Introduce `droid_session.py` Utilities**
   - Define `DroidSessionConfig` with fields: `worktree_path`, `repo_git_dir`, `tasks_dir`, `droids_dir`, `auth_file`, `settings_file`, `prompt_file`, `image_tag`, `worktree_name`, and `command` (string to run inside the container).
   - Implement `get_lw_coder_src_dir` using `Path(__file__).resolve().parent` and surface informative errors if the directory is missing.
   - Implement `patched_worktree_gitdir` context manager that:
     - Reads existing `.git` file contents.
     - Extracts the worktree name (suffix path component).
     - Writes `gitdir: /repo-git/worktrees/<name>\n` while the context is active.
     - Restores the original contents in a `finally` block.
   - Implement `build_docker_command` so it produces the same argument list we run today, using values from `DroidSessionConfig`, creating the tasks directory (`mkdir(parents=True, exist_ok=True)`) before building the command, and honoring the provided `worktree_name`.

3. **Refactor `plan_command.py` to Use Helpers**
   - Replace `_get_lw_coder_src_dir`, `_build_docker_command`, and the inline `.git` file manipulation with imports from `droid_session.py`.
   - Populate `DroidSessionConfig.worktree_name` using the value yielded by `patched_worktree_gitdir` before invoking `build_docker_command`.
   - Adjust helper calls so the prompt file is written exactly where the current implementation expects; any temporary files stay within the plan command module.
   - Keep the `with patched_worktree_gitdir(...)` scope open for the entire Docker run (command construction, `subprocess.run`, and cleanup) so the patched pointer stays active.
   - Catch `RuntimeError` from `get_lw_coder_src_dir` and raise `PlanCommandError` with a helpful message instead of letting the exception bubble out.
   - Keep existing error handling (PlanCommandError) and logging intact, only delegating the shared concerns.

4. **Update CLI Entry Point**
   - Modify `src/lw_coder/cli.py` to import and use `run_code_command` from the new module.
   - Ensure the code path for the plan command remains unchanged aside from helper usage.

5. **Testing**
   - Add `tests/test_code_command.py` to cover:
     - Successful path: monkeypatch `load_plan_metadata` and `ensure_worktree` to confirm they are invoked with the expected values, assert exit code `0`, and capture log output to verify the exact info messages are emitted.
     - Validation failure: have `load_plan_metadata` raise `PlanValidationError` and assert exit code `1` with the error logged.
     - Worktree failure: stub `ensure_worktree` to raise `WorktreeError` and assert exit code `1` with logging.
   - Add `tests/test_droid_session.py` to cover:
     - `patched_worktree_gitdir` rewrites `.git` during the context and restores it afterwards (use a temp directory with a fake `.git` file and confirm contents before/inside/after `with`).
     - `build_docker_command` assembles the expected argument list given a populated `DroidSessionConfig` (use deterministic temp paths and expected string comparison) and creates the tasks directory when it is missing.
     - `get_lw_coder_src_dir` returns the parent directory of `droid_session.py`.
   - Update `tests/test_plan_command.py` (or add a new test) to assert that `plan_command._build_docker_command` no longer exists and that the module delegates to `droid_session.build_docker_command` (e.g., use `monkeypatch` to replace the helper and confirm it is invoked). Verify that a `RuntimeError` from `get_lw_coder_src_dir` becomes a `PlanCommandError`.
   - Ensure existing CLI tests (`tests/test_cli.py`) still pass; update imports/mocks in those tests if they rely on old module locations.

## Deliverables
- `src/lw_coder/code_command.py` with `run_code_command` implementation and logging.
- `src/lw_coder/droid_session.py` exposing the shared helpers.
- Updated `src/lw_coder/plan_command.py` and `src/lw_coder/cli.py` consuming the new utilities.
- New unit-test coverage in `tests/test_code_command.py` and `tests/test_droid_session.py`, plus adjusted plan-command tests verifying helper delegation.

## Out of Scope
- DSPy signature, prompt generation, or any Docker execution beyond constructing commands.
- Changes to run-directory management, prompt storage, or `.lw_coder/runs` handling (no new I/O directories).
- Modifications to Docker image build logic, env forwarding, or context7 installation (handled in later tasks).
- Alterations to plan validation, plan templates, or worktree creation semantics beyond importing the shared helper.
