---
plan_id: eval-command-llm-judges
status: done
git_sha: 51c1a2148bc55864c2a83fa394bd8c268701bb88
evaluation_notes: []
---

# Implement `eval` Command with LLM Judges

## Objectives

- Create a new `lw_coder eval <plan_id>` command that evaluates code changes using repo-specific LLM judges
- Implement DSPy-based judge framework that loads prompts from markdown files
- Create two initial judges: code reuse and plan compliance
- Enable parallel judge execution with detailed feedback output
- Implement comprehensive integration test using real DSPy LLM calls with `dspy.inspect_history()` to verify that judge prompts from markdown files are correctly loaded and passed to the language model

## Requirements & Constraints

### Command Behavior
- Command signature: `lw_coder eval <plan_id>`
- Tab completion support for plan_id (similar to existing commands)
- Evaluates changes in the plan's worktree (`.lw_coder/worktrees/{plan_id}/`)
- Can be run during or after the `code` command execution
- Stop immediately on any judge failure (fail-fast)
- Output detailed judge feedback to console only (no file persistence for now)

### Judge File Format
- Location: `.lw_coder/judges/*.md`
- YAML frontmatter with two required fields:
  - `weight`: float value for weighted scoring
  - `model`: OpenRouter model tag (e.g., "x-ai/grok-4.1-fast")
- Body: Judge instructions in markdown format (loaded as prompt text)
- Example structure:
  ```markdown
  ---
  weight: 0.3
  model: x-ai/grok-4.1-fast
  ---

  You are evaluating code changes for...
  [Judge instructions here]
  ```

### DSPy Integration
- Use DSPy with the `.with_instructions()` pattern to load prompts from markdown files
- Pattern example:
  ```python
  # Load instructions from markdown file body
  judge_instructions = """
  You are evaluating code changes...
  [loaded from judge markdown body]
  """

  # Create base signature with I/O fields only
  class JudgeSignatureBase(dspy.Signature):
      """Base judge signature."""
      plan_content: str = dspy.InputField(desc="Plan content")
      git_changes: str = dspy.InputField(desc="Git changes")
      score: float = dspy.OutputField(desc="Score 0.0-1.0")
      feedback: str = dspy.OutputField(desc="Detailed feedback")

  # Create final signature with loaded instructions
  JudgeSignature = JudgeSignatureBase.with_instructions(judge_instructions)

  # Use with DSPy predictor
  predictor = dspy.Predict(JudgeSignature)
  result = predictor(plan_content=plan, git_changes=changes)
  ```

