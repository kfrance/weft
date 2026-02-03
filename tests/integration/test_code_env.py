"""Integration tests for [code.env] configuration feature.

These tests verify that environment variables from [code.env] are correctly
injected into setup commands during the code command workflow.
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
    # Copy .weft/prompts/active/ for claude-code
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


class TestCodeEnvIntegration:
    """Integration tests for [code.env] with code command."""

    def test_code_env_available_to_setup_commands(self, git_repo, monkeypatch):
        """Verify [code.env] variables are available to setup commands.

        This test:
        1. Creates a repo with [code.env] containing TEST_VAR = "test_value"
        2. Setup command writes $TEST_VAR to a marker file
        3. Verifies marker file contains "test_value"
        """
        # Setup isolated environment
        real_repo = _find_real_repo_root()
        _copy_prompts_to_repo(git_repo.path, real_repo)

        # Create plan file
        plan_id = "test-code-env"
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

        # Track worktree path for verification
        captured_worktree_path = None

        # Create config with [code.env] and setup command
        config_path = git_repo.path / ".weft" / "config.toml"
        config_path.write_text(
            """
schema_version = "1.0"

[code.env]
TEST_VAR = "test_value"
ANOTHER_VAR = "another_value"

[[code.setup]]
name = "write-env-vars"
command = "echo $TEST_VAR > $WEFT_WORKTREE_PATH/.env-marker && echo $ANOTHER_VAR >> $WEFT_WORKTREE_PATH/.env-marker"
"""
        )

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
            "weft.paths.get_weft_src_dir",
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

        # Verify setup command received [code.env] variables
        env_marker = captured_worktree_path / ".env-marker"
        assert env_marker.exists(), "Env marker file should exist (setup command ran)"

        marker_content = env_marker.read_text().strip()
        lines = marker_content.split("\n")
        assert lines[0] == "test_value", f"TEST_VAR should be 'test_value', got '{lines[0]}'"
        assert lines[1] == "another_value", f"ANOTHER_VAR should be 'another_value', got '{lines[1]}'"

    def test_code_env_empty_section_works(self, git_repo, monkeypatch):
        """Verify empty [code.env] section is valid and doesn't break workflow."""
        # Setup isolated environment
        real_repo = _find_real_repo_root()
        _copy_prompts_to_repo(git_repo.path, real_repo)

        # Create plan file
        plan_id = "test-empty-code-env"
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

        # Create config with empty [code.env]
        config_path = git_repo.path / ".weft" / "config.toml"
        config_path.write_text(
            """
schema_version = "1.0"

[code.env]
# Empty - no variables
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
            "weft.paths.get_weft_src_dir",
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
        def mock_subprocess_run(*args, **kwargs):
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(code_command, "subprocess", SimpleNamespace(run=mock_subprocess_run))

        # Run the code command
        exit_code = run_code_command(
            plan_path=plan_path,
            tool="claude-code",
            no_hooks=True,
        )

        # Verify success (empty [code.env] should not break anything)
        assert exit_code == 0

    def test_code_env_invalid_key_fails(self, git_repo, monkeypatch):
        """Verify invalid [code.env] key causes code command to fail."""
        # Setup isolated environment
        real_repo = _find_real_repo_root()
        _copy_prompts_to_repo(git_repo.path, real_repo)

        # Create plan file
        plan_id = "test-invalid-code-env"
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

        # Create config with invalid [code.env] key (contains hyphen)
        config_path = git_repo.path / ".weft" / "config.toml"
        config_path.write_text(
            """
schema_version = "1.0"

[code.env]
INVALID-KEY = "value"
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
            "weft.paths.get_weft_src_dir",
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

        # Verify failure (invalid key should cause error)
        assert exit_code == 1

        # Verify SDK session was NOT called (validation failed before session)
        assert not sdk_called, "SDK session should not be called when [code.env] validation fails"
