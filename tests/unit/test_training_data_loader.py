"""Tests for training_data_loader module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lw_coder.training_data_loader import (
    TrainingDataLoadError,
    discover_training_samples,
    load_training_batch,
    load_training_sample,
)


@pytest.fixture
def training_data_dir(tmp_path: Path) -> Path:
    """Create a basic training data directory structure."""
    training_dir = tmp_path / ".lw_coder" / "training_data"
    training_dir.mkdir(parents=True)
    return training_dir


def create_complete_sample(training_dir: Path, plan_id: str) -> Path:
    """Create a complete training sample with all required files."""
    sample_dir = training_dir / plan_id
    sample_dir.mkdir(parents=True, exist_ok=True)

    # Required files
    (sample_dir / "human_feedback.md").write_text("Agent performed well.")
    (sample_dir / "test_results_after.json").write_text('{"passed": 10, "failed": 0}')
    (sample_dir / "judge_code-reuse.json").write_text(
        json.dumps({
            "judge_name": "code-reuse",
            "score": 0.9,
            "weight": 0.4,
            "feedback": "Good code reuse.",
        })
    )

    # Optional files
    (sample_dir / "plan.md").write_text("# Test Plan\n\nObjectives...")
    (sample_dir / "code_trace.md").write_text("## Tool calls\n\n...")
    (sample_dir / "test_results_before.json").write_text('{"passed": 9, "failed": 1}')

    return sample_dir


class TestDiscoverTrainingSamples:
    """Tests for discover_training_samples function."""

    def test_discover_training_samples(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Finds plan_ids in training_data directory."""
        # Create sample directories
        (training_data_dir / "sample-001").mkdir()
        (training_data_dir / "sample-002").mkdir()
        (training_data_dir / "sample-003").mkdir()

        plan_ids = discover_training_samples(tmp_path)

        assert len(plan_ids) == 3
        assert "sample-001" in plan_ids
        assert "sample-002" in plan_ids
        assert "sample-003" in plan_ids

    def test_discover_training_samples_sorted(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Returns plan_ids in sorted order."""
        (training_data_dir / "zebra").mkdir()
        (training_data_dir / "alpha").mkdir()
        (training_data_dir / "beta").mkdir()

        plan_ids = discover_training_samples(tmp_path)

        assert plan_ids == ["alpha", "beta", "zebra"]

    def test_discover_training_samples_no_directory(self, tmp_path: Path) -> None:
        """Raises error when training_data directory doesn't exist."""
        with pytest.raises(TrainingDataLoadError) as exc_info:
            discover_training_samples(tmp_path)

        assert "Training data directory not found" in str(exc_info.value)

    def test_discover_training_samples_empty(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Returns empty list when no samples exist."""
        plan_ids = discover_training_samples(tmp_path)
        assert plan_ids == []


class TestLoadTrainingSample:
    """Tests for load_training_sample function."""

    def test_load_training_sample_success(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Loads complete sample with all files."""
        create_complete_sample(training_data_dir, "test-sample")

        sample = load_training_sample(tmp_path, "test-sample")

        assert sample.plan_id == "test-sample"
        assert sample.plan_content == "# Test Plan\n\nObjectives..."
        assert sample.code_trace == "## Tool calls\n\n..."
        assert sample.human_feedback == "Agent performed well."
        assert "code-reuse" in sample.judge_results
        assert sample.test_results_before == '{"passed": 9, "failed": 1}'
        assert sample.test_results_after == '{"passed": 10, "failed": 0}'

    def test_load_training_sample_missing_required(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Raises error for missing human_feedback.md."""
        sample_dir = training_data_dir / "incomplete-sample"
        sample_dir.mkdir()
        # Create test_results_after but not human_feedback
        (sample_dir / "test_results_after.json").write_text('{"passed": 10}')
        (sample_dir / "judge_test.json").write_text('{"judge_name": "test", "score": 0.8}')

        with pytest.raises(TrainingDataLoadError) as exc_info:
            load_training_sample(tmp_path, "incomplete-sample")

        assert "Required file missing" in str(exc_info.value)
        assert "human_feedback.md" in str(exc_info.value)

    def test_load_training_sample_optional_missing(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Succeeds when code_trace.md missing."""
        sample_dir = training_data_dir / "minimal-sample"
        sample_dir.mkdir()

        # Only required files
        (sample_dir / "human_feedback.md").write_text("Feedback")
        (sample_dir / "test_results_after.json").write_text('{"passed": 10}')
        (sample_dir / "judge_test.json").write_text(
            json.dumps({"judge_name": "test", "score": 0.8, "weight": 0.5, "feedback": "OK"})
        )

        sample = load_training_sample(tmp_path, "minimal-sample")

        assert sample.plan_id == "minimal-sample"
        assert sample.code_trace == ""  # Optional, defaults to empty
        assert sample.test_results_before == ""  # Optional
        assert sample.human_feedback == "Feedback"

    def test_load_training_sample_no_judges(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Raises error when no judge results found."""
        sample_dir = training_data_dir / "no-judges"
        sample_dir.mkdir()

        (sample_dir / "human_feedback.md").write_text("Feedback")
        (sample_dir / "test_results_after.json").write_text('{"passed": 10}')
        # No judge files

        with pytest.raises(TrainingDataLoadError) as exc_info:
            load_training_sample(tmp_path, "no-judges")

        assert "No judge results found" in str(exc_info.value)

    def test_load_training_sample_not_found(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Raises error when sample directory not found."""
        with pytest.raises(TrainingDataLoadError) as exc_info:
            load_training_sample(tmp_path, "nonexistent-sample")

        assert "Training sample directory not found" in str(exc_info.value)


class TestLoadTrainingBatch:
    """Tests for load_training_batch function."""

    def test_load_training_batch_respects_limit(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Only loads batch_size samples."""
        # Create 5 samples
        for i in range(5):
            create_complete_sample(training_data_dir, f"sample-{i:03d}")

        samples = load_training_batch(tmp_path, batch_size=3)

        assert len(samples) == 3

    def test_load_training_batch_all_available(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Loads all samples when fewer than batch_size exist."""
        create_complete_sample(training_data_dir, "sample-001")
        create_complete_sample(training_data_dir, "sample-002")

        samples = load_training_batch(tmp_path, batch_size=5)

        assert len(samples) == 2

    def test_load_training_batch_empty_directory(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Raises error when no samples."""
        with pytest.raises(TrainingDataLoadError) as exc_info:
            load_training_batch(tmp_path, batch_size=3)

        assert "No training samples found" in str(exc_info.value)

    def test_load_training_batch_skips_invalid(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Skips samples that fail to load and continues."""
        # Create one valid and one invalid sample
        create_complete_sample(training_data_dir, "valid-sample")

        invalid_dir = training_data_dir / "invalid-sample"
        invalid_dir.mkdir()
        # Invalid sample - missing required files

        samples = load_training_batch(tmp_path, batch_size=5)

        # Should only return the valid sample
        assert len(samples) == 1
        assert samples[0].plan_id == "valid-sample"

    def test_load_training_batch_default_size(self, training_data_dir: Path, tmp_path: Path) -> None:
        """Uses default batch_size of 3."""
        for i in range(5):
            create_complete_sample(training_data_dir, f"sample-{i:03d}")

        samples = load_training_batch(tmp_path)  # No batch_size argument

        assert len(samples) == 3
