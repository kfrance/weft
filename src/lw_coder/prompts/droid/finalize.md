# Finalize Plan Workflow

You are finalizing the work for plan `{PLAN_ID}`. Your task is to commit all changes, rebase onto main, and merge the work back into the main branch.

## Workflow Steps

Follow these steps in order:

### 1. Verify uncommitted changes exist

Run `git status` to verify there are uncommitted changes. If the working directory is clean, **stop** and report an error.

### 2. Analyze changed and untracked files

Use `git status` to see all changed and untracked files. Review each file to understand what was modified.

### 3. Stage files for commit

- **Automatically stage** files that are clearly related to the plan implementation (source code, tests, configuration, documentation).
- **Ask the user for confirmation** before staging files that appear:
  - Unrelated to the plan
  - Temporary (e.g., `.pyc`, `.log`, `__pycache__`, temp files)
  - Testing artifacts not meant for commit

The plan file at `.lw_coder/tasks/{PLAN_ID}.md` should ALWAYS be staged.

### 4. Generate commit message

Analyze the staged changes using `git diff --staged` and create a commit message with the following format:

```
<short descriptive summary>
@.lw_coder/tasks/{PLAN_ID}.md

<detailed description of changes>
```

**Requirements:**
- Line 1: Short description (50-72 chars) summarizing the changes
- Line 2: Plan reference `@.lw_coder/tasks/{PLAN_ID}.md`
- Line 3+: Detailed description explaining what changed and why

### 5. Commit the changes

Run:
```bash
git commit -m "<your generated commit message>"
```

Ensure the commit includes the plan file at `.lw_coder/tasks/{PLAN_ID}.md`.

### 6. Rebase onto main

Run:
```bash
git rebase main
```

If conflicts occur, work with the user to resolve them interactively, then continue the rebase with `git rebase --continue`.

### 7. Switch to main repo and merge

First, navigate to the main repository root (not the worktree):
```bash
cd $(git rev-parse --show-toplevel)
```

Then checkout main and merge:
```bash
git checkout main
git merge --ff-only {PLAN_ID}
```

The `--ff-only` flag ensures a fast-forward merge (linear history). If it fails, the rebase step may have issues.

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
