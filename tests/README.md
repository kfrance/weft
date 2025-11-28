# Test Organization

## Directory Structure
- `unit/` - Fast tests with mocked dependencies, no external API calls
- `integration/` - Tests that make real external API calls (Claude SDK, OpenRouter, etc.)
- `conftest.py` - Shared fixtures available to both unit and integration tests

## Adding New Tests
1. **Does your test make external API calls?**
   - Yes -> Add to `tests/integration/` AND mark with `@pytest.mark.integration`
   - No -> Add to `tests/unit/`

2. **Marker Requirement**: All tests in `tests/integration/` MUST have the decorator:
   ```python
   import pytest

   @pytest.mark.integration
   def test_something():
       ...
   ```

   This is enforced by `tests/unit/test_marker_consistency.py`.

## Running Tests
- **Fast unit tests only**: `pytest tests/unit/` OR `pytest` (default)
- **Integration tests only**: `pytest tests/integration/` OR `pytest -m integration`
- **All tests**: `pytest -m ''`

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
import pytest

@pytest.mark.integration
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
