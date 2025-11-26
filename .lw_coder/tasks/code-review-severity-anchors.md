---
plan_id: code-review-severity-anchors
status: done
evaluation_notes: []
git_sha: 1042bc0452b7363249c6b3925ef3aa4637be19d2
---

# Add Severity Classification Anchors to Code Review Agent

## Objectives

1. Improve the code review agent's severity classification accuracy through concrete examples and decision criteria
2. Ensure code reviews stay confined to the plan scope and don't suggest features outside the plan
3. Provide clear, principle-based guidance for classifying issues as HIGH, MEDIUM, or LOW severity
4. Maintain consistency across all three model variants (sonnet, opus, haiku)

## Requirements & Constraints

### Functional Requirements

- Add `plan.md` to the mandatory context gathering section of the code-review-auditor prompt
- Add plan scope confinement guidance to prevent suggestions outside plan scope
- Embed severity classification anchors with both examples and decision criteria directly in the prompt
- Include principle-based duplication threshold: "typically 20+ lines OR synchronized logic requiring coordinated changes (regex, constants, business rules)"
- Mark optimizations/refactoring/nice-to-haves not in plan as LOW severity with user authorization warning
- Explicitly state the agent should never suggest additional features
- Trust agent judgment for edge cases and exceptions

### Technical Constraints

- Must update all three model variants consistently:
  - `.lw_coder/optimized_prompts/claude-code-cli/sonnet/code-review-auditor.md`
  - `.lw_coder/optimized_prompts/claude-code-cli/opus/code-review-auditor.md`
  - `.lw_coder/optimized_prompts/claude-code-cli/haiku/code-review-auditor.md`
- Must preserve existing prompt structure and formatting
- Must maintain existing mandatory context gathering requirements (git commands, file reading, docs)
- Must keep the existing output format (markdown with Type and Severity fields)
- Guidance must be embedded in the prompt itself (not externalized to separate file)

### Project Guidelines

- Follow guidance from `docs/BEST_PRACTICES.md` - violations of documented standards should be HIGH severity
- Respect `docs/THREAT_MODEL.md` - security issues within scope (accidental misconfiguration, data leakage) are HIGH severity
- No automated tests required (manual testing only)

## Work Items

### 1. Update Mandatory Context Gathering Section

**Current state:** Agent reads git status, git diff, git ls-files, complete file contents, and project guidance files (THREAT_MODEL.md, BEST_PRACTICES.md, AGENTS.md)

**Changes needed:**
- Add `plan.md` to the list of files the agent must read during context gathering
- Add note that the agent should understand the plan scope before analyzing code

**Location:** Lines 3-11 in all three code-review-auditor.md files

### 2. Add Plan Scope Confinement Guidance

**New section to add:** After "Analysis Expectations" section (around line 28)

Add guidance that specifies:
- Reviews must stay confined to what the plan calls for
- Don't suggest features or improvements outside plan scope
- Don't suggest additional features under any circumstances
- Optimizations, refactoring, and nice-to-have improvements not in the plan should be marked LOW severity with a note that user authorization is required

### 3. Add Severity Classification Anchors

**New section to add:** After plan scope guidance, before "Reporting Format" section

Create a comprehensive "Severity Classification Guide" section with:

**HIGH Severity - Issues that must be fixed:**
- Causes data loss or corruption
- Causes crashes, errors, or broken functionality
- Violates documented guidelines in `docs/*.md` files (BEST_PRACTICES.md, THREAT_MODEL.md, etc.)
- Security issues within threat model scope (accidental misconfiguration, data leakage through logs/cache, protection against common mistakes)
- Missing or incorrect implementation of features the plan explicitly calls for
- Missing error handling for expected failure cases
- Incorrect logic that produces wrong results
- Significant code duplication:
  - Typically 20+ lines of duplicated code, OR
  - Logic requiring coordinated changes across multiple locations (regex patterns, constants, business rules) regardless of size
  - Example: A regex pattern duplicated in 3 files - changing the validation rule requires updating all 3 copies

