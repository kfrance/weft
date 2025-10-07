---
plan_id: integrate-droid-cli-tool
git_sha: de528997b23028fdd0732ae6d17a8c11ad6c6348
status: done
evaluation_notes:
  - If a non-root user was created in the Dockerfile, will that user have access to droid and other files it needs to run?
  - Was a glibc compatible docker container used since droid is compiled for glibc?
  - Was the integration smoke test implemented?
  - Tests shouldn't be skipped for any reason. Do any tests that were implemented have pytest marks to skip for any reason?
  - Did the .git folder get mounted into the docker container so git commands work in the worktree?
---

# Task Plan: Integrate Droid CLI Tool for Agentic Plan Development

## Objectives
- Extend `lw_coder plan` command to run Factory AI's droid CLI tool in interactive mode as an agentic assistant for plan refinement and creation
- Create Docker environment for isolated droid execution with proper mounting of worktrees, custom droids, and output directories
- Support multiple input modes for initial ideas: markdown files (ignoring existing front matter), inline text via `--text` flag, with Linear integration marked as future work
- Implement `--tool` parameter to specify which coding CLI to use (default: droid), enabling future support for other tools like Goose
- Add custom droid subagent (maintainability-reviewer) that evaluates plans from a long-term maintenance perspective
- User interacts with droid in terminal to refine the idea through Q&A, then droid generates final plan file to `.lw_coder/tasks/` with proper YAML front matter

## Requirements & Constraints
- Plans remain Markdown files; droid generates complete YAML front matter (plan_id, git_sha, status, evaluation_notes)
- The `plan` command provides droid read-only worktree access for code examination but requires isolation for any edits droid makes
- Create detached HEAD worktrees at `.lw_coder/worktrees/temp-<timestamp>` for plan command; remove worktree entirely after completion
- Docker containers run interactively (`docker run -it`) with `droid "<initial_prompt>"` to start conversation with context
- User interacts with droid, asks/answers questions, reviews plan before droid saves it
- User exits droid (via `exit` or Ctrl+C) when finished, which closes container and triggers cleanup
- User must authenticate by running `droid` once manually (login via browser), which creates `~/.factory/auth.json`
- Workflow prompt templates stored in `src/lw_coder/prompts/<tool>/` as part of lw_coder codebase (not per-project)
- Custom subagents stored in `src/lw_coder/droids/` and mounted to `/root/.factory/droids/` in container
- The `code` command remains unchanged for this task (out of scope)
- Linear integration marked as out of scope; implement `--text` and file-based idea inputs only

## Work Items
1. **Directory Structure**
   - Create `src/lw_coder/prompts/droid/` for droid-specific workflow templates
   - Create `src/lw_coder/droids/` for custom droid subagent definitions
   - These directories are part of the lw_coder installation, not per-project configuration
   - Future tools (e.g., goose) would add `src/lw_coder/prompts/goose/` and similar

2. **Docker Environment Setup**
   - Create Dockerfile that installs droid CLI:
     ```dockerfile
     FROM node:20-alpine
     RUN apk add --no-cache curl bash git
     RUN curl -fsSL https://app.factory.ai/cli | sh
     WORKDIR /workspace
     CMD ["/bin/bash"]
     ```
   - Build Docker command template:
     ```bash
     docker run -it --rm \
       -v <temp_worktree_path>:/workspace \
       -v <repo_root>/.lw_coder/tasks:/output \
       -v <lw_coder_src>/droids:/home/droiduser/.factory/droids:ro \
       -v ~/.factory/auth.json:/home/droiduser/.factory/auth.json:ro \
       -v <lw_coder_src>/container_settings.json:/home/droiduser/.factory/settings.json:ro \
       -v <prompt_file>:/tmp/prompt.txt:ro \
       -w /workspace \
       lw_coder_droid:latest \
       bash -c "droid \"$(cat /tmp/prompt.txt)\""
     ```
   - User must login to droid first (run `droid` once outside Docker), which stores authentication in `~/.factory/auth.json`
   - Mount user's `auth.json` and lw_coder's `container_settings.json` (with autonomyLevel: "high" and enableCustomDroids: true) for interactive mode with high autonomy
   - Mount the prompt file and pass it to droid command to start interactive session with initial context
   - The `/workspace` directory contains the temporary worktree for code examination
   - The `/output` directory is where droid writes the final plan file to `.lw_coder/tasks/<plan_id>.md`
   - Custom lw_coder droids mounted to `/root/.factory/droids/` for subagent access
   - Sessions and logs are ephemeral within the container (discarded on exit)

