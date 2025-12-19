---
plan_id: fix-subagent-hallucinations
status: done
evaluation_notes: []
git_sha: fb8fa5d63e12b121ea1fa550285fbc7ddaf56af0
---

# Fix Subagent Hallucination Issues

## Objectives

Fix the subagent hallucination problem in the `lw_coder code` command where code-review-auditor and plan-alignment-checker subagents fabricate analysis without actually reading files or running git commands.

The primary goal is to restructure subagent prompts to explicitly trigger tool invocations rather than displaying commands as markdown examples, ensuring subagents actually gather context before performing analysis.

## Requirements & Constraints

### Requirements

1. **Subagent prompts must trigger actual tool usage**
   - Remove or clarify markdown code block examples that cause confusion
   - Use explicit tool invocation language ("Use the Bash tool to run...", "Use the Read tool to read...")
   - Add verification steps that prevent analysis until files are actually read

2. **Main agent must display full subagent output**
   - Modify main.md prompt to show complete subagent reports verbatim
   - User needs visibility into what subagents are recommending during the coding process
   - Output should be clearly labeled (which subagent, what they found)

3. **Changes must apply to all model families**
   - Prompts exist for both sonnet and haiku models
   - Changes must be consistently applied across both
   - Maintain any model-specific optimizations if they exist

4. **Preserve architectural intent**
   - Subagents must do their own context gathering (read files, run git commands)
   - Main agent context must be preserved (subagents work independently)
   - No changes to the orchestration layer (code remains unchanged)

### Constraints

- Transcripts are available at `/home/kfrance/.claude/projects/-home-kfrance-lw-coder--lw-coder-worktrees-claude-cli-model-default` for validation
- Prompt files are located at `.lw_coder/optimized_prompts/claude-code-cli/{sonnet,haiku}/`
- These are "optimized" prompts (potentially from DSPy/GEPA) - manual changes may affect optimization
- No programmatic validation layer should be added (keep it simple)
- No additional monitoring/logging infrastructure needed

## Work Items

### 1. Analyze Current Prompt Issues

**Investigation phase:**
- Review the existing code-review-auditor.md prompts (sonnet and haiku)
- Review the existing plan-alignment-checker.md prompts (sonnet and haiku)
- Identify specific patterns that cause hallucination:
  - Markdown code blocks that look like examples but aren't invoked
  - Ambiguous language about running vs. showing commands
  - Missing verification steps between context gathering and analysis
- Document the problematic sections

### 2. Restructure code-review-auditor.md

**For both sonnet and haiku versions:**

**Remove/fix problematic patterns:**
- Replace markdown example code blocks with explicit tool invocation instructions
- Change language from "Example command pattern:" to "Use the Bash tool to run:"
- Add explicit steps that must be completed before analysis

**Add verification requirements:**
- Require agent to list files actually read before providing analysis
- Add checkpoints: "After running git diff, verify you can see the changes before proceeding"
- Structure the prompt to make it clear tool invocation is mandatory, not optional

**Maintain analysis quality:**
- Keep the structured JSON output format requirement
- Preserve the severity guidelines and quality assessment sections
- Ensure the prompt still produces useful, specific code review feedback

**Example transformation:**
```
BEFORE:
Example command pattern:
```bash
git diff HEAD~1..HEAD
```

AFTER:
Before analyzing any code, you MUST use the Bash tool to gather context:

1. Use the Bash tool to run: git diff HEAD
2. Use the Bash tool to run: git status --short
3. For each changed file, use the Read tool to read the complete file

After gathering this context, proceed with analysis.
```

### 3. Restructure plan-alignment-checker.md

**For both sonnet and haiku versions:**

**Similar changes as code-review-auditor:**
- Replace examples with explicit tool invocation instructions
- Make context gathering steps mandatory and sequential
- Add verification checkpoints

