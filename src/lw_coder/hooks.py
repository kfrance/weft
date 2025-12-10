"""Configurable hook system for executing user commands at workflow points.

This module implements a hook system that allows developers to configure
commands to run automatically at key workflow points (e.g., after plan creation,
after code completion).

Security Model:
    Hooks execute developer-controlled commands from ~/.lw_coder/config.toml.
    This is the developer's own configuration on their own machine - similar to
    git hooks, shell aliases, or npm scripts. No untrusted input is involved.
    See docs/adr/002-hook-injection-trust.md for detailed rationale.
"""

from __future__ import annotations

import atexit
import subprocess
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING, Protocol

from .config import load_config as load_config_from_module
from .logging_config import get_logger

if TYPE_CHECKING:
    from typing import Any


logger = get_logger(__name__)


class HookError(Exception):
    """Base exception for hook-related errors."""


class HookConfigError(HookError):
    """Exception for configuration loading/validation errors."""


class ProcessExecutor(Protocol):
    """Protocol for dependency injection of process execution.

    Allows mocking process execution in tests.
    """

    def execute(self, command: str) -> subprocess.Popen[bytes]:
        """Execute command string with shell.

        Args:
            command: The shell command to execute.

        Returns:
            Popen object for the spawned process.
        """
        ...


class RealProcessExecutor:
    """Real implementation using subprocess.Popen with shell=True.

    This executes developer-controlled commands from their own config file,
    similar to git hooks or shell aliases.
    """

    def execute(self, command: str) -> subprocess.Popen[bytes]:
        """Execute command string with shell.

        Args:
            command: The shell command to execute.

        Returns:
            Popen object for the spawned process.
        """
        return subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent process group
        )


class HookManager:
    """Manages hook execution and process lifecycle.

    Tracks spawned processes and ensures cleanup on exit.
    """

    def __init__(self, executor: ProcessExecutor | None = None) -> None:
        """Initialize the HookManager.

        Args:
            executor: Process executor to use. Defaults to RealProcessExecutor.
        """
        self._executor: ProcessExecutor = executor or RealProcessExecutor()
        self._processes: list[subprocess.Popen[bytes]] = []
        self._config: dict[str, Any] | None = None
        self._cleanup_registered = False

    def _register_cleanup(self) -> None:
        """Register atexit handler for process cleanup."""
        if not self._cleanup_registered:
            atexit.register(self._cleanup)
            self._cleanup_registered = True

    def _cleanup(self) -> None:
        """Clean up all spawned processes on exit."""
        for proc in self._processes:
            try:
                if proc.poll() is None:  # Still running
                    logger.debug("Terminating hook process PID %d", proc.pid)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Hook process PID %d did not terminate, killing",
                            proc.pid,
                        )
                        proc.kill()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Error during process cleanup: %s", exc)
        self._processes.clear()

    def _prune_completed(self) -> None:
        """Remove finished processes from tracking list."""
        self._processes = [p for p in self._processes if p.poll() is None]

    def load_config(self, force_reload: bool = False) -> dict[str, Any]:
        """Load hook configuration from ~/.lw_coder/config.toml.

        Delegates to the config module for TOML parsing, then validates
        the hooks section.

        Args:
            force_reload: Force reloading config even if cached.

        Returns:
            Dictionary containing hook configuration, or empty dict if not configured.

        Raises:
            HookConfigError: If configuration is malformed.
        """
        if self._config is not None and not force_reload:
            return self._config

        # Delegate TOML parsing to config module
        # Note: config module handles missing file, I/O errors, and TOML parse errors
        # gracefully by returning empty dict and logging appropriately
        full_config = load_config_from_module()

        if not full_config:
            logger.debug("No config loaded, hooks disabled")
            self._config = {}
            return self._config

        # Extract hooks section
        hooks_config = full_config.get("hooks", {})

        # Validate hook structure
        valid_hook_names = {"plan_file_created", "code_sdk_complete", "eval_complete"}
        for hook_name, hook_config in hooks_config.items():
            if hook_name not in valid_hook_names:
                raise HookConfigError(
                    f"Unknown hook '{hook_name}'. Valid hooks: {', '.join(sorted(valid_hook_names))}"
                )

            if not isinstance(hook_config, dict):
                raise HookConfigError(f"Hook '{hook_name}' must be a table, got {type(hook_config).__name__}")

            if "command" not in hook_config:
                raise HookConfigError(f"Hook '{hook_name}' missing required 'command' field")

            if not isinstance(hook_config.get("command"), str):
                raise HookConfigError(f"Hook '{hook_name}' command must be a string")

            enabled = hook_config.get("enabled", True)
            if not isinstance(enabled, bool):
                raise HookConfigError(f"Hook '{hook_name}' enabled must be a boolean, got {type(enabled).__name__}")

        logger.debug("Loaded hook config with %d hooks", len(hooks_config))
        self._config = {"hooks": hooks_config}
        return self._config

    def execute_hook(
        self,
        hook_name: str,
        variables: dict[str, Path | str],
    ) -> None:
        """Execute a configured hook.

        Args:
            hook_name: Name of the hook (e.g., "plan_file_created").
            variables: Dictionary of variable names to values for substitution.

        Raises:
            HookError: If variable substitution fails or command execution fails.
        """
        try:
            config = self.load_config()
        except HookConfigError as exc:
            logger.warning("Hook config error: %s", exc)
            return

        hooks = config.get("hooks", {})
        hook_config = hooks.get(hook_name)

        if hook_config is None:
            logger.debug("Hook '%s' not configured", hook_name)
            return

        enabled = hook_config.get("enabled", True)
        if not enabled:
            logger.debug("Hook '%s' is disabled", hook_name)
            return

        command_template = hook_config["command"]

        # Substitute variables
        try:
            command = substitute_variables(command_template, variables)
        except HookError as exc:
            logger.error("Variable substitution failed for hook '%s': %s", hook_name, exc)
            raise

        logger.info(
            "Executing hook '%s': %s (variables: %s)",
            hook_name,
            command,
            {k: str(v) for k, v in variables.items()},
        )

        # Register cleanup handler before first execution
        self._register_cleanup()

        try:
            proc = self._executor.execute(command)
            self._processes.append(proc)
            logger.debug("Spawned hook process PID %d", proc.pid)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to execute hook '%s': %s", hook_name, exc)
            raise HookError(f"Failed to execute hook '{hook_name}': {exc}") from exc

        # Prune completed processes to prevent unbounded growth
        self._prune_completed()


