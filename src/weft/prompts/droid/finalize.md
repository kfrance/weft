# Finalize Plan Workflow

You are finalizing the work for plan `{PLAN_ID}`. Your task is to commit all changes, rebase onto main, and merge the work back into the main branch.

## Workflow Steps

Follow these steps in order:

### 1. Verify and analyze uncommitted changes

Run `git status` once to:
1. Verify there are uncommitted changes - if the working directory is clean, **stop** and report an error
2. Review the list of changed and untracked files to understand what was modified

### 2. Generate commit message and commit

Generate a commit message based on the git status output, then stage and commit in a single command:

**Commit message format:**
```
<short summary> (50-72 chars)

@.weft/tasks/{PLAN_ID}.md

[2-3 sentence overview of changes]

[Optional: Key technical decisions or non-obvious aspects]

[Optional: Dependencies/Breaking changes]
```

Aim for 10 lines total in body (maximum 15).

**Execute immediately** after generating the message:
```bash
git add -A && git commit -m "<your generated commit message>"
```

This stages all changes (including the plan file at `.weft/tasks/{PLAN_ID}.md`) and commits them in one command.

### 3. Rebase onto main

Run:
```bash
git rebase main
```

If conflicts occur, work with the user to resolve them interactively, then continue the rebase with `git rebase --continue`.

### 4. Switch to main repo and merge

Navigate to the main repository root, checkout main, and merge in a single command chain:
```bash
cd $(git rev-parse --git-common-dir)/.. && git checkout main && git merge --ff-only {PLAN_ID}
```

The `--ff-only` flag ensures a fast-forward merge (linear history). If any step in this chain fails:
- `cd` failure: Could not determine main repository location
- `checkout` failure: Main branch may have conflicts or other issues
- `merge` failure: The rebase step may not have completed correctly

**After successful merge**: Exit with success code. The Python wrapper will automatically clean up the worktree and delete the branch.

## Important Notes

- **No automatic rollback**: If something fails, help the user resolve it interactively.
- **Linear history**: Always use rebase + fast-forward merge to maintain linear history.
- **Plan file is required**: The plan file MUST be included in the commit.
- **User approval**: All git operations require user review via Droid permission prompts.
- **Automatic cleanup**: On successful exit (code 0), the worktree and branch are automatically removed by the Python wrapper. Do not attempt to remove them manually.

## Error Handling

- If there are no uncommitted changes, report an error and stop.
- If staging fails, help the user understand why and retry.
- If rebase encounters conflicts, guide the user through resolution.
- If fast-forward merge fails, investigate the git history and help resolve.
