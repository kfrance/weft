"""Unit tests for plan_id_collision_resolver module.

These tests verify collision detection and resolution logic using mocks.
They do not make any external API calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weft.plan_id_collision_resolver import (
    CollisionInfo,
    CollisionResolverError,
    apply_plan_id_change,
    collect_existing_plan_ids,
    detect_collisions,
    resolve_collisions,
    resolve_plan_id_collisions,
)


def create_plan_file(path: Path, plan_id: str, body: str = "# Plan Content") -> None:
    """Helper to create a plan file with given plan_id."""
    content = f"""---
plan_id: {plan_id}
status: draft
git_sha: {"0" * 40}
evaluation_notes: []
---

{body}
"""
    path.write_text(content, encoding="utf-8")


class TestCollectExistingPlanIds:
    """Tests for collect_existing_plan_ids function."""

    def test_scans_worktree_directory(self, tmp_path: Path) -> None:
        """Verify worktree directory is scanned."""
        worktree_tasks = tmp_path / "worktree" / ".weft" / "tasks"
        worktree_tasks.mkdir(parents=True)

        create_plan_file(worktree_tasks / "plan1.md", "plan-one")
        create_plan_file(worktree_tasks / "plan2.md", "plan-two")

        result = collect_existing_plan_ids(worktree_tasks, None)

        assert "plan-one" in result
        assert "plan-two" in result

    def test_scans_main_directory(self, tmp_path: Path) -> None:
        """Verify main repo directory is scanned."""
        main_tasks = tmp_path / "main" / ".weft" / "tasks"
        main_tasks.mkdir(parents=True)

        create_plan_file(main_tasks / "plan1.md", "main-plan")

        result = collect_existing_plan_ids(None, main_tasks)

        assert "main-plan" in result

    def test_scans_both_directories(self, tmp_path: Path) -> None:
        """Verify both directories are scanned."""
        worktree_tasks = tmp_path / "worktree" / ".weft" / "tasks"
        main_tasks = tmp_path / "main" / ".weft" / "tasks"
        worktree_tasks.mkdir(parents=True)
        main_tasks.mkdir(parents=True)

        create_plan_file(worktree_tasks / "plan1.md", "worktree-plan")
        create_plan_file(main_tasks / "plan2.md", "main-plan")

        result = collect_existing_plan_ids(worktree_tasks, main_tasks)

        assert "worktree-plan" in result
        assert "main-plan" in result

    def test_handles_malformed_files_gracefully(self, tmp_path: Path) -> None:
        """Verify malformed files are skipped with warning."""
        tasks = tmp_path / "tasks"
        tasks.mkdir()

        # Create a valid plan
        create_plan_file(tasks / "valid.md", "valid-plan")

        # Create a malformed plan (no front matter)
        (tasks / "malformed.md").write_text("# No front matter")

        result = collect_existing_plan_ids(tasks, None)

        assert "valid-plan" in result
        assert len(result) == 1

    def test_handles_nonexistent_directory(self, tmp_path: Path) -> None:
        """Verify nonexistent directory is handled."""
        nonexistent = tmp_path / "nonexistent"

        result = collect_existing_plan_ids(nonexistent, None)

        assert result == set()

    def test_handles_empty_directory(self, tmp_path: Path) -> None:
        """Verify empty directory is handled."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = collect_existing_plan_ids(empty_dir, None)

        assert result == set()


