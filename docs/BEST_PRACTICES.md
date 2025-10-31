# Best Practices

- **Keep tests in the default run**: Avoid adding `pytest` markers whose only purpose is to skip tests because a dependency might be missing or the test could be slow. Keep those tests in the normal `pytest` run instead.
- **Use pytest.fail() for missing dependencies, not pytest.skip()**: When a test requires an external dependency that might not be available, use `pytest.fail()` with a clear error message instead of `pytest.skip()`. This ensures developers are notified of missing dependencies rather than silently skipping tests. Example: `pytest.fail("Required dependency 'droid' not found. Install it first with: pip install droid-cli")`.
- **Avoid mocking DSPy and LLMs**: Use real DSPy components with real LLM API calls in tests. Configure tests with actual LLM providers (e.g., OpenRouter) rather than creating mock LLM objects or stub responses. DSPy's caching ensures the first test run hits the API while subsequent runs retrieve cached results, making tests both fast and representative of production behavior.
- **Documentation is verified manually**: Avoid writing tests whose only purpose is to check for the existence of documentation pages or sections—keep effort focused on code behavior.

## Test Optimization

- **Avoid redundant tests**: Before adding a new test, check if similar test coverage already exists. Duplicate tests increase maintenance burden without adding value.
- **Use parametrization for similar test cases**: When testing the same code path with different inputs, use `@pytest.mark.parametrize` instead of writing separate test functions. This keeps tests DRY and makes it easier to add new test cases.
- **Keep parametrized tests focused**: Each parametrized test should verify a single concern or behavior. Don't mix unrelated test scenarios in one parametrized function—this makes failures harder to diagnose.
- **Write descriptive test names**: Test function names should clearly document the behavior being tested. For parametrized tests, use the `ids` parameter to provide clear labels for each test case.
- **Integrate related assertions**: When multiple tests check different aspects of the same error condition, consider combining them into a single parametrized test that verifies all relevant properties (e.g., error type, message content, and paths).
