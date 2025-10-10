# Architecture Decision Records

## Plan ID Uniqueness Performance

**Decision**: Accept O(n) plan_id uniqueness checking by scanning repository files during validation.

**Context**: `validate_plan()` in `src/lw_coder/plan_validator.py` ensures each plan_id is unique across the repository by scanning all `.md` files under `.lw_coder/tasks/`.

**Rationale**: Performance testing with 10,000 plans showed validation completes in ~750ms, which is acceptable for CLI usage. Chose filesystem scanning over maintaining an index to avoid:
- Additional file/database for tracking plan IDs
- Cache invalidation complexity when plans are added/modified outside the CLI

**Future threshold**: At 10,000+ plans (~750ms), we may need to revisit this approach. Consider:
- SQLite index of plan_id → file_path
- In-memory cache with file mtime checks
- Only scanning when plan_id format suggests potential collision

**Date**: 2025-10-06