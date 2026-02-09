---
plan_id: weft-explore-command
status: done
git_sha: 2b953d978520fbc978268fa6c4e6bb3b41a95253
evaluation_notes: []
---

# weft explore Command

## Objectives

Add a `weft explore` command that provides isolated sandbox environments for open-ended work — investigating bugs, brainstorming solutions, evaluating architectural options, or prototyping ideas. Explorations produce optional findings artifacts stored in git refs that feed into the existing `weft plan` and `weft code` pipeline through name resolution. Extend `weft abandon` and `weft status` to manage exploration lifecycle.

Extract a shared `GitRefStore` abstraction from the existing `plan_backup.py` to avoid duplicating git ref storage logic in the new exploration store.

## Requirements & Constraints

### Functional Requirements

1. `weft explore` creates a temporary detached HEAD worktree with sandbox isolation (same sandbox as `weft code`)
2. Optional `--text` flag provides topic context injected into the explore prompt template
3. The Claude session is single-phase interactive (like `weft plan`, not the two-phase SDK+CLI approach of `weft code`)
4. The exploration session is a scratchpad — Claude can write code in the worktree for testing, prototyping, and learning, but nothing is intended for committing
5. During the session, Claude can write a findings artifact to `.exploration_artifact.md` in the worktree root when the user asks
6. The artifact includes a `name:` field in minimal frontmatter so weft can extract the chosen name
7. The LLM chooses the exploration name (descriptive, kebab-case) based on the exploration topic
8. After the session, weft reads the artifact file, extracts the name from frontmatter, and stores the body content as an orphan commit at `refs/weft/explorations/<name>`
9. Ref creation uses atomic `git update-ref` with null expected SHA to prevent overwriting existing explorations
10. `weft plan <exploration-name>` resolves the exploration and uses findings content as idea text input
11. `weft code <exploration-name>` resolves the exploration and creates a quick-fix plan from findings content
12. Consuming an exploration records `exploration_source` in the resulting plan's YAML frontmatter and cleans up the exploration ref
13. `weft abandon <exploration-name>` cleans up exploration refs
14. `weft status` displays active explorations alongside plans

### Name Resolution Order

When `plan` or `code` receives a bare name (no path separators):
1. Check `.weft/tasks/<name>.md` (existing plan file — always takes priority)
2. Check `refs/weft/explorations/<name>` (exploration ref)
3. If neither found, raise `FileNotFoundError`

First match wins. Name collisions between plans and explorations are unlikely since explorations get cleaned up on consumption.

### Artifact File Format

The artifact is written to a single known path in the worktree: `.exploration_artifact.md`. It uses minimal frontmatter for the name, followed by plain markdown findings:

```markdown
---
name: cache-ttl-bug
---

<findings content tailored for the recommended next step>
```

After the session, weft reads this file, extracts the `name` from frontmatter, and stores the body content (everything after the frontmatter) in the git ref. The frontmatter is not stored in the ref — only the findings content.

The findings content is framed differently depending on the recommended next step:
- **For `weft plan`**: A high-level idea document — problem context, why it matters, what was learned, recommended approach. This becomes the input to the plan prompt which then does the deep dive. No code fragments.
- **For `weft code`**: A concise description of what needs to change, why, and where. Enough context to implement a small fix directly. No code fragments.

### Post-Session Flow

After the interactive Claude session ends:

**Findings saved** (`.exploration_artifact.md` exists in worktree root):
- Read the file and parse frontmatter to extract `name`
- Validate the name matches the pattern (`^[a-zA-Z0-9._-]{3,100}$`)
- Create orphan commit and ref via `save_exploration()`
- If ref creation fails (name already exists), print error with worktree path so user can retry
- Print exit message:
  ```
  Exploration saved: <name>

  Next steps:
    weft plan <name>    # Design a detailed plan
    weft code <name>    # Implement directly
  ```
- Worktree is NOT cleaned up (persists for potential revisiting)

