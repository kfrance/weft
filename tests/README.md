# Test Organization

## Directory Structure
- `unit/` - Fast tests with mocked dependencies, no external API calls
- `integration/` - Tests that make real external API calls (Claude SDK, OpenRouter, etc.)
- `conftest.py` - Shared fixtures available to both unit and integration tests

## Adding New Tests
1. **Does your test make external API calls?**
   - Yes -> Add to `tests/integration/`
   - No -> Add to `tests/unit/`

## Running Tests
- **Unit tests only**: `pytest` (default via testpaths)
- **Integration tests only**: `pytest tests/integration/`
- **All tests**: `pytest tests/`

## Test Categories
- **Unit Test**: Tests internal logic, uses mocks, no network calls
- **Integration Test**: Makes real API calls to external services

## Examples

### Unit Test (tests/unit/)
```python
"""Tests that don't make external API calls."""
from unittest.mock import patch

def test_some_function():
    with patch("module.external_call") as mock:
        mock.return_value = {"mocked": "response"}
        result = function_under_test()
        assert result == expected
```

### Integration Test (tests/integration/)
```python
"""Tests that make real API calls."""

def test_real_api():
    """This test calls the actual external API."""
    result = call_real_api()
    assert result is not None
```

## Fixtures

Shared fixtures are defined in `tests/conftest.py` and are automatically available
to all tests in both `tests/unit/` and `tests/integration/`.

Commonly used fixtures:
- `git_repo` - Creates a temporary git repository for testing
- `tmp_path` - Built-in pytest fixture for temporary directories
- `mock_executor_factory` - Creates mock executors for testing
