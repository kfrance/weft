---
plan_id: optimize-finalize-prompts
status: done
evaluation_notes: []
git_sha: 56d22057bbcab0a407368610632f4043511457d4
---

# Optimize Finalize Command Prompts for Speed

## Objectives

Optimize the finalize command prompts (both Claude Code and Droid versions) to reduce execution time by combining related git commands into single bash invocations, minimizing shell resets between commands.

## Requirements & Constraints

### Requirements
- Combine Step 7 commands (cd + checkout + merge) into a single command chain
- Combine Steps 1 & 2 (redundant git status calls) into a single operation
- Streamline Steps 4 & 5 (commit message generation and commit) workflow
- Use `&&` operator for command chaining (fail-fast behavior)
- Maintain prompt clarity and debuggability
- Preserve all verification steps - do not skip important checks
- Update both `src/lw_coder/prompts/claude-code/finalize.md` and `src/lw_coder/prompts/droid/finalize.md`

### Constraints
- Must not reduce error reporting clarity
- Must maintain compatibility with existing test suite
- Cannot modify executor architecture (out of scope for this plan)

### Out of Scope
- Modifying the executor architecture
- Adding new finalize workflow steps
- Changing the git workflow strategy (rebase + fast-forward merge)
- Adding documentation comments about optimization approach or trade-offs
- Writing new tests

## Work Items

### 1. Analyze current prompt structure
- Read both finalize prompts (`claude-code/finalize.md` and `droid/finalize.md`)
- Document current command execution patterns
- Identify all locations where commands can be safely combined

### 2. Optimize Step 7 (navigation + checkout + merge)
- **Current:** Three separate commands or command sequences
  ```bash
  cd $(git rev-parse --git-common-dir)/..
  # then separately:
  git checkout main
  git merge --ff-only {PLAN_ID}
  ```
- **Optimized:** Single command chain
  ```bash
  cd $(git rev-parse --git-common-dir)/.. && git checkout main && git merge --ff-only {PLAN_ID}
  ```
- Update prompt instructions to use combined command
- Ensure error handling guidance is clear (which step failed)

### 3. Optimize Steps 1 & 2 (redundant git status)
- **Current:**
  - Step 1: Run `git status` to verify uncommitted changes exist
  - Step 2: Run `git status` to analyze changed/untracked files
- **Optimized:** Combine into single step that:
  - Runs `git status` once
  - Verifies uncommitted changes exist (stop if clean)
  - Analyzes the changed/untracked files
- Update prompt to merge these steps while maintaining clarity of both purposes

### 4. Streamline Steps 4 & 5 (commit workflow)
- **Current:**
  - Step 4: Analyze staged changes using `git diff --staged` and generate commit message
  - Step 5: Run `git commit -m "<message>"`
- **Optimized:** Keep as two steps but improve prompt wording to indicate tight coupling
  - Make it clear these should happen in immediate succession
  - Guide LLM to minimize delay between analysis and commit
  - Consider combining `git diff --staged` analysis with immediate commit execution
- Ensure commit message generation still happens before commit (not combined into one command)

### 5. General prompt optimization review
- Review entire prompt for other opportunities to:
  - Reduce redundant operations
  - Combine related read-only git commands where appropriate
  - Improve wording to guide faster execution without skipping steps
  - Remove any unnecessary verbosity that slows LLM processing
- Add guidance to help LLM execute commands efficiently without overthinking

### 6. Verify changes don't break tests
- Run existing test suite: `uv run pytest tests/unit/test_finalize_command.py`
- Ensure all tests still pass
- Tests mock the execution so should not be affected, but verify
- If any test failures, investigate and fix

## Deliverables

1. Updated `src/lw_coder/prompts/claude-code/finalize.md` with optimized command sequences
2. Updated `src/lw_coder/prompts/droid/finalize.md` with optimized command sequences
3. All existing tests passing (`tests/unit/test_finalize_command.py`)

## Unit Tests

- Existing unit tests in `tests/unit/test_finalize_command.py` should continue to pass
- Tests mock subprocess execution, so prompt changes should not affect them
- If needed, update test assertions to match new prompt structure

## Integration Tests

- No integration tests required for this change (prompt content only)

## Out of Scope

- Modifying the executor architecture
- Adding new finalize workflow steps or changing git strategy
- Adding documentation comments about optimization approach or trade-offs
- Writing new tests
- Manual testing or verification with real finalization workflows
- Performance benchmarking or metrics collection
- Updating other command prompts (plan, code, eval, etc.)
