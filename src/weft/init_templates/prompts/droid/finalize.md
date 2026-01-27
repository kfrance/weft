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