class TestDetectCollisions:
    """Tests for detect_collisions function."""

    def test_detects_collision_with_existing_ids(self, tmp_path: Path) -> None:
        """Verify collision with existing plan_ids is detected."""
        copied = tmp_path / "copied.md"
        create_plan_file(copied, "existing-plan")

        collisions = detect_collisions([copied], {"existing-plan"})

        assert len(collisions) == 1
        assert collisions[0].file_path == copied
        assert collisions[0].current_plan_id == "existing-plan"

    def test_detects_collision_between_copied_files(self, tmp_path: Path) -> None:
        """Verify collision between copied files is detected."""
        copied1 = tmp_path / "copied1.md"
        copied2 = tmp_path / "copied2.md"
        create_plan_file(copied1, "same-plan-id")
        create_plan_file(copied2, "same-plan-id")

        collisions = detect_collisions([copied1, copied2], set())

        # Both files should be in collisions list
        assert len(collisions) == 2
        file_paths = {c.file_path for c in collisions}
        assert copied1 in file_paths
        assert copied2 in file_paths

    def test_returns_empty_when_no_collisions(self, tmp_path: Path) -> None:
        """Verify empty list when no collisions exist."""
        copied = tmp_path / "copied.md"
        create_plan_file(copied, "unique-plan")

        collisions = detect_collisions([copied], {"other-plan"})

        assert collisions == []

    def test_handles_multiple_unique_files(self, tmp_path: Path) -> None:
        """Verify multiple unique files are handled correctly."""
        copied1 = tmp_path / "copied1.md"
        copied2 = tmp_path / "copied2.md"
        create_plan_file(copied1, "plan-one")
        create_plan_file(copied2, "plan-two")

        collisions = detect_collisions([copied1, copied2], set())

        assert collisions == []

    def test_handles_malformed_files(self, tmp_path: Path) -> None:
        """Verify malformed files are skipped."""
        valid = tmp_path / "valid.md"
        malformed = tmp_path / "malformed.md"

        create_plan_file(valid, "valid-plan")
        malformed.write_text("# No front matter")

        collisions = detect_collisions([valid, malformed], {"valid-plan"})

        # Only valid file should show collision
        assert len(collisions) == 1
        assert collisions[0].file_path == valid


class TestResolveCollisions:
    """Tests for resolve_collisions function."""

    @patch("weft.plan_id_collision_resolver.generate_plan_ids_batch")
    def test_calls_generator_with_all_ids_to_avoid(
        self, mock_generate: MagicMock, tmp_path: Path
    ) -> None:
        """Verify generator is called with all IDs to avoid."""
        from weft.plan_id_generator import PlanIdResult

        mock_generate.return_value = [
            PlanIdResult(file_path=tmp_path / "plan.md", new_plan_id="new-id")
        ]

        collision = CollisionInfo(
            file_path=tmp_path / "plan.md",
            current_plan_id="colliding-id",
            plan_content="# Plan",
        )

        resolve_collisions(
            [collision],
            {"existing-1", "existing-2"},
            "api-key",
            tmp_path,
        )

        # Check that avoid set includes both existing and colliding IDs
        call_args = mock_generate.call_args
        avoid_set = call_args[0][1]  # Second positional arg
        assert "existing-1" in avoid_set
        assert "existing-2" in avoid_set
        assert "colliding-id" in avoid_set

    @patch("weft.plan_id_collision_resolver.generate_plan_ids_batch")
    def test_loops_until_unique_ids_generated(
        self, mock_generate: MagicMock, tmp_path: Path
    ) -> None:
        """Verify looping until all IDs are unique."""
        from weft.plan_id_generator import PlanIdResult

        # First call returns colliding ID, second returns unique
        mock_generate.side_effect = [
            [PlanIdResult(file_path=tmp_path / "plan.md", new_plan_id="still-colliding")],
            [PlanIdResult(file_path=tmp_path / "plan.md", new_plan_id="finally-unique")],
        ]

        collision = CollisionInfo(
            file_path=tmp_path / "plan.md",
            current_plan_id="original-id",
            plan_content="# Plan",
        )

        result = resolve_collisions(
            [collision],
            {"still-colliding"},  # First generated ID will collide
            "api-key",
            tmp_path,
        )

        assert mock_generate.call_count == 2
        assert result[tmp_path / "plan.md"] == "finally-unique"

    @patch("weft.plan_id_collision_resolver.generate_plan_ids_batch")
    def test_accumulates_conflicting_ids_across_iterations(
        self, mock_generate: MagicMock, tmp_path: Path
    ) -> None:
        """Verify conflicting IDs are accumulated across iterations."""
        from weft.plan_id_generator import PlanIdResult

        # Track what avoid sets were passed
        avoid_sets: list[set[str]] = []

        def capture_avoid_set(requests, avoid_set, api_key, cache_dir):
            avoid_sets.append(avoid_set.copy())
            if len(avoid_sets) == 1:
                # First call - return colliding
                return [PlanIdResult(file_path=tmp_path / "plan.md", new_plan_id="iter1-id")]
            else:
                # Second call - return unique
                return [PlanIdResult(file_path=tmp_path / "plan.md", new_plan_id="unique-id")]

        mock_generate.side_effect = capture_avoid_set

        collision = CollisionInfo(
            file_path=tmp_path / "plan.md",
            current_plan_id="original-id",
            plan_content="# Plan",
        )

        resolve_collisions(
            [collision],
            {"iter1-id"},  # First generated ID will collide
            "api-key",
            tmp_path,
        )

        # Second iteration should include both original-id and iter1-id
        assert "original-id" in avoid_sets[1]
        assert "iter1-id" in avoid_sets[1]

    @patch("weft.plan_id_collision_resolver.generate_plan_ids_batch")
    def test_returns_empty_dict_for_no_collisions(
        self, mock_generate: MagicMock, tmp_path: Path
    ) -> None:
        """Verify empty dict returned for no collisions."""
        result = resolve_collisions([], set(), "api-key", tmp_path)
        assert result == {}
        mock_generate.assert_not_called()

    @patch("weft.plan_id_collision_resolver.generate_plan_ids_batch")
    def test_handles_duplicate_ids_among_generated(
        self, mock_generate: MagicMock, tmp_path: Path
    ) -> None:
        """Verify duplicate IDs among generated results are handled."""
        from weft.plan_id_generator import PlanIdResult

        # First call returns duplicate IDs, second returns unique
        mock_generate.side_effect = [
            [
                PlanIdResult(file_path=tmp_path / "plan1.md", new_plan_id="same-id"),
                PlanIdResult(file_path=tmp_path / "plan2.md", new_plan_id="same-id"),
            ],
            [
                PlanIdResult(file_path=tmp_path / "plan1.md", new_plan_id="unique-1"),
                PlanIdResult(file_path=tmp_path / "plan2.md", new_plan_id="unique-2"),
            ],
        ]

        collisions = [
            CollisionInfo(
                file_path=tmp_path / "plan1.md",
                current_plan_id="id-1",
                plan_content="# Plan 1",
            ),
            CollisionInfo(
                file_path=tmp_path / "plan2.md",
                current_plan_id="id-2",
                plan_content="# Plan 2",
            ),
        ]

        result = resolve_collisions(collisions, set(), "api-key", tmp_path)

        assert mock_generate.call_count == 2
        assert result[tmp_path / "plan1.md"] == "unique-1"
        assert result[tmp_path / "plan2.md"] == "unique-2"