3. **Prompt and Subagent Structure**
   - Create `src/lw_coder/prompts/droid/plan.md` workflow template (plain markdown, no frontmatter):
     ```markdown
     Here is an initial idea for a plan that needs to be refined and formalized:

     {IDEA_TEXT}

     Your task:
     1. Examine the codebase in /workspace to understand implementation context
     2. Use the maintainability-reviewer subagent to evaluate long-term maintenance concerns
     3. Ask me clarifying questions ONE AT A TIME until you fully understand the requirements
     4. Generate a complete plan file and save it to /output/<plan_id>.md with this structure:
        - YAML front matter with: plan_id (unique, 3-100 chars, alphanumeric/._- only), git_sha (run `git rev-parse HEAD` to get current commit), status (use "draft"), evaluation_notes (list of questions for evaluation)
        - Markdown body with: Objectives, Requirements & Constraints, Work Items, Deliverables, Out of Scope sections

     When you're ready to write the final plan, let me know and we'll review it together before you save it.
     ```
   - The `{IDEA_TEXT}` placeholder is replaced by lw_coder before passing to droid
   - Create `src/lw_coder/droids/maintainability-reviewer.md` custom subagent:
     ```yaml
     ---
     name: maintainability-reviewer
     description: Evaluates plans and code from a long-term maintenance perspective, identifying technical debt and sustainability concerns
     model: gpt-5-codex
     tools: read-only
     ---

     You are a senior engineering maintainer focused on long-term code health. When reviewing plans or code:
     1. Assess cognitive complexity - will future developers easily understand this?
     2. Identify potential technical debt and suggest mitigation strategies
     3. Evaluate testability - are the proposed changes easy to test and verify?
     4. Consider evolution - how will this code age as requirements change?
     5. Review documentation needs - what context will future maintainers require?
     6. Analyze dependencies - are we introducing hard-to-maintain external dependencies?
     7. Check for common anti-patterns that lead to maintenance burden
     8. Suggest architectural improvements that reduce long-term maintenance cost

     Your goal: ensure code remains maintainable, readable, and adaptable for years to come.
     ```

4. **Temporary Worktree Management**
   - Add utility function to create detached HEAD worktrees: `git worktree add --detach .lw_coder/worktrees/temp-<timestamp> HEAD`
   - Implement cleanup logic to completely remove temporary worktree after droid exits: `git worktree remove <path>`
   - Ensure proper cleanup even if droid fails or user interrupts
   - Handle edge cases: existing temp directories, git errors, locked worktrees

