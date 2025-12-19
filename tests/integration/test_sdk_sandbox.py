"""Integration tests verifying Claude Code SDK sandbox is operational.

This module tests that the Claude Code SDK sandbox is **operational on the current
system**, not that the SDK's sandbox logic is correct. The distinction is important:

**Real-world problem**: On a new system or CI environment, the sandbox can silently
fail if `bubblewrap` and `socat` aren't installed. When this happens, Claude Code
runs without sandboxing, and file writes that should be blocked are allowed.

**Why this matters**: A user believes they're protected by the sandbox (because
sandbox is enabled in settings), but writes to sensitive directories like `~`
actually succeed. This creates a false sense of security.

**Why we test `~` not `/tmp`**: The sandbox allowlist includes `/tmp`, so writes
there succeed even with a working sandbox. To detect a non-functional sandbox,
we must attempt to write to a path that's NOT in the allowlist. The home
directory (`~`) is blocked by a working sandbox but allowed when sandbox fails.

**This is an environmental/operational test**, not a unit/integration test of
weft code. It verifies the deployment environment has the prerequisites
for sandbox functionality.

Prerequisites:
- bubblewrap (bwrap) must be installed: sudo apt install bubblewrap
- socat must be installed: sudo apt install socat
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from weft.sdk_runner import run_sdk_session


class TestSDKSandboxOperational:
    """Tests verifying the SDK sandbox is operational on this system."""

    def test_sdk_sandbox_blocks_write_to_home_directory(self, tmp_path: Path) -> None:
        """Verify SDK sandbox blocks file writes to user's home directory.

        This test catches a specific failure mode: the sandbox is enabled in
        settings but non-functional because bubblewrap/socat aren't installed.
        In this case, the SDK runs without sandboxing and file writes succeed
        when they should fail.

        We write to the home directory because:
        - Home directory is outside the sandbox allowlist
        - A working sandbox blocks writes to ~/
        - A non-functional sandbox allows writes to ~/
        - This distinguishes "sandbox working" from "sandbox broken"

        If this test fails:
        1. Install sandbox dependencies: sudo apt install bubblewrap socat
        2. Verify bwrap is executable: which bwrap
        3. Verify socat is executable: which socat
        4. Re-run the test

        The test cleans up any created files in a finally block to prevent
        pollution even if assertions fail.
        """
        # Use Path.home() for consistent cross-platform home directory resolution
        # This returns the actual home directory regardless of environment quirks
        # Filename is intentionally obscure - no user would ever create this file
        target_file = Path.home() / ".weft_sandbox_test_a9f3e2c1.tmp"

        # Unique content that we'll ask the SDK to write - this lets us verify
        # the file was created by THIS test run, not some other process
        unique_content = "weft_sandbox_verification_8b2f4a1c"

        # Clean up any leftover file from previous failed test run
        # The filename is obscure enough that we can safely delete it
        if target_file.exists():
            target_file.unlink()

        # Create minimal sdk_settings.json with sandbox enabled
        settings_path = tmp_path / "sdk_settings.json"
        settings_path.write_text('{"sandbox": {"enabled": true}}')

        try:
            # Run SDK session with explicit Bash command in prompt
            # We use an explicit command rather than asking the LLM to "create a file"
            # to avoid ambiguity in how the LLM might interpret the request
            asyncio.run(
                run_sdk_session(
                    worktree_path=tmp_path,
                    prompt_content=(
                        "Use the Bash tool to run exactly this command: "
                        f"echo '{unique_content}' > {target_file}"
                    ),
                    model="haiku",  # Cheapest/fastest model for testing
                    sdk_settings_path=settings_path,
                )
            )

            # After session completes, check if the file was created with our content
            if target_file.exists():
                content = target_file.read_text().strip()
                if content == unique_content:
                    # File exists with our unique content - sandbox did NOT block the write
                    pytest.fail(
                        f"Sandbox is non-functional! File was written to {target_file}. "
                        f"This indicates bubblewrap/socat are not installed or not working. "
                        f"Install with: sudo apt install bubblewrap socat"
                    )
                else:
                    # File exists but with different content - unexpected state
                    pytest.fail(
                        f"Unexpected file content at {target_file}. "
                        f"Expected '{unique_content}', got '{content[:50]}...'. "
                        f"This suggests another process created this file."
                    )

            # File does not exist - sandbox successfully blocked the write
            # Test passes

        finally:
            # Cleanup in finally block guarantees no pollution even on assertion failure
            # This ensures the test environment is clean for the next run
            if target_file.exists():
                target_file.unlink()
