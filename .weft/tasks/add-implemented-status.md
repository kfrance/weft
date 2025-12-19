---
plan_id: add-implemented-status
status: done
evaluation_notes: []
git_sha: eb6cadead626d3eda3cca43da658abd22d4fdce3
---

# Objectives

Add `implemented` status to the plan lifecycle to fix tab completion issue where finalized plans cannot be tab-completed because they are marked `done` immediately after the code command finishes.

# Requirements & Constraints

- Change status lifecycle from `draft` → `coding` → `done` to `draft` → `coding` → `implemented` → `done`
- The `code` command must set status to `implemented` on successful exit (currently sets `done`)
- The `finalize` command continues to set status to `done` (no change required)
- Tab completion filters plans with `status: done` (no change required)
- Remove unused `review` status from valid statuses
- Maintain backward compatibility: existing plans with `status: done` remain valid (all have been finalized)
- All changes must pass existing tests with appropriate updates

# Work Items

1. **Update plan_validator.py to support new status values**
   - Locate valid status definitions (likely in parametrized tests around line 75)
   - Update valid statuses from `["draft", "coding", "done", "review"]` to `["draft", "coding", "implemented", "done"]`
   - Remove `review` from any status validation logic

2. **Update code_command.py to set implemented status**
   - Locate status update after successful session (around line 392)
   - Change `update_plan_fields(plan_path, {"status": "done"})` to `update_plan_fields(plan_path, {"status": "implemented"})`
   - Verify this is the only location in code_command.py that sets status to `done`

3. **Update test_code_command.py for new status**
   - Find all test assertions expecting `status: done` after code command execution
   - Update assertions to expect `status: implemented` instead
   - Update test function names containing "done" to use "implemented" (e.g., `test_code_command_status_done_on_success` → `test_code_command_status_implemented_on_success`)
   - Verify tests still cover the full lifecycle including finalize setting `done`

4. **Update test_plan_validator.py**
   - Remove `review` from parametrized test cases (line ~75)
   - Add test cases validating `implemented` as a valid status
   - Ensure no tests rely on `review` status being valid

5. **Search for and update other test files**
   - Search all test files for references to `status: done` in contexts related to code command
   - Update any fixtures or test data that should use `implemented` instead
   - Verify test_finalize_command.py correctly expects input plans with `implemented` status

6. **Verify finalize_command.py requires no changes**
   - Confirm finalize_command.py:188 sets `status: done` (should remain unchanged)
   - Confirm finalize reads plans regardless of whether they're `implemented` or `done`

7. **Verify completion/cache.py requires no changes**
   - Confirm cache.py:83 filters `status: done` (should remain unchanged)
   - This is the core fix: implemented plans will now appear in tab completion

# Deliverables

- Updated `src/lw_coder/plan_validator.py` with new valid statuses: `draft`, `coding`, `implemented`, `done`
- Updated `src/lw_coder/code_command.py` setting `status: implemented` on success
- Updated `tests/test_code_command.py` with corrected assertions and test names
- Updated `tests/test_plan_validator.py` removing `review` status tests
- Any other updated test files that reference the status lifecycle
- All tests passing with new status lifecycle

# Out of Scope

- Adding state transition validation logic (e.g., preventing draft → done)
- Migrating existing plans with `status: done` (all have been finalized)
- Adding documentation about the status lifecycle (can be done separately)
- Changing status names to alternatives like `validated` or `merged`
- Adding explicit `finalized` boolean flag
- Implementing file locking for concurrent modifications
- Adding git state verification matching plan status

# Test Cases

## Feature: Add implemented status to plan lifecycle
The system needs a new `implemented` status between `coding` and `done` so that completed code work can be tab-completed before finalization.

### Scenario: Code command sets implemented status on success
```gherkin
Given a plan file with status "coding"
When the code command session exits successfully with code 0
Then the plan file status should be updated to "implemented"
And the plan should appear in tab completion results
```

### Scenario: Finalize command still sets done status
```gherkin
Given a plan file with status "implemented"
When the finalize command completes successfully
Then the plan file status should be updated to "done"
And the plan should not appear in tab completion results
```

### Scenario: Plan validator accepts implemented status
```gherkin
Given a plan file with status "implemented" in the YAML front matter
When the plan is validated by load_plan_metadata
Then validation should succeed
And the metadata.status should equal "implemented"
```

### Scenario: Plan validator rejects review status
```gherkin
Given a plan file with status "review" in the YAML front matter
When the plan is validated by load_plan_metadata
Then validation should fail
And an error should indicate "review" is not a valid status
```

### Scenario: Tab completion includes implemented plans
```gherkin
Given a tasks directory with multiple plan files
And one plan has status "draft"
And one plan has status "coding"
And one plan has status "implemented"
And one plan has status "done"
When tab completion requests active plans
Then the results should include plans with status "draft", "coding", and "implemented"
And the results should not include plans with status "done"
```

### Scenario: Code command does not set done status
```gherkin
Given a plan file with status "coding"
When the code command session exits successfully
Then the plan file status should be "implemented"
And the plan file status should not be "done"
```

### Scenario: Backward compatibility with existing done plans
```gherkin
Given a plan file with status "done" from before this change
When the plan is validated by load_plan_metadata
Then validation should succeed
And the plan should be treated as fully completed
```

### Scenario: Full lifecycle progression
```gherkin
Given a newly created plan with status "draft"
When the code command starts execution
Then the status should change to "coding"
When the code command session exits successfully
Then the status should change to "implemented"
When the finalize command completes successfully
Then the status should change to "done"
```
