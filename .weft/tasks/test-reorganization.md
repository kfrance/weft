---
plan_id: test-reorganization
status: done
evaluation_notes: []
git_sha: 74ec90fab5547981bef4bb0be6c47d91b6e85c0e
---

# Test Reorganization: Separate Unit and Integration Tests

## Objectives

Reorganize the test suite to clearly separate fast unit tests from long-running integration tests that make real external API calls. This will enable developers to run fast tests during development while ensuring integration tests are properly isolated and marked.

## Requirements & Constraints

### Primary Requirements
1. **Final Test Count**: End with exactly 425 tests (424 original + 1 marker consistency verification test)
2. **Separate by API Calls**: Unit tests use mocks/no external calls; Integration tests make real API calls (SDK, LLM, etc.)
3. **Flat Directory Structure**: Use `tests/unit/` and `tests/integration/` (no nested completion subfolder)
4. **Dual Selection System**: Support both directory-based AND marker-based test selection
   - Directory: `pytest tests/unit/` or `pytest tests/integration/`
   - Marker: `pytest -m "not integration"` (current default)
5. **Split Individual Tests**: Don't just move files - split test functions that are incorrectly categorized
6. **Enforce Marker Consistency**: All tests in `tests/integration/` MUST have `@pytest.mark.integration` decorator

### Test Categorization Rules
- **Integration Test**: Makes real external API calls to Claude SDK, OpenRouter, or other external services
- **Unit Test**: Tests internal logic using mocks, no external network calls

### Current State Inventory
- **Total Tests**: 424 tests
  - Unit tests (default run): 418 tests
  - Integration tests (marked): 6 tests

- **Integration Test Files** (make real API calls):
  - `tests/test_sdk_integration.py` - 2 tests (already marked)
  - `tests/test_sdk_network.py` - 4 tests (already marked) - **NOTE**: Not in worktree, exists in main repo
  - `tests/test_judge_executor_integration.py` - 1 integration test (`test_execute_judge_with_real_llm`)

- **Misleadingly Named Files** (actually unit tests using mocks):
  - `tests/test_trace_capture_integration.py` - 10 tests (uses mocks, no API calls)
  - `tests/completion/test_integration.py` - 6 tests (tests argparse integration, no API calls)

- **Mixed Files** (need to split):
  - `tests/test_judge_executor_integration.py`:
    - Integration: `test_execute_judge_with_real_llm` (1 test)
    - Unit: `test_execute_judge_invalid_api_key`, `test_get_openrouter_api_key_not_found`, `test_get_cache_dir` (3 tests)

### Constraints
- Must work with existing `pyproject.toml` pytest configuration
- Shared fixtures in `tests/conftest.py` must remain accessible to both test types
- Cannot add new tests (except the marker consistency verification test)
- Must maintain backward compatibility for CI/CD commands
- All integration tests MUST be marked with `@pytest.mark.integration` to prevent accidental inclusion in fast test runs

## Work Items

### 1. Audit and Document Current State
- [ ] Run `pytest --collect-only -q` to get baseline count (418 unit + 6 integration = 424 total)
- [ ] Audit all test files for relative imports that might break after moves
  ```bash
  grep -r "^from \.\." tests/
  grep -r "^from \." tests/ | grep -v "^from lw_coder"
  ```
- [ ] Document per-file test counts for verification after migration
- [ ] Create `tests/README.md` documenting new test organization structure and rules

### 2. Create Directory Structure
- [ ] Create `tests/unit/` directory
- [ ] Create `tests/integration/` directory
- [ ] Create `tests/unit/conftest.py` with comment: "# Unit test fixtures - see tests/conftest.py for shared fixtures"
- [ ] Create `tests/integration/conftest.py` with comment: "# Integration test fixtures - see tests/conftest.py for shared fixtures"
- [ ] Keep existing `tests/conftest.py` for shared fixtures

