---
plan_id: test-isolation-fixes
status: done
evaluation_notes: []
git_sha: efa2c3b6a97ab062b5a1e721bbba1fa892a0a0dc
---

# Test Isolation Fixes

## Objectives

Improve test isolation to prevent tests from accidentally operating on the real weft repository or user configuration. This addresses:

1. A unit test (`test_find_repo_root_from_cwd`) that finds the real repo instead of the test fixture
2. Integration smoke tests that create/delete files in the real repository
3. Code duplication across conftest files
4. Missing CWD isolation for unit tests

## Requirements & Constraints

- Unit tests must not access the real weft repository or user home directory
- Integration tests may make real API calls but should use `tmp_path` for filesystem operations
- Existing test behavior must be preserved (tests should pass after refactoring)
- Follow project testing guidelines from CLAUDE.md (no mocking DSPy/LLMs, use pytest.fail() for missing deps)

## Work Items

### 1. Create shared test helpers module

**File:** `tests/helpers.py` (new)

Create a dedicated module for test helpers that are currently duplicated across conftest files:

- `GitRepo` dataclass - Git repository helper for running git commands
- `write_plan()` function - Helper to write plan files with YAML front matter

This eliminates the "circular import" issue that caused the duplication, since test files can import directly from `tests.helpers` instead of `conftest`.

### 2. Deduplicate conftest files

**Files to modify:**
- `tests/conftest.py` - Import from `tests.helpers`, remove local definitions
- `tests/unit/conftest.py` - Import from `tests.helpers`, remove duplicated `GitRepo` and `write_plan`
- `tests/integration/conftest.py` - Import from `tests.helpers`, remove duplicated `GitRepo` and `write_plan`

The `git_repo` fixture in `tests/conftest.py` should use the imported `GitRepo` class.

### 3. Add CWD isolation fixture

**File:** `tests/conftest.py`

Add an autouse fixture that changes CWD to `tmp_path` for all unit tests:

```python
@pytest.fixture(autouse=True)
def isolate_cwd(request, tmp_path, monkeypatch):
    """Isolate current working directory to prevent tests from operating in real repo.

    Changes CWD to tmp_path for unit tests. This prevents functions like
    find_repo_root() from accidentally finding the real weft repository
    when called without an explicit path argument.

    Integration tests (in tests/integration/) skip this isolation.
    """
    if _is_integration_test(request):
        return
    monkeypatch.chdir(tmp_path)
```

### 4. Fix test_find_repo_root_from_cwd

**File:** `tests/unit/test_repo_utils.py`

Update `test_find_repo_root_from_cwd` to explicitly change to the `git_repo` fixture's directory before calling `find_repo_root()`:

**Current behavior (broken):**
- Calls `find_repo_root()` with CWD = real weft repo
- Finds real repo, asserts it exists (passes but tests wrong thing)

**Fixed behavior:**
- Change CWD to `git_repo.path` using `monkeypatch.chdir()`
- Call `find_repo_root()` which now finds the isolated test repo
- Assert result equals `git_repo.path`

### 5. Refactor test_command_smoke.py for isolation

**File:** `tests/integration/test_command_smoke.py`

Refactor `TestCodeCommandSmoke.test_code_command_setup_completes` to use an isolated environment instead of the real repository:

**Current behavior (dangerous):**
- Creates plan file in real repo root: `repo_root / f"{plan_id}.md"`
- Creates worktree in real repo: `.weft/worktrees/test-smoke-temp`
- Cleanup in `finally` block (fragile if exceptions occur)

**Fixed approach:**
1. Create isolated git repo in `tmp_path` using the `git_repo` fixture
2. Copy required prompt files from real repo to isolated repo
3. Mock `find_repo_root()` or path resolution to use isolated repo
4. Create plan file and worktree in isolated repo
5. No cleanup needed (pytest handles `tmp_path` cleanup)

For `TestPlanCommandSmoke.test_plan_command_setup_completes`:
- Similar refactoring to use isolated environment
- Copy prompts directory structure to tmp_path

**Prompt files to copy:**
- `src/prompts/claude-code/` directory (or minimal subset needed for smoke test)
- `src/prompts/droid/` directory (if testing droid tool)

### 6. Remove dangerous documentation

**File:** `tests/integration/test_command_smoke.py`

Remove or update the comment at lines 14-16:
```python
# NOTE: These tests run against the REAL weft repository (not a temp repo)
# because they need access to real project files like prompts/active/.
```

Replace with documentation explaining the isolation approach.

## Deliverables

1. New `tests/helpers.py` module with shared test utilities
2. Updated conftest files with no duplicated code
3. `isolate_cwd` autouse fixture for unit test CWD isolation
4. Fixed `test_find_repo_root_from_cwd` test
5. Refactored smoke tests that no longer touch the real repository

## Unit Tests

No new unit tests are needed. The existing tests will validate the changes:

- `test_find_repo_root_from_cwd` - Will now correctly test against isolated repo
- `test_find_repo_root_not_in_git` - Already uses `monkeypatch.chdir(tmp_path)`, validates error case
- Other unit tests - Should continue to pass with CWD isolation (already use tmp_path or git_repo properly)

Run `uv run pytest tests/unit/` to verify no regressions.

## Integration Tests

No new integration tests are needed. The refactored smoke tests serve as integration tests:

- `test_plan_command_setup_completes` - Validates plan command initialization
- `test_code_command_setup_completes` - Validates code command initialization

Run `uv run pytest tests/integration/test_command_smoke.py` to verify the refactored tests pass.

## Out of Scope

- **ADR for test isolation strategy** - Could be added later but not required for this fix
- **Pre-commit hooks for isolation violations** - Nice-to-have but not part of this plan
- **Filesystem access guardrails** - The CWD isolation addresses the immediate issue; broader guardrails can be added later
- **Refactoring integration test categorization** - Current directory-based categorization is sufficient
- **`real_trace_content` fixture** - This reads committed test data from the repo, which is acceptable (similar to test fixtures)
