"""Implementation of the code command for plan validation and worktree preparation.

This module provides the core business logic for the `lw_coder code` command,
separating it from CLI argument parsing and dispatch.

Now runs directly on the host environment instead of in Docker containers.
"""

from __future__ import annotations

import fnmatch
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from claude_agent_sdk import AgentDefinition

from .executors import ExecutorRegistry, ExecutorError
from .hooks import trigger_hook
from .host_runner import build_host_command, get_lw_coder_src_dir, host_runner_config
from .logging_config import get_logger
from .sdk_runner import SDKRunnerError, run_sdk_session_sync
from .param_validation import get_effective_model
from .plan_lifecycle import (
    PlanLifecycleError,
    get_current_head_sha,
    update_plan_fields,
)
from .plan_validator import (
    PLACEHOLDER_SHA,
    PlanValidationError,
    extract_front_matter,
    load_plan_metadata,
)
from .repo_utils import RepoUtilsError, find_repo_root
from .prompt_loader import PromptLoadingError, load_prompts
from .run_manager import (
    RunManagerError,
    copy_coding_droids,
    create_run_directory,
    prune_old_runs,
)
from .trace_capture import TraceCaptureError, capture_session_trace
from .worktree_utils import WorktreeError, ensure_worktree
from .cache_sync import (
    check_rsync_available,
    get_global_cache_dir,
    get_worktree_cache_dir,
    sync_cache_from_worktree,
    sync_cache_to_worktree,
)

logger = get_logger(__name__)

# Agent descriptions - single source of truth for both filesystem and programmatic agents
AGENT_DESCRIPTIONS = {
    "code-review-auditor": "Reviews code changes for quality and compliance",
    "plan-alignment-checker": "Verifies implementation aligns with the original plan",
}


def _filter_env_vars(patterns: list[str]) -> dict[str, str]:
    """Filter environment variables based on patterns.

    Args:
        patterns: List of patterns (supports wildcards and "*" for all)

    Returns:
        Dictionary of matching environment variables
    """
    if "*" in patterns:
        # Forward all environment variables
        return dict(os.environ)

    filtered = {}
    for pattern in patterns:
        for key, value in os.environ.items():
            if fnmatch.fnmatch(key, pattern):
                filtered[key] = value

    return filtered


def _write_sub_agents(
    prompts: dict[str, str], worktree_path: Path, model: str
) -> None:
    """Write sub-agent files to .claude/agents/ directory.

    Tool inheritance: The 'tools:' field is intentionally omitted from the YAML
    front matter to enable subagents to inherit tool access from the parent
    Claude Code agent. Including 'tools: ["*"]' actually prevents tool access.

    Args:
        prompts: Dictionary containing sub-agent prompts.
        worktree_path: Path to the worktree directory.
        model: Model variant being used.

    Raises:
        IOError: If writing files fails.
    """
    agents_dir = worktree_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    # Write code-review-auditor agent
    # Note: 'tools:' field is omitted to enable tool inheritance from parent Claude Code agent
    code_review_agent = agents_dir / "code-review-auditor.md"
    code_review_frontmatter = f"""---
name: code-review-auditor
description: {AGENT_DESCRIPTIONS["code-review-auditor"]}
model: {model}
---

{prompts['code_review_auditor']}
"""
    code_review_agent.write_text(code_review_frontmatter, encoding="utf-8")
    logger.debug("Wrote code-review-auditor agent to %s", code_review_agent)

    # Write plan-alignment-checker agent
    # Note: 'tools:' field is omitted to enable tool inheritance from parent Claude Code agent
    plan_alignment_agent = agents_dir / "plan-alignment-checker.md"
    plan_alignment_frontmatter = f"""---
name: plan-alignment-checker
description: {AGENT_DESCRIPTIONS["plan-alignment-checker"]}
model: {model}
---

{prompts['plan_alignment_checker']}
"""
    plan_alignment_agent.write_text(plan_alignment_frontmatter, encoding="utf-8")
    logger.debug("Wrote plan-alignment-checker agent to %s", plan_alignment_agent)


