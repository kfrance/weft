---
plan_id: LW-99-status-command
status: done
git_sha: a7090461cd0d26e51917043af8c92631f89ab65c
linear_issue_id: LW-99
evaluation_notes: []
---

# Add `weft status` Command

## Objectives

Add a new `weft status` command that provides a dashboard view of all plans and their current state in the weft pipeline, enabling users to quickly see what tasks need attention without manually checking multiple directories.

## Requirements & Constraints

### Display Requirements

The command displays a table with the following columns:

| Column | Source |
|--------|--------|
| Plan ID | `plan_id` from frontmatter |
| Status | `status` from frontmatter (draft/ready/coding/implemented/done/abandoned) |
| Worktree | ✓ if `.weft/worktrees/<plan_id>` exists |
| Coded | ✓ if `.weft/sessions/<plan_id>/code/` exists |
| Eval | ✓ if `.weft/sessions/<plan_id>/eval/` exists |
| Training | ✓ if `.weft/training_data/<plan_id>/` exists |
| Modified | Last modified time of plan file (human-readable relative time, e.g., "2 days ago") |

### CLI Options

- `--status <statuses>`: Filter by status (comma-separated, e.g., `--status ready,coding`)
- `--sort <field>`: Sort by field (`plan_id`, `status`, `modified`)
- `--reverse`: Reverse sort order

### Behavior

- **Default sort**: By status (pipeline order: draft → ready → coding → implemented → done → abandoned), then by modified time (newest first) within each status
- **Empty results**: Show table headers with no rows
- **Frontmatter extraction**: Use existing `get_all_plans()` from `completion/cache.py` which handles malformed files gracefully
- **Table formatting**: Use `tabulate` library with `simple` format
- **Time formatting**: Use `humanize` library for relative time display

### Dependencies

Add to `pyproject.toml`:
- `tabulate>=0.9.0`
- `humanize>=4.0.0`

## Work Items

### 1. Add Dependencies

**File**: `pyproject.toml`

Add `tabulate>=0.9.0` and `humanize>=4.0.0` to the dependencies list.

### 2. Create Status Command Module

**File**: `src/weft/status_command.py`

Implement the status command with:

- `run_status_command(status_filter, sort_field, reverse)` - Main entry point returning exit code
- `_get_pipeline_state(repo_root, plan_id)` - Check existence of worktree/session/training directories
- `_get_status_order(status)` - Return sort order for status values (pipeline order)
- `_format_table(plans, repo_root)` - Format plan data as table using tabulate

**Reuse existing infrastructure:**
- Import `get_all_plans()` and `PlanInfo` from `completion.cache` for plan scanning (already handles malformed files, caching)
- Import `find_repo_root()` from `repo_utils`
- Use `humanize.naturaltime()` for relative time formatting

### 3. Update CLI

**File**: `src/weft/cli.py`

- Add `status` subparser with `--status`, `--sort`, `--reverse` arguments
- Add lazy-loaded dispatch block for status command
- No tab completion needed for status command arguments

### 4. Unit Tests

**File**: `tests/unit/test_status_command.py`

Test cases:

**Plan scanning (via cache integration):**
- Empty tasks directory → empty table with headers
- Multiple plans → returns all plan metadata in table
- Handles missing `.weft/tasks/` directory gracefully

**Edge cases for malformed data:**
- Plan file with no frontmatter section at all → skipped with warning, doesn't crash
- Plan file with empty/null `plan_id` → handled gracefully
- Inaccessible plan file (permission denied) → skipped with warning, doesn't crash

**Pipeline state detection:**
- Plan with no artifacts → all artifact columns show `-`
- Plan with worktree only → Worktree shows `✓`, others show `-`
- Plan with all artifacts → all artifact columns show `✓`

**Filtering:**
- `--status ready` → shows only ready plans
- `--status ready,coding` → shows ready and coding plans
- `--status` with no matches → empty table with headers

**Sorting:**
- Default sort (status then modified) produces correct order
- `--sort plan_id` sorts alphabetically
- `--sort modified` sorts by file mtime
- `--reverse` reverses the sort order

**Output formatting:**
- Table includes all expected columns
- Empty table shows headers only
- Modified time shows relative format (e.g., "2 days ago")

### 5. Update CLI Tests

**File**: `tests/unit/test_cli.py`

- Add `"status"` to `test_subcommand_help_no_import_errors` parametrize list
- Add status command test case to `test_all_subcommands_dispatch_without_import_errors`

## Deliverables

1. New `weft status` command showing pipeline state for all plans
2. Filter and sort options for focused views
3. Human-readable table output with relative timestamps
4. Comprehensive unit test coverage

## Out of Scope

- JSON output format (table only for now)
- Integration tests (command is purely local filesystem operations)
- Tab completion for `--status` values
- Colored output or progress indicators
