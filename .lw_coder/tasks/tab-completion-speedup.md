---
git_sha: a781b401a639148dcbf1d50c4fd8d2488c35e792
plan_id: tab-completion-speedup
status: done
evaluation_notes: []
---

# Tab Completion Speedup

## Objectives

Improve tab completion performance by eliminating heavy module imports during bash tab completion operations.

**Primary Goals:**
- Reduce tab completion latency by ~600ms-1.15s
- Remove yaml dependency entirely (switch to regex parsing)
- Lazy-load command modules to avoid importing heavy dependencies during completion
- Establish performance regression testing to prevent future slowdowns

**Success Criteria:**
- Tab completion completes in <200ms (median of 10 runs, threshold determined empirically post-implementation)
- Command modules (code, finalize, plan, recover) are not imported during tab completion
- All existing functionality continues to work correctly
- Performance regression test catches future heavy imports

## Requirements & Constraints

**Requirements:**
- Maintain backward compatibility - all CLI commands must work exactly as before
- Preserve all existing validation logic and error messages
- Plan files in `.lw_coder/tasks/` remain unchanged (no format changes)
- Tests must verify functional correctness and performance

**Constraints:**
- Plan files use simple YAML format only (key: value pairs, simple lists)
- Regex parser must handle current plan file format:
  - String fields: `git_sha`, `plan_id`, `status`, `linear_issue_id`, `created_by`, `created_at`, `notes`
  - List fields: `evaluation_notes` (can be empty: `[]` or have items)
- Performance threshold must be measured after implementation (not guessed beforehand)
- Changes must not break existing tests

**Technical Constraints:**
- Python 3.10+ (existing project requirement)
- Must work with argcomplete tab completion system
- Lazy imports must not introduce import-order side effects

## Work Items

### 1. Replace YAML Parsing with Regex in plan_validator.py

**Current State:**
- `plan_validator.py` imports yaml at line 11
- `_extract_front_matter()` uses `yaml.safe_load()` to parse front matter
- This adds ~100-150ms import overhead during tab completion

**Changes Required:**

**1.1. Remove yaml import**
- Delete `import yaml` from line 11 in `src/lw_coder/plan_validator.py`
- Remove yaml from project dependencies in `pyproject.toml` (if not used elsewhere)

**1.2. Implement regex-based front matter parser**

Replace `_extract_front_matter()` implementation with regex-based parsing:

**Pseudocode:**
```
function _extract_front_matter(markdown: str) -> (dict, str):
    # Validate front matter delimiters (---) at start
    # Find closing delimiter
    # Extract lines between delimiters

    # Parse each line in front matter:
    #   - If line matches "key: value" pattern:
    #     - If value is "[]", store as empty list
    #     - If value is non-empty, store as string
    #     - If value is empty, expect list items on following lines
    #   - If line matches "  - item" pattern:
    #     - Add to current list being built

    # Return (front_matter_dict, body_text)
```

**Implementation notes:**
- Use regex patterns to match field declarations and list items
- Handle both empty lists (`[]`) and multi-line list items (`- item`)
- Preserve existing error messages for malformed front matter
- Add docstring: "Uses regex instead of YAML for performance. Migrate to YAML if format becomes complex."

**1.3. Update error handling**
- Ensure regex parsing errors provide helpful messages
- Test edge cases: empty front matter, malformed delimiters, invalid syntax

**1.4. Update tests**
- Review tests in `tests/test_plan_validator.py`
- Remove any yaml-specific test setup/mocking
- Add tests for regex parser edge cases:
  - Empty lists: `evaluation_notes: []`
  - Lists with items:
    ```yaml
    evaluation_notes:
      - "note 1"
      - "note 2"
    ```
  - All required/optional fields
  - Malformed front matter

### 2. Lazy-Load Command Modules in cli.py

**Current State:**
- Lines 11-19 import command modules at top level:
  ```python
  from .code_command import run_code_command
  from .finalize_command import run_finalize_command
  from .plan_command import run_plan_command
  from .recover_command import run_recover_command
  ```
- These imports pull in heavy dependencies (executors, sdk_runner, worktree_utils, etc.)
- `eval_command` already uses lazy-loading pattern (lines 232-233)

**Changes Required:**

**2.1. Remove top-level command imports**

Delete lines 11, 14, 17, 19 in `src/lw_coder/cli.py`:
```python
# DELETE these lines:
from .code_command import run_code_command
from .finalize_command import run_finalize_command
from .plan_command import run_plan_command
from .recover_command import run_recover_command
```

**2.2. Add lazy imports in command dispatch blocks**

Follow the existing `eval_command` pattern (lines 232-233) for all command handlers:

**For each command (plan, finalize, recover-plan, code):**
- Add lazy import at the start of the command's `if` block
- Include comment: `# Lazy import to avoid loading heavy dependencies during tab completion`
- Import only the specific function needed (e.g., `from .code_command import run_code_command`)
- Keep all existing logic unchanged after the import

