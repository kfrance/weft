---
plan_id: remove-gherkin-test-format
status: done
evaluation_notes: []
git_sha: 6f46ee864333c898136c5693ec85a2cfd912d119
---

# Task Plan: Replace Gherkin Test Format with Unit/Integration Test Sections

## Objectives
- Remove Gherkin-formatted test case requirements from plan file templates
- Replace with separate Unit Tests and Integration Tests sections that align with project test organization
- Maintain overall plan template structure while making test guidance more practical and flexible

## Requirements & Constraints
- Update both plan template files: `src/lw_coder/prompts/claude-code/plan.md` and `src/lw_coder/prompts/droid/plan.md`
- Keep templates synchronized (both should have identical content)
- Align with existing test organization documented in CLAUDE.md (tests/unit/ and tests/integration/)
- Preserve all other template sections (YAML front matter, Objectives, Requirements & Constraints, Work Items, Deliverables, Out of Scope)
- No changes needed to existing plan files or test code
- New format should provide clear guidance on what unit vs integration tests are needed

## Work Items
1. **Update Template Files**
   - Edit `src/lw_coder/prompts/claude-code/plan.md` (lines 15-22)
   - Edit `src/lw_coder/prompts/droid/plan.md` (lines 15-22)
   - Replace Gherkin test case instruction with two-section approach:
     - Unit Tests section (fast tests, mocked dependencies, no external API calls)
     - Integration Tests section (real API calls, end-to-end validations)

2. **Validation**
   - Verify both template files remain synchronized
   - Ensure YAML front matter and other sections are unchanged
   - Confirm the new format provides clear, actionable test guidance

## Deliverables
- Updated `src/lw_coder/prompts/claude-code/plan.md` with Unit/Integration test sections
- Updated `src/lw_coder/prompts/droid/plan.md` with Unit/Integration test sections
- Both templates remain synchronized and functionally equivalent

## Out of Scope
- Modifying existing plan files in `.lw_coder/tasks/`
- Updating test code or test organization
- Adding automated validation of plan template format
- Changing any other parts of the plan template structure

## Unit Tests
- No unit tests needed (this is a documentation/template change)

## Integration Tests
- No integration tests needed (this is a documentation/template change)
