#!/usr/bin/env python3
"""Manual SDK runner / sandbox debug script.

A lightweight standalone script for testing and debugging the SDK runner
and bwrap sandbox without going through the full `weft code` workflow.

Supports two modes:
  - sdk <prompt>    Run a Claude Code SDK session with an arbitrary prompt
  - bash <command>  Run an arbitrary bash command inside the bwrap sandbox

Usage:
    python scripts/test_sdk_headless.py sdk "Write a hello world program"
    python scripts/test_sdk_headless.py bash "ls -la"
    python scripts/test_sdk_headless.py sdk --model opus "Explain this code"
    python scripts/test_sdk_headless.py bash --no-sandbox "echo hello"
    python scripts/test_sdk_headless.py sdk --verbose "Debug this"
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# Add src directory to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from weft.logging_config import get_logger  # noqa: E402
from weft.param_validation import get_effective_model  # noqa: E402
from weft.paths import get_sdk_settings_path  # noqa: E402
from weft.repo_utils import RepoUtilsError, find_repo_root  # noqa: E402
from weft.sandbox import (  # noqa: E402
    SandboxConfig,
    SandboxConfigError,
    build_bwrap_command,
    load_sandbox_config,
)
from weft.sdk_runner import SDKRunnerError, run_sdk_session_sync  # noqa: E402

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Command-line arguments to parse. Defaults to sys.argv[1:].

    Returns:
        Parsed argument namespace.
    """
    # Shared options available in each subcommand via parent parser
    shared_parser = argparse.ArgumentParser(add_help=False)
    shared_parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("."),
        help="Target directory (default: current working directory)",
    )
    shared_parser.add_argument(
        "--no-sandbox",
        action="store_true",
        help="Bypass sandbox isolation",
    )
    shared_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug-level logging for troubleshooting",
    )

    parser = argparse.ArgumentParser(
        description="Manual SDK runner / sandbox debug script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  %(prog)s sdk "Write a hello world program"\n'
            '  %(prog)s bash "ls -la"\n'
            '  %(prog)s sdk --model opus "Explain this code"\n'
            '  %(prog)s bash --no-sandbox "echo hello"\n'
            '  %(prog)s sdk --verbose "Debug this"\n'
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # SDK subcommand
    sdk_parser = subparsers.add_parser(
        "sdk",
        parents=[shared_parser],
        help="Run an SDK session with the given prompt",
    )
    sdk_parser.add_argument(
        "prompt",
        help="Prompt to send to the SDK session",
    )
    sdk_parser.add_argument(
        "--model",
        default=None,
        help="Override model selection (default: uses 3-tier precedence)",
    )

    # Bash subcommand
    bash_parser = subparsers.add_parser(
        "bash",
        parents=[shared_parser],
        help="Run a bash command inside the bwrap sandbox",
    )
    bash_parser.add_argument(
        "bash_command",
        metavar="command",
        help="Bash command to run",
    )

    return parser.parse_args(argv)


def setup_logging(verbose: bool) -> None:
    """Configure logging level based on verbosity flag.

    Args:
        verbose: If True, set logging to DEBUG level; otherwise WARNING.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    # Also adjust the weft logger
    logging.getLogger("weft").setLevel(level)


def load_config(
    workdir: Path, no_sandbox: bool
) -> tuple[Path, Path, SandboxConfig | None]:
    """Load repository and sandbox configuration.

    Args:
        workdir: Target working directory (resolved to absolute path internally).
        no_sandbox: If True, skip sandbox configuration.

    Returns:
        Tuple of (repo_root, resolved_workdir, sandbox_config).
        sandbox_config is None when --no-sandbox is set.

    Raises:
        SystemExit: If workdir doesn't exist or is not in a git repo.
    """
    # Resolve workdir to absolute path
    workdir = workdir.resolve()
    if not workdir.exists():
        print(f"Error: Working directory does not exist: {workdir}", file=sys.stderr)
        sys.exit(1)
    if not workdir.is_dir():
        print(f"Error: Not a directory: {workdir}", file=sys.stderr)
        sys.exit(1)

    # Find repo root
    try:
        repo_root = find_repo_root(workdir)
    except RepoUtilsError as exc:
        print(
            f"Error: Not in a git repository: {exc}\n"
            f"Hint: Run this script from within a git repository, "
            f"or use --workdir to specify a path inside one.",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.debug("Repo root: %s", repo_root)
    logger.debug("Working directory: %s", workdir)

    if no_sandbox:
        logger.debug("Sandbox disabled via --no-sandbox")
        return repo_root, workdir, None

    # Load sandbox config
    config_path = repo_root / ".weft" / "config.toml"
    try:
        sandbox_config = load_sandbox_config(config_path)
    except SandboxConfigError as exc:
        print(
            f"Error: Failed to load sandbox config from {config_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.debug("Sandbox config loaded from %s", config_path)
    return repo_root, workdir, sandbox_config


def run_sdk(args: argparse.Namespace, workdir: Path, sandbox_config: SandboxConfig | None) -> int:
    """Run an SDK session with the given prompt.

    Args:
        args: Parsed command-line arguments.
        workdir: Resolved working directory.
        sandbox_config: Sandbox configuration, or None if disabled.

    Returns:
        Exit code (0 on success, 1 on failure).
    """
    model = get_effective_model(args.model, "code")
    if model is None:
        print("Error: Could not determine model to use.", file=sys.stderr)
        return 1
    logger.debug("Effective model: %s", model)

    try:
        sdk_settings_path = get_sdk_settings_path()
    except RuntimeError as exc:
        print(f"Error: Cannot locate SDK settings: {exc}", file=sys.stderr)
        return 1

    logger.debug("SDK settings path: %s", sdk_settings_path)
    logger.debug("Prompt: %s", args.prompt)

    try:
        session_id = run_sdk_session_sync(
            worktree_path=workdir,
            prompt_content=args.prompt,
            model=model,
            sdk_settings_path=sdk_settings_path,
            sandbox_config=sandbox_config,
        )
    except SDKRunnerError as exc:
        print(f"Error: SDK session failed: {exc}", file=sys.stderr)
        return 1

    print(f"Session ID: {session_id}")
    return 0


def run_bash(
    args: argparse.Namespace,
    workdir: Path,
    repo_root: Path,
    sandbox_config: SandboxConfig | None,
) -> int:
    """Run a bash command, optionally inside the bwrap sandbox.

    Args:
        args: Parsed command-line arguments.
        workdir: Resolved working directory.
        repo_root: Repository root path.
        sandbox_config: Sandbox configuration, or None if disabled.

    Returns:
        Exit code from the subprocess.
    """
    command = args.bash_command

    if sandbox_config is None:
        # No sandbox — run directly
        logger.debug("Running command directly (no sandbox): %s", command)
        result = subprocess.run(
            ["bash", "-c", command],
            cwd=workdir,
        )
        return result.returncode

    # Build and run sandboxed command
    repo_git_dir = repo_root / ".git"
    logger.debug("Building bwrap command with git dir: %s", repo_git_dir)

    cmd = build_bwrap_command(command, sandbox_config, workdir, repo_git_dir)
    logger.debug("Bwrap command: %s", cmd)

    result = subprocess.run(cmd, cwd=workdir)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command-line arguments. Defaults to sys.argv[1:].

    Returns:
        Exit code.
    """
    args = parse_args(argv)
    setup_logging(args.verbose)

    repo_root, workdir, sandbox_config = load_config(args.workdir, args.no_sandbox)

    if args.command == "sdk":
        return run_sdk(args, workdir, sandbox_config)
    elif args.command == "bash":
        return run_bash(args, workdir, repo_root, sandbox_config)
    else:
        # Should not happen due to required=True on subparsers
        print(f"Error: Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