### 3. Move and Split Test Files

#### 3a. Move Pure Integration Test Files
- [ ] Move `tests/test_sdk_integration.py` → `tests/integration/test_sdk.py`
  - Verify: 2 tests, both have `@pytest.mark.integration`
- [ ] Handle `tests/test_sdk_network.py` (exists in main repo, not in worktree)
  - Document: Will move to `tests/integration/test_sdk_network.py` when merged
  - Verify: 4 tests, all have `@pytest.mark.integration`

#### 3b. Split Mixed Test File
- [ ] Split `tests/test_judge_executor_integration.py`:
  - Create `tests/integration/test_judge_executor_api.py`:
    - Move `test_execute_judge_with_real_llm` (1 test)
    - Verify it has `@pytest.mark.integration` decorator
    - Add module docstring explaining it makes real LLM API calls
  - Create `tests/unit/test_judge_executor.py`:
    - Move `test_execute_judge_invalid_api_key` (1 test)
    - Move `test_get_openrouter_api_key_not_found` (1 test)
    - Move `test_get_cache_dir` (1 test)
    - Total: 3 tests
    - Add module docstring explaining these are unit tests with no external calls
  - Delete original `tests/test_judge_executor_integration.py`

#### 3c. Rename and Move Misleadingly Named Files
- [ ] Move `tests/test_trace_capture_integration.py` → `tests/unit/test_trace_capture_integration.py`
  - Keep "integration" in name to indicate component integration (not API integration)
  - Add module docstring: "Unit tests for trace capture. Despite the name, these use mocks and make no external API calls. The 'integration' refers to component integration, not external API integration."
  - Verify: 10 tests, none have `@pytest.mark.integration`

- [ ] Move `tests/completion/test_integration.py` → `tests/unit/test_completion_integration.py`
  - Add module docstring: "Unit tests for argparse/argcomplete integration. No external API calls."
  - Verify: 6 tests, none have `@pytest.mark.integration`

#### 3d. Move All Remaining Unit Tests
- [ ] Move all files from `tests/` root to `tests/unit/`:
  - All files from `tests/*.py` (excluding conftest.py)
  - All files from `tests/completion/*.py`
  - Total: ~30 test files
  - Remove empty `tests/completion/` directory

### 4. Update pytest Configuration
- [ ] Update `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  pythonpath = ["src"]
  testpaths = ["tests"]  # Still discovers both unit and integration
  addopts = "-m 'not integration'"  # Default excludes integration tests
  markers = [
      "integration: marks tests as integration tests that make real external API calls (deselect with '-m \"not integration\"')",
  ]
  ```

### 5. Add Marker Verification Test
- [ ] Create `tests/unit/test_marker_consistency.py`:
  ```python
  """Verify all tests in tests/integration/ have @pytest.mark.integration."""
  import ast
  from pathlib import Path

  def test_integration_tests_have_marker():
      """All tests in tests/integration/ must be marked with @pytest.mark.integration."""
      integration_dir = Path(__file__).parent.parent / "integration"
      if not integration_dir.exists():
          return  # Skip if integration dir doesn't exist yet

      unmarked = []
      for test_file in integration_dir.glob("test_*.py"):
          # Parse file and check for pytest.mark.integration on test functions/classes
          # Implementation details omitted for brevity

      assert not unmarked, f"Integration tests missing @pytest.mark.integration: {unmarked}"
  ```

### 6. Update Documentation
- [ ] Update `CLAUDE.md`:
  - Change "Run tests: `uv run pytest`" to include directory examples
  - Add "Run unit tests: `uv run pytest tests/unit/`"
  - Update "Run integration tests" from `pytest -m integration` to also mention `pytest tests/integration/`
  - Add note about marker requirement for integration tests