def substitute_variables(command: str, variables: dict[str, Path | str]) -> str:
    """Substitute variables in a command string.

    Uses string.Template for ${variable} syntax substitution.

    Args:
        command: Command string with ${variable} placeholders.
        variables: Dictionary of variable names to Path or string values.

    Returns:
        Command string with variables substituted.

    Raises:
        HookError: If a referenced variable is not defined.

    Example:
        >>> substitute_variables("code-oss ${worktree_path}", {"worktree_path": Path("/tmp/wt")})
        'code-oss /tmp/wt'
    """
    # Convert Path objects to strings
    str_vars = {k: str(v) for k, v in variables.items()}

    template = Template(command)
    try:
        return template.substitute(str_vars)
    except KeyError as exc:
        raise HookError(f"Undefined variable in command: {exc}") from exc
    except ValueError as exc:
        raise HookError(f"Invalid variable syntax in command: {exc}") from exc


def trigger_hook(
    hook_name: str,
    variables: dict[str, Path | str],
    manager: HookManager | None = None,
    console_output: bool = True,
) -> None:
    """Trigger a hook with the given variables.

    This is the main public API for triggering hooks. It handles errors
    gracefully and provides console feedback.

    Args:
        hook_name: Name of the hook to trigger.
        variables: Dictionary of variable names to values.
        manager: HookManager to use. Creates a new one if not provided.
        console_output: Whether to print console feedback.
    """
    if manager is None:
        manager = HookManager()

    try:
        # Check if hook is configured before showing console output
        config = manager.load_config()
        hooks = config.get("hooks", {})
        hook_config = hooks.get(hook_name)

        if hook_config is None:
            return

        if not hook_config.get("enabled", True):
            return

        if console_output:
            # Import here to avoid circular dependency
            try:
                from rich.console import Console
                console = Console()
                console.print(f"[dim]→ Running {hook_name} hook in background[/dim]")
            except ImportError:
                print(f"→ Running {hook_name} hook in background")

        manager.execute_hook(hook_name, variables)
    except HookError as exc:
        logger.warning("Hook '%s' failed: %s", hook_name, exc)
        if console_output:
            try:
                from rich.console import Console
                console = Console()
                console.print(f"[yellow]⚠ Hook '{hook_name}' failed: {exc}[/yellow]")
            except ImportError:
                print(f"⚠ Hook '{hook_name}' failed: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in hook '%s': %s", hook_name, exc)


# Global hook manager instance for convenience
_global_manager: HookManager | None = None


def get_hook_manager() -> HookManager:
    """Get or create the global HookManager instance.

    Returns:
        Global HookManager instance.
    """
    global _global_manager
    if _global_manager is None:
        _global_manager = HookManager()
    return _global_manager
