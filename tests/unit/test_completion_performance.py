"""Performance regression tests for tab completion.

These tests ensure that tab completion remains fast by detecting when heavy
module imports are accidentally added to the import path.
"""

from __future__ import annotations

import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest


# Performance threshold for tab completion in milliseconds.
# Threshold set to 250ms based on empirical testing with 30% margin.
# This value should be updated if performance characteristics change significantly.
# Measured on 2025-11-26 during initial implementation.
THRESHOLD_MS = 250.0


class TestTabCompletionPerformance:
    """Test suite for tab completion performance."""

    @pytest.fixture(autouse=True)
    def setup_git_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Create a temporary git repo with sample plan files."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

        # Create .weft/tasks directory with sample plans
        tasks_dir = tmp_path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True)

        # Create a few sample plan files
        for i in range(3):
            plan = tasks_dir / f"plan-{i}.md"
            plan.write_text(
                f"""---
git_sha: {"a" * 40}
plan_id: plan-{i}
status: draft
evaluation_notes: []
---

# Plan {i}

This is a sample plan.
"""
            )

        # Set working directory to temp repo
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_tab_completion_performance_threshold(self, tmp_path: Path) -> None:
        """Test that tab completion completes within performance threshold.

        This test runs the completion import simulation multiple times and verifies
        that the median time is below the threshold. This catches regressions from
        accidentally importing heavy modules during tab completion.

        Performance threshold rationale:
        - Tab completion should be nearly instantaneous (<200ms perceived)
        - Heavy imports (yaml, dspy, sdk_runner) each add 100-500ms
        - If this test fails, check for:
          1. New top-level imports in cli.py
          2. Non-lazy imports in completion/cache.py or completers.py
          3. Imports added to plan_validator.py
        """
        num_runs = 10
        times: list[float] = []

        # Run multiple iterations to get stable measurements
        for _ in range(num_runs):
            start = time.perf_counter()
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from weft.completion.cache import get_active_plans; get_active_plans()",
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

            # Check that the import succeeded
            if result.returncode != 0:
                pytest.fail(
                    f"Tab completion import failed with return code {result.returncode}.\n"
                    f"stdout: {result.stdout}\n"
                    f"stderr: {result.stderr}"
                )

        median_time = statistics.median(times)
        p95_time = statistics.quantiles(times, n=20)[18] if len(times) >= 20 else max(times)

        # Assert median is below threshold
        if median_time > THRESHOLD_MS:
            pytest.fail(
                f"Tab completion is too slow!\n"
                f"Median time: {median_time:.1f}ms (threshold: {THRESHOLD_MS}ms)\n"
                f"P95 time: {p95_time:.1f}ms\n"
                f"All times: {[f'{t:.1f}' for t in times]}\n\n"
                f"Common causes of slowdown:\n"
                f"1. New top-level imports in cli.py (should be lazy-loaded)\n"
                f"2. Imports in completion/cache.py or completers.py\n"
                f"3. Heavy imports in plan_validator.py (use regex, not yaml)\n"
                f"4. Import-time side effects in command modules\n\n"
                f"Run: python -X importtime -c 'from weft.completion.cache import get_active_plans'\n"
                f"to identify which imports are slow."
            )

    def test_cli_import_does_not_load_command_modules(self) -> None:
        """Test that importing cli.py doesn't import command modules.

        Command modules (code_command, finalize_command, etc.) import heavy
        dependencies. They should be lazy-loaded only when their command runs.
        """
        # Run a Python command that imports cli and checks sys.modules
        code = """
import sys

# Import the cli module
from weft import cli

# Check that heavy command modules are NOT imported
heavy_modules = [
    'weft.code_command',
    'weft.finalize_command',
    'weft.plan_command',
    'weft.recover_command',
    'weft.eval_command',
]

imported_heavy = [m for m in heavy_modules if m in sys.modules]
if imported_heavy:
    print(f"ERROR: Heavy modules imported at cli load time: {imported_heavy}")
    sys.exit(1)
else:
    print("OK: No heavy modules imported")
    sys.exit(0)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            pytest.fail(
                f"CLI imports heavy modules at load time.\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}\n\n"
                f"Fix: Move imports inside command dispatch blocks in cli.py"
            )
