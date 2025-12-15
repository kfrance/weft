---
plan_id: eval-session-metadata
status: done
evaluation_notes: []
git_sha: 6eaf2c10a3fd9d427616814f15179205261264f2
---

# Eval Session Metadata and Prompt Capture

## Objectives

Enable training for specific models and toolchains by:
1. Recording which tool (claude-code or droid) and model (opus, sonnet, haiku) was used during `code` command execution
2. Capturing the exact prompts (main + subagents) used for each coding session with a fingerprint hash for easy comparison
3. Computing an eval fingerprint from judge configurations to identify comparable evaluations
4. Including this metadata in training data so the `train` command can filter and analyze by tool/model/fingerprints
5. Migrating existing training samples to include this metadata

## Requirements & Constraints

### Functional Requirements
- `code` command must write all prompts (main + subagents) to `session_dir/prompts/`
- `code` command must write `metadata.json` to `session_dir/` with tool, model, timestamp, and prompt_fingerprint
- `eval` command must compute eval_fingerprint from loaded judges and add it to metadata
- `eval` command must copy prompts and metadata from the code session directory to the training data directory (when creating training data)
- Training samples must include the prompts that were used for that session
- Existing training samples must be migrated to include prompts and metadata

### Technical Constraints
- Unified `PromptSnapshot` model replaces separate `CurrentPrompts`/`UsedPrompts` to avoid duplication
- Both claude-code and droid tools must be handled consistently
- Missing prompts/metadata must be handled gracefully (optional fields default to None)
- Fingerprints use SHA256 truncated to 8 characters for readability

### Fingerprint Computation

**Prompt fingerprint** (computed during `code` command):
- Sort subagents by name for deterministic ordering
- Concatenate main prompt and all subagent prompts with their names
- Return first 8 characters of SHA256 hash

**Eval fingerprint** (computed during `eval` command):
- Sort judges by name for deterministic ordering
- Concatenate judge name, weight, and prompt for each judge
- Return first 8 characters of SHA256 hash

### Data Format

**Session metadata.json** (written by `code` command):
```json
{
  "tool": "claude-code",
  "model": "sonnet",
  "recorded_at": "2025-12-12T14:30:00Z",
  "prompt_fingerprint": "b7d4e2f9"
}
```

**Training data metadata.json** (after `eval` command adds eval_fingerprint):
```json
{
  "tool": "claude-code",
  "model": "sonnet",
  "recorded_at": "2025-12-12T14:30:00Z",
  "prompt_fingerprint": "b7d4e2f9",
  "eval_fingerprint": "a3f8b2c1"
}
```

**Training data directory structure after changes:**
```
.lw_coder/training_data/<plan_id>/
  prompts/
    main.md
    code-review-auditor.md  (if claude-code)
    plan-alignment-checker.md  (if claude-code)
  metadata.json
  plan.md
  code_trace.md
  human_feedback.md
  judge_*.json
  judge_*.md
  test_results_before.json
  test_results_after.json
```

## Work Items

### 1. Refactor CurrentPrompts to PromptSnapshot (training_types.py)

- Rename `CurrentPrompts` to `PromptSnapshot`
- Update docstrings to reflect dual use (current and historical prompts)

### 2. Create SessionMetadata model (training_types.py)

- Add new `SessionMetadata` Pydantic model with fields: tool, model, recorded_at, prompt_fingerprint, eval_fingerprint (optional)

### 3. Update TrainingSample model (training_types.py)

- Add `used_prompts: PromptSnapshot | None` field
- Add `tool: str` field with default "claude-code"
- Add `model: str | None` field
- Add `prompt_fingerprint: str | None` field
- Add `eval_fingerprint: str | None` field

### 4. Create fingerprint module (fingerprint.py)

- Create new module with `compute_prompt_fingerprint()` and `compute_eval_fingerprint()` functions
- Keep fingerprint logic centralized for consistency

### 5. Update prompt_loader.py to use PromptSnapshot

- Update `load_current_prompts_for_training()` to return `PromptSnapshot` instead of `CurrentPrompts`
- Update imports and type hints

### 6. Update prompt_trainer.py to use PromptSnapshot

- Update function signatures to accept `PromptSnapshot`
- Update imports

### 7. Write prompts to session directory (code_command.py)

- Create function to write all prompts to `session_dir/prompts/`
- For claude-code: write main.md and all subagent .md files
- For droid: write the droid prompt as main.md
- Call this function after creating the session directory

### 8. Write metadata.json to session directory (code_command.py)

- Create function to write metadata.json with tool, model, recorded_at, and prompt_fingerprint
- Call this function after creating the session directory

### 9. Compute prompt_fingerprint in code_command.py

- Import fingerprint computation from fingerprint module
- Compute fingerprint before writing metadata
- Pass fingerprint to metadata writing function

### 10. Remove redundant main prompt writing (code_command.py)

- Remove the existing code at lines 371-378 that writes only main.md to session_dir/prompts/
- The new prompt writing function will handle all prompt writing

### 11. Add copy_prompts function (training_data_exporter.py)

- Add function to copy prompts directory from session to staging
- Return warning message if prompts not found (non-fatal)

### 12. Add copy_and_update_metadata function (training_data_exporter.py)

- Add function to copy metadata.json from session and add eval_fingerprint
- Takes eval_fingerprint as parameter (computed by eval_command)
- If session metadata missing, create minimal metadata with just eval_fingerprint

### 13. Update create_training_data signature (training_data_exporter.py)

