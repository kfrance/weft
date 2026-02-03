"""Unit tests for output formatting module.

Tests verify observable behavior using capsys to capture stdout,
ensuring the formatting functions produce expected output.
"""

from __future__ import annotations

import pytest


class MockTextBlock:
    """Mock TextBlock for testing."""

    def __init__(self, text: str = ""):
        self.text = text


class MockToolUseBlock:
    """Mock ToolUseBlock for testing."""

    def __init__(self, name: str = "", input_data: dict | None = None):
        self.name = name
        self.input = input_data or {}


class MockThinkingBlock:
    """Mock ThinkingBlock for testing."""

    def __init__(self, thinking: str = ""):
        self.thinking = thinking


class MockAssistantMessage:
    """Mock AssistantMessage for testing."""

    def __init__(self, content: list | None = None):
        self.content = content or []


class MockUnknownBlock:
    """Mock unknown block type for testing graceful handling."""

    def __init__(self, text: str = ""):
        self.text = text


class TestTextBlockOutput:
    """Tests for text block formatting."""

    def test_text_block_output_has_prefix(self, capsys: pytest.CaptureFixture) -> None:
        """Verify TextBlock content prints with triangle prefix."""
        from weft.output import format_text_block

        block = MockTextBlock(text="Hello, world!")
        format_text_block(block)

        captured = capsys.readouterr()
        assert "▶" in captured.out
        assert "Hello, world!" in captured.out

    def test_empty_text_block_handled(self, capsys: pytest.CaptureFixture) -> None:
        """Verify empty TextBlock doesn't crash and produces no output."""
        from weft.output import format_text_block

        block = MockTextBlock(text="")
        format_text_block(block)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_none_text_block_handled(self, capsys: pytest.CaptureFixture) -> None:
        """Verify TextBlock with None text doesn't crash."""
        from weft.output import format_text_block

        block = MockTextBlock()
        block.text = None  # type: ignore
        format_text_block(block)

        captured = capsys.readouterr()
        assert captured.out == ""


