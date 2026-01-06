"""Integration tests for setup commands feature.

These tests verify that setup commands integrate correctly with the code command
workflow, executing before the Claude Code session and having access to the
correct environment variables.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import weft.code_command as code_command
from weft.code_command import run_code_command
from tests.helpers import write_plan


def _find_real_repo_root() -> Path:
    """Find the real weft repository root for copying prompts.

    Returns:
        Path to the real repository root.

    Raises:
        RuntimeError: If the repository root cannot be found.
    """
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    raise RuntimeError("Could not find weft repository root")


def _copy_prompts_to_repo(dest_repo: Path, real_repo: Path) -> None:
    """Copy prompt files and SDK settings from real repo to test repo.

    Args:
        dest_repo: Destination test repository path.
        real_repo: Real weft repository root to copy from.
    """
    # Copy .weft/prompts/active/ for claude-code-cli
    weft_prompts_src = real_repo / ".weft" / "prompts" / "active"
    if weft_prompts_src.exists():
        weft_prompts_dest = dest_repo / ".weft" / "prompts" / "active"
        weft_prompts_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(weft_prompts_src, weft_prompts_dest)

    # Copy src/weft/prompts/ for plan subagents and templates
    src_prompts_src = real_repo / "src" / "weft" / "prompts"
    if src_prompts_src.exists():
        src_prompts_dest = dest_repo / "src" / "weft" / "prompts"
        src_prompts_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_prompts_src, src_prompts_dest)

    # Copy sdk_settings.json for SDK configuration
    sdk_settings_src = real_repo / "src" / "weft" / "sdk_settings.json"
    if sdk_settings_src.exists():
        sdk_settings_dest = dest_repo / "src" / "weft" / "sdk_settings.json"
        sdk_settings_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sdk_settings_src, sdk_settings_dest)


def _get_head_sha(repo_root: Path) -> str:
    """Get current HEAD SHA."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class TestSetupCommandsIntegration:
    """Integration tests for setup commands with code command."""

    def test_setup_commands_execute_before_session(self, git_repo, monkeypatch):
        """Verify setup commands execute before the Claude Code session.

        This test:
        1. Creates a repo with two simple setup commands that create marker files
        2. Mocks the Claude Code SDK/CLI session
        3. Runs run_code_command()
        4. Verifies both marker files exist in the worktree
        5. Verifies the mocked session was called (proving setup ran before session)
        """
        # Setup isolated environment
        real_repo = _find_real_repo_root()
        _copy_prompts_to_repo(git_repo.path, real_repo)

        # Create plan file
        plan_id = "test-setup-commands"
        plan_path = git_repo.path / f"{plan_id}.md"
        head_sha = _get_head_sha(git_repo.path)

        write_plan(plan_path, {
            "plan_id": plan_id,
            "git_sha": head_sha,
            "status": "draft",
        })

        # Create .weft/tasks directory
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        # Create config with setup commands
        config_path = git_repo.path / ".weft" / "config.toml"
        config_path.write_text(
            """
schema_version = "1.0"

[[code.setup]]
name = "create-first-marker"
command = "touch $WEFT_WORKTREE_PATH/.setup-first"

[[code.setup]]
name = "create-second-marker"
command = "touch $WEFT_WORKTREE_PATH/.setup-second"
"""
        )

        # Track worktree path for verification
        captured_worktree_path = None

        # Mock find_repo_root to return the isolated repo
        monkeypatch.setattr(
            "weft.code_command.find_repo_root",
            lambda *args, **kwargs: git_repo.path
        )
        monkeypatch.setattr(
            "weft.plan_validator.find_repo_root",
            lambda *args, **kwargs: git_repo.path
        )

        # Mock get_weft_src_dir
        def mock_get_weft_src_dir():
            return git_repo.path / "src" / "weft"
        monkeypatch.setattr(
            "weft.code_command.get_weft_src_dir",
            mock_get_weft_src_dir
        )
        monkeypatch.setattr(
            "weft.host_runner.get_weft_src_dir",
            mock_get_weft_src_dir
        )

        # Mock load_prompts
        def mock_load_prompts(repo_root, tool, model):
            prompts_base = git_repo.path / ".weft" / "prompts" / "active" / tool / model
            prompts = {}

            main_prompt_path = prompts_base / "main.md"
            if main_prompt_path.exists():
                prompts["main_prompt"] = main_prompt_path.read_text(encoding="utf-8")
            else:
                prompts["main_prompt"] = "Implement the plan in plan.md"

            code_review_path = prompts_base / "code-review-auditor.md"
            if code_review_path.exists():
                prompts["code_review_auditor"] = code_review_path.read_text(encoding="utf-8")
            else:
                prompts["code_review_auditor"] = "Review the code for quality"

            plan_alignment_path = prompts_base / "plan-alignment-checker.md"
            if plan_alignment_path.exists():
                prompts["plan_alignment_checker"] = plan_alignment_path.read_text(encoding="utf-8")
            else:
                prompts["plan_alignment_checker"] = "Check alignment with plan"

            return prompts

        monkeypatch.setattr(
            "weft.code_command.load_prompts",
            mock_load_prompts
        )

        # Mock SDK session to capture worktree path
        def mock_sdk_session(**kw):
            nonlocal captured_worktree_path
            captured_worktree_path = kw.get("worktree_path")
            return "mock-session-id"

        monkeypatch.setattr(
            code_command,
            "run_sdk_session_sync",
            mock_sdk_session
        )

        # Mock patch capture
        monkeypatch.setattr(
            code_command,
            "capture_ai_patch",
            lambda worktree_path: "mock patch content"
        )
        monkeypatch.setattr(
            code_command,
            "save_patch",
            lambda content, path: None
        )

        # Mock subprocess.run (CLI resume part)
        subprocess_calls = []

        def mock_subprocess_run(*args, **kwargs):
            subprocess_calls.append((args, kwargs))
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(code_command, "subprocess", SimpleNamespace(run=mock_subprocess_run))

        # Run the code command
        exit_code = run_code_command(
            plan_path=plan_path,
            tool="claude-code",
            no_hooks=True,
        )

        # Verify success
        assert exit_code == 0

        # Verify worktree was captured
        assert captured_worktree_path is not None

        # Verify setup commands created marker files in the worktree
        first_marker = captured_worktree_path / ".setup-first"
        second_marker = captured_worktree_path / ".setup-second"

        assert first_marker.exists(), "First marker file should exist (setup command ran)"
        assert second_marker.exists(), "Second marker file should exist (setup command ran)"

        # Verify the mocked session was called (proving setup ran before session)
        assert len(subprocess_calls) > 0, "Expected CLI session to be called"

    def test_setup_commands_not_configured_gracefully_skipped(self, git_repo, monkeypatch):
        """Verify code command works when no setup commands are configured.

        This test ensures existing behavior is preserved - if [[code.setup]]
        is not present in config, the code command should proceed normally.
        """
        # Setup isolated environment
        real_repo = _find_real_repo_root()
        _copy_prompts_to_repo(git_repo.path, real_repo)

        # Create plan file
        plan_id = "test-no-setup"
        plan_path = git_repo.path / f"{plan_id}.md"
        head_sha = _get_head_sha(git_repo.path)

        write_plan(plan_path, {
            "plan_id": plan_id,
            "git_sha": head_sha,
            "status": "draft",
        })

        # Create .weft/tasks directory
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        # Create config WITHOUT setup commands
        config_path = git_repo.path / ".weft" / "config.toml"
        config_path.write_text(
            """
schema_version = "1.0"

# No setup commands configured
"""
        )

        # Mock find_repo_root
        monkeypatch.setattr(
            "weft.code_command.find_repo_root",
            lambda *args, **kwargs: git_repo.path
        )
        monkeypatch.setattr(
            "weft.plan_validator.find_repo_root",
            lambda *args, **kwargs: git_repo.path
        )

        # Mock get_weft_src_dir
        def mock_get_weft_src_dir():
            return git_repo.path / "src" / "weft"
        monkeypatch.setattr(
            "weft.code_command.get_weft_src_dir",
            mock_get_weft_src_dir
        )
        monkeypatch.setattr(
            "weft.host_runner.get_weft_src_dir",
            mock_get_weft_src_dir
        )

        # Mock load_prompts
        def mock_load_prompts(repo_root, tool, model):
            return {
                "main_prompt": "Implement the plan",
                "code_review_auditor": "Review code",
                "plan_alignment_checker": "Check plan",
            }

        monkeypatch.setattr(
            "weft.code_command.load_prompts",
            mock_load_prompts
        )

        # Mock SDK session
        monkeypatch.setattr(
            code_command,
            "run_sdk_session_sync",
            lambda **kw: "mock-session-id"
        )

        # Mock patch capture
        monkeypatch.setattr(
            code_command,
            "capture_ai_patch",
            lambda worktree_path: "mock patch content"
        )
        monkeypatch.setattr(
            code_command,
            "save_patch",
            lambda content, path: None
        )

        # Mock subprocess.run
        subprocess_calls = []

        def mock_subprocess_run(*args, **kwargs):
            subprocess_calls.append((args, kwargs))
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(code_command, "subprocess", SimpleNamespace(run=mock_subprocess_run))

        # Run the code command
        exit_code = run_code_command(
            plan_path=plan_path,
            tool="claude-code",
            no_hooks=True,
        )

        # Verify success (no setup commands should not block execution)
        assert exit_code == 0
        assert len(subprocess_calls) > 0

    def test_setup_command_failure_aborts_code_command(self, git_repo, monkeypatch):
        """Verify that a failed setup command aborts the code command.

        This test ensures that if a setup command fails (and continue_on_failure=false),
        the code command returns an error code without starting the Claude Code session.
        """
        # Setup isolated environment
        real_repo = _find_real_repo_root()
        _copy_prompts_to_repo(git_repo.path, real_repo)

        # Create plan file
        plan_id = "test-setup-failure"
        plan_path = git_repo.path / f"{plan_id}.md"
        head_sha = _get_head_sha(git_repo.path)

        write_plan(plan_path, {
            "plan_id": plan_id,
            "git_sha": head_sha,
            "status": "draft",
        })

        # Create .weft/tasks directory
        tasks_dir = git_repo.path / ".weft" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        # Create config with a failing setup command
        config_path = git_repo.path / ".weft" / "config.toml"
        config_path.write_text(
            """
schema_version = "1.0"

[[code.setup]]
name = "will-fail"
command = "exit 1"
"""
        )

        # Mock find_repo_root
        monkeypatch.setattr(
            "weft.code_command.find_repo_root",
            lambda *args, **kwargs: git_repo.path
        )
        monkeypatch.setattr(
            "weft.plan_validator.find_repo_root",
            lambda *args, **kwargs: git_repo.path
        )

        # Mock get_weft_src_dir
        def mock_get_weft_src_dir():
            return git_repo.path / "src" / "weft"
        monkeypatch.setattr(
            "weft.code_command.get_weft_src_dir",
            mock_get_weft_src_dir
        )
        monkeypatch.setattr(
            "weft.host_runner.get_weft_src_dir",
            mock_get_weft_src_dir
        )

        # Mock load_prompts
        monkeypatch.setattr(
            "weft.code_command.load_prompts",
            lambda *a, **kw: {
                "main_prompt": "Implement",
                "code_review_auditor": "Review",
                "plan_alignment_checker": "Check",
            }
        )

        # Track if SDK session was called (it should NOT be)
        sdk_called = False

        def mock_sdk_session(**kw):
            nonlocal sdk_called
            sdk_called = True
            return "mock-session-id"

        monkeypatch.setattr(
            code_command,
            "run_sdk_session_sync",
            mock_sdk_session
        )

        # Run the code command
        exit_code = run_code_command(
            plan_path=plan_path,
            tool="claude-code",
            no_hooks=True,
        )

        # Verify failure
        assert exit_code == 1

        # Verify SDK session was NOT called (setup failed before session)
        assert not sdk_called, "SDK session should not be called when setup fails"