**No findings saved** (`.exploration_artifact.md` does not exist):
- Prompt: "No findings were saved. Delete the worktree? (y/n)"
- If yes: clean up worktree, exploration leaves no trace
- If no: print worktree path for later access
- If EOF/Ctrl+D: treat as "no" (preserve worktree, don't hang)

### Constraints

- Worktrees use temp naming (timestamp-based, like `weft plan`), never renamed to match exploration name
- Same sandbox configuration as `weft code` (disallowed_commands, bwrap, filesystem isolation)
- No trace capture
- No session resumability
- Name validation: same pattern as plan IDs (`^[a-zA-Z0-9._-]{3,100}$`)
- Code written during exploration is for learning/testing only, not for committing

## Work Items

### 1. Git Ref Store Abstraction

Extract shared git ref storage logic from `src/weft/plan_backup.py` into a new `src/weft/git_ref_store.py` module.

The `GitRefStore` class encapsulates the common pattern of storing content as orphan commits referenced by git refs:

- **save(name, content, file_path, commit_message, atomic)**: Create orphan commit with content at `file_path` in the tree. Create/update ref at `refs/<namespace>/<name>`. When `atomic=True`, fail if ref already exists (use null expected SHA in `git update-ref`). When `atomic=False`, force-update existing ref.
- **read(name, file_path)**: Read content from `git show refs/<namespace>/<name>:<file_path>`.
- **list_refs()**: List all refs in namespace with metadata (name, timestamp) via `git for-each-ref`.
- **delete(name)**: Delete ref (idempotent).
- **exists(name)**: Check if ref exists via `git show-ref --verify`.
- **move(name, dest_store)**: Move ref from this namespace to another `GitRefStore`'s namespace.

Constructor takes `repo_root: Path` and `namespace: str` (e.g., `"plan-backups"`, `"weft/explorations"`).

Refactor `plan_backup.py` to use `GitRefStore` internally. All existing `plan_backup.py` tests must continue to pass — this is a pure refactoring with no behavior change.

### 2. Exploration Store Module

Create `src/weft/exploration_store.py` as a thin wrapper around `GitRefStore` for managing exploration artifacts.

Uses `GitRefStore(repo_root, "weft/explorations")` with `file_path="findings.md"` and `atomic=True` for saves.

Operations:
- **save_exploration(repo_root, name, content)**: Save with atomic creation. Commit message: `Exploration: <name>`.
- **read_exploration(repo_root, name)**: Read findings content.
- **list_explorations(repo_root)**: List all explorations with metadata (name, timestamp).
- **delete_exploration(repo_root, name)**: Delete exploration ref (idempotent).
- **exploration_exists(repo_root, name)**: Check if exploration ref exists.

Name validation uses the same `_PLAN_ID_PATTERN` from `plan_validator.py`.

### 3. Explore Prompt Template

Create `src/weft/prompts/claude-code/explore.md`:

```markdown
You are in an exploration session. Your role is to be a flexible thinking partner — investigating code, brainstorming solutions, evaluating options, and helping generate ideas.

## Topic

{TOPIC_TEXT}

## Guidelines

- Adapt to what the user needs: investigating a bug, brainstorming architecture options, evaluating trade-offs, prototyping ideas, or something else entirely
- When brainstorming, present multiple options — help the user see possibilities they might not have considered, including creative and unconventional approaches
- Read code, trace execution paths, examine test cases, check configurations
- You can write code in the worktree for testing and experimentation — use it as a scratchpad to try things out, run tests, or prototype ideas
- Code written during exploration is for learning only and will not be committed
- Look for `CLAUDE.md` and `AGENTS.md` in the repository for project guidance

## Saving Findings

When the user asks you to save your findings, write a markdown document to `.exploration_artifact.md` in the repository root.

**Before writing**, check which exploration names are already taken:

```
git show-ref refs/weft/explorations
```

Then choose a short, descriptive name that is not already in use (e.g., `cache-ttl-bug`, `auth-latency`, `migration-strategy`). The name must be 3-100 characters using only lowercase letters, numbers, hyphens, periods, and underscores.

### Artifact Format

The artifact must start with a frontmatter block containing the chosen name, followed by your findings in plain markdown:


---
name: <chosen-name>
---

<findings content>


The content after the frontmatter depends on the recommended next step:

**If recommending `weft plan <name>`** (the problem needs design work before implementation):

Write an idea document that provides good context for planning. Include:
- What the problem or goal is and why it matters
- What you learned during exploration that informs the approach
- Your recommended approach at a high level
- Key constraints or considerations discovered

This becomes the starting input for an interactive planning session that will dive into details, ask clarifying questions, and produce a detailed implementation plan. Keep it high-level — no code fragments.

**If recommending `weft code <name>`** (the fix is small and straightforward):

Write a concise description that provides enough context to implement directly. Include:
- What needs to change and why
- Where the change needs to happen
- Any relevant context that would help the implementer

This creates a quick-fix implementation task. Keep it focused and brief — no code fragments.

End with a clear recommendation: `weft plan <name>` or `weft code <name>`.

### Important

- Only save findings when the user explicitly asks
- Do not save findings automatically when the session ends
- If the user exits without saving findings, that is fine — no artifact is produced
```

When `--text` is not provided, `{TOPIC_TEXT}` is replaced with: `Open-ended exploration. The user will guide the session interactively.`

### 4. Explore Command Module

Create `src/weft/explore_command.py` with `run_explore_command(text, tool, model, no_hooks)`.

Flow:
1. Find repo root
2. Load explore prompt template, inject topic text into `{TOPIC_TEXT}` placeholder
3. Write prompt to temp file (`/tmp/claude/weft/explore-<PID>.txt`)
4. Create temporary detached HEAD worktree (reuse `create_temp_worktree()` from `temp_worktree.py`)
5. Sync files from repo to worktree (if configured via `file_sync`)
6. Load sandbox config from `.weft/config.toml`
7. Get executor via `ExecutorRegistry`, build command, wrap with bwrap sandbox
8. Run executor interactively (single-phase, same as `weft plan`)
9. Post-session: check if `.exploration_artifact.md` exists in worktree root
10. Handle findings/no-findings per the post-session flow above
11. Return exit code

### 5. CLI Integration

Modify `src/weft/cli.py`:

- Add `explore` subparser with arguments:
  - `--text`: optional topic text
  - `--tool`: coding tool (default: `claude-code`)
  - `--model`: model variant
  - `--no-hooks`: disable hooks
- Add lazy import and dispatch block for `run_explore_command()`
- Apply same tool/model validation pattern as other commands

### 6. Exploration Resolver

Create `src/weft/exploration_resolver.py` with an `ExplorationResolver` class (companion to `PlanResolver`):

- **resolve(name: str, repo_root: Path) -> str | None**: Check `refs/weft/explorations/<name>` via `exploration_store.read_exploration()`. Returns exploration content string if ref exists, `None` otherwise.

This is a separate class from `PlanResolver` to maintain clean abstraction boundaries — `PlanResolver` resolves to file paths, `ExplorationResolver` resolves to content strings.

### 7. Plan/Code Exploration Consumption

Modify `src/weft/cli.py` dispatch for `plan` and `code` commands to check exploration refs when plan file resolution finds no match:

**For `weft plan <name>`**:
- When `PlanResolver.resolve()` raises `FileNotFoundError` for a bare name, call `ExplorationResolver.resolve()`
- If exploration found: pass content as `text` parameter to `run_plan_command()` (same as `--text` path)
- After plan command returns successfully, clean up the exploration ref via `delete_exploration()`

**For `weft code <name>`**:
- When `PlanResolver.resolve()` raises `FileNotFoundError` for a bare name, call `ExplorationResolver.resolve()`
- If exploration found: create quick-fix plan from content (same as `--text` path), passing `exploration_source` parameter
- After code command returns successfully, clean up the exploration ref via `delete_exploration()`

The resolution orchestration (plan file → exploration ref) is a few lines added to the existing `except FileNotFoundError` blocks in cli.py. The actual exploration lookup is delegated to `ExplorationResolver`.

### 8. Plan Validator Updates

Modify `src/weft/plan_validator.py`:

- Add `"exploration_source"` to the `_OPTIONAL_KEYS` set
- Add `exploration_source: str | None = None` field to the `PlanMetadata` dataclass
- In `load_plan_metadata()`, extract `exploration_source` from frontmatter and pass to `PlanMetadata` constructor

### 9. Quick Fix Updates

Modify `src/weft/quick_fix.py`:

- Add optional `exploration_source: str | None = None` parameter to `create_quick_fix_plan()`
- When provided, include `exploration_source: <value>` in the YAML frontmatter of the generated quick-fix plan

### 10. Abandon Command Extension

Modify `src/weft/abandon_command.py`:

- When input doesn't resolve to a plan file, check for an exploration ref before treating as raw plan_id
- Add exploration ref detection alongside existing plan artifact detection
- When abandoning an exploration: delete the exploration ref (no backup namespace move — explorations don't need recovery)
- Show exploration info in confirmation prompt
- Worktree cleanup for explorations: the temp-named worktree path isn't derivable from the exploration name, so worktree cleanup for explorations is limited to what's discoverable (exploration ref cleanup is the primary action)

### 11. Status Command Extension

Modify `src/weft/status_command.py`:

- Add a separate "Explorations" section below the plans table
- List exploration name and timestamp (from commit metadata)
- Source data from `exploration_store.list_explorations()`
- Only show the explorations section when explorations exist

### Unit Tests

#### New: `tests/unit/test_git_ref_store.py`

Tests using `git_repo` fixture (real git operations, no external APIs):

- `test_save_creates_orphan_commit_and_ref` — verify ref created at expected path with correct content
- `test_save_atomic_rejects_duplicate` — verify error when ref already exists and `atomic=True`
- `test_save_force_updates_existing` — verify force-update when `atomic=False`
- `test_read_returns_content` — verify content round-trip (save then read)
- `test_read_not_found_raises` — verify error on missing ref
- `test_list_refs_returns_metadata` — verify listing returns name and timestamp
- `test_list_refs_empty` — verify empty list when no refs exist
- `test_delete_removes_ref` — verify ref deletion
- `test_delete_idempotent` — verify no error when ref doesn't exist
- `test_exists_true_and_false` — verify existence check both ways
- `test_move_between_namespaces` — verify ref moved from source to destination namespace
- `test_validates_name` — verify name pattern enforcement

#### New: `tests/unit/test_exploration_store.py`

Tests using `git_repo` fixture:

- `test_save_exploration_creates_ref` — verify exploration saved at `refs/weft/explorations/<name>`
- `test_save_exploration_atomic_rejects_duplicate` — verify error when name already exists
- `test_read_exploration_returns_content` — verify content round-trip
- `test_read_exploration_not_found_raises` — verify error on missing exploration
- `test_list_explorations_returns_metadata` — verify listing with name and timestamp
- `test_list_explorations_empty` — verify empty list
- `test_delete_exploration_removes_ref` — verify ref deletion
- `test_delete_exploration_idempotent` — verify no error on missing ref
- `test_exploration_exists` — verify existence check
- `test_save_exploration_validates_name` — verify name validation (invalid chars, too short, too long)
- `test_save_exploration_rejects_empty_content` — verify error on empty content

#### Verify: `tests/unit/test_plan_backup.py`

All existing `test_plan_backup.py` tests must continue to pass after the `GitRefStore` refactoring. No new tests needed — the refactoring is behavior-preserving.

#### New: `tests/unit/test_explore_command.py`

Tests with mocked executor/subprocess (no external APIs):

- `test_explore_creates_temp_worktree` — verify temp worktree creation
- `test_explore_injects_topic_text` — verify prompt template populated with `--text` value
- `test_explore_default_topic` — verify default topic text when `--text` not provided
- `test_explore_detects_artifact_file` — verify post-session detection of `.exploration_artifact.md`
- `test_explore_parses_name_from_frontmatter` — verify name extracted from artifact frontmatter
- `test_explore_saves_exploration_ref` — verify `save_exploration()` called with correct content (frontmatter stripped) and name
- `test_explore_prints_next_steps` — verify exit message format matches spec
- `test_explore_no_findings_prompts_cleanup[yes]` — verify worktree cleaned up when user confirms
- `test_explore_no_findings_prompts_cleanup[no]` — verify worktree persists when user declines
- `test_explore_no_findings_prompts_cleanup[eof]` — verify worktree persists on EOF/Ctrl+D
- `test_explore_sandbox_config` — verify sandbox configuration matches `weft code` restrictions
- `test_explore_invalid_name_in_frontmatter` — verify error when name doesn't match pattern
- `test_explore_missing_name_in_frontmatter` — verify error when frontmatter lacks `name` field
- `test_explore_ref_exists_error` — verify error message and worktree preservation when atomic ref creation fails

#### New: `tests/unit/test_exploration_resolver.py`

- `test_resolve_exploration_found` — verify content returned when ref exists
- `test_resolve_exploration_not_found_returns_none` — verify `None` when ref missing
- `test_resolve_plan_file_takes_priority` — verify that when both `.weft/tasks/<name>.md` and `refs/weft/explorations/<name>` exist, the plan file wins

#### Modified: `tests/unit/test_cli.py`

- Add `"explore"` to `test_all_subcommands_dispatch_without_import_errors` parametrized list
- Add `"explore"` to `test_subcommand_help_no_import_errors` parametrized list
- Add test for explore command dispatch with `--text` flag

#### Modified: `tests/unit/test_plan_validator.py`

- `test_exploration_source_accepted_as_optional_key` — verify frontmatter with `exploration_source` passes validation
- `test_plan_metadata_includes_exploration_source` — verify field populated in PlanMetadata

#### Modified: `tests/unit/test_abandon_command.py`

- `test_abandon_exploration_deletes_ref` — verify exploration ref cleanup
- `test_abandon_exploration_shows_info_in_prompt` — verify confirmation prompt mentions exploration

#### Modified: `tests/unit/test_status_command.py`

- `test_status_shows_explorations_section` — verify explorations appear in output
- `test_status_no_explorations_section_when_empty` — verify section hidden when no explorations

### Integration Tests

The following existing integration tests must continue to pass:

- `tests/integration/test_abandon_integration.py::test_end_to_end_abandon_workflow`
- `tests/integration/test_abandon_integration.py::test_recover_abandoned_plan_workflow`
- `tests/integration/test_abandon_integration.py::test_multiple_abandon_recover_cycles`
- `tests/integration/test_abandon_integration.py::test_list_abandoned_plans_flag`
- `tests/integration/test_abandon_integration.py::test_list_all_plans_flag`
- `tests/integration/test_abandon_integration.py::test_list_abandoned_shows_reason`
- `tests/integration/test_abandon_integration.py::test_git_refs_integrity_after_operations`

## Deliverables

1. `src/weft/git_ref_store.py` — Shared git ref storage abstraction
2. `src/weft/exploration_store.py` — Exploration artifact storage (thin wrapper around GitRefStore)
3. `src/weft/explore_command.py` — Explore command implementation
4. `src/weft/exploration_resolver.py` — Exploration name resolution
5. `src/weft/prompts/claude-code/explore.md` — Explore prompt template (full content specified in Work Item 3)
6. Refactored `src/weft/plan_backup.py` — Uses GitRefStore internally (behavior-preserving)
7. Modified `src/weft/cli.py` — Explore subparser and exploration resolution in plan/code dispatch
8. Modified `src/weft/plan_validator.py` — `exploration_source` in optional keys and `PlanMetadata`
9. Modified `src/weft/quick_fix.py` — `exploration_source` support in quick-fix plan creation
10. Modified `src/weft/abandon_command.py` — Exploration abandonment support
11. Modified `src/weft/status_command.py` — Exploration display section
12. `tests/unit/test_git_ref_store.py` — Unit tests for shared ref store
13. `tests/unit/test_exploration_store.py` — Unit tests for exploration store
14. `tests/unit/test_explore_command.py` — Unit tests for explore command
15. `tests/unit/test_exploration_resolver.py` — Unit tests for exploration resolver
16. Modified unit test files: `test_cli.py`, `test_plan_validator.py`, `test_abandon_command.py`, `test_status_command.py`

## Out of Scope

- Droid explore prompt template (claude-code only in this iteration)
- Session resumability (future enhancement per idea doc)
- Explore within existing worktrees (always starts fresh from HEAD)
- Session trace capture
- Session context carryover to downstream commands
- Auto-push/pull of exploration refs across devices
- `weft explore list` subcommand (covered by `weft status`)
