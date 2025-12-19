---
plan_id: cleanup-overmocked-tests
status: done
evaluation_notes: []
git_sha: d3a667e148265e93112fb27d2b16d5389099f877
---

# Cleanup Over-Mocked and Trivial Tests

## Objectives

Remove tests that provide false confidence by testing implementation details or library code rather than meaningful behavior. Consolidate redundant tests using parametrization to reduce maintenance burden while preserving coverage of actual behaviors.

## Requirements & Constraints

- Preserve tests that verify meaningful behavior
- Use `@pytest.mark.parametrize` for consolidating similar test cases (per CLAUDE.md guidelines)
- Do not reduce coverage of actual application logic
- Follow existing test organization patterns in the codebase

## Work Items

### 1. Delete trivial logging config tests

**File:** `tests/unit/test_logging_config.py`

Delete the following tests that test library code or trivial behavior:
- `test_configure_logging_creates_log_directory` - tests `Path.mkdir()`
- `test_configure_logging_sets_info_level_by_default` - tests logging level assignment
- `test_configure_logging_sets_debug_level_when_requested` - tests logging level assignment
- `test_get_logger_returns_logger` - tests `logging.getLogger()` returns a Logger
- `test_logging_handlers_configured` - tests implementation detail (specific handler types)

**Keep:** `test_configure_logging_idempotent` - prevents real bug (duplicate handlers)

### 2. Delete over-mocked rollback tests

**File:** `tests/unit/test_init_command.py`

Delete tests that mock `shutil.copytree`/`shutil.copy2` and track internal call sequences:
- `test_init_rollback_on_permission_error` (lines 541-564)
- `test_init_rollback_on_disk_full` (lines 567-590)

**Rationale:** These test implementation details (which internal call to fail on) rather than behavior. Real filesystem errors are platform-dependent and impractical to simulate reliably.

### 3. Delete hash calculation tests

**File:** `tests/unit/test_init_command.py`

Delete tests that verify Python's `hashlib` library:
- `test_calculate_file_hash` (lines 51-64)
- `test_calculate_file_hash_binary_file` (lines 67-77)

**Rationale:** `calculate_file_hash` is a 3-line wrapper around `hashlib.sha256()`. These tests verify the standard library, not application logic.

### 4. Consolidate yes/no prompt tests

**File:** `tests/unit/test_init_command.py`

Replace 4 near-identical tests with 1 parametrized test:
- `test_prompt_yes_no_accepts_y`
- `test_prompt_yes_no_accepts_yes`
- `test_prompt_yes_no_accepts_n`
- `test_prompt_yes_no_accepts_no`

**New test:**
```python
@pytest.mark.parametrize(
    "user_input,expected",
    [
        ("y", True),
        ("yes", True),
        ("n", False),
        ("no", False),
    ],
    ids=["y", "yes", "n", "no"],
)
def test_prompt_yes_no_accepts_valid_input(monkeypatch, user_input, expected):
    """Test prompt_yes_no accepts valid yes/no inputs."""
    monkeypatch.setattr("builtins.input", lambda x: user_input)
    result = prompt_yes_no("Test?", skip_prompts=False)
    assert result is expected
```

### 5. Consolidate VERSION file error tests

**File:** `tests/unit/test_init_command.py`

Replace 2 similar error tests with 1 parametrized test:
- `test_load_version_file_invalid_json`
- `test_load_version_file_missing_file`

**New test:**
```python
@pytest.mark.parametrize(
    "setup_file",
    [
        pytest.param(lambda p: p.write_text("not valid json"), id="invalid_json"),
        pytest.param(lambda p: None, id="missing_file"),  # don't create file
    ],
)
def test_load_version_file_error_cases(tmp_path, setup_file):
    """Test load_version_file raises InitCommandError for invalid/missing files."""
    version_file = tmp_path / "VERSION"
    setup_file(version_file)

    with pytest.raises(InitCommandError) as exc_info:
        load_version_file(version_file)

    assert "Failed to read VERSION file" in str(exc_info.value)
```

### 6. Consolidate templates directory tests

**File:** `tests/unit/test_init_command.py`

Replace 4 existence-check tests with 1 parametrized test:
- `test_get_templates_dir_returns_path`
- `test_get_templates_dir_contains_judges`
- `test_get_templates_dir_contains_prompts`
- `test_get_templates_dir_contains_version`

**New test:**
```python
@pytest.mark.parametrize(
    "subpath",
    [
        pytest.param(".", id="templates_dir"),
        pytest.param("judges", id="judges"),
        pytest.param("prompts", id="prompts"),
        pytest.param("VERSION", id="version_file"),
    ],
)
def test_templates_dir_contains_required_paths(subpath):
    """Test templates directory contains required files and subdirectories."""
    templates_dir = get_templates_dir()
    path = templates_dir / subpath if subpath != "." else templates_dir
    assert path.exists()
```

## Deliverables

1. Modified `tests/unit/test_logging_config.py` with only idempotency test remaining
2. Modified `tests/unit/test_init_command.py` with:
   - 6 tests deleted (2 rollback, 2 hash, implicitly replaced by consolidation)
   - 10 tests consolidated into 3 parametrized tests
3. All remaining tests pass

## Unit Tests

No new unit tests needed - this plan reduces test count while preserving meaningful coverage.

The following tests are preserved as they test real behavior:
- `test_configure_logging_idempotent` - prevents handler duplication bug
- `test_load_version_file` - verifies JSON parsing works
- All customization detection tests - verify file change detection logic
- All init command behavior tests - verify correct files are created
- `test_prompt_yes_no_skip_prompts_returns_true` - verifies skip behavior
- `test_prompt_yes_no_eof_returns_false` - verifies non-interactive handling
- `test_prompt_yes_no_reprompts_on_invalid_input` - verifies retry logic

## Integration Tests

No integration tests needed for this cleanup work.

## Out of Scope

- Refactoring the `AtomicInitializer` class or rollback logic
- Adding new test coverage for untested code paths
- Modifying the implementation code in `init_command.py` or `logging_config.py`
- Changes to other test files not mentioned in this plan