**MEDIUM Severity - Quality issues affecting maintainability:**
- Weak test assertions that don't properly verify behavior
- Missing test coverage for edge cases (when tests don't fail but coverage gaps exist)
- Inconsistent patterns that don't violate documented standards
- Minor maintainability concerns that make future changes harder

**LOW Severity - Improvements that require user authorization:**
- Missing comments or documentation
- Performance optimizations not called for in the plan (add note: "⚠️ Optimization suggestion - requires user authorization before implementing")
- Refactoring not called for in the plan (add note: "⚠️ Refactoring suggestion - requires user authorization before implementing")
- Nice-to-have improvements not in the plan
- Minor performance inefficiencies with minimal impact
- Code duplication under 20 lines that doesn't represent synchronized logic

### 4. Add Decision Criteria

**Add subsection:** "Severity Decision Questions"

Provide a decision flow to help classify issues:

1. **Does this violate a documented standard in docs/*.md?** → HIGH
2. **Does this cause data loss, crashes, or incorrect results?** → HIGH
3. **Is this a security issue within our threat model scope?** → HIGH
4. **Is this missing or incorrectly implementing something the plan calls for?** → HIGH
5. **Is this duplicated logic that would require synchronized changes?** → HIGH (regardless of line count)
6. **Is this 20+ lines of duplicated code?** → HIGH
7. **Is this a test quality issue (weak assertions, missing coverage)?** → MEDIUM
8. **Is this an inconsistency or minor maintainability concern?** → MEDIUM
9. **Is this an optimization/refactoring not in the plan?** → LOW (note user auth required)
10. **Is this a comment/documentation suggestion?** → LOW

**Trust your judgment for edge cases and exceptions**

### 5. Update All Three Model Variants

Apply all changes consistently to:
1. `.lw_coder/optimized_prompts/claude-code-cli/sonnet/code-review-auditor.md`
2. `.lw_coder/optimized_prompts/claude-code-cli/opus/code-review-auditor.md`
3. `.lw_coder/optimized_prompts/claude-code-cli/haiku/code-review-auditor.md`

Ensure formatting, structure, and content are identical across all three files.

### 6. Verify Prompt Structure

After updates, verify:
- Markdown formatting is correct
- Section order is logical (Context Gathering → Verification → Analysis → Plan Scope → Severity Guide → Reporting → Guardrails)
- No broken references or inconsistencies
- Total prompt length is reasonable (not excessively long)

## Deliverables

1. **Updated code-review-auditor.md (sonnet variant)**
   - Location: `.lw_coder/optimized_prompts/claude-code-cli/sonnet/code-review-auditor.md`
   - Includes plan.md in context gathering
   - Includes plan scope confinement
   - Includes severity classification anchors with examples and decision criteria

2. **Updated code-review-auditor.md (opus variant)**
   - Location: `.lw_coder/optimized_prompts/claude-code-cli/opus/code-review-auditor.md`
   - Identical changes to sonnet variant

3. **Updated code-review-auditor.md (haiku variant)**
   - Location: `.lw_coder/optimized_prompts/claude-code-cli/haiku/code-review-auditor.md`
   - Identical changes to sonnet variant

## Out of Scope

- Creating separate `docs/REVIEW_SEVERITY.md` file (guidance embedded in prompt instead)
- Adding CRITICAL severity tier (keeping 3-tier system: HIGH/MEDIUM/LOW)
- Automated test coverage (manual testing only)
- Changes to `plan-alignment-checker` agent
- Changes to `main.md` prompt
- Changes to `code_command.py` (plan.md already copied to worktree)
- Modifications to existing issue Type categories (logic, test_quality, architecture, security)
- Hard enforcement of line count thresholds (using "typically" to allow judgment)

## Test Cases

Manual testing scenarios to verify the severity classification improvements:

```gherkin
Feature: Severity Classification with Anchors

  Scenario: High severity for data loss issue
    Given a code change that could silently overwrite files due to missing existence check
    And the plan calls for safe file handling
    When the code-review-auditor analyzes the changes
    Then it should classify the issue as HIGH severity
    And it should reference data loss in the description

  Scenario: High severity for docs violation
    Given test code that mocks DSPy/LLM calls
    And docs/BEST_PRACTICES.md explicitly forbids this pattern
    When the code-review-auditor analyzes the changes
    Then it should classify the issue as HIGH severity
    And it should reference the BEST_PRACTICES.md violation

  Scenario: High severity for significant code duplication (line count)
    Given 25 lines of identical code duplicated in 3 files
    When the code-review-auditor analyzes the changes
    Then it should classify the issue as HIGH severity
    And it should note the duplication requires coordinated changes

  Scenario: High severity for synchronized logic duplication
    Given a 5-line regex pattern duplicated in 3 locations
    And changing the validation rule would require updating all 3 copies
    When the code-review-auditor analyzes the changes
    Then it should classify the issue as HIGH severity
    And it should note this is synchronized logic requiring one source of truth

  Scenario: Medium severity for weak test assertion
    Given a test with only "assert result is not None"
    And the test doesn't verify expected behavior
    When the code-review-auditor analyzes the changes
    Then it should classify the issue as MEDIUM severity
    And it should recommend stronger assertions

  Scenario: Low severity for optimization not in plan
    Given code that recreates directories unnecessarily
    And the plan doesn't call for performance optimization
    When the code-review-auditor analyzes the changes
    Then it should classify the issue as LOW severity
    And it should include warning "⚠️ Optimization suggestion - requires user authorization before implementing"

  Scenario: Low severity for missing comments
    Given complex logic without explanatory comments
    When the code-review-auditor analyzes the changes
    Then it should classify the issue as LOW severity
    And it should note this is a documentation improvement

  Scenario: Plan scope confinement - no feature suggestions
    Given code that implements all plan requirements correctly
    And the code could benefit from additional features not in the plan
    When the code-review-auditor analyzes the changes
    Then it should NOT suggest additional features
    And it should report "No issues found" if plan is fully implemented

  Scenario: Plan scope confinement - reads plan.md
    Given the code review agent is invoked
    When it begins context gathering
    Then it should read plan.md from the worktree
    And it should list plan.md in the "Files read" section of the report

  Scenario: Agent judgment for edge cases
    Given a security vulnerability outside the documented threat model
    And the issue could cause real harm
    When the code-review-auditor analyzes the changes
    Then it should use judgment to flag the issue appropriately
    And it should explain the security concern clearly
```