**2.3. Verify import side effects**
- Audit command modules for import-time side effects:
  - Signal handlers
  - Global state initialization
  - Logging configuration
  - Module-level execution
- Ensure lazy loading doesn't break initialization order

### 3. Add Performance Regression Test

**Create `tests/completion/test_performance.py`:**

**Test structure:**
- Create test function `test_tab_completion_performance_threshold(tmp_path)`
- Set up temporary git repo with sample plan files in `.lw_coder/tasks/`
- Run tab completion simulation 10 times by importing `lw_coder.completion.cache` in subprocess
- Calculate median time
- Assert median < THRESHOLD_MS (placeholder: 200ms, update after measuring)
- Provide helpful error message listing common causes of slowdown

**Performance threshold measurement process:**
After implementing all changes, measure the threshold by running tab completion 100 times:
```bash
python3 -c "
import time, statistics, subprocess, sys
times = []
for i in range(100):
    start = time.perf_counter()
    subprocess.run([sys.executable, '-c',
        'from lw_coder.completion.cache import get_active_plans; get_active_plans()'
    ], capture_output=True, check=True)
    times.append((time.perf_counter() - start) * 1000)
print(f'p50: {statistics.median(times):.1f}ms')
print(f'p95: {statistics.quantiles(times, n=20)[18]:.1f}ms')
print(f'p99: {max(times):.1f}ms')
"
```

**Post-implementation steps:**
- Calculate threshold: p95 + 30% margin
- Update `THRESHOLD_MS` constant in test
- Document in test docstring: "Threshold set to Xms based on p95=Yms + 30% margin, measured YYYY-MM-DD"

### 4. Update Existing Tests

**4.1. Verify all tests pass**
- Run full test suite: `uv run pytest`
- Fix any tests that fail due to:
  - Missing yaml mocking
  - Import order assumptions
  - Command module initialization

**4.2. Update yaml-related tests**
- Search for yaml mocking in tests: `grep -r "yaml" tests/`
- Update or remove yaml-specific test setup
- Ensure tests work with regex parser

**4.3. Test lazy-loading behavior**
- Add test to verify command modules aren't imported at CLI startup
- Verify each command executes correctly with lazy imports

### 5. Documentation Updates

**5.1. Update CLAUDE.md**
- No changes needed (implementation detail, not user-facing)

**5.2. Add inline code comments**
- Comment in `plan_validator.py` explaining regex approach:
  ```python
  # Note: Using regex instead of YAML for performance and simplicity.
  # Plan files use simple format (key: value pairs, simple lists).
  # If format becomes complex (nested structures, multiline values, etc.),
  # migrate to full YAML parsing library.
  ```

**5.3. Update completion architecture docs**
- Update `docs/COMPLETION.md` architecture section to reflect:
  - Regex parsing instead of YAML
  - Lazy-loaded command modules
  - Performance testing approach

## Deliverables

1. **Modified `src/lw_coder/plan_validator.py`**
   - YAML import removed
   - Regex-based `_extract_front_matter()` implementation
   - All validation logic preserved
   - Inline documentation about regex approach

2. **Modified `src/lw_coder/cli.py`**
   - Command module imports removed from top-level
   - Lazy imports added to each command dispatch block
   - Comments explaining lazy-loading pattern

3. **New test file `tests/completion/test_performance.py`**
   - Performance regression test with empirically measured threshold
   - Documentation of measurement process
   - Helpful error messages for debugging

4. **Updated existing tests**
   - All tests passing with regex parser
   - No yaml mocking remaining
   - Lazy-loading verified

5. **Updated documentation**
   - Code comments explaining design decisions
   - `docs/COMPLETION.md` updated with architecture changes

6. **Performance measurements**
   - Documented baseline (100 runs, p95, p99)
   - Threshold calculation (p95 + 30%)
   - Before/after comparison

## Out of Scope

**Explicitly NOT included in this plan:**

1. **Caching of parsed plan metadata** - Current approach parses on each tab completion; caching could be added later if needed

2. **Import-weight testing** - Not using sys.modules checks to verify specific modules aren't imported

3. **Migration path back to YAML** - If plan format becomes complex, we'll handle yaml migration as a separate task

4. **Optimizing other CLI operations** - Focus is solely on tab completion performance, not command execution speed

5. **Changes to plan file format** - Plan files remain unchanged, only parsing implementation changes

6. **Support for complex YAML features** - Regex parser handles current simple format only (no nested structures, multiline values, anchors, etc.)

7. **Performance optimization for command execution** - Lazy-loading helps tab completion; command execution can still import everything

8. **Removal of other heavy dependencies** - Only addressing yaml and command module imports; other dependencies (dspy, etc.) remain
