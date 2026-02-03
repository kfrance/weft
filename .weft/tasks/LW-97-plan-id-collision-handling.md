---
plan_id: LW-97-plan-id-collision-handling
status: done
git_sha: 009a6948da451819cfdc68a03c30ee4aff91ea67
evaluation_notes: []
linear_issue_id: LW-97
---

# Handle duplicate plan_id collisions after plan generation

## Objectives

Automatically detect and resolve plan_id collisions after plan files are copied from the worktree to the main repository, providing seamless UX without user intervention.

## Requirements & Constraints

### Functional Requirements
- Detect plan_id collisions between copied files and existing plans in main repo's `.weft/tasks/`
- Detect plan_id collisions between copied files and other plans in worktree's `.weft/tasks/`
- Detect plan_id collisions between multiple copied files themselves
- Resolve collisions by generating completely new plan_ids based on plan content using LLM
- Update both the plan_id field in front matter AND the filename to match
- Batch all colliding plans in a single LLM call for efficiency
- Loop until all plan_ids are unique (no retry limit)
- Provide the LLM with all previously-conflicting plan_ids to avoid

### Non-Functional Requirements
- Silent logging only (no user notification of renames)
- No opt-out mechanism
- Use atomic file operations (write-then-move) to prevent inconsistent state

### Technical Constraints
- Use OpenRouter with `x-ai/grok-4.1-fast` model (consistent with existing DSPy infrastructure)
- Follow existing patterns from `judge_executor.py` for DSPy integration
- Reuse `plan_validator.py` for plan_id extraction
- Reuse `plan_lifecycle.py:update_plan_fields()` pattern for front matter updates

## Work Items

### 1. Create `plan_id_generator.py` module

New module for LLM-based plan_id generation:

- DSPy signature that accepts:
  - Plan content (markdown body)
  - List of plan_ids to avoid (all conflicting names from all iterations)
- Returns a new unique plan_id based on plan content
- Support batching: accept multiple plans, return multiple new plan_ids
- Follow `judge_executor.py` pattern for OpenRouter/DSPy setup
- Use `x-ai/grok-4.1-fast` model

### 2. Create `plan_id_collision_resolver.py` module

New module for collision detection and resolution orchestration:

- `collect_existing_plan_ids(worktree_tasks_dir, main_tasks_dir) -> set[str]`
  - Scan both directories for all existing plan_ids
  - Use `plan_validator.py` logic for extracting plan_ids from files
  - Handle malformed files gracefully (skip with warning log)

- `detect_collisions(copied_files, existing_plan_ids) -> list[CollisionInfo]`
  - Check each copied file's plan_id against existing_plan_ids
  - Check for collisions between copied files themselves
  - Return list of files that need new plan_ids

- `resolve_collisions(collisions, existing_plan_ids, api_key, cache_dir) -> dict[Path, str]`
  - Batch all colliding plans in one LLM call
  - Track all conflicting plan_ids across iterations
  - Loop until all generated plan_ids are unique
  - Return mapping of file paths to new plan_ids

- `apply_plan_id_change(source_path, new_plan_id, dest_dir) -> Path`
  - Write updated content to new file with new name (atomic write-then-move)
  - Delete old file only after new file is confirmed
  - Return path to new file

### 3. Modify `plan_file_copier.py`

Integrate collision resolution into the copy workflow:

- After `copy_plan_files()` completes, call collision resolver
- Pass both worktree and main repo task directories
- Update `CopyResult.file_mapping` if any files were renamed
- Log collision resolutions at debug level

### 4. Unit Tests

**New file: `tests/unit/test_plan_id_generator.py`**
- Test DSPy signature construction with plan content and conflicting IDs
- Test batching multiple plans produces multiple unique IDs
- Test response parsing extracts plan_ids correctly
- Test handling of edge cases (empty content, very long content)

**New file: `tests/unit/test_plan_id_collision_resolver.py`**
- Test `collect_existing_plan_ids` scans both directories
- Test `collect_existing_plan_ids` handles malformed files gracefully
- Test `detect_collisions` finds collision with main repo
- Test `detect_collisions` finds collision with worktree
- Test `detect_collisions` finds collision between copied files
- Test `detect_collisions` returns empty list when no collisions
- Test `resolve_collisions` loops until all IDs unique (mock LLM returning collision on first try)
- Test `resolve_collisions` accumulates conflicting IDs across iterations
- Test `apply_plan_id_change` uses atomic write-then-move
- Test `apply_plan_id_change` cleans up old file after success
- Test `apply_plan_id_change` does not delete old file if write fails

**Additions to `tests/unit/test_plan_file_copier.py`**
- Test collision resolver is called after copy completes
- Test `CopyResult.file_mapping` reflects renamed files
- Test no LLM call when no collisions detected

### 5. Integration Tests

No new integration tests required. The DSPy/OpenRouter infrastructure is already validated by `tests/integration/test_judge_executor_api.py`. Unit tests with mocked DSPy are sufficient for the plan_id_generator logic.

## Deliverables

1. `src/weft/plan_id_generator.py` — DSPy-based plan_id generation
2. `src/weft/plan_id_collision_resolver.py` — Collision detection and resolution
3. Modified `src/weft/plan_file_copier.py` — Integration point
4. `tests/unit/test_plan_id_generator.py` — Unit tests for generator
5. `tests/unit/test_plan_id_collision_resolver.py` — Unit tests for resolver
6. Updated `tests/unit/test_plan_file_copier.py` — Tests for integration

## Out of Scope

- Pre-populating existing plan_ids in Claude Code prompt (Option 1 from task)
- User notification or confirmation of plan_id changes
- Opt-out mechanism or configuration
- Retry limits on LLM calls
- Deterministic fallback (e.g., appending numeric suffix)
- Repair mechanism for inconsistent state (deferred to future work if needed)
- ADR for this feature (routine implementation, not a significant architectural choice)