def _build_agent_definitions(
    prompts: dict[str, str], model: str
) -> dict[str, AgentDefinition]:
    """Build programmatic agent definitions from prompts dictionary.

    Creates AgentDefinition objects for SDK execution. These are built from
    the same prompts used for filesystem agents, ensuring synchronization.

    NOTE: Agents are registered in two ways due to SDK limitation:
    1. Filesystem (.claude/agents/*.md) - for CLI resume sessions
    2. Programmatic (agents parameter) - for SDK execution
    Both are built from the same prompts source to ensure synchronization.
    The SDK does not discover filesystem agents in .claude/agents/ directories.

    Args:
        prompts: Dictionary containing agent prompts.
        model: Model variant being used.

    Returns:
        Dictionary mapping agent names to AgentDefinition objects.
    """
    agents = {
        "code-review-auditor": AgentDefinition(
            description=AGENT_DESCRIPTIONS["code-review-auditor"],
            prompt=prompts["code_review_auditor"],
            model=model,
        ),
        "plan-alignment-checker": AgentDefinition(
            description=AGENT_DESCRIPTIONS["plan-alignment-checker"],
            prompt=prompts["plan_alignment_checker"],
            model=model,
        ),
    }
    return agents


def run_code_command(
    plan_path: Path | str,
    tool: str = "claude-code",
    model: str | None = None,
    no_hooks: bool = False,
) -> int:
    """Execute the code command: end-to-end coding workflow.

    This function orchestrates:
    1. Plan validation
    2. Configuration loading
    3. Prompt loading from disk
    4. Worktree preparation
    5. Sub-agent file writing
    6. Claude Code CLI or Droid execution

    Args:
        plan_path: Path to the plan file (string or Path object).
        tool: Coding tool to use (default: "claude-code"). Valid: "claude-code", "droid".
        model: Model variant to use. Valid: "sonnet", "opus", "haiku" for claude-code.
               Defaults to "sonnet" for claude-code. Not used for droid.
        no_hooks: If True, disable execution of configured hooks.

    Returns:
        Exit code: 0 for success, 1 for failure.
    """
    if no_hooks:
        logger.info("Hooks disabled via --no-hooks flag")
    # Resolve plan path
    if isinstance(plan_path, str):
        plan_path = Path(plan_path)

    # Get effective model using 3-tier precedence: CLI flag > config.toml > hardcoded default
    # For droid tool, always use None (droid doesn't support model selection)
    if tool == "droid":
        effective_model = None
    else:
        effective_model = get_effective_model(model, "code")

    head_sha: str | None = None
    front_matter: dict[str, object] | None = None

    try:
        repo_root = find_repo_root(plan_path)
    except RepoUtilsError:
        repo_root = None

    if repo_root is not None:
        try:
            head_sha = get_current_head_sha(repo_root)
        except PlanLifecycleError as exc:
            logger.error("Failed to resolve repository HEAD: %s", exc)
            return 1

    if plan_path.exists():
        try:
            content = plan_path.read_text(encoding="utf-8")
            fm, _ = extract_front_matter(content)
            if isinstance(fm, dict):
                front_matter = fm
        except (OSError, PlanValidationError):
            front_matter = None

    plan_updated = False
    original_fields: dict[str, str] = {}

    if front_matter and head_sha:
        existing_git_sha = front_matter.get("git_sha")
        normalized_git_sha = (
            existing_git_sha.strip().lower()
            if isinstance(existing_git_sha, str)
            else None
        )

        if isinstance(existing_git_sha, str):
            original_fields["git_sha"] = existing_git_sha
        status_field = front_matter.get("status")
        if isinstance(status_field, str):
            original_fields["status"] = status_field

        if (
            normalized_git_sha
            and normalized_git_sha != PLACEHOLDER_SHA
            and normalized_git_sha != head_sha
        ):
            logger.error(
                "Plan git_sha %s does not match repository HEAD %s. "
                "Please ensure the plan is in sync with the latest commit before running code. "
                "Check for uncommitted changes or regenerate the plan after rebasing.",
                normalized_git_sha,
                head_sha,
            )
            return 1

        try:
            update_plan_fields(plan_path, {"git_sha": head_sha, "status": "coding"})
            plan_updated = True
        except PlanLifecycleError as exc:
            logger.error("Failed to update plan metadata before coding session: %s", exc)
            return 1
    elif head_sha and not plan_path.exists():
        logger.error("Plan file not found: %s", plan_path)
        return 1

    # Load and validate plan metadata
    try:
        metadata = load_plan_metadata(plan_path)
    except PlanValidationError as exc:
        if plan_updated and original_fields:
            try:
                update_plan_fields(plan_path, original_fields)
            except PlanLifecycleError as rollback_exc:
                logger.warning(
                    "Failed to restore plan metadata after validation error: %s",
                    rollback_exc,
                )
        logger.error("Plan validation failed: %s", exc)
        return 1

    logger.info("Plan validation succeeded for %s", metadata.plan_path)

    # Use sensible defaults for environment configuration
    forward_env_patterns: list[str] = ["OPENROUTER_*"]

    # Create run directory
    try:
        run_dir = create_run_directory(metadata.repo_root, metadata.plan_id)
    except RunManagerError as exc:
        logger.error("Failed to create run directory: %s", exc)
        return 1

    # Copy coding droids to run directory (for backward compatibility)
    try:
        droids_dir = copy_coding_droids(run_dir)
    except RunManagerError as exc:
        logger.error("Failed to copy coding droids: %s", exc)
        return 1

    # Load optimized prompts from disk (project-relative) if using Claude Code
    prompts = None
    if tool == "claude-code":
        try:
            logger.info("Loading optimized prompts for Claude Code CLI (%s model)...", effective_model)
            prompts = load_prompts(
                repo_root=metadata.repo_root,
                tool="claude-code-cli",
                model=effective_model,
            )
            logger.info("Prompts loaded successfully from %s/.lw_coder/optimized_prompts/", metadata.repo_root)
        except PromptLoadingError as exc:
            logger.error("Prompt loading failed: %s", exc)
            return 1

    # Prune old run directories (non-fatal if it fails)
    try:
        prune_old_runs(metadata.repo_root, active_run_dir=run_dir)
    except RunManagerError as exc:
        logger.warning("Failed to prune old run directories: %s", exc)

    # Prepare worktree
    try:
        worktree_path = ensure_worktree(metadata)
        logger.info("Worktree prepared at: %s", worktree_path)
    except WorktreeError as exc:
        logger.error("Worktree preparation failed: %s", exc)
        return 1

    # Write sub-agents to .claude/agents/ directory if using Claude Code
    if tool == "claude-code" and prompts:
        try:
            _write_sub_agents(prompts, worktree_path, effective_model)
            logger.info("Sub-agents written to %s/.claude/agents/", worktree_path)
        except (IOError, OSError) as exc:
            logger.error("Failed to write sub-agents: %s", exc)
            return 1

    # Copy plan file to worktree root
    plan_md_path = worktree_path / "plan.md"
    try:
        shutil.copy2(plan_path, plan_md_path)
        logger.debug("Copied plan to %s", plan_md_path)
    except (OSError, IOError) as exc:
        logger.error("Failed to copy plan to worktree: %s", exc)
        return 1

    # Filter environment variables to forward
    env_vars = _filter_env_vars(forward_env_patterns)
    if env_vars:
        logger.debug("Forwarding %d environment variable(s) to executor", len(env_vars))

    # Log configuration
    logger.info("Using tool: %s", tool)
    if effective_model:
        logger.info("Using model: %s", effective_model)
    logger.info("Run artifacts available at: %s", run_dir)
    logger.info("  Coding droids: %s", droids_dir)
    if tool == "claude-code":
        logger.info("  Sub-agents: %s/.claude/agents/", worktree_path)

    # Use executors pattern to build command
    try:
        executor = ExecutorRegistry.get_executor(tool)
        executor.check_auth()
    except ExecutorError as exc:
        logger.error("Executor error: %s", exc)
        return 1

    # Create main prompt file in run directory for reference
    if tool == "claude-code" and prompts:
        main_prompt_path = run_dir / "prompts" / "main.md"
        main_prompt_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            main_prompt_path.write_text(prompts["main_prompt"], encoding="utf-8")
            logger.debug("Wrote main prompt to %s", main_prompt_path)
        except (OSError, IOError) as exc:
            logger.warning("Failed to write main prompt to run directory: %s", exc)
    elif tool == "droid":
        # For droid, we need to create a simple prompt file
        main_prompt_path = run_dir / "prompts" / "droid_prompt.md"
        main_prompt_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Load the droid prompt from template
            src_dir = get_lw_coder_src_dir()
            droid_prompt_template = src_dir / "prompts" / "droid" / "code.md"
            if droid_prompt_template.exists():
                droid_prompt = droid_prompt_template.read_text(encoding="utf-8")
                main_prompt_path.write_text(droid_prompt, encoding="utf-8")
                logger.debug("Wrote droid prompt to %s", main_prompt_path)
            else:
                # Fallback to a basic prompt if template doesn't exist
                main_prompt_path.write_text(
                    "Implement the plan in plan.md\n",
                    encoding="utf-8"
                )
                logger.warning("Droid prompt template not found, using basic prompt")
        except (OSError, IOError) as exc:
            logger.warning("Failed to write droid prompt to run directory: %s", exc)

    # Sync cache to worktree before execution
    global_cache = get_global_cache_dir()
    worktree_cache = get_worktree_cache_dir(worktree_path)

    rsync_available = check_rsync_available()
    if not rsync_available:
        logger.warning(
            "rsync is not available. DSPy cache sync disabled. "
            "Install rsync to enable cache synchronization between worktrees."
        )
    else:
        logger.debug("Syncing DSPy cache to worktree...")
        sync_cache_to_worktree(global_cache, worktree_cache)

    # Capture execution start time for trace capture
    execution_start = time.time()

    # Session ID for SDK-based execution (claude-code only)
    session_id: str | None = None

    # For claude-code: Run SDK session first, then resume with CLI
    if tool == "claude-code" and prompts:
        src_dir = get_lw_coder_src_dir()
        sdk_settings_path = src_dir / "sdk_settings.json"

        if not sdk_settings_path.exists():
            logger.error(
                "SDK settings file not found at %s. Ensure the package is properly installed.",
                sdk_settings_path,
            )
            return 1

        logger.info("Running initial SDK session...")

        # Build agent definitions for SDK execution
        # NOTE: Agents are registered in two ways due to SDK limitation:
        # 1. Filesystem (.claude/agents/*.md) - for CLI resume sessions
        # 2. Programmatic (agents parameter) - for SDK execution
        # Both are built from the same prompts source to ensure synchronization.
        agents = _build_agent_definitions(prompts, effective_model)

        try:
            session_id = run_sdk_session_sync(
                worktree_path=worktree_path,
                prompt_content=prompts["main_prompt"],
                model=effective_model,
                sdk_settings_path=sdk_settings_path,
                agents=agents,
            )
            logger.info("SDK session completed. Session ID: %s", session_id)
        except SDKRunnerError as exc:
            logger.error("SDK session failed: %s", exc)
            return 1

        # Trigger code_sdk_complete hook after SDK session completes
        if not no_hooks:
            trigger_hook(
                "code_sdk_complete",
                {
                    "worktree_path": worktree_path,
                    "plan_path": plan_path,
                    "plan_id": metadata.plan_id,
                    "repo_root": metadata.repo_root,
                },
            )

        # Build CLI resume command: claude -r <session_id> --model <model>
        command = f"claude -r {shlex.quote(session_id)} --model {shlex.quote(effective_model)}"
        logger.info("Resuming with CLI session...")
    else:
        # For droid or other tools: use executor pattern directly
        command = executor.build_command(main_prompt_path, effective_model)

    # Use auth file from home directory
    auth_file = Path.home() / ".factory" / "auth.json"

    # Launch host-based session
    executor_env = executor.get_env_vars(Path.home() / ".factory")
    runner_config = host_runner_config(
        worktree_path=worktree_path,
        repo_git_dir=metadata.repo_root / ".git",
        tasks_dir=metadata.repo_root / ".lw_coder" / "tasks",
        droids_dir=droids_dir,
        auth_file=auth_file,
        command=command,
        host_factory_dir=Path.home() / ".factory",
        env_vars=env_vars,
    )

    # Build host command
    host_cmd, host_env = build_host_command(runner_config)
    logger.info("Launching %s session on host...", tool)
    logger.debug("Host command: %s", " ".join(host_cmd))

    try:
        # Run interactively, streaming output to user
        result = subprocess.run(
            host_cmd,
            check=False,  # Don't raise on non-zero exit
            env=host_env,
            cwd=worktree_path,
        )

        # Capture execution end time for trace capture
        execution_end = time.time()

        if result.returncode == 0:
            try:
                update_plan_fields(plan_path, {"status": "implemented"})
            except PlanLifecycleError as exc:
                logger.warning(
                    "Failed to update plan status to 'implemented' after successful session: %s",
                    exc,
                )

        # Capture conversation trace (non-fatal if it fails)
        if tool == "claude-code":
            try:
                trace_file = capture_session_trace(
                    worktree_path=worktree_path,
                    command="code",
                    run_dir=run_dir,
                    execution_start=execution_start,
                    execution_end=execution_end,
                    session_id=session_id,
                )
                if trace_file:
                    logger.debug("Trace captured at: %s", trace_file)
            except TraceCaptureError as exc:
                logger.warning("Warning: Trace capture failed")
                logger.debug("Trace capture error details: %s", exc)

        if result.returncode != 0:
            logger.warning("%s session exited with code %d", tool, result.returncode)
        else:
            logger.info("%s session completed successfully", tool)

        # Log follow-up information
        logger.info(
            "\nSession complete. Worktree remains at: %s\n"
            "To resume, cd to the worktree and continue working.\n"
            "Run artifacts saved to: %s",
            worktree_path,
            run_dir,
        )

        # Return the session's exit code
        return result.returncode

    except KeyboardInterrupt:
        execution_end = time.time()
        logger.info("%s session interrupted by user", tool)

        # Capture conversation trace even for interrupted sessions (non-fatal if it fails)
        if tool == "claude-code":
            try:
                trace_file = capture_session_trace(
                    worktree_path=worktree_path,
                    command="code",
                    run_dir=run_dir,
                    execution_start=execution_start,
                    execution_end=execution_end,
                    session_id=session_id,
                )
                if trace_file:
                    logger.debug("Trace captured at: %s", trace_file)
            except TraceCaptureError as exc:
                logger.warning("Warning: Trace capture failed")
                logger.debug("Trace capture error details: %s", exc)

        return 130  # Standard exit code for SIGINT
    except Exception as exc:
        execution_end = time.time()
        logger.error("Failed to run %s session: %s", tool, exc)
        return 1
    finally:
        # Sync cache from worktree back to global (even on failure/interruption)
        if rsync_available:
            logger.debug("Syncing DSPy cache from worktree back to global...")
            sync_cache_from_worktree(worktree_cache, global_cache)

        # Clean up plan.md from worktree, even on failure or interruption
        try:
            if plan_md_path.exists():
                plan_md_path.unlink()
                logger.debug("Cleaned up plan.md from worktree")
        except (OSError, IOError) as exc:
            logger.warning("Failed to clean up plan.md from worktree: %s", exc)

        # Clean up .claude/agents/ directory from worktree if using Claude Code
        if tool == "claude-code":
            try:
                agents_dir = worktree_path / ".claude" / "agents"
                if agents_dir.exists():
                    # Remove the agent files we created
                    for agent_file in ["code-review-auditor.md", "plan-alignment-checker.md"]:
                        agent_path = agents_dir / agent_file
                        if agent_path.exists():
                            agent_path.unlink()

                    # Try to remove empty directories
                    try:
                        agents_dir.rmdir()  # Remove .claude/agents if empty
                        logger.debug("Removed empty .claude/agents/ directory")
                    except OSError:
                        # Directory not empty, which is fine - user may have other files
                        pass

                    # Try to remove .claude directory if empty
                    try:
                        (worktree_path / ".claude").rmdir()
                        logger.debug("Removed empty .claude/ directory")
                    except OSError:
                        # Directory not empty, which is fine
                        pass

                logger.debug("Cleaned up agents from worktree")
            except (OSError, IOError) as exc:
                logger.warning("Failed to clean up agents from worktree: %s", exc)