5. **CLI Command Extension**
   - Update docopt usage string to support:
     - `lw_coder plan <plan_path>` - read idea from markdown file (ignore any existing YAML frontmatter)
     - `lw_coder plan --text <description>` - inline idea text
     - `lw_coder plan [options] --tool <tool_name>` - specify tool (default: "droid")
   - Implement plan command flow:
     1. **Pre-flight check**: Verify `~/.factory/auth.json` exists and contains `access_token` and `refresh_token` keys
        - If missing, print clear error: "Droid authentication required. Please run 'droid' once to login via browser."
        - Exit with error code if authentication not found
     2. Parse input: extract idea text from file or --text argument
     3. Load prompt template from `src/lw_coder/prompts/<tool>/plan.md`
     4. Combine: replace `{IDEA_TEXT}` placeholder in template with extracted idea
     5. Create temporary detached HEAD worktree: `git worktree add --detach .lw_coder/worktrees/temp-<timestamp> HEAD`
     6. Build/run Docker container with droid in interactive mode:
        ```bash
        docker run -it --rm \
          -v "$temp_worktree_path:/workspace" \
          -v "$repo_root/.lw_coder/tasks:/output" \
          -v "$lw_coder_src/droids:/home/droiduser/.factory/droids:ro" \
          -v ~/.factory/auth.json:/home/droiduser/.factory/auth.json:ro \
          -v "$lw_coder_src/container_settings.json:/home/droiduser/.factory/settings.json:ro" \
          -v "$prompt_file:/tmp/prompt.txt:ro" \
          -w /workspace \
          lw_coder_droid:latest \
          bash -c "droid \"$(cat /tmp/prompt.txt)\""
        ```
        - Note: Interactive mode uses container_settings.json with autonomyLevel: "high" and enableCustomDroids: true, allowing droid to run commands without manual approval and use custom subagents like maintainability-reviewer
        - The prompt is passed via command line to start the interactive session with initial context
     8. Wait for user to exit droid (user types `exit` or Ctrl+C), which closes container
     9. Remove temporary worktree: `git worktree remove <path>` (with `--force` if needed)
   - Handle errors and interruptions gracefully with try/finally to ensure worktree cleanup
   - Log to user where the plan should appear (`.lw_coder/tasks/<plan_id>.md`) and remind them to exit droid when done

6. **Testing**
   - Unit tests for authentication pre-flight check:
     - Test failure when `~/.factory/auth.json` is missing
     - Test failure when `auth.json` exists but lacks required keys
     - Test success when valid authentication is present
   - Unit tests for temporary worktree creation and complete removal
   - Unit tests for template loading and placeholder replacement ({IDEA_TEXT}, {GIT_SHA})
   - Test cleanup happens even on failures and interruptions
   - Docker image build test (verify Dockerfile builds successfully)
   - Integration smoke test (requires Docker and droid authentication):
     - Pass simple prompt to droid exec in non-interactive mode
     - Use /tmp/lw_coder_test_<random> for output isolation
     - Verify output file appears in expected location
     - Clean up /tmp test directories after execution
     - Requires Docker installed and `~/.factory/auth.json` present
   - Manual verification for full interactive workflow:
     - Run plan command with real user interaction
     - Verify custom droids accessible in container
     - Ensure worktree isolation works correctly
     - Test that user can interact with droid and command waits for container exit

## Deliverables
- Dockerfile for droid CLI execution environment at `docker/droid/Dockerfile`
- Prompt template in `src/lw_coder/prompts/droid/plan.md`
- Maintainability-reviewer subagent in `src/lw_coder/droids/maintainability-reviewer.md`
- Container settings file in `src/lw_coder/container_settings.json` (autonomyLevel: "high", enableCustomDroids: true)
- Extended CLI with `--text` and `--tool` parameters
- Authentication pre-flight check utilities
- Temporary worktree management utilities
- Docker execution wrapper with interactive terminal support
- Comprehensive test coverage
- Documentation in README or setup guide explaining droid authentication requirement (one-time login via browser)

## Out of Scope
- Modifications to `lw_coder code` command (future task)
- Linear issue integration (`--linear` flag)
- Plan validation and automatic retry logic if droid generates invalid plans (future enhancement)
- Support for other coding CLI tools beyond droid (infrastructure ready, implementations future)
- Automatic branch creation during plan command (deferred to code command)
- Remote repository interactions (fetch, push)
- Pruning/cleanup of orphaned worktrees from previous runs (manual git worktree prune if needed)
- Web-based UI for droid interaction
- Multi-tool orchestration (running multiple coding CLIs in sequence)
