---
plan_id: plan-augment-plan-fields
branch_name: lw/plan/augment-plan-fields
git_sha: 6488c0e47c1e773607a2176afda6057c71157a0f
status: draft
evaluation_notes:
  - Do the validator tests cover the new required front matter fields?
  - Are the optional metadata fields handled gracefully when present or absent?
  - Do the updated tests include both success and failure scenarios for the new schema?
---

# Task Plan: Expand Plan Metadata Schema

## Objectives
- Update plan validation to require \`plan_id\`, \`branch_name\`, \`git_sha\`, \`status\`, and \`evaluation_notes\` in the front matter.
- Treat \`linear_issue_id\`, \`created_by\`, \`created_at\`, and \`notes\` as optional metadata surfaced to downstream consumers when present.
- Extend the test suite to cover the new schema while keeping existing validations intact.
- Fix \`tests/test_plan_validator.py::test_nonexistent_git_sha\` so it exercises \`load_plan_metadata\` and asserts the missing-commit failure.

## Requirements & Constraints
- Plans remain Markdown files with YAML front matter followed by non-empty body content.
- The status field must use one of the enumerated values: `draft`, `ready`, `coding`, `review`, `done`, or `abandoned` (case-insensitive, normalized to lowercase).
- The validator should provide clear, actionable error messages when required fields are missing or malformed.
- Field validation rules:
  - `plan_id`: Pattern `^[a-zA-Z0-9._-]{3,100}$` and must be unique within `.lw_coder/tasks/` directory
  - `branch_name`: Non-empty string
  - `created_at` (optional): Valid ISO 8601 datetime format, validated by parsing
- Breaking change: All existing tests will be updated to use the new required field schema.
- Unknown fields beyond the defined required and optional fields are rejected.
- Existing integration coverage that asserts CLI behavior must continue to pass unchanged.

## Work Items
1. **Schema & Validator**
   - Expand `_REQUIRED_KEYS` to include the new mandatory fields: `plan_id`, `branch_name`, `status`
   - Update `_enforce_exact_keys()` to allow defined optional fields: `linear_issue_id`, `created_by`, `created_at`, `notes`
   - Add validation functions for new fields:
     - `plan_id`: regex pattern + uniqueness check in `.lw_coder/tasks/`
     - `status`: case-insensitive enum validation, normalize to lowercase
     - `created_at`: ISO 8601 datetime parsing validation
     - `branch_name`: non-empty string validation
   - Adjust `PlanMetadata` dataclass with new required fields and optional fields (defaulting to `None`).
2. **CLI Adjustments**
   - Keep current minimal output; new metadata available programmatically through `PlanMetadata`.
3. **Testing**
   - Update all existing test helper functions to use new required schema (breaking change approach).
   - Add unit tests that exercise success cases with optional metadata present/absent.
   - Add failure cases for missing required fields, invalid status values, malformed optional fields, duplicate plan_id.
   - Fix incomplete `test_nonexistent_git_sha` test to call `load_plan_metadata()` and assert failure.
   - Verify integration tests still succeed with updated fixtures.

## Deliverables
- Updated validator and CLI source reflecting the expanded schema.
- Enhanced tests demonstrating validation for the new required and optional fields.
- Confirmation that the full test suite passes.

## Out of Scope
- Automatic branch creation or remote interactions within the CLI.
- Persisting or mutating plan status outside of validation.
- Worktree orchestration changes beyond recognizing the new metadata fields.
