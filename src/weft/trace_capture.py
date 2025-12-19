"""Trace capture for Claude Code conversation sessions.

This module captures conversation traces from weft plan and code sessions,
converting Claude Code's internal JSONL conversation format into clean markdown
files for DSPy prompt improvement analysis.

WARNING: This module relies on undocumented Claude Code internals (~/.claude/projects/).
See docs/adr/001-trace-capture-claude-dependency.md for details.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Optional, List

from .logging_config import get_logger

logger = get_logger(__name__)

# Retention period for trace directories (30 days)
TRACE_RETENTION_DAYS = 30


class TraceCaptureError(Exception):
    """Raised when trace capture operations fail."""
    pass


def find_project_folder(worktree_path: Path, execution_window: Tuple[float, float]) -> Optional[Path]:
    """Find the Claude Code project folder matching the worktree path.

    Searches ~/.claude/projects/ for folders containing JSONL files modified
    within the execution window. Uses filesystem modification time to find
    the matching session.

    Args:
        worktree_path: Path to the worktree directory
        execution_window: Tuple of (start_time, end_time) in seconds since epoch

    Returns:
        Path to the matching project folder, or None if not found
    """
    claude_projects = Path.home() / ".claude" / "projects"

    if not claude_projects.exists():
        logger.debug("Claude projects directory not found: %s", claude_projects)
        return None

    start_time, end_time = execution_window
    logger.debug("Searching for project folder with files modified between %s and %s",
                 datetime.fromtimestamp(start_time), datetime.fromtimestamp(end_time))

    # Convert worktree path to expected folder name format
    # Claude Code strips leading /, then replaces /, ., _ with -, then prefixes with -
    # Example: /home/user/weft/.weft/worktrees/foo -> -home-user-weft--weft-worktrees-foo
    worktree_str = str(worktree_path.resolve())
    expected_folder_name = "-" + worktree_str.lstrip("/").replace("/", "-").replace(".", "-").replace("_", "-")

    logger.debug("DEBUG: Worktree path: %s", worktree_str)
    logger.debug("DEBUG: Expected folder name: %s", expected_folder_name)

    # List all available folders for debugging
    available_folders = [f.name for f in claude_projects.iterdir() if f.is_dir()]
    logger.debug("DEBUG: Available project folders (%d): %s", len(available_folders), available_folders)

    # Try exact match first
    expected_folder = claude_projects / expected_folder_name
    logger.debug("DEBUG: Checking for exact match at: %s", expected_folder)
    if expected_folder.exists() and expected_folder.is_dir():
        # Check if it has any JSONL files (don't check timestamps for exact match)
        # The JSONL files continue to be modified after creation, so mtime is unreliable
        jsonl_files = list(expected_folder.glob("*.jsonl"))
        logger.debug("DEBUG: Found %d JSONL files in exact match folder", len(jsonl_files))
        if jsonl_files:
            logger.debug("Found matching project folder (exact match): %s", expected_folder)
            return expected_folder

    # Fall back to searching all folders
    logger.debug("DEBUG: Exact match failed, trying time-based search")
    for folder in claude_projects.iterdir():
        if not folder.is_dir():
            continue

        # Check for JSONL files modified within execution window
        jsonl_files_in_folder = list(folder.glob("*.jsonl"))
        logger.debug("DEBUG: Checking folder %s (%d JSONL files)", folder.name, len(jsonl_files_in_folder))

        for jsonl_file in jsonl_files_in_folder:
            try:
                mtime = jsonl_file.stat().st_mtime
                mtime_str = datetime.fromtimestamp(mtime).isoformat()
                logger.debug("DEBUG: File %s has mtime %s", jsonl_file.name, mtime_str)
                if start_time <= mtime <= end_time:
                    logger.debug("Found matching project folder (time-based): %s", folder)
                    return folder
            except OSError as e:
                logger.debug("DEBUG: Failed to stat file %s: %s", jsonl_file, e)
                continue

    logger.debug("No matching project folder found")
    return None


def collect_jsonl_files(project_folder: Path) -> List[Path]:
    """Collect all JSONL files from the project folder.

    Args:
        project_folder: Path to the Claude Code project folder

    Returns:
        List of JSONL file paths, sorted by modification time
    """
    jsonl_files = list(project_folder.rglob("*.jsonl"))
    jsonl_files.sort(key=lambda f: f.stat().st_mtime)
    logger.debug("Found %d JSONL file(s) in %s", len(jsonl_files), project_folder)
    return jsonl_files


def match_session_files(jsonl_files: List[Path], worktree_path: Path) -> Optional[str]:
    """Match JSONL files to the worktree path and extract session ID.

    Reads the first line of each JSONL file to check if the cwd field
    matches the worktree path.

    Args:
        jsonl_files: List of JSONL file paths to check
        worktree_path: Path to the worktree directory

    Returns:
        Session ID if a match is found, None otherwise
    """
    worktree_str = str(worktree_path.resolve())
    logger.debug("DEBUG: Matching session for worktree: %s", worktree_str)

    for jsonl_file in jsonl_files:
        logger.debug("DEBUG: Checking JSONL file: %s", jsonl_file)
        try:
            with jsonl_file.open("r", encoding="utf-8") as f:
                first_line = f.readline()
                if not first_line:
                    logger.debug("DEBUG: First line is empty")
                    continue

                data = json.loads(first_line)
                cwd = data.get("cwd", "")
                session_id = data.get("sessionId", "")

                logger.debug("DEBUG: JSONL cwd: %s", cwd)
                logger.debug("DEBUG: JSONL sessionId: %s", session_id)
                logger.debug("DEBUG: Match? cwd == worktree_str: %s", cwd == worktree_str)

                if cwd == worktree_str and session_id:
                    logger.debug("Matched session %s in file %s", session_id, jsonl_file)
                    return session_id
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read JSONL file %s: %s", jsonl_file, e)
            continue

    logger.debug("No session match found for worktree %s", worktree_path)
    return None


def parse_jsonl_file(file_path: Path) -> List[dict]:
    """Parse a JSONL file into a list of message objects.

    Args:
        file_path: Path to the JSONL file

    Returns:
        List of message dictionaries
    """
    messages = []

    try:
        with file_path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    message = json.loads(line)
                    messages.append(message)
                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON on line %d of %s: %s", line_num, file_path, e)
                    continue
    except OSError as e:
        raise TraceCaptureError(f"Failed to read JSONL file {file_path}: {e}") from e

    logger.debug("Parsed %d message(s) from %s", len(messages), file_path)
    return messages


def filter_and_clean_messages(messages: List[dict]) -> dict[str, List[dict]]:
    """Filter out file history snapshots and group messages by agent.

    Args:
        messages: List of raw message dictionaries

    Returns:
        Dictionary mapping agent ID to list of messages (main conversation uses "main" key)
    """
    grouped = {"main": []}

    for message in messages:
        msg_type = message.get("type", "")

        # Remove file history snapshots
        if msg_type == "file-history-snapshot":
            continue

        # Group by agent ID
        agent_id = message.get("agentId", "")
        is_sidechain = message.get("isSidechain", False)

        if is_sidechain and agent_id:
            # Subagent message
            if agent_id not in grouped:
                grouped[agent_id] = []
            grouped[agent_id].append(message)
        else:
            # Main conversation message
            grouped["main"].append(message)

    logger.debug("Grouped messages: %d main, %d subagent(s)",
                 len(grouped["main"]), len(grouped) - 1)
    return grouped


def truncate_content(content: str, max_chars: int = 200) -> str:
    """Truncate content if it exceeds max_chars.

    Format: [first 50 chars][... N chars truncated ...][last 150 chars]

    Args:
        content: Content string to truncate
        max_chars: Maximum character limit (default: 200)

    Returns:
        Original or truncated content
    """
    if len(content) <= max_chars:
        return content

    truncated_count = len(content) - 200
    return f"{content[:50]}[... {truncated_count} chars truncated ...]{content[-150:]}"


def clean_tool_results(messages: List[dict]) -> List[dict]:
    """Truncate large tool result content.

    Args:
        messages: List of message dictionaries

    Returns:
        List of messages with truncated tool results
    """
    cleaned = []

    for message in messages:
        message_copy = message.copy()

        if message.get("type") == "user":
            msg_content = message.get("message", {}).get("content", [])

            if isinstance(msg_content, list):
                cleaned_content = []
                for item in msg_content:
                    item_copy = item.copy() if isinstance(item, dict) else item

                    if isinstance(item_copy, dict) and item_copy.get("type") == "tool_result":
                        content_str = item_copy.get("content", "")
                        if isinstance(content_str, str) and len(content_str) > 200:
                            item_copy["content"] = truncate_content(content_str)

                    cleaned_content.append(item_copy)

                # Update the message copy with cleaned content
                if "message" not in message_copy:
                    message_copy["message"] = {}
                message_copy["message"]["content"] = cleaned_content

        cleaned.append(message_copy)

    return cleaned


def generate_markdown(grouped_messages: dict[str, List[dict]], session_metadata: dict) -> str:
    """Generate markdown representation of the conversation.

    Args:
        grouped_messages: Dictionary mapping agent ID to messages
        session_metadata: Metadata about the session (session_id, command, timestamp, etc.)

    Returns:
        Formatted markdown string
    """
    lines = []

    # Header
    lines.append("# Conversation Trace")
    lines.append("")
    lines.append("## Session Metadata")
    lines.append("")
    lines.append(f"- **Session ID**: {session_metadata.get('session_id', 'unknown')}")
    lines.append(f"- **Command**: {session_metadata.get('command', 'unknown')}")
    lines.append(f"- **Timestamp**: {session_metadata.get('timestamp', 'unknown')}")
    lines.append(f"- **Worktree**: {session_metadata.get('worktree', 'unknown')}")
    lines.append(f"- **Git Branch**: {session_metadata.get('git_branch', 'unknown')}")
    lines.append("")

    # Main conversation
    lines.append("## Main Conversation")
    lines.append("")

    main_messages = grouped_messages.get("main", [])
    for message in main_messages:
        lines.extend(_format_message(message))

    # Subagent conversations
    for agent_id, messages in grouped_messages.items():
        if agent_id == "main":
            continue

        lines.append(f"## Subagent: agent-{agent_id}")
        lines.append("")

        for message in messages:
            lines.extend(_format_message(message))

    return "\n".join(lines)


def _format_message(message: dict) -> List[str]:
    """Format a single message as markdown lines.

    Args:
        message: Message dictionary

    Returns:
        List of markdown lines
    """
    lines = []
    msg_type = message.get("type", "unknown")
    timestamp = message.get("timestamp", "")

    if msg_type == "user":
        lines.append(f"### [{timestamp}] User")
        lines.append("")

        msg_content = message.get("message", {}).get("content", [])
        if isinstance(msg_content, str):
            lines.append(msg_content)
        elif isinstance(msg_content, list):
            for item in msg_content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        lines.append(item.get("text", ""))
                    elif item.get("type") == "tool_result":
                        lines.append(f"**Tool Result** (ID: {item.get('tool_use_id', 'unknown')})")
                        lines.append("```")
                        lines.append(str(item.get("content", "")))
                        lines.append("```")

    elif msg_type == "assistant":
        lines.append(f"### [{timestamp}] Assistant")
        lines.append("")

        msg_content = message.get("message", {}).get("content", [])
        if isinstance(msg_content, list):
            for item in msg_content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        lines.append(item.get("text", ""))
                    elif item.get("type") == "thinking":
                        lines.append("**Thinking:**")
                        lines.append("```")
                        lines.append(item.get("thinking", ""))
                        lines.append("```")
                    elif item.get("type") == "tool_use":
                        lines.append(f"**Tool: {item.get('name', 'unknown')}**")
                        lines.append("```json")
                        lines.append(json.dumps(item.get("input", {}), indent=2))
                        lines.append("```")

    lines.append("")
    return lines


def create_plan_trace_directory(repo_root: Path) -> Path:
    """Create timestamped directory for plan trace storage.

    Adapted from run_manager.py:create_run_directory() but creates directories
    in .weft/plan-traces/<timestamp>/ instead.

    Args:
        repo_root: Repository root directory

    Returns:
        Path to the created trace directory

    Raises:
        TraceCaptureError: If directory creation fails
    """
    # Create timestamp: YYYYMMDD_HHMMSS
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Build trace directory path: .weft/plan-traces/<timestamp>
    trace_dir = repo_root / ".weft" / "plan-traces" / timestamp

    try:
        trace_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        # If directory exists (rare race condition), append microseconds
        timestamp_with_micro = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        trace_dir = repo_root / ".weft" / "plan-traces" / timestamp_with_micro
        try:
            trace_dir.mkdir(parents=True, exist_ok=False)
        except OSError as e:
            raise TraceCaptureError(
                f"Failed to create plan trace directory {trace_dir}: {e}"
            ) from e
    except OSError as e:
        raise TraceCaptureError(
            f"Failed to create plan trace directory {trace_dir}: {e}"
        ) from e

    logger.info("Created plan trace directory: %s", trace_dir)
    return trace_dir


def prune_old_plan_traces(repo_root: Path) -> int:
    """Remove plan trace directories older than retention period.

    Adapted from run_manager.py:prune_old_runs().

    Args:
        repo_root: Repository root directory

    Returns:
        Number of directories pruned
    """
    traces_base = repo_root / ".weft" / "plan-traces"

    if not traces_base.exists():
        logger.debug("No plan-traces directory to prune")
        return 0

    # Calculate cutoff time
    cutoff_time = time.time() - (TRACE_RETENTION_DAYS * 24 * 60 * 60)
    pruned_count = 0
    errors = []

    # Iterate through timestamp directories
    for timestamp_dir in traces_base.iterdir():
        if not timestamp_dir.is_dir():
            continue

        # Check directory age using modification time
        try:
            dir_mtime = timestamp_dir.stat().st_mtime
            if dir_mtime < cutoff_time:
                # Directory is older than retention period
                logger.debug("Pruning old plan trace directory: %s", timestamp_dir)
                import shutil
                shutil.rmtree(timestamp_dir)
                pruned_count += 1
        except OSError as e:
            error_msg = f"Failed to prune {timestamp_dir}: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)
            continue

    if pruned_count > 0:
        logger.info("Pruned %d old plan trace director%s",
                   pruned_count, "y" if pruned_count == 1 else "ies")

    return pruned_count


def capture_session_trace(
    worktree_path: Path,
    command: str,
    run_dir: Path,
    execution_start: float,
    execution_end: float,
    session_id: Optional[str] = None,
) -> Optional[Path]:
    """Capture conversation trace from Claude Code session.

    Main entry point for trace capture. Searches for Claude Code conversation
    files, parses them, and generates a clean markdown trace.

    When session_id is provided (from SDK execution), it is used directly to
    filter messages instead of relying on timing-based folder matching.

    Args:
        worktree_path: Path to the worktree directory
        command: Command type ("plan" or "code")
        run_dir: Directory where trace should be stored
        execution_start: Subprocess start time (seconds since epoch)
        execution_end: Subprocess end time (seconds since epoch)
        session_id: Optional session ID from SDK execution. When provided,
                    skips timing-based search and uses session ID directly.

    Returns:
        Path to the created trace file, or None if capture failed

    Raises:
        TraceCaptureError: If capture fails
    """
    logger.debug("Starting trace capture for %s command", command)
    logger.debug("DEBUG: execution_start: %s (%s)", execution_start, datetime.fromtimestamp(execution_start).isoformat())
    logger.debug("DEBUG: execution_end: %s (%s)", execution_end, datetime.fromtimestamp(execution_end).isoformat())
    if session_id:
        logger.debug("DEBUG: Using provided session_id: %s", session_id)

    # Calculate execution window with 5-second buffer
    execution_window = (execution_start - 5, execution_end + 5)
    logger.debug("DEBUG: execution_window: (%s, %s)",
                 datetime.fromtimestamp(execution_window[0]).isoformat(),
                 datetime.fromtimestamp(execution_window[1]).isoformat())

    # Find project folder
    project_folder = find_project_folder(worktree_path, execution_window)
    if not project_folder:
        logger.warning("Could not find Claude Code project folder for worktree %s", worktree_path)
        return None

    logger.debug("DEBUG: Found project folder: %s", project_folder)

    # Collect JSONL files
    jsonl_files = collect_jsonl_files(project_folder)
    if not jsonl_files:
        logger.warning("No JSONL files found in project folder %s", project_folder)
        return None

    logger.debug("DEBUG: Found %d JSONL files to check", len(jsonl_files))

    # Use provided session_id or match from files
    if not session_id:
        session_id = match_session_files(jsonl_files, worktree_path)
        if not session_id:
            logger.warning("Could not match session for worktree %s", worktree_path)
            return None

    # Parse all JSONL files for this session
    all_messages = []
    for jsonl_file in jsonl_files:
        messages = parse_jsonl_file(jsonl_file)
        # Filter to messages from this session
        session_messages = [m for m in messages if m.get("sessionId") == session_id]
        all_messages.extend(session_messages)

    if not all_messages:
        logger.warning("No messages found for session %s", session_id)
        return None

    # Filter and group messages
    grouped_messages = filter_and_clean_messages(all_messages)

    # Clean tool results
    for agent_id in grouped_messages:
        grouped_messages[agent_id] = clean_tool_results(grouped_messages[agent_id])

    # Extract metadata from first message
    first_message = all_messages[0] if all_messages else {}
    session_metadata = {
        "session_id": session_id,
        "command": command,
        "timestamp": datetime.fromtimestamp(execution_start).isoformat(),
        "worktree": str(worktree_path),
        "git_branch": first_message.get("gitBranch", "unknown"),
    }

    # Generate markdown
    markdown_content = generate_markdown(grouped_messages, session_metadata)

    # Write to trace file
    trace_file = run_dir / "trace.md"
    try:
        trace_file.write_text(markdown_content, encoding="utf-8")
        logger.info("Trace captured successfully: %s", trace_file)
        return trace_file
    except OSError as e:
        raise TraceCaptureError(f"Failed to write trace file {trace_file}: {e}") from e