class TestToolBlockOutput:
    """Tests for tool block formatting."""

    def test_tool_block_output_has_prefix_and_name(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify ToolUseBlock prints with wrench emoji and tool name."""
        from weft.output import format_tool_block

        block = MockToolUseBlock(name="Bash", input_data={})
        format_tool_block(block)

        captured = capsys.readouterr()
        assert "🛠️" in captured.out
        assert "Bash" in captured.out

    def test_tool_block_shows_description_when_available(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify description appears in output when provided."""
        from weft.output import format_tool_block

        block = MockToolUseBlock(
            name="Bash", input_data={"description": "Run tests"}
        )
        format_tool_block(block)

        captured = capsys.readouterr()
        assert "🛠️" in captured.out
        assert "Bash" in captured.out
        assert "Run tests" in captured.out

    def test_tool_block_without_description(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify tool block without description still works."""
        from weft.output import format_tool_block

        block = MockToolUseBlock(name="Glob", input_data={"pattern": "*.py"})
        format_tool_block(block)

        captured = capsys.readouterr()
        assert "🛠️" in captured.out
        assert "Glob" in captured.out

    def test_read_tool_shows_file_path(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify Read tool shows the file path being read."""
        from weft.output import format_tool_block

        block = MockToolUseBlock(name="Read", input_data={"file_path": "/src/main.py"})
        format_tool_block(block)

        captured = capsys.readouterr()
        assert "🛠️" in captured.out
        assert "Read" in captured.out
        assert "/src/main.py" in captured.out

    def test_write_tool_shows_file_path(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify Write tool shows the file path being written."""
        from weft.output import format_tool_block

        block = MockToolUseBlock(
            name="Write", input_data={"file_path": "/output/result.txt"}
        )
        format_tool_block(block)

        captured = capsys.readouterr()
        assert "🛠️" in captured.out
        assert "Write" in captured.out
        assert "/output/result.txt" in captured.out

    def test_description_takes_precedence_over_file_path(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify description is shown instead of file_path when both present."""
        from weft.output import format_tool_block

        block = MockToolUseBlock(
            name="Read",
            input_data={"file_path": "/some/file.py", "description": "Read config"}
        )
        format_tool_block(block)

        captured = capsys.readouterr()
        assert "Read config" in captured.out
        # file_path should not appear when description is present
        assert "/some/file.py" not in captured.out


class TestThinkingBlockOutput:
    """Tests for thinking block formatting."""

    def test_thinking_block_output_is_styled(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify ThinkingBlock content appears in output without prefix."""
        from weft.output import format_thinking_block

        block = MockThinkingBlock(thinking="Let me think about this...")
        format_thinking_block(block)

        captured = capsys.readouterr()
        assert "Let me think about this..." in captured.out
        # ThinkingBlock should NOT have the triangle prefix (unlike TextBlock)
        assert not captured.out.startswith("▶")

    def test_empty_thinking_block_handled(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify empty ThinkingBlock doesn't crash."""
        from weft.output import format_thinking_block

        block = MockThinkingBlock(thinking="")
        format_thinking_block(block)

        captured = capsys.readouterr()
        assert captured.out == ""


class TestAssistantMessage:
    """Tests for assistant message handling."""

    def test_mixed_blocks_all_print(self, capsys: pytest.CaptureFixture) -> None:
        """Verify AssistantMessage with multiple block types prints all blocks."""
        # Use real SDK types for this test
        from claude_agent_sdk import TextBlock, ToolUseBlock, ThinkingBlock
        from weft.output import print_assistant_message

        # Create message with real SDK block types (all three types)
        message = MockAssistantMessage(
            content=[
                TextBlock(text="Starting task"),
                ThinkingBlock(thinking="Analyzing the request...", signature="sig-123"),
                ToolUseBlock(
                    id="test-1",
                    name="Bash",
                    input={"description": "List files"}
                ),
                TextBlock(text="Task complete"),
            ]
        )

        print_assistant_message(message)

        captured = capsys.readouterr()
        assert "▶" in captured.out  # TextBlock prefix
        assert "Starting task" in captured.out
        assert "Analyzing the request..." in captured.out  # ThinkingBlock content
        assert "🛠️" in captured.out  # ToolUseBlock prefix
        assert "Bash" in captured.out
        assert "Task complete" in captured.out

    def test_unknown_block_type_handled_gracefully(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify unrecognized block types don't crash."""
        from claude_agent_sdk import TextBlock
        from weft.output import print_assistant_message

        # Create message with a known block and an unknown block type
        message = MockAssistantMessage(
            content=[
                TextBlock(text="Known block"),
                MockUnknownBlock(text="Unknown block content"),
            ]
        )

        # Should not raise
        print_assistant_message(message)

        captured = capsys.readouterr()
        assert "Known block" in captured.out
        # Unknown block should also print its text content via fallback
        assert "Unknown block content" in captured.out


class TestFallbackBehavior:
    """Tests for fallback when Rich is unavailable."""

    def test_fallback_when_rich_unavailable(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """Verify output still works without Rich (mock ImportError)."""
        # Save original state
        import weft.output as output_module
        original_rich_available = output_module.RICH_AVAILABLE
        original_console = output_module._console

        try:
            # Simulate Rich being unavailable
            output_module.RICH_AVAILABLE = False
            output_module._console = None

            # Test text block
            block = MockTextBlock(text="Fallback test")
            output_module.format_text_block(block)

            captured = capsys.readouterr()
            assert "▶" in captured.out
            assert "Fallback test" in captured.out

        finally:
            # Restore original state
            output_module.RICH_AVAILABLE = original_rich_available
            output_module._console = original_console

    def test_tool_block_fallback(self, capsys: pytest.CaptureFixture) -> None:
        """Verify tool block fallback without Rich."""
        import weft.output as output_module
        original_rich_available = output_module.RICH_AVAILABLE
        original_console = output_module._console

        try:
            output_module.RICH_AVAILABLE = False
            output_module._console = None

            block = MockToolUseBlock(name="Read", input_data={"description": "Read file"})
            output_module.format_tool_block(block)

            captured = capsys.readouterr()
            assert "🛠️" in captured.out
            assert "Read" in captured.out
            assert "Read file" in captured.out

        finally:
            output_module.RICH_AVAILABLE = original_rich_available
            output_module._console = original_console

    def test_thinking_block_fallback(self, capsys: pytest.CaptureFixture) -> None:
        """Verify thinking block fallback without Rich."""
        import weft.output as output_module
        original_rich_available = output_module.RICH_AVAILABLE
        original_console = output_module._console

        try:
            output_module.RICH_AVAILABLE = False
            output_module._console = None

            block = MockThinkingBlock(thinking="Deep thoughts")
            output_module.format_thinking_block(block)

            captured = capsys.readouterr()
            assert "Deep thoughts" in captured.out

        finally:
            output_module.RICH_AVAILABLE = original_rich_available
            output_module._console = original_console
