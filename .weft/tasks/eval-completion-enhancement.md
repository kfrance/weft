---
plan_id: eval-completion-enhancement
status: done
evaluation_notes: []
git_sha: 4d948aa0ff259790099c4ace598a480690e19904
---

# Eval Command Completion Enhancement

## Objectives

1. Enable tab completion for the `eval` command to show both finished and unfinished plans
2. Order completions with unfinished plans first (alphabetically), then finished plans (by file mtime, most recent first)
3. Remove outdated `--no-cache` instruction from uv commands in prompts

## Requirements & Constraints

- Only the eval command's completion behavior changes; other commands continue to show only active plans
- Use file modification time to determine recency for finished plans
- Ordering logic lives in the completer layer, not the cache layer (separation of concerns)
- Extend existing test files rather than creating new ones

## Work Items

### 1. Parameterize cache function

**File:** `src/weft/completion/cache.py`

- Add `include_finished: bool = False` parameter to `get_active_plans()` method
- When `include_finished=True`, include plans with status == "done"
- Return plans in simple alphabetical order (ordering logic handled by completer)
- Update module-level `get_active_plans()` convenience function with same parameter
- Maintain backward compatibility: existing callers with no parameter get current behavior

### 2. Add eval-specific completer

**File:** `src/weft/completion/completers.py`

- Add `complete_eval_plans(prefix, parsed_args, **kwargs)` function
- Call `get_active_plans(include_finished=True)` to get all plans
- Apply two-tier ordering:
  - Tier 1: Unfinished plans (status != "done"), sorted alphabetically
  - Tier 2: Finished plans (status == "done"), sorted by file mtime (most recent first)
- Filter by prefix and return results

### 3. Wire up new completer

**File:** `src/weft/cli.py`

- Import `complete_eval_plans` from completers module
- Change eval command's `plan_id` argument completer from `complete_plan_files` to `complete_eval_plans`

### 4. Remove --no-cache instruction

**Files to modify:**

- `.weft/prompts/active/claude-code-cli/sonnet/main.md` - Remove line containing `--no-cache` instruction
- `.weft/prompts/active/claude-code-cli/opus/main.md` - Remove line containing `--no-cache` instruction
- `.weft/prompts/active/claude-code-cli/haiku/main.md` - Remove line containing `--no-cache` instruction
- `src/weft/init_templates/prompts/claude-code-cli/sonnet/main.md` - Remove line containing `--no-cache` instruction
- `src/weft/init_templates/prompts/claude-code-cli/opus/main.md` - Remove line containing `--no-cache` instruction
- `src/weft/init_templates/prompts/claude-code-cli/haiku/main.md` - Remove line containing `--no-cache` instruction
- `src/weft/test_runner.py` (line 70) - Remove line containing `--no-cache` instruction

### 5. Unit Tests

**Extend `tests/unit/test_completion_cache.py`:**

- Test `get_active_plans(include_finished=True)` returns both done and non-done plans
- Test `get_active_plans(include_finished=False)` excludes done plans (existing behavior)
- Test default parameter maintains backward compatibility
- Test with mix of statuses (draft, ready, coding, implemented, done, abandoned)
- Test caching works correctly with new parameter

**Extend `tests/unit/test_completion_completers.py`:**

- Test `complete_eval_plans()` returns all plans (finished and unfinished)
- Test two-tier ordering: unfinished plans first (alphabetically sorted)
- Test two-tier ordering: finished plans second (sorted by mtime, most recent first)
- Test prefix filtering works correctly
- Test edge case: plans with identical mtime (stable sort)
- Test edge case: empty prefix returns all plans
- Test edge case: all plans done
- Test edge case: no plans done

### 6. Integration Tests

Per test-reviewer analysis, no integration tests are required for these changes:

- The CLI validation tests don't specifically test eval completion
- The test_runner integration tests validate execution behavior, not prompt content
- Unit tests provide sufficient coverage for the completion and prompt changes

## Deliverables

- Modified `src/weft/completion/cache.py` with parameterized `include_finished` support
- New `complete_eval_plans()` function in `src/weft/completion/completers.py`
- Updated eval command wiring in `src/weft/cli.py`
- Seven prompt/template files with `--no-cache` instruction removed
- Extended unit tests in `test_completion_cache.py` and `test_completion_completers.py`

## Out of Scope

- Changing completion behavior for other commands (code, finalize, judge, abandon)
- Adding `finished_at` timestamp field to plan YAML
- Performance optimization for large numbers of plan files
- Tab completion for plan paths (only plan IDs)
