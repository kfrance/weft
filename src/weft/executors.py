"""Executor abstraction for different coding tools (Droid, Claude Code CLI, etc).

This module provides a pluggable executor pattern that abstracts away tool-specific
implementation details like authentication, command building, and environment setup.
"""

from __future__ import annotations

import shlex
from abc import ABC, abstractmethod
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


class ExecutorError(Exception):
    """Raised when executor operations fail."""


class Executor(ABC):
    """Abstract base class for coding tool executors."""

    @abstractmethod
    def check_auth(self) -> None:
        """Check if the executor's authentication is properly configured.

        Raises:
            ExecutorError: If authentication is not properly configured.
        """

    @abstractmethod
    def build_command(self, prompt_path: Path, model: str, headless: bool = False) -> str:
        """Build the command to run with the prompt file.

        Args:
            prompt_path: Path to the prompt file.
            model: Model variant to use (e.g., "sonnet", "opus", "haiku").
                   Implementations may validate or ignore this parameter based
                   on their capabilities. ClaudeCodeExecutor validates and uses
                   it; other executors may ignore it.
            headless: If True, build command for non-interactive execution.
                     ClaudeCodeExecutor adds -p flag; other executors may ignore.

        Returns:
            Command string to execute (e.g., 'droid "$(cat /path/to/prompt.txt)"')

        Raises:
            ValueError: If the model parameter is invalid or unsupported by the executor.
        """

    @abstractmethod
    def get_env_vars(self, host_factory_dir: Path) -> dict[str, str] | None:
        """Get executor-specific environment variables.

        Args:
            host_factory_dir: Path to the host's .factory directory.

        Returns:
            Dictionary of environment variables or None.
        """


class DroidExecutor(Executor):
    """Executor for Droid CLI tool."""

    def check_auth(self) -> None:
        """Check if Droid authentication is properly configured.

        Validates that auth.json exists in ~/.factory with required tokens.

        Raises:
            ExecutorError: If Droid authentication is not properly configured.
        """
        from .droid_auth import DroidAuthError, check_droid_auth

        try:
            check_droid_auth()
        except DroidAuthError as exc:
            raise ExecutorError(str(exc)) from exc

    def build_command(self, prompt_path: Path, model: str, headless: bool = False) -> str:
        """Build the droid command.

        Args:
            prompt_path: Path to the prompt file.
            model: Model variant to use (unused for Droid).
            headless: Unused for Droid (always runs non-interactively).

        Returns:
            Droid command string with properly escaped paths.
        """
        prompt_path_escaped = shlex.quote(str(prompt_path))
        return f'droid "$(cat {prompt_path_escaped})"'

    def get_env_vars(self, host_factory_dir: Path) -> dict[str, str] | None:
        """Get Droid-specific environment variables.

        Droid CLI discovers droids from ~/.factory/droids/ (personal) and
        <repo>/.factory/droids/ (project) per its documentation.

        Args:
            host_factory_dir: Path to the host's .factory directory (unused).

        Returns:
            None, as Droid doesn't require special environment setup.
        """
        return None


class ClaudeCodeExecutor(Executor):
    """Executor for Claude Code CLI tool."""

    # Valid model values for Claude Code CLI
    VALID_MODELS = {"sonnet", "opus", "haiku"}

    def check_auth(self) -> None:
        """Check if Claude Code authentication is properly configured.

        Claude Code typically handles authentication automatically or through
        environment variables, so this check is a no-op for now.
        """
        logger.debug("Claude Code CLI authentication check (no-op)")

    def build_command(self, prompt_path: Path, model: str, headless: bool = False) -> str:
        """Build the Claude Code command.

        Args:
            prompt_path: Path to the prompt file.
            model: Model variant to use (e.g., "sonnet", "opus", "haiku").
            headless: If True, add -p flag for non-interactive execution.

        Returns:
            Claude Code CLI command string with properly escaped paths.

        Raises:
            ValueError: If model parameter contains invalid characters that could
                       enable flag injection (e.g., starts with '-', contains spaces).
        """
        # Validate model parameter - only allow known valid values
        if not model:
            raise ValueError("Model parameter cannot be empty")
        if model not in self.VALID_MODELS:
            valid_models = ", ".join(sorted(self.VALID_MODELS))
            raise ValueError(
                f"Invalid model '{model}'. Must be one of: {valid_models}"
            )

        prompt_path_escaped = shlex.quote(str(prompt_path))
        model_escaped = shlex.quote(model)

        if headless:
            return f'claude -p --model {model_escaped} "$(cat {prompt_path_escaped})"'
        return f'claude --model {model_escaped} "$(cat {prompt_path_escaped})"'

    def get_env_vars(self, host_factory_dir: Path) -> dict[str, str] | None:
        """Get Claude Code-specific environment variables.

        Args:
            host_factory_dir: Path to the host's .factory directory (not used).

        Returns:
            None, as Claude Code doesn't require special environment setup.
        """
        return None


class ExecutorRegistry:
    """Registry for managing available executors."""

    _executors: dict[str, Executor] = {
        "droid": DroidExecutor(),
        "claude-code": ClaudeCodeExecutor(),
    }

    @classmethod
    def get_executor(cls, tool: str) -> Executor:
        """Get an executor by name.

        Args:
            tool: Name of the tool (e.g., "droid", "claude-code").

        Returns:
            Executor instance for the specified tool.

        Raises:
            ExecutorError: If the tool is not registered.
        """
        if tool not in cls._executors:
            available = ", ".join(sorted(cls._executors.keys()))
            raise ExecutorError(
                f"Unknown executor tool '{tool}'. Available tools: {available}"
            )
        return cls._executors[tool]

    @classmethod
    def register_executor(cls, name: str, executor: Executor) -> None:
        """Register a new executor.

        Args:
            name: Name of the executor.
            executor: Executor instance.
        """
        cls._executors[name] = executor

    @classmethod
    def list_executors(cls) -> list[str]:
        """List all available executor names.

        Returns:
            Sorted list of available executor names.
        """
        return sorted(cls._executors.keys())
