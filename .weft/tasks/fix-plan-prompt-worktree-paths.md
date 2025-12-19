---
plan_id: fix-plan-prompt-worktree-paths
status: done
evaluation_notes: []
git_sha: e0485693df6d8adeafda17ba564fab7ba2d38215
---

# Fix Plan Prompt Template to Use Worktree Paths

## Objectives

Update the plan command prompt templates to explicitly instruct executors to look for documentation files in their current working directory (the worktree), rather than using the ambiguous phrase "in the project" which causes Claude Code to attempt reading files from the main repository outside the worktree.

## Requirements & Constraints

### Requirements
- Update `src/lw_coder/prompts/claude-code/plan.md` to replace "in the project" with "in your current working directory"
- Update `src/lw_coder/prompts/droid/plan.md` to replace "in the project" with "in your current working directory"
- Maintain all other functionality and wording in the prompt templates
- Ensure the change applies to both line 5 (documentation lookup) and line 8 (codebase examination) in claude-code/plan.md
- Ensure the change applies to line 5 in droid/plan.md (line 8 already correctly references "/workspace")

### Constraints
- Must not break existing plan command functionality
- Must preserve the template placeholder `{IDEA_TEXT}` and all task instructions
- Changes must be minimal and focused on the path reference issue only
- Must work for both Claude Code and Droid executors

## Work Items

1. **Update claude-code/plan.md**
   - Change line 5: Replace "in the project" with "in your current working directory"
   - Change line 8: Replace "in the project" with "in your current working directory"

2. **Update droid/plan.md**
   - Change line 5: Replace "in the project" with "in your current working directory"
   - Verify line 8 already has explicit "/workspace" reference (no change needed)

3. **Verify changes**
   - Read both files to confirm changes are applied correctly
   - Ensure no other unintended modifications were made

## Deliverables

- Modified `src/lw_coder/prompts/claude-code/plan.md` with updated path references
- Modified `src/lw_coder/prompts/droid/plan.md` with updated path references
- Both files should instruct executors to look for files "in your current working directory" instead of "in the project"

## Out of Scope

- Updating other prompt templates (code.md, finalize.md) - these can be addressed in a future plan if needed
- Adding inline documentation or comments to prompt files
- Creating test coverage for prompt isolation
- Architectural refactoring of prompt template system
- More explicit wording like "repository root in your current working directory"
- Documentation updates to explain the worktree isolation model
