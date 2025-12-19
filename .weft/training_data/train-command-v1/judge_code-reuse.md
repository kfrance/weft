# Judge: code-reuse

**Weight**: 0.40
**Score**: 1.00 / 1.00

## Feedback

### Overall Assessment
Excellent code reuse practices throughout the changes. The implementation faithfully follows the plan without reimplementing existing logic. New functionality (training data loading, DSPy prompt generation, candidate writing) is cleanly separated into dedicated modules. Existing modules like `prompt_loader.py`, `init_command.py`, and `cli.py` are appropriately extended rather than duplicated. No instances of duplicated logic, missed abstractions, or pattern inconsistencies were found.

### Positive Examples of Good Reuse
1. **prompt_loader.py extension (lines ~20-160)**:
   - Added `_migrate_prompts_if_needed()` and `_get_prompts_base()` as targeted extensions to handle new `prompts/active/` structure.
   - `load_current_prompts_for_training()` reuses existing file discovery patterns and adds dynamic subagent loading via `glob("*.md")` – perfect reuse of Pathlib without reimplementing directory scanning.
   - Falls back gracefully to old `optimized_prompts/` with one-time migration using `shutil.copytree()` – delegates to stdlib instead of custom copy logic.

2. **cli.py integration (lines ~250-290)**:
   - Follows exact pattern of other commands (lazy imports in `main()` dispatch: `from .train_command import run_train_command`).
   - Parser setup mirrors `eval_parser` structure (e.g., `--model` with default).
   - No duplication of argument validation or dispatch logic.

3. **init_command.py migration (lines ~300-320, ~450-470)**:
   - Updates `copy_optimized_prompts()` to new path (`prompts/active`), reuses existing `shutil.copytree()` and atomic staging.
   - Detects customizations for both old/new paths via `detect_customizations()` extension.
   - Cleanup of old `optimized_prompts/` is a clean addition without reimplementing directory ops.

4. **train_command.py orchestration**:
   - Reuses `find_repo_root()`, `load_training_batch()`, `load_current_prompts_for_training()`, `get_cache_dir()`.
   - Parameter validation via new `_validate_parameters()` but follows patterns from other commands.
   - Output formatting reuses logger patterns from `eval_command.py`.

5. **DSPy integration in prompt_trainer.py**:
   - Follows established DSPy pattern from codebase (e.g., `dspy.Signature`, `dspy.Predict`, OpenRouter LM config matching CLAUDE.md guidelines).
   - No reimplementation of judge_executor logic – new `PromptTrainerSignature` is feature-specific.
   - Token extraction `_extract_token_usage()` is minimal and new (no equivalent exists).

6. **Tests**:
   - Unit tests follow existing pytest patterns (e.g., `tmp_path` fixtures, `monkeypatch` for subprocess).
   - Integration test `test_train_command_end_to_end()` uses real DSPy per CLAUDE.md ("no mocks for DSPy"), with caching.

### No Reimplemented Functionality Found
- **New modules** (`training_types.py`, `training_data_loader.py`, `prompt_trainer.py`, `candidate_writer.py`, `train_command.py`): All genuinely new abstractions for training workflow. No duplication of existing loaders (e.g., `plan_validator.py`), git utils, or DSPy patterns.
- **Judge formatting** in `training_data_loader.py._format_judge_results()`: Simple new logic for concatenating JSON/MD files – no overlap with judge_executor output parsing.
- **Candidate numbering/writing**: Custom regex/glob logic specific to `candidate-NNN/` – no existing equivalent.
- **Directory migration**: Uses stdlib `shutil`/`Path.mkdir()` – no custom FS ops reimplemented.
- **Git deletions** (optimized_prompts): Necessary for migration, not code duplication.

### Recommendations for Further Reuse (Minor)
- Consider extracting common DSPy LM config (OpenRouter, cache, reasoning) into a shared `dspy_utils.py` utility if more signatures are added (already good pattern adherence).
- `candidate_writer.py` filename sanitization could reuse a general `safe_filename()` util if added later, but it's feature-specific and minimal.

This change demonstrates mature codebase stewardship: extends without duplication, preserves patterns, adds comprehensive tests (unit + real DSPy integration).
