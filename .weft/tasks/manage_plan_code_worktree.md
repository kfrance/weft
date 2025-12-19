---
plan_id: manage-plan-code-worktree
git_sha: a4eca188015cb3c711fd2ec36a73a1778e836b75
status: done
evaluation_notes:
  - Do both CLI commands create or reuse the shared worktree exactly once and report its path?
  - Are error scenarios covered by tests, including branch mismatch, missing worktree registration, and duplicate usage elsewhere?
  - Did the validator/tests drop the branch_name field and keep plan_id requirements intact?
---

# Task Plan: Manage Shared Plan/Code Worktree

## Objectives
- Introduce an `lw_coder plan` CLI command (stub or placeholder signature) that prepares the shared Git worktree for a task plan.
- Extend `lw_coder code` to share the same worktree preparation behavior.
- Derive the worktree branch name from `plan_id` (just the plan_id itself), eliminating the `branch_name` front matter field.
- Report the resolved worktree location upon success while preserving existing validation messaging.

## Requirements & Constraints
- Plans remain Markdown with YAML front matter; reuse existing validation, now requiring `plan_id`, `git_sha`, `status`, and `evaluation_notes` (no `branch_name`).
- Both commands must:
  - Run the validator and stop if it fails.
  - Ensure `.lw_coder/worktrees/<plan_id>` exists; create intermediate directories if needed.
  - Verify the directory is either absent or a registered Git worktree; error with guidance if a non-worktree directory is present.
  - Ensure a Git worktree exists at that path on branch `<plan_id>`, creating the branch from the plan's `git_sha` when necessary.
  - Refuse to proceed if the branch tip differs from `git_sha`, or if another worktree already uses the branch; surface clear error messages via `print`.
  - On success, keep the “Plan validation succeeded…” message and append the worktree path information.
- Commands should not alter the worktree’s dirty state, fetch remotes, or change plan `status` values.
- The project now includes a configured logging setup; leverage the existing logger for informational/error output instead of introducing new print-only paths.

## Work Items
1. **Schema Revision**
   - Remove the `branch_name` requirement from validator, metadata, and tests.
   - Update task documentation/examples to reflect deriving branch names from `plan_id`.
2. **Worktree Utilities**
   - Implement shared helper(s) for resolving plan metadata, computing worktree paths, and encapsulating Git interactions (existence checks, branch creation, worktree add/list logic).
   - Detect and report edge cases: existing non-worktree directories, branch checked out elsewhere, branch tip mismatch.
3. **CLI Updates**
   - Add the `plan` subcommand (placeholder signature for now) that invokes the shared worktree preparation.
   - Extend `code` to reuse the same helper and print the worktree path after successful validation.
4. **Testing**
   - Unit-test the new helper logic using temporary repos to simulate success and failure states.
   - Update CLI integration tests (leveraging the existing temporary `git_repo` fixture so our real repo is never touched) to cover both commands: successful setup, branch mismatch rejection, reused worktree, non-worktree directory error, and branch tip mismatch.
   - Ensure evaluation notes/settings align with the revised schema.

## Deliverables
- Updated validator, CLI, and supporting modules implementing the worktree management behavior.
- Comprehensive tests validating success paths and representative failure conditions.
- Documentation within `.lw_coder/tasks/` reflecting the schema change and new command responsibilities.

## Out of Scope
- Automating dirty-state detection, fetch/reset behavior, or additional worktree cleanup.
- Implementing post-code commands that handle commits, pushes, or teardown.
- Introducing structured logging or standardized error formats beyond current `print` statements.
- Editor launching, file copying, or other workflow automation inside the worktree.