class TestApplyPlanIdChange:
    """Tests for apply_plan_id_change function."""

    def test_uses_atomic_write_then_move(self, tmp_path: Path) -> None:
        """Verify atomic write-then-move pattern is used."""
        source = tmp_path / "original.md"
        create_plan_file(source, "old-plan-id")

        result = apply_plan_id_change(source, "new-plan-id", tmp_path)

        # New file should exist
        assert result == tmp_path / "new-plan-id.md"
        assert result.exists()

        # Old file should be deleted
        assert not source.exists()

    def test_updates_plan_id_in_content(self, tmp_path: Path) -> None:
        """Verify plan_id is updated in file content."""
        source = tmp_path / "original.md"
        create_plan_file(source, "old-plan-id", body="# My Plan Body")

        result = apply_plan_id_change(source, "new-plan-id", tmp_path)

        content = result.read_text(encoding="utf-8")
        assert "plan_id: new-plan-id" in content
        assert "# My Plan Body" in content
        assert "old-plan-id" not in content

    def test_cleans_up_old_file_after_success(self, tmp_path: Path) -> None:
        """Verify old file is removed after successful rename."""
        source = tmp_path / "original.md"
        create_plan_file(source, "old-plan-id")

        apply_plan_id_change(source, "new-plan-id", tmp_path)

        assert not source.exists()

    def test_does_not_delete_old_file_if_write_fails(self, tmp_path: Path) -> None:
        """Verify old file is preserved if write fails."""
        source = tmp_path / "original.md"
        create_plan_file(source, "old-plan-id")

        # Make destination directory read-only to cause write failure
        dest_dir = tmp_path / "readonly"
        dest_dir.mkdir()

        with patch("tempfile.mkstemp") as mock_mkstemp:
            mock_mkstemp.side_effect = OSError("Cannot create temp file")

            with pytest.raises(CollisionResolverError):
                apply_plan_id_change(source, "new-plan-id", dest_dir)

        # Original file should still exist
        assert source.exists()

    def test_preserves_other_front_matter_fields(self, tmp_path: Path) -> None:
        """Verify other front matter fields are preserved."""
        source = tmp_path / "original.md"
        content = """---
plan_id: old-plan-id
status: coding
git_sha: abcd1234abcd1234abcd1234abcd1234abcd1234
evaluation_notes:
- note 1
- note 2
linear_issue_id: LW-123
---

# Plan Body
"""
        source.write_text(content, encoding="utf-8")

        result = apply_plan_id_change(source, "new-plan-id", tmp_path)

        new_content = result.read_text(encoding="utf-8")
        assert "plan_id: new-plan-id" in new_content
        assert "status: coding" in new_content
        assert "linear_issue_id: LW-123" in new_content
        assert "# Plan Body" in new_content