- [ ] Update `docs/BEST_PRACTICES.md`:
  - Add section on "Test Organization"
  - Document distinction: Unit (fast, mocked) vs Integration (slow, real API calls)
  - Explain when to use `tests/unit/` vs `tests/integration/`
  - Document requirement: All integration tests MUST have `@pytest.mark.integration` decorator
  - Add guidance on where to put new tests

- [ ] Create `tests/README.md`:
  ```markdown
  # Test Organization

  ## Directory Structure
  - `unit/` - Fast tests with mocked dependencies, no external API calls
  - `integration/` - Tests that make real external API calls (Claude SDK, OpenRouter, etc.)
  - `conftest.py` - Shared fixtures available to both unit and integration tests

  ## Adding New Tests
  1. **Does your test make external API calls?**
     - Yes → Add to `tests/integration/` AND mark with `@pytest.mark.integration`
     - No → Add to `tests/unit/`

  2. **Marker Requirement**: All tests in `tests/integration/` MUST have the decorator:
     ```python
     @pytest.mark.integration
     def test_something():
         ...
     ```

  ## Running Tests
  - **Fast unit tests only**: `pytest tests/unit/` OR `pytest` (default)
  - **Integration tests only**: `pytest tests/integration/` OR `pytest -m integration`
  - **All tests**: `pytest tests/` OR `pytest -m ''`

  ## Test Categories
  - **Unit Test**: Tests internal logic, uses mocks, no network calls
  - **Integration Test**: Makes real API calls to external services
  ```

### 7. Validation and Verification
- [ ] Run `pytest --collect-only -q` and verify 425 total tests collected (424 original + 1 marker verification)
- [ ] Run `pytest --collect-only -q tests/unit/` and verify 419 tests (418 original + 1 marker verification)
- [ ] Run `pytest --collect-only -q tests/integration/` and verify 6 tests
- [ ] Run `pytest --collect-only -q -m integration` and verify same count as directory-based selection
- [ ] Run `pytest --collect-only -q -m "not integration"` and verify same count as unit directory
- [ ] Run actual unit tests: `pytest tests/unit/` (should be fast)
- [ ] Verify no relative import errors
- [ ] Verify shared fixtures from `tests/conftest.py` are accessible in both directories
- [ ] Run marker consistency test to ensure all integration tests are marked

## Deliverables

1. **Reorganized Test Structure**:
   ```
   tests/
   ├── conftest.py (shared fixtures)
   ├── unit/
   │   ├── conftest.py (unit-specific fixtures with comment)
   │   ├── test_*.py (418 original unit tests across ~32 files)
   │   ├── test_marker_consistency.py (1 new verification test)
   │   └── ... (all former tests/ files except integration tests)
   ├── integration/
   │   ├── conftest.py (integration-specific fixtures with comment)
   │   ├── test_sdk.py (2 tests, marked)
   │   ├── test_sdk_network.py (4 tests, marked)
   │   └── test_judge_executor_api.py (1 test, marked)
   └── README.md (test organization guide)
   ```

2. **Updated Configuration**:
   - `pyproject.toml` with updated pytest configuration
   - Default test run excludes integration tests via marker

3. **Updated Documentation**:
   - `CLAUDE.md` with new test commands and organization
   - `docs/BEST_PRACTICES.md` with test categorization rules and marker requirements
   - `tests/README.md` with comprehensive test organization guide

4. **Verification Report**:
   - Test count verification (424 before = 424 after)
   - Per-file test count verification
   - Marker consistency verification (all integration tests marked)
   - Import validation (no broken imports)
   - Fixture accessibility verification

## Out of Scope

- Adding new tests or test coverage (except the marker consistency verification test)
- Refactoring existing test implementations
- Changing test assertions or behavior
- Modifying CI/CD pipeline configuration (beyond what's needed for new paths)
- Performance optimization of tests
- Adding test utilities or helper functions
- Implementing pre-commit hooks for marker enforcement (future enhancement)
- Handling `test_sdk_network.py` migration (will be done when file appears in worktree)
