---
plan_id: round-out-eval-command
status: done
evaluation_notes: []
git_sha: 69f854e7d020209c65fd1f3c0120704ea0e7ba6f
---

# Round Out Eval Command with Complete Training Data Collection

## Objectives

- Enhance the eval command to collect comprehensive training data for DSPy prompt optimization
- Run tests before and after implementation using Claude Code SDK (headless execution)
- Collect structured human feedback via interactive Claude Code session
- Reorganize storage structure for better organization: rename runs→sessions, organize all artifacts by plan_id
- Create permanent training_data/ directory with all evaluation artifacts (committed to git)
- Generate per-judge output files in both JSON (machine-readable) and markdown (human-readable) formats
- Ensure robust error handling for multi-step evaluation process

## Requirements & Constraints

### Functional Requirements

**1. Test Execution via Claude Code SDK**
- Run tests in "before" state (at plan's git_sha commit) using headless Claude Code SDK
- Run tests in "after" state (current worktree) using headless Claude Code SDK
- Use `run_sdk_session_sync()` pattern from code_command.py (lines 366-372)
- Prompt Claude Code to run tests and output structured JSON with schema:
  ```json
  {
    "command": "uv run pytest",
    "exit_code": 1,
    "total_tests": 45,
    "passed_tests": 42,
    "failed_tests": 3,
    "failed_test_details": [...],
    "summary": "3 tests failed due to...",
    "analysis": "The failures suggest that...",
    "possible_solutions": ["Solution 1", "Solution 2"],
    "recommended_fix": "Update the test expectations because..."
  }
  ```
- Save results to `test_results_before.json` and `test_results_after.json`
- Test failures are DATA, not errors - eval command succeeds even if tests fail
- Claude Code SDK must handle any test framework (delegates to CLAUDE.md context)

**2. Human Feedback Collection**
- After judges and tests complete, launch interactive Claude Code session
- Use prompt template at `src/lw_coder/prompts/claude-code/eval-feedback.md`
- Prompt helps user compose free-form feedback (not rigidly structured)
- May or may not include sections like "Strengths" or "Issues" - user decides
- Claude Code creates `human_feedback.md` when user is satisfied
- On session exit, copy file to `sessions/<plan_id>/eval/`
- No approval prompts after session - file is ready when Claude exits

**3. Judge Results Enhancement**
- Generate one JSON file per judge: `judge_<name>.json` (e.g., `judge_code-reuse.json`)
- Generate one markdown file per judge: `judge_<name>.md` (human-readable formatted version)
- JSON contains: judge_name, weight, score, feedback
- Markdown contains: formatted sections with score, weight, and detailed feedback
- Extract judge name from JudgeResult.judge_name field (confirmed available in judge_executor.py)

**4. Training Data Creation**
- After all steps complete successfully, create `.lw_coder/training_data/<plan_id>/`
- Copy/generate files:
  - `plan.md` - copy from `.lw_coder/tasks/<plan_id>.md`
  - `code_trace.md` - copy from `.lw_coder/sessions/<plan_id>/code/trace.md`
  - `test_results_before.json` - copy from sessions eval/
  - `test_results_after.json` - copy from sessions eval/
  - `human_feedback.md` - copy from sessions eval/
  - `judge_<name>.json` - copy from sessions eval/ (one per judge)
  - `judge_<name>.md` - copy from sessions eval/ (one per judge)
- Training data is PERMANENT - never pruned, expected to be committed to git
- If code trace doesn't exist, warn user: "Code trace not found. Training example will be incomplete. Continue? (y/n)"

**5. Storage Reorganization**
- Rename `.lw_coder/runs/` → `.lw_coder/sessions/`
- New structure:
  ```
  .lw_coder/sessions/<plan_id>/
  ├── plan/
  │   └── trace.md                    # Plan session trace
  ├── code/                            # Code session (no timestamp)
  │   ├── trace.md
  │   ├── droids/
  │   └── prompts/
  └── eval/                            # NEW: Eval outputs
      ├── test_results_before.json
      ├── test_results_after.json
      ├── human_feedback.md
      ├── judge_<name>.json
      └── judge_<name>.md
  ```
- Sessions have 30-day retention (existing RUN_RETENTION_DAYS policy)
- Update plan_command.py to store plan traces at `sessions/<plan_id>/plan/trace.md`
- Update code_command.py to store code artifacts at `sessions/<plan_id>/code/`
- Read plan_id from created plan.md after Claude Code session exits (for plan command)

**6. Console Output**
- Show progress: "Running judges...", "Running before tests...", "Running after tests...", "Collecting feedback..."
- Show judge scores as they complete: "code-reuse: 0.85/1.00"
- Show test summaries: "Before: 42/45 passed", "After: 45/45 passed"
- Don't show full judge feedback or detailed test output in console (that goes in files)

**7. Idempotency and Resume**
- Eval command should be re-runnable if it fails partway through
- Skip steps that have already completed successfully:
  - **Judges**: Run only for judges whose output files don't exist. If new judges were added, run those. If judges were removed, delete their stale output files.
  - If test_results_before.json exists, skip before-tests
  - If test_results_after.json exists, skip after-tests
  - If human_feedback.md exists, skip feedback collection (user can use --force to re-provide)
  - If training_data/<plan_id>/ exists, skip training data creation (existence check only - staging pattern ensures atomic creation)
- Add `--force` flag to force re-running all steps and overwrite existing results
- Show clear messages: "Skipping judges (already run, use --force to re-run)"
- **Note**: Staleness detection (e.g., code changed since last test run) is out of scope - user should use --force if they need fresh results

### Technical Constraints

**1. Claude Code SDK Integration**
- Use existing `run_sdk_session_sync()` from sdk_runner.py
- Headless mode for test execution (no user interaction)
- Interactive mode for feedback collection
- Same SDK settings path as code command: `src/lw_coder/sdk_settings.json`
- Model: use same effective_model as eval command (default: sonnet)

**2. Git SHA Handling**
- Primary: Use plan file's `git_sha` field to determine "before" state
- Validate SHA exists: `git rev-parse --verify <sha>`
- Fallback: If git_sha is missing or invalid:
  - Log warning: "Plan's git_sha '<sha>' not found. Skipping before-tests."
  - Prompt user: "Training data will include after-tests only. Continue? (y/n)"
  - If yes, proceed without before-tests
  - If no, exit eval command
- This is an edge case (shouldn't happen often)

**3. Error Handling**
- Test failures are data (exit_code != 0 is acceptable)
- Claude Code SDK failures should be caught and reported clearly
- Missing code trace: warn and ask user to continue
- Invalid git_sha: warn and skip before-tests
- Partial eval failures: if any step fails, don't create training_data/
- Use staging directory pattern for atomic training_data creation:
  - Collect all artifacts in temp directory first
  - Only copy to training_data/ if all steps succeed
  - If any step fails, clean up temp directory and exit

**4. CLAUDE.md Dependency**
- Test execution relies on CLAUDE.md being committed and up-to-date
- For "before" tests: worktree at git_sha has CLAUDE.md from that commit
- For "after" tests: worktree has current CLAUDE.md
- Claude Code naturally understands how to run tests for each version
- No hardcoded test commands needed

**5. Test Reuse Requirements**
- Review existing tests in `tests/test_eval_command.py`
- Modify existing tests rather than creating duplicates
- Only create new tests when absolutely necessary
- Follow BEST_PRACTICES.md guidelines:
  - Use pytest.fail() for missing dependencies, not pytest.skip()
  - Use real DSPy/LLM calls (benefits from caching)
  - Don't test interactive commands directly
  - Use parametrization for similar test cases

**6. Integration Test Requirement**
- Create ONE integration test that actually runs Claude Code SDK
- Test must run on this repo (lw_coder)
- Mark with `@pytest.mark.integration`
- Test verifies: Claude Code SDK can run tests and produce valid JSON output
- This test is REQUIRED to pass for task completion
- May be slow/expensive - that's acceptable for integration test

### Design Constraints

**1. Training Data Format**
- All files in training_data/ are plain text (JSON or markdown)
- No binary files, no compression (for now)
- Human-readable where possible (markdown preferred over JSON for narrative content)
- Machine-parseable where needed (JSON for structured data)

**2. Retention Policy**
- Sessions: 30-day retention via existing prune_old_runs() logic
- Training data: PERMANENT, no pruning ever
- Update prune logic to handle new sessions/ structure
- Sessions are NOT committed to git
- Training data IS committed to git (user is aware of potential growth)

**3. Backward Compatibility**
- Old runs/ and plan-traces/ directories: user will delete manually via cleanup script
- No auto-migration of old data
- New code only reads from new sessions/ structure
- Old structure support is out of scope

**4. Modularity**
- Test execution logic in separate module (e.g., test_runner.py)
- Feedback collection logic in separate module (e.g., feedback_collector.py)
- Training data creation logic in separate module (e.g., training_data_exporter.py)
- Eval command orchestrates these modules

## Work Items

### 1. Create Storage Reorganization Infrastructure

**1.1 Update run_manager.py → session_manager.py**
- Rename file: `run_manager.py` → `session_manager.py`
- Update all function names: `create_run_directory` → `create_session_directory`
- Change path: `.lw_coder/runs/` → `.lw_coder/sessions/`
- Update structure to support new layout:
  ```python
  def create_session_directory(repo_root: Path, plan_id: str, session_type: str) -> Path:
      """Create session directory for plan, code, or eval.

      Args:
          repo_root: Repository root
          plan_id: Plan identifier
          session_type: One of 'plan', 'code', 'eval'

      Returns:
          Path like .lw_coder/sessions/<plan_id>/<session_type>/
      """
  ```
- Update prune function: `prune_old_runs` → `prune_old_sessions`
- Keep 30-day retention policy (RUN_RETENTION_DAYS → SESSION_RETENTION_DAYS)
- Update all imports throughout codebase

**1.2 Update code_command.py**
- Import from session_manager instead of run_manager
- Update session creation to use new structure (no timestamp subdirectory)
- Change trace capture path: `session_dir / "trace.md"` (not `session_dir / timestamp / "trace.md"`)
- Update droids and prompts paths to `session_dir / "droids"` and `session_dir / "prompts"`
- Remove timestamp logic (single code session per plan, multiple runs is future work)

**1.3 Update plan_command.py**
- Import from session_manager
- **Timing consideration**: plan_id is not known until AFTER Claude Code session creates the plan file
- Flow:
  1. Run Claude Code session (creates plan file in worktree)
  2. Copy plan files from worktree to main repo (existing logic at lines 342-347)
  3. Extract plan_id from copied files (existing logic at lines 356-363)
  4. Create session directory: `create_session_directory(repo_root, plan_id, "plan")`
  5. Capture trace to the session directory
- Store plan trace at: `.lw_coder/sessions/<plan_id>/plan/trace.md`
- **Note**: This changes the current flow where trace directory is created BEFORE session runs
- The trace capture must happen AFTER we know the plan_id
- If no plan file was created (user cancelled without creating plan), skip trace capture

**1.4 Update trace_capture.py**
- `create_plan_trace_directory` can be removed or simplified:
  - Plan trace directories are now created via `session_manager.create_session_directory()`
  - The function may still be useful as a thin wrapper that calls session_manager
- `prune_old_plan_traces` should be removed:
  - Pruning is now handled by `session_manager.prune_old_sessions()` which handles all session types
  - Remove calls to `prune_old_plan_traces()` from plan_command.py
- `capture_session_trace` remains unchanged - it writes to whatever directory is provided

**1.5 Create cleanup script**
- Create standalone script: `cleanup_old_storage.py` in repo root (NOT in src/)
- Script should:
  - List all directories to be deleted:
    - `.lw_coder/runs/` (all contents)
    - `.lw_coder/plan-traces/` (all contents)
  - Calculate and display total size
  - Show detailed list of what will be removed
  - Prompt: "Delete these directories? This cannot be undone. Type 'yes' to confirm: "
  - Only delete if user types exactly 'yes'
  - Log what was deleted
- Add `cleanup_old_storage.py` to .gitignore
- Add comment in script: "# DO NOT COMMIT THIS SCRIPT - for manual repo cleanup only"
- Document in plan: User will run this manually in each repo after upgrade

### 2. Create Claude Session Abstraction Layer

**2.1 Create claude_session.py module**
- File: `src/lw_coder/claude_session.py`
- Purpose: Reusable abstraction around `run_sdk_session_sync()` for all Claude Code SDK interactions
- This module will be used by: test execution, feedback collection, and refactored code command

**2.2 Implement run_headless_session()**
- Function signature:
  ```python
  def run_headless_session(
      worktree_path: Path,
      prompt: str,
      model: str,
      expected_output: Path,
      sdk_settings_path: Path
  ) -> Path:
      """Run headless Claude Code session via SDK.

      Executes prompt, waits for completion, validates output file exists.
      Use for: test execution, non-interactive tasks.

      Args:
          worktree_path: Path to worktree for session execution
          prompt: Prompt content for Claude Code
          model: Model to use (sonnet, opus, haiku)
          expected_output: File that should be created by session
          sdk_settings_path: Path to SDK settings.json

      Returns:
          Path to output file

      Raises:
          ClaudeSessionError: If session fails or output missing
      """
  ```
- Implementation:
  ```python
  session_id = run_sdk_session_sync(
      worktree_path=worktree_path,
      prompt_content=prompt,
      model=model,
      sdk_settings_path=sdk_settings_path
  )

  if not expected_output.exists():
      raise ClaudeSessionError(
          f"Expected output file not created: {expected_output}"
      )

  return expected_output
  ```

**2.3 Implement run_interactive_session()**
- Function signature:
  ```python
  def run_interactive_session(
      worktree_path: Path,
      prompt: str,
      model: str,
      expected_output: Path,
      sdk_settings_path: Path
  ) -> Path:
      """Run SDK session then launch CLI for user interaction.

      Runs headless SDK first (for logging/tracing), then launches
      interactive CLI for user to continue working.
      Use for: feedback collection, interactive editing tasks.

      Args:
          worktree_path: Path to worktree for session execution
          prompt: Initial prompt content for Claude Code
          model: Model to use (sonnet, opus, haiku)
          expected_output: File that should be created by session
          sdk_settings_path: Path to SDK settings.json

      Returns:
          Path to output file

      Raises:
          ClaudeSessionError: If session fails or output missing
      """
  ```
- Implementation:
  ```python
  # Run SDK first (for logging/tracing)
  session_id = run_sdk_session_sync(
      worktree_path=worktree_path,
      prompt_content=prompt,
      model=model,
      sdk_settings_path=sdk_settings_path
  )

  # Launch CLI for interactive user session
  command = f"claude -r {shlex.quote(session_id)} --model {shlex.quote(model)}"
  subprocess.run(shlex.split(command), cwd=worktree_path, check=True)

  if not expected_output.exists():
      raise ClaudeSessionError(
          f"Expected output file not created: {expected_output}"
      )

  return expected_output
  ```

**2.4 Add ClaudeSessionError exception**
- Define custom exception for session failures
- Include helpful error messages for debugging

**2.5 Add unit tests for claude_session.py**
- File: `tests/test_claude_session.py`
- Mock `run_sdk_session_sync()` for testing
- Test output validation logic
- Test error handling for missing output files
- Test both headless and interactive modes

### 3. Implement Test Execution via Claude Code SDK

**3.1 Create test execution prompt template**
- File: `src/lw_coder/prompts/claude-code/test-execution.md` or inline in test_runner.py
- Content:
  ```markdown
  # Test Execution for Evaluation

  You need to run all tests in this codebase and report the results in a structured format.

  ## Instructions

  1. **Check CLAUDE.md**: Look for the CLAUDE.md file in the repository root. This file should contain instructions on how to run tests for this project.

  2. **Run all tests**: Execute ALL test types documented in CLAUDE.md:
     - Unit tests
     - Integration tests
     - End-to-end tests
     - Any other test categories

     If CLAUDE.md lists multiple test commands or categories, run them all.

  3. **Collect results**: Observe the test execution and collect:
     - The command(s) you ran
     - The exit code
     - Total number of tests
     - Number of passed tests
     - Number of failed tests
     - Details of any failed tests (test name, error message, file location)

  4. **Create output file**: Write the results to `test_results.json` in the current directory with this exact schema:
     ```json
     {
       "command": "the full test command you ran",
       "exit_code": 0,
       "total_tests": 45,
       "passed_tests": 45,
       "failed_tests": 0,
       "failed_test_details": [
         {
           "test_name": "test_example",
           "file": "tests/test_example.py",
           "error_message": "AssertionError: expected X but got Y"
         }
       ],
       "summary": "Brief summary of test results",
       "analysis": "Your analysis of what the test results mean",
       "possible_solutions": ["Solution 1", "Solution 2"],
       "recommended_fix": "Your recommendation for addressing any failures"
     }
     ```

  5. **Handle failures**: If tests fail, that's okay - capture the failure details in the JSON. Don't treat test failures as errors in your execution.

  ## Important Notes

  - If CLAUDE.md is missing or doesn't document test commands, write a JSON file with an error message explaining this
  - Don't make assumptions about the test framework (pytest, unittest, jest, etc.) - let CLAUDE.md guide you
  - If multiple commands are needed, run them all and combine the results
  - The analysis, possible_solutions, and recommended_fix fields should contain YOUR insights about the test results
  ```
- Template variables: None (self-contained prompt)

**3.2 Create test runner module**
- File: `src/lw_coder/test_runner.py`
- Function: `run_tests_via_sdk(worktree_path: Path, output_file: Path, model: str) -> None`
- Uses `run_headless_session()` from claude_session.py
- Loads prompt template (to be finalized)
- Validates output file exists and contains valid JSON after SDK session
- Raises TestRunnerError if SDK fails or output is invalid

**3.3 Implement before-tests logic**
- Function: `run_before_tests(plan_path: Path, plan_id: str, repo_root: Path, model: str) -> Optional[Path]`
- Read git_sha from plan file
- Validate with `git rev-parse --verify <sha>`
- If invalid:
  - Log warning with SHA
  - Prompt user: "Skip before-tests? (y/n)"
  - Return None if user confirms
  - Exit if user declines
- Create temp worktree at git_sha:
  ```python
  temp_worktree = repo_root / ".lw_coder" / "temp-worktrees" / f"{plan_id}-before"
  subprocess.run(["git", "worktree", "add", str(temp_worktree), sha], check=True)
  ```
- Run tests via SDK in temp worktree
- Save output to `sessions/<plan_id>/eval/test_results_before.json`
- Clean up temp worktree:
  ```python
  subprocess.run(["git", "worktree", "remove", str(temp_worktree)], check=True)
  ```
- Return path to test results file

**3.4 Implement after-tests logic**
- Function: `run_after_tests(plan_id: str, repo_root: Path, model: str) -> Path`
- Worktree path: `.lw_coder/worktrees/<plan_id>/` (existing worktree from code command)
- Run tests via SDK in existing worktree
- Save output to `sessions/<plan_id>/eval/test_results_after.json`
- Return path to test results file

**3.5 Add error handling**
- Define TestRunnerError exception
- Catch SDK errors and provide clear messages
- Validate JSON schema after SDK completes:
  ```python
  from jsonschema import validate, ValidationError

  TEST_RESULT_SCHEMA = {
      "type": "object",
      "required": ["command", "exit_code", "total_tests"],
      "properties": {
          "command": {"type": "string"},
          "exit_code": {"type": "integer"},
          "total_tests": {"type": "integer"},
          # ... more fields
      }
  }
  ```
- If validation fails, raise TestRunnerError with helpful message

**3.6 Add unit tests**
- File: `tests/test_test_runner.py`
- Mock SDK calls for fast unit tests
- Test validation logic
- Test error handling
- Test JSON schema validation

**3.7 Add integration test**
- File: `tests/test_test_runner_integration.py`
- Mark with `@pytest.mark.integration`
- Actually call Claude Code SDK to run tests on lw_coder repo
- Verify:
  - SDK completes successfully
  - Output JSON file exists
  - JSON schema is valid
  - Test counts are reasonable (could be 100+, even 300+ tests)
- This test MUST PASS for task completion
- May be slow/expensive - that's acceptable

### 4. Implement Human Feedback Collection

**4.1 Create feedback prompt (built entirely in Python)**
- No template file - build the entire prompt string in `feedback_collector.py`
- Create a function like `build_feedback_prompt(plan_id: str, eval_results: str) -> str` that returns the full prompt
- Use Python f-strings to insert plan_id and formatted evaluation results directly
- Prompt content should include:
  ```markdown
  # Evaluation Feedback Collection

  You are helping the user provide feedback on a code implementation that was just evaluated. Your role is to help them compose thoughtful feedback based on the evaluation results.

  ## Context

  The user just ran an evaluation on plan: {plan_id}

  The evaluation included:
  - LLM judge scores assessing code quality and plan compliance
  - Test results before implementation (baseline)
  - Test results after implementation (current state)

  ## Your Task

  Help the user compose feedback about the implementation. This feedback will be used as training data for improving future code implementations.

  1. **Present the evaluation results**: Show the user the judge scores and test results so they can review them.

  2. **Gather their feedback**: Ask the user what feedback they have about the implementation. This is free-form - they can structure it however they want. Some users might organize feedback into sections like "Strengths" and "Issues", others might write narrative feedback, and others might use bullet points. Let them decide.

  3. **Help refine**: Offer to help them compose or refine their feedback if they want assistance. You can suggest improvements to clarity, help them articulate concerns, or add details they might have missed.

  4. **Create the file**: When the user is satisfied with their feedback, write it to `human_feedback.md` in the current directory.

  ## Important Notes

  - This is their feedback, not yours. Don't insert your own analysis unless they ask for it.
  - There's no required structure - respect however they want to organize their thoughts.
  - Don't ask for approval after creating the file - when it's written, you're done.
  - The file will be automatically copied to the training data when this session ends.

  ## Evaluation Results

  {eval_results}

  Now please present these results to the user and help them compose their feedback.
  ```

**4.2 Create feedback collector module**
- File: `src/lw_coder/feedback_collector.py`
- Function: `collect_human_feedback(plan_id: str, repo_root: Path, model: str) -> Path`
- Load feedback prompt from template file
- Get worktree path: `.lw_coder/worktrees/<plan_id>/`
- Use `run_interactive_session()` from claude_session.py:
  ```python
  from claude_session import run_interactive_session

  feedback_path = run_interactive_session(
      worktree_path=worktree_path,
      prompt=feedback_prompt,
      model=model,
      expected_output=worktree_path / "human_feedback.md",
      sdk_settings_path=sdk_settings_path
  )
  ```
- Note: All interaction happens INSIDE the Claude Code session
- When session exits, human_feedback.md should exist in worktree
- Copy `human_feedback.md` to `sessions/<plan_id>/eval/`
- Return path to saved feedback file

**4.3 Add error handling**
- Define FeedbackCollectionError exception
- Handle missing feedback file
- Handle user cancellation (Ctrl+C during Claude session)
- Provide clear error messages

**4.4 Add tests**
- Mock interactive Claude Code session
- Test file validation
- Test copying to sessions directory

### 5. Enhance Judge Results Output

**5.1 Update eval_command.py**
- Remove console output of judge results (or minimize to just scores)
- **Incremental judge execution for idempotency**:
  ```python
  # Discover which judges need to run
  discovered_judges = discover_judges(judges_dir)
  discovered_names = {j.name for j in discovered_judges}

  # Check which judge outputs already exist
  existing_outputs = {p.stem.replace("judge_", "") for p in eval_dir.glob("judge_*.json")}

  # Delete outputs for removed judges
  for stale_name in existing_outputs - discovered_names:
      (eval_dir / f"judge_{stale_name}.json").unlink()
      (eval_dir / f"judge_{stale_name}.md").unlink(missing_ok=True)
      logger.info("Removed stale judge output: %s", stale_name)

  # Run only judges that don't have outputs yet
  judges_to_run = [j for j in discovered_judges if j.name not in existing_outputs]
  if not judges_to_run:
      logger.info("All judges already run (use --force to re-run)")
  ```
- After judges execute, save results to files:
  ```python
  for result in judge_results:
      # Save JSON
      json_path = eval_dir / f"judge_{result.judge_name}.json"
      json_data = {
          "judge_name": result.judge_name,
          "weight": result.weight,
          "score": result.score,
          "feedback": result.feedback
      }
      json_path.write_text(json.dumps(json_data, indent=2))

      # Save markdown
      md_path = eval_dir / f"judge_{result.judge_name}.md"
      md_content = format_judge_markdown(result)
      md_path.write_text(md_content)
  ```
- Show scores to console: "code-reuse: 0.85/1.00"

**5.2 Create markdown formatting function**
- Function: `format_judge_markdown(result: JudgeResult) -> str`
- Generate human-readable markdown:
  ```markdown
  # Judge: {judge_name}

  **Weight**: {weight}
  **Score**: {score:.2f} / 1.00

  ## Feedback

  {feedback}
  ```

**5.3 Update tests**
- Modify existing tests in `tests/test_eval_command.py`
- Test per-judge file generation
- Test markdown formatting
- Don't create duplicate tests

### 6. Implement Training Data Export

**6.1 Create training data exporter module**
- File: `src/lw_coder/training_data_exporter.py`
- Function: `create_training_data(plan_id: str, repo_root: Path) -> Path`
- Use staging directory pattern for atomic operations:
  ```python
  with tempfile.TemporaryDirectory() as staging:
      staging_path = Path(staging)

      # Copy all files to staging
      copy_plan_file(plan_id, repo_root, staging_path)
      copy_code_trace(plan_id, repo_root, staging_path)
      copy_test_results(plan_id, repo_root, staging_path)
      copy_judge_results(plan_id, repo_root, staging_path)
      copy_human_feedback(plan_id, repo_root, staging_path)

      # Atomic commit: only copy to training_data if all succeeded
      training_data_dir = repo_root / ".lw_coder" / "training_data" / plan_id
      shutil.copytree(staging_path, training_data_dir)
  ```
- If any copy fails, staging directory is automatically cleaned up (tempfile behavior)
- Return path to created training data directory

**6.2 Implement copy functions**
- `copy_plan_file()`: Copy from `.lw_coder/tasks/<plan_id>.md` to `plan.md`
- `copy_code_trace()`: Copy from `.lw_coder/sessions/<plan_id>/code/trace.md` to `code_trace.md`
  - Check if file exists first
  - If missing: warn user and ask to continue
  - Return without copying if user confirms
- `copy_test_results()`: Copy both before and after JSON files (handle missing before gracefully)
- `copy_judge_results()`: Copy all `judge_*.json` and `judge_*.md` files
- `copy_human_feedback()`: Copy `human_feedback.md`

**6.3 Add validation**
- Function: `validate_training_data(training_data_dir: Path) -> list[str]`
- Check required files exist:
  - plan.md (required)
  - code_trace.md (warn if missing)
  - test_results_after.json (required)
  - test_results_before.json (optional)
  - human_feedback.md (required)
  - At least one judge_*.json file (required)
- Return list of warnings/issues
- Log validation results

**6.4 Add error handling**
- Define TrainingDataExportError exception
- Handle file copy failures
- Handle missing source files
- Provide clear error messages

**6.5 Add tests**
- Test staging directory pattern
- Test atomic commit behavior
- Test validation logic
- Test error handling for missing files

### 7. Refactor Code Command to Use Claude Session Abstraction

**7.1 Update code_command.py imports**
- Import from claude_session instead of calling run_sdk_session_sync directly
- Remove subprocess logic for CLI resume (now handled by run_interactive_session)

**7.2 Refactor SDK execution (lines 353-379)**
- Replace current pattern:
  ```python
  # OLD:
  session_id = run_sdk_session_sync(...)
  command = f"claude -r {session_id} --model {model}"
  subprocess.run(...)
  ```
- With:
  ```python
  # NEW:
  from claude_session import run_interactive_session

  # Note: code command doesn't expect a specific output file
  # So we don't validate expected_output (pass None or handle specially)
  run_interactive_session(
      worktree_path=worktree_path,
      prompt=prompts["main_prompt"],
      model=effective_model,
      expected_output=None,  # No specific file expected for code command
      sdk_settings_path=sdk_settings_path
  )
  ```
- May need to adjust run_interactive_session() to handle None for expected_output
- Or create a variant: run_interactive_session_no_output()

**7.3 Update trace capture**
- Trace capture still uses session_id (currently returned by run_sdk_session_sync)
- If run_interactive_session() returns session_id, use that
- Otherwise, may need to adjust trace capture to work without session_id
- Or have run_interactive_session() optionally return session_id

**7.4 Test the refactored code command**
- Ensure existing functionality preserved
- Code command still works with SDK + CLI pattern
- Trace capture still works

### 8. Update Tests for Claude Session Refactoring

**8.1 Update conftest.py auto-mock fixture**
- File: `tests/conftest.py`
- Current fixture (line 86-104) mocks: `code_command.run_sdk_session_sync`
- Update to mock at new location: `claude_session.run_sdk_session_sync`
- Change from:
  ```python
  monkeypatch.setattr(
      "lw_coder.code_command.run_sdk_session_sync",
      mock_sdk_session
  )
  ```
- To:
  ```python
  monkeypatch.setattr(
      "lw_coder.claude_session.run_sdk_session_sync",
      mock_sdk_session
  )
  ```
- This affects ALL unit tests (autouse fixture)

**8.2 Update test_code_command.py monkeypatch calls**
- File: `tests/test_code_command.py`
- Three tests directly monkeypatch run_sdk_session_sync:
  - Line 905: `test_code_command_with_claude_code_tool_explicit_model()`
  - Line 981: `test_code_command_default_tool_and_model()`
  - Line 1044: `test_code_command_sdk_session_failure()`
- Update all three to monkeypatch at new location
- Change from:
  ```python
  monkeypatch.setattr(
      "lw_coder.code_command.run_sdk_session_sync",
      mock_session
  )
  ```
- To:
  ```python
  monkeypatch.setattr(
      "lw_coder.claude_session.run_sdk_session_sync",
      mock_session
  )
  ```

**8.3 Review other test files**
- Check `test_cli.py`, `test_write_sub_agents.py`, `test_sdk_integration.py`
- Most should be unaffected (they mock at higher level via conftest.py)
- Integration tests (`test_sdk_integration.py`) make real SDK calls - should still work

**8.4 Add tests for new modules**
- `test_claude_session.py` - test both headless and interactive functions
- Test output validation, error handling

### 9. Update Eval Command

**9.1 Modify run_eval_command()**
- Update function signature to accept model and force parameters
- Implement idempotency: skip completed steps unless --force is used
- Orchestrate all steps:
  1. Validate inputs (plan exists, worktree exists)
  2. Create eval session directory
  3. Run judges (skip if already done unless --force)
  4. Run before tests (skip if already done unless --force)
  5. Run after tests (skip if already done unless --force)
  6. Collect human feedback (skip if already done unless --force)
  7. Create training data (skip if already exists unless --force)
- Show progress messages for each step
- Show skip messages: "Skipping X (already done, use --force to re-run)"
- Show results: judge scores, test counts

**9.2 Add progress indicators**
- Show clear progress for each step
- Show summaries (scores, test counts)
- Don't show full detailed output (that's in files)

**9.3 Update CLI integration**
- File: `src/lw_coder/cli.py`
- Add `--force` flag to eval command
- Ensure model parameter exists (may already be there)
- Update help text:
  - Document new functionality
  - Explain --force flag behavior
  - Note that eval is idempotent (can be re-run safely)

**9.4 Update existing tests**
- Modify tests in `tests/test_eval_command.py`
- Update mocks for new flow
- Don't duplicate existing test coverage

### 10. Documentation

**10.1 Move CLI documentation from CLAUDE.md to README.md**
- Remove "### CLI Usage" section from CLAUDE.md (lines 20-64)
- Remove "#### Init Command", "#### Quick Fix Mode", "#### Eval Command" subsections
- Keep only development commands in CLAUDE.md (install, test, run CLI)
- Move all CLI usage documentation to README.md

**10.2 Update README.md with full CLI documentation**
- Add comprehensive CLI Usage section with all commands:
  - init command (with flags and examples)
  - plan command
  - code command (with quick fix mode)
  - eval command (updated for new functionality)
  - finalize command
  - completion command
- Add section on eval command workflow:
  ```markdown
  ### Eval Command

  The `eval` command evaluates code changes and creates training data for DSPy prompt optimization:

  ```bash
  uv run lw_coder eval <plan_id>
  ```

  **What it does:**
  - Runs LLM judges to evaluate code quality and plan compliance
  - Runs tests before/after implementation via Claude Code SDK
  - Collects human feedback through interactive Claude Code session
  - Creates permanent training data in `.lw_coder/training_data/<plan_id>/`

  **Requirements:**
  - Your project's CLAUDE.md must document how to run tests
  - `OPENROUTER_API_KEY` in `~/.lw_coder/.env`

  **Flags:**
  - `--force`: Re-run all evaluation steps, overwriting existing results
  ```
- Document training data structure and purpose
- Explain test execution via Claude Code SDK
- Document human feedback collection process

**10.3 Document storage reorganization in README.md**
- Explain new sessions/ structure
- Document cleanup script usage
- Note: manual migration required (run cleanup script)

**10.4 Document CLAUDE.md requirements in README.md**
- Target project's CLAUDE.md must be committed to repo
- Must contain test execution instructions
- Examples of good test documentation
- This is required for eval command to work properly

**10.5 Keep CLAUDE.md minimal**
- CLAUDE.md should only contain:
  - Project overview
  - Development commands (install, test, run)
  - Testing organization and guidelines
- All user-facing CLI documentation goes in README.md

### 11. Testing

**11.1 Review existing tests across ALL test files**
- Don't just review `tests/test_eval_command.py`
- Check ALL test files for potential duplicates:
  - `tests/test_code_command.py`
  - `tests/test_cli.py`
  - `tests/test_sdk_integration.py`
  - `tests/test_trace_capture.py`
  - Any other relevant test files
- Modify existing tests to work with new flow
- Only add new tests when absolutely necessary

**11.2 Add new tests only where needed**
- Test runner module tests (`tests/test_test_runner.py`)
- Claude session abstraction tests (`tests/test_claude_session.py`)
- Feedback collector tests (basic functionality only)
- Training data exporter tests
- Idempotency tests (verify skipping works, --force overrides)
- **Pruning test**: Verify sessions/ gets pruned but training_data/ never does

**11.3 No interactive session tests**
- Don't create tests that require interactive Claude Code sessions
- Mock all Claude Code interactions in unit tests
- Integration test (3.7) runs SDK headless only (for tests)

**11.4 Test error handling**
- Test error handling paths
- Test edge cases (missing files, invalid git_sha, etc.)
- Test partial failure scenarios

## Deliverables

1. **Updated Storage Structure**
   - `.lw_coder/sessions/<plan_id>/` with plan/, code/, eval/ subdirectories
   - All code updated to use new structure
   - No timestamp for code sessions (single session per plan)

2. **Enhanced Eval Command**
   - Runs tests before/after via Claude Code SDK (headless)
   - Collects human feedback via Claude Code (interactive)
   - Creates permanent training data with all artifacts
   - Shows progress and scores to console
   - Handles errors gracefully (test failures, missing git_sha, etc.)

3. **Training Data Directory**
   - `.lw_coder/training_data/<plan_id>/` with all required files:
     - plan.md, code_trace.md
     - test_results_before.json, test_results_after.json
     - human_feedback.md
     - judge_<name>.json and judge_<name>.md (per judge)
   - Permanent storage (no pruning)
   - Expected to be committed to git

4. **New Modules**
   - `session_manager.py` (renamed from run_manager.py)
   - `test_runner.py` (test execution via SDK)
   - `feedback_collector.py` (human feedback collection)
   - `training_data_exporter.py` (training data creation)

5. **Feedback Prompt Template**
   - `src/lw_coder/prompts/claude-code/eval-feedback.md`
   - Guides user through feedback process
   - Structures output in markdown format

6. **Cleanup Script**
   - `cleanup_old_storage.py` in repo root
   - NOT committed to git (in .gitignore)
   - Shows what will be deleted, asks for confirmation
   - User runs manually in each repo

7. **Refactored Code Command**
   - code_command.py uses claude_session.py abstraction
   - Cleaner, more testable SDK interaction
   - Consistent pattern across all Claude Code usage

8. **Updated Tests**
   - conftest.py auto-mock updated for new module location
   - test_code_command.py monkeypatch calls updated (3 tests)
   - New test_claude_session.py for abstraction layer
   - All existing tests still pass

9. **Updated Documentation**
   - CLAUDE.md updated with new eval command details
   - README.md updated with training data structure
   - Migration documentation for storage reorganization
   - CLAUDE.md requirements documented

10. **Comprehensive Tests**
    - Integration test for test runner (runs Claude Code SDK headless - REQUIRED TO PASS)
    - Unit tests for all new modules
    - Updated existing tests across all test files (not just test_eval_command.py)
    - Pruning test: verifies training_data/ never gets pruned
    - Idempotency tests: verifies eval can be re-run safely
    - No interactive session tests

## Out of Scope

1. **Multiple Code Sessions Per Plan**
   - Currently: single code session per plan (no timestamp)
   - Future work: support re-running code command multiple times
   - Would need versioning or timestamp strategy

2. **Plan Trace in Training Data**
   - Training data focuses on code command optimization
   - Plan traces not needed for current use case
   - May add later if plan command optimization becomes priority

3. **Compiled Training Sample JSON**
   - No single consolidated training_sample.json file
   - Individual files are sufficient for current needs
   - May add later if DSPy requires specific format

4. **Old Data Migration**
   - No automatic migration of runs/ and plan-traces/ data
   - User deletes old structure manually via cleanup script
   - New code only works with new structure

5. **Training Data Pruning**
   - Training data is permanent (no retention policy)
   - User is aware of potential git repository growth
   - Future optimization (compression, Git LFS, etc.) out of scope

6. **Test Framework Detection**
   - Tests delegated to Claude Code via CLAUDE.md
   - No automatic detection of pytest/unittest/etc.
   - No fallback to direct pytest execution

7. **Feedback Collection Retries**
   - If feedback collection fails, eval command fails
   - No automatic retry or recovery
   - User must re-run eval command

8. **Judge Result Aggregation**
   - No overall weighted score calculation in files
   - Per-judge files only
   - Aggregation can be done externally if needed

9. **Test Result Visualization**
   - No graphs, charts, or formatted reports
   - Raw JSON and markdown only
   - Visualization out of scope

10. **Partial Eval Re-runs**
    - Can't re-run just one step (e.g., only judges)
    - Must re-run entire eval command
    - Step-by-step execution out of scope

11. **Alternative Test Execution Methods**
    - No fallback to direct pytest execution
    - No configuration for custom test commands
    - Claude Code SDK is the only test execution method

12. **Training Data Versioning**
    - No version field in training data files
    - No schema versioning
    - Format changes are breaking changes