class TestResolvePlanIdCollisions:
    """Tests for resolve_plan_id_collisions main entry point."""

    @patch("weft.plan_id_collision_resolver.resolve_collisions")
    @patch("weft.plan_id_collision_resolver.detect_collisions")
    @patch("weft.plan_id_collision_resolver.collect_existing_plan_ids")
    def test_orchestrates_full_workflow(
        self,
        mock_collect: MagicMock,
        mock_detect: MagicMock,
        mock_resolve: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify full workflow is orchestrated correctly."""
        # Setup
        main_tasks = tmp_path / "main"
        main_tasks.mkdir()
        copied = main_tasks / "plan.md"
        create_plan_file(copied, "colliding-id")

        mock_collect.return_value = {"existing-id"}
        mock_detect.return_value = [
            CollisionInfo(
                file_path=copied,
                current_plan_id="colliding-id",
                plan_content="# Plan",
            )
        ]
        mock_resolve.return_value = {copied: "new-unique-id"}

        # Execute
        with patch.object(Path, "unlink"):  # Don't actually delete files
            with patch("weft.plan_id_collision_resolver.apply_plan_id_change") as mock_apply:
                mock_apply.return_value = main_tasks / "new-unique-id.md"

                result = resolve_plan_id_collisions(
                    copied_files=[copied],
                    worktree_tasks_dir=None,
                    main_tasks_dir=main_tasks,
                    api_key="api-key",
                    cache_dir=tmp_path,
                )

        # Verify
        assert result == {"plan.md": "new-unique-id.md"}
        mock_collect.assert_called_once()
        mock_detect.assert_called_once()
        mock_resolve.assert_called_once()

    @patch("weft.plan_id_collision_resolver.detect_collisions")
    @patch("weft.plan_id_collision_resolver.collect_existing_plan_ids")
    def test_returns_empty_when_no_collisions(
        self,
        mock_collect: MagicMock,
        mock_detect: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify empty dict returned when no collisions."""
        main_tasks = tmp_path / "main"
        main_tasks.mkdir()
        copied = main_tasks / "plan.md"
        create_plan_file(copied, "unique-id")

        mock_collect.return_value = set()
        mock_detect.return_value = []  # No collisions

        result = resolve_plan_id_collisions(
            copied_files=[copied],
            worktree_tasks_dir=None,
            main_tasks_dir=main_tasks,
            api_key="api-key",
            cache_dir=tmp_path,
        )

        assert result == {}

    @patch("weft.plan_id_collision_resolver.collect_existing_plan_ids")
    def test_excludes_copied_files_from_existing_ids(
        self,
        mock_collect: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Verify copied files' plan_ids are excluded from existing set."""
        main_tasks = tmp_path / "main"
        main_tasks.mkdir()
        copied = main_tasks / "plan.md"
        create_plan_file(copied, "should-be-excluded")

        # Simulate that the copied file's ID is in the collected set
        mock_collect.return_value = {"should-be-excluded", "other-id"}

        with patch("weft.plan_id_collision_resolver.detect_collisions") as mock_detect:
            mock_detect.return_value = []

            resolve_plan_id_collisions(
                copied_files=[copied],
                worktree_tasks_dir=None,
                main_tasks_dir=main_tasks,
                api_key="api-key",
                cache_dir=tmp_path,
            )

            # Check that detect_collisions was called without copied file's ID
            call_args = mock_detect.call_args
            existing_ids = call_args[0][1]
            assert "should-be-excluded" not in existing_ids
            assert "other-id" in existing_ids
