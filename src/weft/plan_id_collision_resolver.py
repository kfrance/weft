"""Collision detection and resolution for plan_ids.

Detects plan_id collisions between plan files and resolves them by
generating new unique plan_ids using an LLM.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .logging_config import get_logger
from .plan_id_generator import (
    PlanIdGenerationError,
    PlanIdRequest,
    generate_plan_ids_batch,
)
from .plan_validator import PlanValidationError, extract_front_matter

logger = get_logger(__name__)


class CollisionResolverError(Exception):
    """Raised when collision resolution fails."""

    pass


@dataclass
class CollisionInfo:
    """Information about a plan_id collision.

    Attributes:
        file_path: Path to the file with the collision.
        current_plan_id: The current plan_id that collides.
        plan_content: The markdown body of the plan.
    """

    file_path: Path
    current_plan_id: str
    plan_content: str


def collect_existing_plan_ids(
    worktree_tasks_dir: Path | None,
    main_tasks_dir: Path | None,
) -> set[str]:
    """Collect all existing plan_ids from worktree and main repo task directories.

    Args:
        worktree_tasks_dir: Path to worktree's .weft/tasks directory (optional).
        main_tasks_dir: Path to main repo's .weft/tasks directory (optional).

    Returns:
        Set of all plan_ids found in both directories.
    """
    plan_ids: set[str] = set()

    for tasks_dir in [worktree_tasks_dir, main_tasks_dir]:
        if tasks_dir is None or not tasks_dir.exists():
            continue

        try:
            for file_path in tasks_dir.glob("*.md"):
                if not file_path.is_file():
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8")
                    front_matter, _ = extract_front_matter(content)
                    plan_id = front_matter.get("plan_id")
                    if isinstance(plan_id, str) and plan_id.strip():
                        plan_ids.add(plan_id.strip())
                except PlanValidationError as e:
                    logger.debug(
                        "Skipping malformed plan file %s: %s",
                        file_path.name,
                        e,
                    )
                except OSError as e:
                    logger.warning(
                        "Failed to read plan file %s: %s",
                        file_path.name,
                        e,
                    )
        except OSError as e:
            logger.warning(
                "Failed to scan tasks directory %s: %s",
                tasks_dir,
                e,
            )

    logger.debug("Collected %d existing plan_ids", len(plan_ids))
    return plan_ids


def detect_collisions(
    copied_files: list[Path],
    existing_plan_ids: set[str],
) -> list[CollisionInfo]:
    """Detect plan_id collisions for copied files.

    Checks each copied file's plan_id against:
    1. The set of existing plan_ids
    2. Other copied files (detecting duplicates among copied files)

    Args:
        copied_files: List of file paths that were copied.
        existing_plan_ids: Set of plan_ids already in use.

    Returns:
        List of CollisionInfo for files that have colliding plan_ids.
    """
    collisions: list[CollisionInfo] = []
    seen_plan_ids: dict[str, Path] = {}

    for file_path in copied_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            front_matter, body = extract_front_matter(content)
            plan_id = front_matter.get("plan_id")

            if not isinstance(plan_id, str) or not plan_id.strip():
                logger.debug(
                    "Skipping file without valid plan_id: %s",
                    file_path.name,
                )
                continue

            plan_id = plan_id.strip()

            # Check collision with existing plan_ids
            has_collision = plan_id in existing_plan_ids

            # Check collision with other copied files
            if plan_id in seen_plan_ids:
                has_collision = True
                # Also add the first file with this plan_id if not already added
                first_file = seen_plan_ids[plan_id]
                if not any(c.file_path == first_file for c in collisions):
                    try:
                        first_content = first_file.read_text(encoding="utf-8")
                        first_fm, first_body = extract_front_matter(first_content)
                        collisions.append(
                            CollisionInfo(
                                file_path=first_file,
                                current_plan_id=plan_id,
                                plan_content=first_body,
                            )
                        )
                    except (OSError, PlanValidationError) as e:
                        logger.warning(
                            "Failed to read file %s for collision info: %s",
                            first_file.name,
                            e,
                        )

            if has_collision:
                collisions.append(
                    CollisionInfo(
                        file_path=file_path,
                        current_plan_id=plan_id,
                        plan_content=body,
                    )
                )
                logger.debug(
                    "Detected collision for plan_id '%s' in %s",
                    plan_id,
                    file_path.name,
                )

            # Track this plan_id for checking subsequent files
            if plan_id not in seen_plan_ids:
                seen_plan_ids[plan_id] = file_path

        except PlanValidationError as e:
            logger.debug(
                "Skipping malformed plan file %s: %s",
                file_path.name,
                e,
            )
        except OSError as e:
            logger.warning(
                "Failed to read plan file %s: %s",
                file_path.name,
                e,
            )

    if collisions:
        logger.info(
            "Found %d plan_id collision(s) that need resolution",
            len(collisions),
        )

    return collisions


def resolve_collisions(
    collisions: list[CollisionInfo],
    existing_plan_ids: set[str],
    api_key: str,
    cache_dir: Path,
) -> dict[Path, str]:
    """Resolve plan_id collisions by generating new unique plan_ids.

    Batches all colliding plans in a single LLM call. Loops until all
    generated plan_ids are unique (no retry limit).

    Args:
        collisions: List of collision information.
        existing_plan_ids: Set of plan_ids already in use.
        api_key: OpenRouter API key.
        cache_dir: Directory for DSPy cache.

    Returns:
        Mapping of file paths to new plan_ids.

    Raises:
        CollisionResolverError: If resolution fails after many iterations.
    """
    if not collisions:
        return {}

    # Build the set of all plan_ids to avoid (existing + all conflicting)
    all_plan_ids_to_avoid = set(existing_plan_ids)
    for collision in collisions:
        all_plan_ids_to_avoid.add(collision.current_plan_id)

    # Prepare requests for LLM
    requests = [
        PlanIdRequest(
            plan_content=collision.plan_content,
            file_path=collision.file_path,
        )
        for collision in collisions
    ]

    # Loop until all generated plan_ids are unique
    max_iterations = 100  # Safety limit to prevent infinite loops
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        logger.debug(
            "Collision resolution iteration %d, avoiding %d plan_ids",
            iteration,
            len(all_plan_ids_to_avoid),
        )

        try:
            results = generate_plan_ids_batch(
                requests, all_plan_ids_to_avoid, api_key, cache_dir
            )
        except PlanIdGenerationError as e:
            raise CollisionResolverError(f"Failed to generate plan_ids: {e}") from e

        # Check for uniqueness among generated plan_ids
        generated_ids = [r.new_plan_id for r in results]

        # Check if any generated ID collides with avoid list or with each other
        has_collision = False
        new_collisions: list[CollisionInfo] = []

        for i, result in enumerate(results):
            if result.new_plan_id in all_plan_ids_to_avoid:
                has_collision = True
                # Add to avoid list for next iteration
                all_plan_ids_to_avoid.add(result.new_plan_id)
                new_collisions.append(collisions[i])
            elif generated_ids.count(result.new_plan_id) > 1:
                # Multiple files got the same new plan_id
                has_collision = True
                all_plan_ids_to_avoid.add(result.new_plan_id)
                new_collisions.append(collisions[i])

        if not has_collision:
            # All plan_ids are unique - build and return the mapping
            mapping = {r.file_path: r.new_plan_id for r in results}
            logger.info(
                "Resolved %d plan_id collision(s) in %d iteration(s)",
                len(mapping),
                iteration,
            )
            return mapping

        # Update for next iteration - only retry the ones that still collide
        if new_collisions:
            collisions = new_collisions
            requests = [
                PlanIdRequest(
                    plan_content=c.plan_content,
                    file_path=c.file_path,
                )
                for c in collisions
            ]

    raise CollisionResolverError(
        f"Failed to resolve collisions after {max_iterations} iterations"
    )


def apply_plan_id_change(
    source_path: Path,
    new_plan_id: str,
    dest_dir: Path,
) -> Path:
    """Apply a plan_id change: update content and rename file atomically.

    Uses write-then-move pattern to prevent inconsistent state.

    Args:
        source_path: Path to the original plan file.
        new_plan_id: The new plan_id to use.
        dest_dir: Directory where the new file should be placed.

    Returns:
        Path to the new file.

    Raises:
        CollisionResolverError: If the change fails.
    """
    new_filename = f"{new_plan_id}.md"
    new_path = dest_dir / new_filename

    try:
        # Read original content
        content = source_path.read_text(encoding="utf-8")

        # Create a temporary file in the same directory for atomic write
        # We use tempfile to get a unique temp name
        temp_fd, temp_path_str = tempfile.mkstemp(
            dir=dest_dir,
            prefix=".plan_rename_",
            suffix=".md.tmp",
        )

        temp_path = Path(temp_path_str)
        fd_closed = False

        try:
            # Write updated content with new plan_id
            # Use update_plan_fields pattern but write to temp first
            from .plan_lifecycle import _split_front_matter

            import os

            import yaml

            front_matter_text, body_text = _split_front_matter(content)
            front_matter = yaml.safe_load(front_matter_text) if front_matter_text.strip() else {}

            if not isinstance(front_matter, dict):
                raise CollisionResolverError(
                    f"Plan front matter must be a mapping in {source_path.name}"
                )

            # Update the plan_id
            front_matter["plan_id"] = new_plan_id

            # Reconstruct the content
            yaml_block = yaml.safe_dump(front_matter, sort_keys=False).strip()
            new_content = f"---\n{yaml_block}\n---\n{body_text}"

            # Write to temp file
            os.write(temp_fd, new_content.encode("utf-8"))
            os.close(temp_fd)
            fd_closed = True

            # Atomic move to final destination
            temp_path.rename(new_path)

            logger.debug(
                "Applied plan_id change: %s -> %s (new file: %s)",
                source_path.name,
                new_plan_id,
                new_filename,
            )

            # Delete the old file only after successful rename
            if source_path.exists() and source_path != new_path:
                try:
                    source_path.unlink()
                    logger.debug("Removed old file: %s", source_path.name)
                except OSError as e:
                    logger.warning(
                        "Failed to remove old file %s: %s",
                        source_path.name,
                        e,
                    )

            return new_path

        except Exception:
            # Ensure file descriptor is closed on failure
            if not fd_closed:
                try:
                    import os
                    os.close(temp_fd)
                except OSError:
                    pass
            # Clean up temp file on failure
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

    except Exception as e:
        raise CollisionResolverError(
            f"Failed to apply plan_id change for {source_path.name}: {e}"
        ) from e


def resolve_plan_id_collisions(
    copied_files: list[Path],
    worktree_tasks_dir: Path | None,
    main_tasks_dir: Path,
    api_key: str,
    cache_dir: Path,
) -> dict[str, str]:
    """Main entry point for plan_id collision resolution.

    Detects and resolves all plan_id collisions for the copied files.

    Args:
        copied_files: List of file paths that were copied.
        worktree_tasks_dir: Path to worktree's .weft/tasks directory (optional).
        main_tasks_dir: Path to main repo's .weft/tasks directory.
        api_key: OpenRouter API key.
        cache_dir: Directory for DSPy cache.

    Returns:
        Mapping of original filenames to new filenames (only for renamed files).

    Raises:
        CollisionResolverError: If resolution fails.
    """
    # Collect existing plan_ids
    existing_plan_ids = collect_existing_plan_ids(worktree_tasks_dir, main_tasks_dir)

    # Remove plan_ids of the copied files themselves from existing set
    # (they're "new" so we only care about collisions with other files)
    for file_path in copied_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            front_matter, _ = extract_front_matter(content)
            plan_id = front_matter.get("plan_id")
            if isinstance(plan_id, str) and plan_id.strip():
                existing_plan_ids.discard(plan_id.strip())
        except (OSError, PlanValidationError):
            pass

    # Detect collisions
    collisions = detect_collisions(copied_files, existing_plan_ids)

    if not collisions:
        logger.debug("No plan_id collisions detected")
        return {}

    # Resolve collisions
    resolution_map = resolve_collisions(
        collisions, existing_plan_ids, api_key, cache_dir
    )

    # Apply changes
    filename_mapping: dict[str, str] = {}

    for file_path, new_plan_id in resolution_map.items():
        old_filename = file_path.name
        new_path = apply_plan_id_change(file_path, new_plan_id, main_tasks_dir)
        new_filename = new_path.name
        filename_mapping[old_filename] = new_filename

    return filename_mapping
