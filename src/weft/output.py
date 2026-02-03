"""Output formatting for headless mode using Rich library.

This module provides styled terminal output for SDK session messages,
with visual distinction between AI conversational text, tool calls,
and thinking blocks.

Styling:
- AI conversational text (TextBlock): triangle prefix (▶), default color
- Tool calls (ToolUseBlock): wrench emoji (🛠️), cyan color
- Thinking blocks (ThinkingBlock): orange color, italics, no prefix

Gracefully falls back to plain text if Rich is unavailable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Attempt to import Rich, with graceful fallback
try:
    from rich.console import Console
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

if TYPE_CHECKING:
    from claude_agent_sdk import AssistantMessage

# Module-level console instance (lazy initialization)
_console: Any = None


def _get_console() -> Any:
    """Get or create the Rich console instance.

    Returns:
        Rich Console instance, or None if Rich is unavailable.
    """
    global _console
    if _console is None and RICH_AVAILABLE:
        _console = Console()
    return _console


def format_text_block(block: Any) -> None:
    """Format and print a TextBlock with triangle prefix.

    Args:
        block: TextBlock with .text attribute.
    """
    text = getattr(block, "text", "") or ""
    if not text:
        return

    console = _get_console()
    if console and RICH_AVAILABLE:
        # Print with triangle prefix, default color
        console.print(f"▶ {text}")
    else:
        # Plain text fallback
        print(f"▶ {text}")


def format_tool_block(block: Any) -> None:
    """Format and print a ToolUseBlock with wrench emoji in cyan.

    Shows the tool name and description if available. For Read/Write tools,
    shows the file path being accessed.

    Args:
        block: ToolUseBlock with .name and .input attributes.
    """
    name = getattr(block, "name", "") or ""
    input_data = getattr(block, "input", {}) or {}
    desc = input_data.get("description", "") if isinstance(input_data, dict) else ""
    file_path = input_data.get("file_path", "") if isinstance(input_data, dict) else ""

    # Build output text based on available info
    if desc:
        output_text = f"🛠️ {name}: {desc}"
    elif file_path and name in ("Read", "Write"):
        output_text = f"🛠️ {name}: {file_path}"
    else:
        output_text = f"🛠️ {name}"

    console = _get_console()
    if console and RICH_AVAILABLE:
        # Print in cyan
        styled = Text(output_text, style="cyan")
        console.print(styled)
    else:
        # Plain text fallback
        print(output_text)


def format_thinking_block(block: Any) -> None:
    """Format and print a ThinkingBlock in orange italics.

    Args:
        block: ThinkingBlock with .thinking attribute.
    """
    thinking = getattr(block, "thinking", "") or ""
    if not thinking:
        return

    console = _get_console()
    if console and RICH_AVAILABLE:
        # Print in orange (using 'dark_orange' which is close) with italics
        styled = Text(thinking, style="italic orange3")
        console.print(styled)
    else:
        # Plain text fallback
        print(thinking)


def print_assistant_message(message: "AssistantMessage") -> None:
    """Print an AssistantMessage with formatted blocks.

    Handles multiple block types within a message, formatting each
    appropriately. Unknown block types are handled gracefully.

    Args:
        message: AssistantMessage containing content blocks.
    """
    # Lazy import to avoid circular imports and allow fallback testing
    try:
        from claude_agent_sdk import TextBlock, ToolUseBlock, ThinkingBlock
    except ImportError:
        # If SDK not available, just print raw content
        for block in getattr(message, "content", []):
            text = getattr(block, "text", None) or getattr(block, "thinking", None)
            if text:
                print(text)
        return

    content = getattr(message, "content", []) or []

    for block in content:
        if isinstance(block, TextBlock):
            format_text_block(block)
        elif isinstance(block, ToolUseBlock):
            format_tool_block(block)
        elif isinstance(block, ThinkingBlock):
            format_thinking_block(block)
        else:
            # Unknown block type - try to extract text and print
            # Don't crash, just skip if no useful content
            text = (
                getattr(block, "text", None)
                or getattr(block, "thinking", None)
                or getattr(block, "content", None)
            )
            if text and isinstance(text, str):
                console = _get_console()
                if console and RICH_AVAILABLE:
                    console.print(text)
                else:
                    print(text)
