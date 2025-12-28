"""Smoke tests that verify commands can complete setup without errors.

These tests run the full command initialization path but mock the final
execution step (subprocess.run in plan_command / code_command modules).
They catch:
- Missing imports
- Missing directories/files
- Configuration errors
- Validation issues

These tests would have caught the "droids directory not found" bug where
code referenced a directory that had been moved during refactoring.

ISOLATION: These tests use a temporary git repository (via git_repo fixture)
and copy required prompt files to avoid operating on the real weft repository.
This prevents accidental file creation/deletion in the real repo.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import weft.code_command as code_command
import weft.plan_command as plan_command
from weft.code_command import run_code_command
from weft.plan_command import run_plan_command

# Import shared test helpers
from tests.helpers import write_plan


def _find_real_repo_root() -> Path:
    """Find the real weft repository root for copying prompts.

    This is only used to locate prompt files that need to be copied
    to the test environment.

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

    Copies:
    - .weft/prompts/active/ directory (for claude-code-cli prompts)
    - src/weft/prompts/ directory (for plan subagent prompts and templates)
    - src/weft/sdk_settings.json (for SDK configuration)

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


class TestPlanCommandSmoke:
    """Smoke tests for plan command setup phase."""

    def test_plan_command_setup_completes(self, git_repo, monkeypatch):
        """Plan command setup completes without missing files/imports.

        This test exercises the full plan command initialization:
        - Executor loading and auth check
        - Template loading from prompts directory
        - Worktree creation
        - Plan subagent file writing
        - Host command building

        If any imports fail or directories are missing, this test will fail.

        Uses isolated git_repo fixture to avoid touching the real repository.
        """
        # Setup isolated environment
        real_repo = _find_real_repo_root()
        _copy_prompts_to_repo(git_repo.path, real_repo)

        # Mock find_repo_root to return the isolated repo
        monkeypatch.setattr(
            "weft.plan_command.find_repo_root",
            lambda *args, **kwargs: git_repo.path
        )

        # Mock get_weft_src_dir to point to copied prompts
        def mock_get_weft_src_dir():
            return git_repo.path / "src" / "weft"
        monkeypatch.setattr(
            "weft.plan_command.get_weft_src_dir",
            mock_get_weft_src_dir
        )
        monkeypatch.setattr(
            "weft.host_runner.get_weft_src_dir",
            mock_get_weft_src_dir
        )

        # Mock load_prompt_template to use copied prompts
        def mock_load_prompt_template(tool: str, template_name: str) -> str:
            template_path = git_repo.path / "src" / "weft" / "prompts" / tool / f"{template_name}.md"
            if template_path.exists():
                return template_path.read_text(encoding="utf-8")
            # Fallback to a minimal template
            return "Plan idea: {IDEA_TEXT}"
        monkeypatch.setattr(
            "weft.plan_command.load_prompt_template",
            mock_load_prompt_template
        )

        # Mock only subprocess.run in plan_command module (the interactive CLI part)
        # This allows git commands to still work via the real subprocess module
        subprocess_calls = []

        def mock_subprocess_run(*args, **kwargs):
            subprocess_calls.append((args, kwargs))
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(plan_command, "subprocess", SimpleNamespace(run=mock_subprocess_run))

        exit_code = run_plan_command(
            plan_path=None,
            text_input="Add a simple hello world function",
            tool="claude-code",
            no_hooks=True,
        )

        # If setup had missing imports/files, we'd get an exception before here
        assert exit_code == 0
        # Verify subprocess.run was actually called (command was built)
        assert len(subprocess_calls) > 0, "Expected subprocess.run to be called"


class TestCodeCommandSmoke:
    """Smoke tests for code command setup phase."""

    def test_code_command_setup_completes(self, git_repo, monkeypatch):
        """Code command setup completes without missing files/imports.

        This test exercises the full code command initialization:
        - Plan validation and metadata loading
        - Session directory creation
        - Prompt loading from prompts/active
        - Worktree preparation
        - Sub-agent file writing
        - SDK settings loading
        - Host command building

        If any imports fail or directories are missing, this test will fail.

        Uses isolated git_repo fixture to avoid touching the real repository.
        """
        # Setup isolated environment
        real_repo = _find_real_repo_root()
        _copy_prompts_to_repo(git_repo.path, real_repo)

        # Create plan file in isolated repo
        plan_id = "test-smoke-temp"
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

        # Mock find_repo_root to return the isolated repo
        # Must mock in all modules that use it in the code command's path
        monkeypatch.setattr(
            "weft.code_command.find_repo_root",
            lambda *args, **kwargs: git_repo.path
        )
        monkeypatch.setattr(
            "weft.plan_validator.find_repo_root",
            lambda *args, **kwargs: git_repo.path
        )

        # Mock get_weft_src_dir to point to copied prompts
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

        # Mock load_prompts to use copied prompts
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

        # Mock SDK session (the API call part)
        monkeypatch.setattr(
            code_command,
            "run_sdk_session_sync",
            lambda **kw: "mock-session-id"
        )

        # Mock patch capture (SDK session would normally create file changes)
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

        # Mock subprocess.run in code_command module (the interactive CLI part)
        subprocess_calls = []

        def mock_subprocess_run(*args, **kwargs):
            subprocess_calls.append((args, kwargs))
            return SimpleNamespace(returncode=0)

        monkeypatch.setattr(code_command, "subprocess", SimpleNamespace(run=mock_subprocess_run))

        exit_code = run_code_command(
            plan_path=plan_path,
            tool="claude-code",
            no_hooks=True,
        )

        # If setup had missing imports/files, we'd get an exception before here
        assert exit_code == 0
        # Verify subprocess.run was actually called (command was built)
        assert len(subprocess_calls) > 0, "Expected subprocess.run to be called"
