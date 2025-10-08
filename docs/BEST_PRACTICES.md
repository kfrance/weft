# Best Practices

- **Keep tests in the default run**: Avoid adding `pytest` markers whose only purpose is to skip tests because a dependency (e.g., Docker) might be missing or the test could be slow. Keep those tests in the normal `pytest` run instead.
- **Avoid mocking DSPy and LLMs**: Use real DSPy components with real LLM API calls in tests. Configure tests with actual LLM providers (e.g., OpenRouter) rather than creating mock LLM objects or stub responses. DSPy's caching ensures the first test run hits the API while subsequent runs retrieve cached results, making tests both fast and representative of production behavior.
- **Documentation is verified manually**: Avoid writing tests whose only purpose is to check for the existence of documentation pages or sections—keep effort focused on code behavior.
