# Best Practices

- **Keep tests in the default run**: Avoid adding `pytest` markers whose only purpose is to skip tests because a dependency (e.g., Docker) might be missing or the test could be slow. Keep those tests in the normal `pytest` run instead.
- **Avoid mocking DSPy**: Use the real DSPy components in tests to benefit from their caching behavior. The first run may take longer, but subsequent runs stay fast and reflect production usage more accurately.
