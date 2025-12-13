"""Trace summarizer for generating compressed trace summaries.

This module generates compressed trace summaries for training data,
reducing 266KB-688KB traces to ~5-10KB while preserving information
valuable for DSPy prompt optimization.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import dspy

from .judge_executor import configure_dspy_cache, get_cache_dir, get_openrouter_api_key
from .logging_config import get_logger
from .trace_parser import (
    TraceMetadata,
    count_tools_by_type,
    detect_errors,
    extract_bash_commands,
    extract_file_paths,
    parse_subagent_sections,
    parse_tool_calls,
    parse_trace_metadata,
)

logger = get_logger(__name__)


class TraceSummarizationError(Exception):
    """Raised when trace summarization fails."""
    pass


def extract_structural_data(trace_content: str) -> dict:
    """Extract structural summary from trace content.

    Uses trace_parser to build a structural summary containing:
    - Tool counts by type
    - Files read (unique paths)
    - Files modified/created
    - Bash commands
    - Error count and messages

    Args:
        trace_content: Full trace markdown content

    Returns:
        Dictionary with structural data
    """
    # Parse tool calls
    tool_calls = parse_tool_calls(trace_content)

    # Count tools by type
    tool_counts = count_tools_by_type(tool_calls)

    # Extract file paths
    file_paths = extract_file_paths(tool_calls)

    # Extract bash commands
    bash_commands = extract_bash_commands(tool_calls)

    # Detect errors
    errors = detect_errors(trace_content)

    # Parse metadata
    metadata = parse_trace_metadata(trace_content)

    return {
        'metadata': {
            'session_id': metadata.session_id,
            'command': metadata.command,
            'timestamp': metadata.timestamp,
            'worktree': metadata.worktree,
            'git_branch': metadata.git_branch,
        },
        'tool_counts': tool_counts,
        'files': {
            'read': sorted(file_paths['read']),
            'modified': sorted(file_paths['modified']),
            'created': sorted(file_paths['created']),
        },
        'bash_commands': bash_commands,
        'error_count': len(errors),
        'errors': errors[:5],  # Limit to first 5 errors
    }


# Summarization prompt loaded from file
def _load_summarization_prompt() -> str:
    """Load the summarization prompt from the prompts directory."""
    prompt_path = Path(__file__).parent / "prompts" / "trace_summarization.md"
    if not prompt_path.exists():
        raise TraceSummarizationError(
            f"Summarization prompt not found: {prompt_path}"
        )
    return prompt_path.read_text(encoding="utf-8")


class TraceSummarizationSignature(dspy.Signature):
    """Signature for trace summarization."""

    trace_content: str = dspy.InputField(
        desc="Full trace markdown content"
    )
    subagent_sections: str = dspy.InputField(
        desc="Extracted subagent conversation sections as formatted text"
    )
    structural_data: str = dspy.InputField(
        desc="JSON-formatted structural data extracted from trace"
    )

    narrative_summary: str = dspy.OutputField(
        desc="Narrative summary focusing on task intent, subagent feedback (verbatim), and response to feedback"
    )


def generate_narrative_summary(
    trace_content: str,
    subagent_sections: dict[str, str],
    model: str,
) -> str:
    """Generate narrative summary using DSPy.

    Args:
        trace_content: Full trace markdown content
        subagent_sections: Dictionary mapping agent ID to section content
        model: OpenRouter model tag for DSPy calls

    Returns:
        Narrative summary as markdown text

    Raises:
        TraceSummarizationError: If summarization fails
    """
    logger.info("Generating narrative summary with model %s", model)

    try:
        # Get API key
        api_key = get_openrouter_api_key()

        # Configure DSPy cache
        cache_dir = get_cache_dir()
        configure_dspy_cache(cache_dir)

        # Format subagent sections for input
        subagent_text = ""
        for agent_id, content in subagent_sections.items():
            subagent_text += f"\n## Subagent: agent-{agent_id}\n\n{content}\n"

        # Extract structural data for context
        structural_data = extract_structural_data(trace_content)
        import json
        structural_json = json.dumps(structural_data, indent=2)

        # Load summarization prompt
        instructions = _load_summarization_prompt()

        # Create LM with specified model
        lm = dspy.LM(
            f"openrouter/{model}",
            api_key=api_key,
            max_tokens=16000,
            temperature=0.3,
        )

        # Create signature with instructions
        InstructedSignature = TraceSummarizationSignature.with_instructions(
            instructions
        )

        # Create predictor and run
        predictor = dspy.Predict(InstructedSignature)
        with dspy.context(lm=lm):
            result = predictor(
                trace_content=trace_content,
                subagent_sections=subagent_text if subagent_text else "No subagent sections found.",
                structural_data=structural_json,
            )

        narrative = str(result.narrative_summary)
        logger.debug("Generated narrative summary (%d chars)", len(narrative))

        return narrative

    except Exception as exc:
        raise TraceSummarizationError(
            f"Failed to generate narrative summary: {exc}"
        ) from exc


def _format_structural_section(structural_data: dict) -> str:
    """Format structural data as markdown section.

    Args:
        structural_data: Dictionary from extract_structural_data()

    Returns:
        Formatted markdown string
    """
    lines = []

    # Metadata
    lines.append("## Session Metadata")
    lines.append("")
    meta = structural_data.get('metadata', {})
    lines.append(f"- **Session ID**: {meta.get('session_id', 'unknown')}")
    lines.append(f"- **Command**: {meta.get('command', 'unknown')}")
    lines.append(f"- **Timestamp**: {meta.get('timestamp', 'unknown')}")
    lines.append(f"- **Git Branch**: {meta.get('git_branch', 'unknown')}")
    lines.append("")

    # Tool counts
    lines.append("## Tool Usage")
    lines.append("")
    tool_counts = structural_data.get('tool_counts', {})
    if tool_counts:
        sorted_tools = sorted(tool_counts.items(), key=lambda x: -x[1])
        for tool_name, count in sorted_tools:
            lines.append(f"- {tool_name}: {count}")
    else:
        lines.append("No tool calls recorded.")
    lines.append("")

    # Files
    lines.append("## Files Accessed")
    lines.append("")
    files = structural_data.get('files', {})

    modified = files.get('modified', [])
    created = files.get('created', [])
    read_files = files.get('read', [])

    if modified:
        lines.append("### Modified")
        for f in modified:
            lines.append(f"- {f}")
        lines.append("")

    if created:
        lines.append("### Created")
        for f in created:
            lines.append(f"- {f}")
        lines.append("")

    if read_files:
        lines.append("### Read")
        # Limit to first 20 files to keep summary compact
        for f in read_files[:20]:
            lines.append(f"- {f}")
        if len(read_files) > 20:
            lines.append(f"- ... and {len(read_files) - 20} more")
        lines.append("")

    # Bash commands
    lines.append("## Bash Commands")
    lines.append("")
    bash_commands = structural_data.get('bash_commands', [])
    if bash_commands:
        for cmd in bash_commands[:10]:  # Limit to first 10
            # Truncate long commands
            if len(cmd) > 100:
                cmd = cmd[:100] + "..."
            lines.append(f"- `{cmd}`")
        if len(bash_commands) > 10:
            lines.append(f"- ... and {len(bash_commands) - 10} more")
    else:
        lines.append("No bash commands recorded.")
    lines.append("")

    # Errors
    error_count = structural_data.get('error_count', 0)
    errors = structural_data.get('errors', [])
    lines.append("## Errors")
    lines.append("")
    if error_count > 0:
        lines.append(f"**{error_count} error(s) detected**")
        lines.append("")
        for i, error in enumerate(errors, 1):
            # Truncate long errors
            if len(error) > 200:
                error = error[:200] + "..."
            lines.append(f"{i}. {error}")
    else:
        lines.append("No errors detected.")
    lines.append("")

    return "\n".join(lines)


def create_trace_summary(trace_path: Path, model: str) -> Path:
    """Generate a compressed trace summary.

    Main entry point for trace summarization. Reads the full trace,
    extracts structural data, generates a narrative summary, and
    writes the combined summary alongside the original trace.

    Args:
        trace_path: Path to the code_trace.md file
        model: OpenRouter model tag for DSPy calls

    Returns:
        Path to the created summary file (code_trace_summary.md)

    Raises:
        TraceSummarizationError: If summarization fails
    """
    logger.info("Creating trace summary for %s", trace_path)

    if not trace_path.exists():
        raise TraceSummarizationError(f"Trace file not found: {trace_path}")

    # Read trace content
    try:
        trace_content = trace_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TraceSummarizationError(
            f"Failed to read trace file: {exc}"
        ) from exc

    original_size = len(trace_content)
    logger.debug("Original trace size: %d bytes", original_size)

    # Extract structural data
    structural_data = extract_structural_data(trace_content)

    # Parse subagent sections
    subagent_sections = parse_subagent_sections(trace_content)
    logger.debug("Found %d subagent section(s)", len(subagent_sections))

    # Generate narrative summary
    narrative = generate_narrative_summary(
        trace_content=trace_content,
        subagent_sections=subagent_sections,
        model=model,
    )

    # Format structural section
    structural_section = _format_structural_section(structural_data)

    # Combine into summary document
    summary_lines = [
        "# Trace Summary",
        "",
        "This is a compressed summary of the full conversation trace.",
        "Original trace preserved in `code_trace.md`.",
        "",
        structural_section,
        "## Narrative Summary",
        "",
        narrative,
    ]

    summary_content = "\n".join(summary_lines)
    summary_size = len(summary_content)

    logger.info(
        "Summary compression: %d bytes -> %d bytes (%.1f%% reduction)",
        original_size,
        summary_size,
        100 * (1 - summary_size / original_size) if original_size > 0 else 0,
    )

    # Write summary file
    summary_path = trace_path.parent / "code_trace_summary.md"
    try:
        summary_path.write_text(summary_content, encoding="utf-8")
        logger.info("Wrote trace summary to %s", summary_path)
    except OSError as exc:
        raise TraceSummarizationError(
            f"Failed to write summary file: {exc}"
        ) from exc

    return summary_path


def needs_regeneration(trace_path: Path, summary_path: Path) -> bool:
    """Check if summary needs regeneration based on file modification times.

    Args:
        trace_path: Path to the code_trace.md file
        summary_path: Path to the code_trace_summary.md file

    Returns:
        True if summary doesn't exist or is older than trace
    """
    if not summary_path.exists():
        return True

    try:
        trace_mtime = trace_path.stat().st_mtime
        summary_mtime = summary_path.stat().st_mtime
        return trace_mtime > summary_mtime
    except OSError:
        return True