- Add `eval_fingerprint: str` parameter to `create_training_data()`
- Call copy_prompts and copy_and_update_metadata functions
- Handle warnings (non-fatal, just log them)

### 14. Update validate_training_data (training_data_exporter.py)

- Add optional checks for prompts/ directory and metadata.json
- These are optional files, so missing them generates warnings not errors

### 15. Compute eval_fingerprint in eval_command.py

- Import fingerprint computation from fingerprint module
- After loading judges, compute the eval_fingerprint
- Pass eval_fingerprint to `create_training_data()` call

### 16. Update training_data_loader.py to load prompts and metadata

- Add function to load prompts from training data directory into PromptSnapshot
- Add function to load metadata from training data directory
- Update `load_training_sample()` to populate new fields (used_prompts, tool, model, fingerprints)

### 17. Pass used_prompts to prompt trainer (prompt_trainer.py)

- Update trainer to receive and use `used_prompts` from training samples
- This allows the DSPy trainer to see historical prompt context

### 18. Migrate existing training data

**Location:** `.lw_coder/training_data/test-planner-subagent/`

Manual migration steps:
1. Create `prompts/` directory
2. Copy prompts from `.lw_coder/prompts/active/claude-code-cli/opus/` to `prompts/`
3. Compute prompt_fingerprint from copied prompts
4. Compute eval_fingerprint from current judges in `.lw_coder/judges/`
5. Create `metadata.json` with tool="claude-code", model="opus", recorded_at (use git commit date for this sample), prompt_fingerprint, eval_fingerprint
6. Verify the plan.md file exists (it appears to be missing from this sample)

## Deliverables

1. New `fingerprint.py` module with fingerprint computation functions
2. Updated `training_types.py` with `PromptSnapshot`, `SessionMetadata`, and updated `TrainingSample`
3. Updated `code_command.py` with prompt/metadata writing and prompt_fingerprint computation
4. Updated `eval_command.py` with eval_fingerprint computation
5. Updated `training_data_exporter.py` with copy functions for prompts and metadata
6. Updated `training_data_loader.py` with loading functions for prompts and metadata
7. Updated `prompt_loader.py` and `prompt_trainer.py` to use `PromptSnapshot`
8. Migrated existing training sample(s)

## Out of Scope

- **Train command filtering** - filtering by tool/model/fingerprints will be added in a future task
- Rich metadata capture (tool version, token usage, duration) - can be added later
- Indexing or caching for large-scale training data - not needed with current sample counts
- Sanitization of prompts for secrets/PII - can be added later if needed
- Reference-based storage instead of copying - copying is simpler and data volume is manageable

## Unit Tests

### test_fingerprint.py (new file)

**TestComputePromptFingerprint:**
- `test_compute_prompt_fingerprint_deterministic`: Same inputs produce same fingerprint
- `test_compute_prompt_fingerprint_changes_with_content`: Different content produces different fingerprint
- `test_compute_prompt_fingerprint_subagent_order_independent`: Subagents sorted by name before hashing

**TestComputeEvalFingerprint:**
- `test_compute_eval_fingerprint_deterministic`: Same judges produce same fingerprint
- `test_compute_eval_fingerprint_changes_with_judges`: Different judges produce different fingerprint
- `test_compute_eval_fingerprint_judge_order_independent`: Judges sorted by name before hashing

### test_code_command.py

**New tests:**
- `test_code_command_writes_prompts_directory`: Verify session_dir/prompts/ contains main.md and subagent files
- `test_code_command_writes_metadata_json`: Verify session_dir/metadata.json with correct structure
- `test_code_command_metadata_includes_prompt_fingerprint`: Verify prompt_fingerprint in metadata
- `test_code_command_metadata_tool_model_combinations` (parametrized): Test claude-code/sonnet, claude-code/opus, droid/None

### test_eval_command.py

**New tests:**
- `test_eval_command_computes_eval_fingerprint`: Verify eval_fingerprint computed from judges
- `test_eval_command_passes_eval_fingerprint_to_exporter`: Verify fingerprint passed to create_training_data

### test_training_data_exporter.py

**TestCopyPrompts (new class):**
- `test_copies_prompts_directory_to_staging`: Verify full directory copy
- `test_returns_warning_when_prompts_missing`: Verify warning when directory missing
- `test_copies_all_markdown_files`: Verify all .md files copied

**TestCopyAndUpdateMetadata (new class):**
- `test_copies_metadata_and_adds_eval_fingerprint`: Verify file copy and eval_fingerprint added
- `test_creates_minimal_metadata_when_source_missing`: Verify minimal metadata created
- `test_preserves_existing_metadata_fields`: Verify tool, model, prompt_fingerprint preserved

**Update TestCreateTrainingData:**
- `test_create_training_data_includes_prompts_and_metadata`: Verify prompts/ and metadata.json in output
- `test_create_training_data_requires_eval_fingerprint`: Verify eval_fingerprint parameter required

### test_training_data_loader.py

**TestLoadTrainingSampleWithMetadata (new class):**
- `test_load_sample_populates_used_prompts`: Verify used_prompts field populated from prompts/
- `test_load_sample_populates_tool_and_model`: Verify tool/model from metadata.json
- `test_load_sample_populates_fingerprints`: Verify prompt_fingerprint and eval_fingerprint loaded
- `test_load_sample_handles_missing_prompts`: Verify used_prompts=None when prompts/ missing
- `test_load_sample_handles_missing_metadata`: Verify defaults when metadata.json missing

## Integration Tests

None required for this task. Integration tests for train command filtering will be added when that feature is implemented.
