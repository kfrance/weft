"""Central constants for tool names and supported tools.

This module provides the single source of truth for:
- Default tool name (claude-code)
- Set of supported tools for validation
- Mapping of legacy tool names to current names for migration
"""

from __future__ import annotations

# Default coding tool name used when no tool is explicitly specified
DEFAULT_CODING_TOOL = "claude-code"

# Set of valid tool names for validation
SUPPORTED_TOOLS: frozenset[str] = frozenset({"claude-code", "droid"})

# Mapping of legacy tool names to their current equivalents
# Used for automatic migration of prompt directories
LEGACY_TOOL_NAMES: dict[str, str] = {
    "claude-code-cli": "claude-code",
}