### DSPy Configuration
- Use OpenRouter via LiteLLM (DSPy's default)
- Disk caching at `~/.lw_coder/dspy_cache`
- Load `OPENROUTER_API_KEY` from `~/.lw_coder/.env`
- Configure DSPy LM per judge using the model from frontmatter
- Use same DSPy setup pattern from old implementation:
  ```python
  lm = dspy.LM("openrouter/{model}", api_key=api_key, max_tokens=64000)
  dspy.configure(lm=lm, cache={"type": "disk", "path": str(cache_dir)})
  ```

### Judge Input/Output Schema
- **Inputs** (same for all judges):
  - `plan_content: str` - Full plan.md file content from worktree
  - `git_changes: str` - Combined git diff, status, and changed file contents

- **Outputs** (same for all judges):
  - `score: float` - Score from 0.0 to 1.0
  - `feedback: str` - Detailed explanation and recommendations

### Judge Execution
- Discover all judge files in `.lw_coder/judges/` directory
- Run all judges in parallel (concurrent execution)
- Collect all results before displaying any output
- If any judge fails, stop immediately and show error
- Display results after all judges complete:
  - Show each judge's name, score, and full feedback
  - Format output for readability on console

### Initial Judges to Implement

#### 1. Code Reuse Judge (`.lw_coder/judges/code-reuse.md`)
**Purpose**: Evaluate whether code properly reuses existing functionality

**Evaluation criteria**:
- Check if code reimplemented functionality when it should have called existing functions/utilities
- Verify code properly reuses existing abstractions and patterns from the codebase
- Note: Look for reimplemented functionality, not exact copy-paste (code may differ but duplicate logic)

**Suggested frontmatter**:
- `weight: 0.4`
- `model: x-ai/grok-4.1-fast`

#### 2. Plan Compliance Judge (`.lw_coder/judges/plan-compliance.md`)
**Purpose**: Verify implementation matches plan requirements

**Evaluation criteria**:
- Similar to existing `plan-alignment-checker` subagent
- Verify all plan requirements are implemented
- Check for out-of-scope additions (scope creep)
- Ensure deliverables match plan specifications
- Flag missing requirements or implementations that go beyond the plan

**Suggested frontmatter**:
- `weight: 0.6`
- `model: x-ai/grok-4.1-fast`

### Testing Requirements
- Follow `docs/BEST_PRACTICES.md` guidelines:
  - Use `pytest.fail()` for missing dependencies, not `pytest.skip()`
  - Use real DSPy with real LLM API calls (benefits from caching)
  - Don't test interactive commands directly
  - Use parametrization for similar test cases
- Test judge file parsing (YAML frontmatter + body extraction)
- Test judge discovery in `.lw_coder/judges/` directory
- Test DSPy signature creation with `.with_instructions()`
- Test parallel execution with mock judges
- Test error handling (judge failure, missing worktree, invalid plan_id)
- Integration test with real LLM calls (marked as slow/expensive)

### Documentation
- Update `README.md` with eval command section (similar to existing plan/code command sections)
- Update `CLAUDE.md` with eval command usage in CLI commands section
- Document judge file format and how to create new judges
- Add examples of good judge prompts
- Document DSPy usage rationale (different from static prompts in code command)

## Work Items

### 1. Set Up Judge Infrastructure
- Create `.lw_coder/judges/` directory structure
- Implement judge file loader:
  - Parse YAML frontmatter (extract `weight`, `model`)
  - Extract markdown body content
  - Validate required fields exist
- Create judge discovery function (scan `.lw_coder/judges/*.md`)
- Add tests for judge file parsing

### 2. Implement DSPy Judge Framework
- Create base DSPy Signature class for judges:
  - Input fields: `plan_content`, `git_changes`
  - Output fields: `score`, `feedback`
- Implement `.with_instructions()` pattern to inject loaded prompts
- Create DSPy configuration function:
  - Initialize cache at `~/.lw_coder/dspy_cache`
  - Load `OPENROUTER_API_KEY` from `~/.lw_coder/.env`
  - Configure DSPy LM with model from judge frontmatter
- Implement judge execution function that:
  - Takes judge config (weight, model, instructions)
  - Configures DSPy with appropriate model
  - Creates signature with `.with_instructions()`
  - Calls DSPy predictor
  - Returns score and feedback
- Add tests for DSPy integration

### 3. Implement Git Context Gathering
- Create function to gather evaluation context from worktree:
  - Read `plan.md` from worktree root
  - Run `git status` in worktree
  - Run `git diff HEAD` to get all changes
  - Read full contents of changed files
  - Combine into structured string for judge input
- Handle worktree not existing (clear error message)
- Add tests for context gathering

### 4. Implement Parallel Judge Execution
- Create parallel execution orchestrator:
  - Run all judges concurrently
  - Collect all results
  - Fail-fast on any judge error
  - Return list of judge results (name, score, feedback)
- Use appropriate async/parallel execution mechanism
- Handle errors gracefully with clear messages
- Add tests for parallel execution

### 5. Create `eval` CLI Command
- Add `eval` subcommand to CLI in `src/lw_coder/cli.py`
- Implement main eval command function:
  - Accept plan_id argument
  - Validate plan exists and has worktree
  - Discover judges in `.lw_coder/judges/`
  - Gather git context from worktree
  - Execute all judges in parallel
  - Format and display results
- Add tab completion for plan_id (reuse existing completion logic)
- Add error handling for:
  - Invalid/missing plan_id
  - Worktree doesn't exist
  - No judges found
  - Judge execution failures
  - Missing OPENROUTER_API_KEY
- Add tests for eval command (with mocked judges)

### 6. Create Initial Judge Prompts
- Write code reuse judge prompt (`.lw_coder/judges/code-reuse.md`):
  - Clear instructions for evaluating code reuse
  - Examples of good vs bad reuse patterns
  - Guidance on scoring (0.0-1.0 scale)
  - Format for detailed feedback
- Write plan compliance judge prompt (`.lw_coder/judges/plan-compliance.md`):
  - Instructions similar to plan-alignment-checker
  - Systematic verification of plan requirements
  - Detection of out-of-scope implementations
  - Scoring guidance and feedback format
- Test both judges with real evaluation scenarios

### 7. Implement Output Formatting
- Create console output formatter that displays:
  - Header with plan_id and worktree path
  - Each judge's results:
    - Judge name
    - Score (formatted clearly)
    - Full detailed feedback (wrapped/formatted for readability)
  - Summary section (optional: show weighted scores)
- Ensure output is clear and easy to read
- Add color/formatting if appropriate (using click styling)

### 8. Documentation and Integration
- Update `README.md` with eval command section:
  - Command usage: `lw_coder eval <plan_id>`
  - When to use it (during or after code command)
  - Example output format
  - Follow structure of existing plan/code command sections
- Update `CLAUDE.md` with:
  - `lw_coder eval <plan_id>` in CLI commands section
  - When to use eval command
  - How to interpret judge output
- Create judge development guide:
  - How to write a new judge
  - Judge prompt best practices
  - Examples of effective judge prompts
  - Testing judges
- Document DSPy reintroduction rationale:
  - Why DSPy for judges vs static prompts for code command
  - Different use cases: dynamic evaluation vs static implementation
  - Future: judge prompt optimization via DSPy/GEPA
- Update dependencies in `pyproject.toml` if needed

## Deliverables

1. Working `lw_coder eval <plan_id>` command with tab completion
2. Judge framework that loads prompts from `.lw_coder/judges/*.md` files
3. DSPy integration using `.with_instructions()` pattern
4. Two functional judges:
   - Code reuse judge
   - Plan compliance judge
5. Parallel judge execution with detailed console output
6. Comprehensive test suite following best practices
7. Documentation in CLAUDE.md and judge development guide

## Out of Scope

- Judge result persistence to files (console output only for now)
- Judge prompt optimization via GEPA (future enhancement)
- Web UI or formatted reports (console output only)
- Judge versioning or migration system
- Plugin system for external judges
- Performance metrics or benchmarking
- Cost tracking per judge execution
- Retry logic for failed judges (fail immediately)
- Support for judge dependencies or ordering
- Incremental evaluation (only changed files)

## Test Cases

```gherkin
Feature: Eval Command with LLM Judges
  Scenario: Evaluate code changes with all judges
    Given a plan "test-plan" with worktree at ".lw_coder/worktrees/test-plan"
    And the worktree has uncommitted changes
    And two judges exist in ".lw_coder/judges/"
    When I run "lw_coder eval test-plan"
    Then both judges execute in parallel
    And I see detailed output for each judge with score and feedback
    And the command exits successfully
    And using dspy.inspect_history() shows that:
      - Both judges' prompts from markdown files were loaded
      - Judge instructions appear in the LLM system messages
      - Responses include both score and feedback fields
    (Note: inspect_history() only logs LLM calls, not full program execution)

  Scenario: Fail fast on judge error
    Given a plan with valid worktree
    And a judge that will fail (invalid model, API error, etc.)
    When I run "lw_coder eval <plan_id>"
    Then the command stops immediately on judge failure
    And I see a clear error message
    And the command exits with non-zero status

  Scenario: Handle missing worktree
    Given a plan_id without a worktree
    When I run "lw_coder eval <plan_id>"
    Then I see an error message about missing worktree
    And the command exits with non-zero status

```
