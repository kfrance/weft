---
plan_id: LW-107-repo-specific-finalize
status: done
evaluation_notes: []
git_sha: 90a3bb4a338f5cd4e800e40a8c12f59d0ba3e414
---

# Repo-Specific Finalize Command

## Linear Issue

LW-107

## Objectives

Make the finalize command repo-specific by moving prompts to `.weft/prompts/active/` (like the code command). The default workflow changes from merge-to-main to PR creation, but repos can customize the finalize prompt to implement any workflow they prefer.

## Requirements & Constraints

1. **Prompt Location**: Finalize prompts load from `.weft/prompts/active/<tool>/finalize.md` instead of bundled templates
2. **No Model Variants**: Single prompt per tool (unlike code command's sonnet/opus/haiku variants)
3. **Auto-Copy Fallback**: If repo-specific prompt doesn't exist, auto-copy from bundled default to `.weft/prompts/active/` on first run
4. **Init Integration**: `weft init` copies finalize prompt templates alongside code prompts
5. **Default Workflow**: PR creation (push branch + `gh pr create`) instead of merge to main
6. **Cleanup Behavior**: Remove worktree after PR creation, but keep the branch
7. **Plan Status**: Remains "done" after successful PR creation
8. **PR Verification**: Verify PR was created before cleanup (replace merge verification)

## Work Items

### 1. Update Bundled Finalize Prompts

Update the bundled templates in `src/weft/prompts/` with PR-creation workflow:

**File: `src/weft/prompts/claude-code/finalize.md`**

~~~markdown
# Finalize Plan Workflow

You are finalizing the work for plan `{PLAN_ID}`. Your task is to commit all changes, push the branch, and create a pull request.

## Sandbox Notice

You are running in a sandbox environment. Read-only git commands like `git status`, `git log`, `git diff`, and `git branch` work normally in the sandbox. However, git commands that modify the repository (such as `git add`, `git commit`, `git push`) and the `gh` CLI need to run outside the sandbox. When executing these commands, request to run them outside the sandbox so the user can approve them.

## Workflow Steps

Follow these steps in order:

### 1. Verify and analyze uncommitted changes

Run `git status` once to:
1. Verify there are uncommitted changes - if the working directory is clean, **stop** and report an error
2. Review the list of changed and untracked files to understand what was modified

### 2. Stage changes deliberately

Review the `git status` output and stage files with explicit reasoning:

1. **Never use bulk staging commands** - `git add -A`, `git add .`, and `git add -u` are all forbidden
2. **Stage files individually or in logical groups**, explaining your reasoning:
   - For each file or group, explain why it belongs in this commit
   - Logical groupings are acceptable (e.g., "these 3 test files for the new feature")
   - Adding a folder is OK only when you're certain all its contents belong in the commit
3. **Report what you skipped** - explicitly list any files from `git status` that you did NOT stage and explain why (e.g., "Skipping `debug.log` - temporary debug file")
4. Run `git status` again to verify what will be committed

**Never stage these file types:**
- Generated files (logs, caches, `__pycache__/`, `node_modules/`)
- Editor/IDE config (`.idea/`, `.vscode/`, `*.swp`)
- Environment/secret files (`.env`, `*.pem`, credentials)
- Build artifacts (`dist/`, `build/`, `*.egg-info/`)
- Temporary or debug files created during development

If all files in `git status` are being staged, explicitly note: "All changed files are relevant to this commit - no files skipped."

### 3. Generate commit message and commit

**Commit message format:**

    <short summary> (50-72 chars)

    @.weft/tasks/{PLAN_ID}.md

    [2-3 sentence overview of changes]

    [Optional: Key technical decisions or non-obvious aspects]

    [Optional: Dependencies/Breaking changes]

Aim for 10 lines total in body (maximum 15).

**Commit** with your generated message:

    git commit -m "<your generated commit message>"

### 4. Push the branch

Push the branch to the remote:

    git push -u origin {PLAN_ID}

If the push fails due to upstream changes, fetch and rebase first:

    git fetch origin && git rebase origin/<base-branch> && git push -u origin {PLAN_ID}

If conflicts occur during rebase, work with the user to resolve them interactively, then continue with `git rebase --continue`.

### 5. Create pull request

Create a pull request using the GitHub CLI:

    gh pr create --title "<short summary from commit>" --body "<PR description>"

**PR description format:**

    ## Summary

    [2-3 sentences describing what this PR does]

    ## Plan Reference

    @.weft/tasks/{PLAN_ID}.md

    ## Changes

    [Bullet list of key changes]

After successfully creating the PR, report the PR URL to the user and exit with success code.

## Important Notes

- **No automatic rollback**: If something fails, help the user resolve it interactively.
- **Plan file is required**: The plan file MUST be included in the commit.
- **User approval**: All git operations require user review via Claude Code permission prompts.
- **Automatic cleanup**: On successful exit (code 0), the worktree is automatically removed by the Python wrapper. The branch is preserved for the pull request.

## Error Handling

- If there are no uncommitted changes, report an error and stop.
- If staging fails, help the user understand why and retry.
- If push fails, investigate and help resolve (often requires rebase).
- If PR creation fails, check `gh auth status` and help the user authenticate if needed.
~~~

**File: `src/weft/prompts/droid/finalize.md`**

~~~markdown
# Finalize Plan Workflow

You are finalizing the work for plan `{PLAN_ID}`. Your task is to commit all changes, push the branch, and create a pull request.

## Workflow Steps

Follow these steps in order:

### 1. Verify and analyze uncommitted changes

Run `git status` once to:
1. Verify there are uncommitted changes - if the working directory is clean, **stop** and report an error
2. Review the list of changed and untracked files to understand what was modified

### 2. Stage changes deliberately

Review the `git status` output and stage files with explicit reasoning:

1. **Never use bulk staging commands** - `git add -A`, `git add .`, and `git add -u` are all forbidden
2. **Stage files individually or in logical groups**, explaining your reasoning:
   - For each file or group, explain why it belongs in this commit
   - Logical groupings are acceptable (e.g., "these 3 test files for the new feature")
   - Adding a folder is OK only when you're certain all its contents belong in the commit
3. **Report what you skipped** - explicitly list any files from `git status` that you did NOT stage and explain why (e.g., "Skipping `debug.log` - temporary debug file")
4. Run `git status` again to verify what will be committed

**Never stage these file types:**
- Generated files (logs, caches, `__pycache__/`, `node_modules/`)
- Editor/IDE config (`.idea/`, `.vscode/`, `*.swp`)
- Environment/secret files (`.env`, `*.pem`, credentials)
- Build artifacts (`dist/`, `build/`, `*.egg-info/`)
- Temporary or debug files created during development

If all files in `git status` are being staged, explicitly note: "All changed files are relevant to this commit - no files skipped."

### 3. Generate commit message and commit

**Commit message format:**

    <short summary> (50-72 chars)

    @.weft/tasks/{PLAN_ID}.md

    [2-3 sentence overview of changes]

    [Optional: Key technical decisions or non-obvious aspects]

    [Optional: Dependencies/Breaking changes]

Aim for 10 lines total in body (maximum 15).

**Commit** with your generated message:

    git commit -m "<your generated commit message>"

### 4. Push the branch

Push the branch to the remote:

    git push -u origin {PLAN_ID}

If the push fails due to upstream changes, fetch and rebase first:

    git fetch origin && git rebase origin/<base-branch> && git push -u origin {PLAN_ID}

If conflicts occur during rebase, work with the user to resolve them interactively, then continue with `git rebase --continue`.

### 5. Create pull request

Create a pull request using the GitHub CLI:

    gh pr create --title "<short summary from commit>" --body "<PR description>"

**PR description format:**

    ## Summary

    [2-3 sentences describing what this PR does]

    ## Plan Reference

    @.weft/tasks/{PLAN_ID}.md

    ## Changes

    [Bullet list of key changes]

After successfully creating the PR, report the PR URL to the user and exit with success code.

## Important Notes

- **No automatic rollback**: If something fails, help the user resolve it interactively.
- **Plan file is required**: The plan file MUST be included in the commit.
- **User approval**: All git operations require user review via Droid permission prompts.
- **Automatic cleanup**: On successful exit (code 0), the worktree is automatically removed by the Python wrapper. The branch is preserved for the pull request.

## Error Handling

- If there are no uncommitted changes, report an error and stop.
- If staging fails, help the user understand why and retry.
- If push fails, investigate and help resolve (often requires rebase).
- If PR creation fails, check `gh auth status` and help the user authenticate if needed.
~~~

### 2. Create Finalize Prompt Loader Function

Add a new function to `src/weft/prompt_loader.py`:

```python
def load_finalize_prompt(repo_root: Path, tool: str) -> str:
    """Load finalize prompt from repo-specific location, auto-copying from bundled if missing.

    Args:
        repo_root: Path to repository root
        tool: Tool name (e.g., "claude-code", "droid")

    Returns:
        Finalize prompt content as string

    Raises:
        PromptLoaderError: If prompt cannot be loaded or auto-copied
    """
```

Behavior:
- Check for `.weft/prompts/active/<tool>/finalize.md`
- If missing, create parent directories and copy from bundled `src/weft/prompts/<tool>/finalize.md`
- Return the prompt content
- Raise `PromptLoaderError` if bundled template is also missing

### 3. Update Init Command

Modify `src/weft/init_command.py` to copy finalize prompts during `weft init`:

- Update `AtomicInitializer.copy_optimized_prompts()` to also copy finalize prompt templates
- Copy `src/weft/prompts/<tool>/finalize.md` to `.weft/prompts/active/<tool>/finalize.md` for each supported tool
- Update VERSION file hashing to include finalize prompts

### 4. Update Finalize Command

Modify `src/weft/finalize_command.py`:

- Replace `load_prompt_template(tool, "finalize")` with `load_finalize_prompt(repo_root, tool)`
- Replace `verify_branch_merged_to_main()` with new `verify_pr_created()` function that checks `gh pr list --head {PLAN_ID}`
- Update cleanup logic: remove worktree but preserve branch (modify `_cleanup_worktree_and_branch()` to skip branch deletion)

### 5. Unit Tests

**File: `tests/unit/test_prompt_loader.py`** - Add tests for `load_finalize_prompt()`:
- Test loading from existing repo-specific location
- Test auto-copy when repo-specific prompt missing (including directory creation)
- Test auto-copy is idempotent (calling twice doesn't fail)
- Test error handling when bundled template also missing
- Test placeholder replacement works correctly (multiple `{PLAN_ID}` occurrences)

**File: `tests/unit/test_finalize_command.py`** - Update existing tests:
- Update mocks from `load_prompt_template` to `load_finalize_prompt`
- Update `verify_branch_merged_to_main` mocks to `verify_pr_created`
- Add test verifying branch is NOT deleted after successful completion
- Add test verifying worktree IS removed after successful completion
- Add test for `verify_pr_created()` success case (PR exists)
- Add test for `verify_pr_created()` failure case (no PR found)

**File: `tests/unit/test_init_command.py`** - Add/update tests:
- Test that finalize prompts are copied during init for both claude-code and droid
- Update directory structure verification tests to include finalize prompts at `.weft/prompts/active/<tool>/finalize.md`
- Verify VERSION file hash tests include finalize prompts

### 6. Integration Tests

**File: `tests/integration/test_finalize_flow.py`** - New integration test:

Test the finalize command orchestration with mocked executor in an isolated test environment:

**Setup (following existing integration test patterns):**
- Use `git_repo` fixture to create an isolated temporary git repository
- Run `weft init --yes` in the test repo to set up `.weft/prompts/active/` with finalize prompts
- Create a plan file in `.weft/tasks/` with valid YAML front matter
- Create a worktree for the plan (simulating `weft code` having run)
- Add uncommitted changes in the worktree

**Test execution:**
- Mock the executor's `run()` method to simulate successful Claude Code execution (exit code 0)
- Mock `subprocess.run` for `gh pr list` to return a PR for the branch
- Call `run_finalize_command()` with the test plan

**Assertions:**
- Verify the prompt written to the temp file contains the plan_id
- Verify worktree directory no longer exists after completion
- Verify branch still exists after completion (check with `git branch --list`)
- Verify plan status is set to "done"

This tests the orchestration logic without running the interactive Claude Code session, entirely within the temporary test environment.

## Deliverables

1. Updated `src/weft/prompts/claude-code/finalize.md` with PR workflow
2. Updated `src/weft/prompts/droid/finalize.md` with PR workflow
3. New `load_finalize_prompt()` function in `src/weft/prompt_loader.py`
4. New `verify_pr_created()` function in `src/weft/finalize_command.py`
5. Updated `src/weft/init_command.py` to copy finalize prompts
6. Updated `src/weft/finalize_command.py` to use repo-specific prompts and new verification
7. Updated unit tests in `tests/unit/`
8. New integration test in `tests/integration/test_finalize_flow.py`

## Out of Scope

- Customization UI for finalize prompts (users edit files directly)
- Multiple finalize workflows per repo (single prompt per tool)
- Model-specific finalize prompt variants
- Automatic PR merge after creation
- Branch protection rule handling
- Configurable base branch (users customize the prompt if needed)
- PR template customization beyond the prompt
