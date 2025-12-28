# Unit test fixtures - see tests/conftest.py for shared fixtures

from pathlib import Path

import pytest

# Import shared helpers from the dedicated module
from tests.helpers import GitRepo, write_plan


@pytest.fixture
def real_trace_content() -> str:
    """Load the committed test-planner-subagent trace file.

    This fixture provides access to a real trace file for testing trace parsing
    and summarization. The trace file is committed in the repository at
    .weft/training_data/test-planner-subagent/code_trace.md

    Note: This fixture intentionally reads from the real repository, as it
    accesses committed test data fixtures (similar to other test fixtures).
    """
    # Find the repo root by looking for pyproject.toml
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            break
        current = current.parent

    trace_path = current / ".weft" / "training_data" / "test-planner-subagent" / "code_trace.md"
    if not trace_path.exists():
        pytest.skip("Test trace file not available")

    return trace_path.read_text(encoding="utf-8")


# Re-export helpers for convenience (test files should import from tests.helpers directly)
__all__ = ["GitRepo", "write_plan", "real_trace_content"]