**Specific to plan alignment:**
- Emphasize reading the plan.md file first (Use Read tool)
- Then reading implementation files (Use Read tool for each)
- Then comparing requirements to implementation

**Maintain output structure:**
- Keep the structured alignment report format
- Preserve requirements coverage tracking
- Ensure the prompt still identifies gaps and deviations effectively

### 4. Modify main.md to Display Subagent Output

**For both sonnet and haiku versions:**

**Current state** (from analysis):
- Main prompt says "Synthesize results" and "Combine findings"
- This likely causes main agent to summarize rather than display full output

**Required changes:**
- Add explicit instruction to display FULL verbatim output from both subagents
- Structure the output clearly:
  ```
  ## Code Review Auditor Report
  [Full output from code-review-auditor]

  ## Plan Alignment Checker Report
  [Full output from plan-alignment-checker]
  ```
- Main agent can still synthesize AFTER showing full reports
- User needs to see complete subagent recommendations during coding

### 5. Test the Changes

**Validation approach:**

1. **Manual testing with a sample plan:**
   - Run `lw_coder code` with a test plan
   - Monitor the Claude Code CLI session
   - Verify subagents actually invoke Bash and Read tools
   - Check that main agent displays full subagent output

2. **Transcript analysis:**
   - After test run, examine transcripts in `/home/kfrance/.claude/projects/`
   - Look for actual tool invocations (Bash tool, Read tool) in agent-*.jsonl files
   - Verify no more hallucinations (fabricated line numbers, unread files)

3. **Compare before/after:**
   - Use Oct 28 transcripts as "before" baseline (known hallucinations)
   - New transcripts should show actual tool usage
   - Document the improvement

### 6. Update Both Model Families Consistently

**Ensure consistency:**
- Apply identical changes to sonnet/ and haiku/ directories
- Verify all three prompt files updated in both:
  - code-review-auditor.md
  - plan-alignment-checker.md
  - main.md
- Check for any model-specific differences that should be preserved

## Deliverables

1. **Updated prompt files** (6 files total):
   - `.lw_coder/optimized_prompts/claude-code-cli/sonnet/code-review-auditor.md`
   - `.lw_coder/optimized_prompts/claude-code-cli/sonnet/plan-alignment-checker.md`
   - `.lw_coder/optimized_prompts/claude-code-cli/sonnet/main.md`
   - `.lw_coder/optimized_prompts/claude-code-cli/haiku/code-review-auditor.md`
   - `.lw_coder/optimized_prompts/claude-code-cli/haiku/plan-alignment-checker.md`
   - `.lw_coder/optimized_prompts/claude-code-cli/haiku/main.md`

2. **Test validation results**:
   - Transcript showing actual tool invocations by subagents
   - Verification that hallucinations are eliminated
   - Confirmation that main agent displays full subagent output

3. **Documentation of changes** (optional but recommended):
   - Brief note documenting what was changed and why
   - Could be added to this plan's evaluation_notes after testing

## Out of Scope

The following are explicitly NOT part of this plan:

1. **Architectural changes**:
   - No context-first architecture (main agent gathering context)
   - No changes to orchestration layer code
   - No changes to parallel_executor.py or orchestrator.py

2. **Validation/monitoring infrastructure**:
   - No ToolUsageValidator class
   - No programmatic checking of tool invocations
   - No hallucination detection systems
   - No logging/metrics infrastructure

3. **Testing infrastructure**:
   - No automated tests for prompt effectiveness
   - No unit tests for subagent behavior
   - Validation is manual only

4. **Prompt optimization**:
   - No re-running DSPy/GEPA optimization after changes
   - Manual edits only
   - Accept that this may invalidate existing optimizations

5. **Other model families**:
   - No opus model (doesn't currently exist in the directory structure)
   - Only sonnet and haiku

6. **Fixing other potential issues**:
   - Only addressing the hallucination problem
   - Not improving analysis quality, output formatting, etc.
   - Not adding new subagent types
