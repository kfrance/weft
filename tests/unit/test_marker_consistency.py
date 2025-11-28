"""Verify all tests in tests/integration/ have @pytest.mark.integration.

This test ensures marker consistency: every test in the integration directory
must be marked with @pytest.mark.integration to prevent accidental inclusion
in fast test runs.
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_integration_tests_have_marker() -> None:
    """All tests in tests/integration/ must be marked with @pytest.mark.integration."""
    integration_dir = Path(__file__).parent.parent / "integration"
    if not integration_dir.exists():
        return  # Skip if integration dir doesn't exist yet

    unmarked: list[str] = []

    for test_file in integration_dir.glob("test_*.py"):
        tree = ast.parse(test_file.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            # Check test functions
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                if not _has_integration_marker(node):
                    # Check if the function is inside a class with the marker
                    parent_has_marker = False
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.ClassDef):
                            for child in parent.body:
                                if child is node:
                                    parent_has_marker = _has_integration_marker(parent)
                                    break
                    if not parent_has_marker:
                        unmarked.append(f"{test_file.name}::{node.name}")

            # Check test classes
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                if not _has_integration_marker(node):
                    # Check each test method in the class
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                            if not _has_integration_marker(item):
                                unmarked.append(f"{test_file.name}::{node.name}::{item.name}")

    assert not unmarked, (
        f"Integration tests missing @pytest.mark.integration decorator:\n"
        + "\n".join(f"  - {t}" for t in unmarked)
    )


def _has_integration_marker(node: ast.FunctionDef | ast.ClassDef) -> bool:
    """Check if a function or class has the pytest.mark.integration decorator."""
    for decorator in node.decorator_list:
        # Handle @pytest.mark.integration
        if isinstance(decorator, ast.Attribute):
            if decorator.attr == "integration":
                if isinstance(decorator.value, ast.Attribute):
                    if decorator.value.attr == "mark":
                        if isinstance(decorator.value.value, ast.Name):
                            if decorator.value.value.id == "pytest":
                                return True
    return False
