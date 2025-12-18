# Contributing to weft

Thank you for considering contributing to weft! This document outlines the process for contributing.

## Contributor License Agreement

Before we can accept your contribution, you must agree to our [Contributor License Agreement](CLA.md). When you open a pull request, the CLA Assistant bot will prompt you to sign if you haven't already. This is a one-time process that takes about 30 seconds.

The CLA grants the maintainer the ability to relicense your contributions if needed, while you retain copyright ownership of your work.

## How to Contribute

### Reporting Issues

- Check existing issues to avoid duplicates
- Provide a clear description of the problem
- Include steps to reproduce, expected behavior, and actual behavior
- Include your environment details (OS, Python version, etc.)

### Submitting Changes

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes
4. Run tests: `uv run pytest`
5. Commit with clear, descriptive messages
6. Open a pull request against `main`

### Code Style

- Follow existing code conventions in the project
- Keep changes focused and minimal
- Add tests for new functionality

### Testing

Run the test suite before submitting:

```bash
# Unit tests (fast, no API calls)
uv run pytest

# Integration tests (makes real API calls)
uv run pytest tests/integration/

# All tests
uv run pytest tests/
```

## Questions?

Open an issue if you have questions about contributing.
