from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


def _write_plan(path: Path, data: dict, body: str = "# CLI Plan") -> None:
    yaml_block = yaml.safe_dump(data, sort_keys=False).strip()
    content = f"---\n{yaml_block}\n---\n\n{body}\n"
    path.write_text(content, encoding="utf-8")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src_dir = Path(__file__).resolve().parent.parent / "src"
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(src_dir)
        if not existing_pythonpath
        else f"{str(src_dir)}{os.pathsep}{existing_pythonpath}"
    )
    return subprocess.run(
        [sys.executable, "-m", "lw_coder.cli", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def test_cli_success(git_repo):
    repo = git_repo
    plan_path = repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": repo.latest_commit(),
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-cli-success",
            "branch_name": "feature/cli-test",
            "status": "draft",
        },
        body="# Refactor API\n\nEnsure docstrings are accurate."
    )

    result = _run_cli("code", str(plan_path))

    assert result.returncode == 0
    assert "Plan validation succeeded" in result.stdout
    assert result.stderr == ""


def test_cli_failure_invalid_sha(git_repo):
    repo = git_repo
    plan_path = repo.path / "plan.md"
    _write_plan(
        plan_path,
        {
            "git_sha": "f" * 40,
            "evaluation_notes": ["All tests pass"],
            "plan_id": "plan-cli-invalid",
            "branch_name": "feature/invalid-sha",
            "status": "draft",
        },
    )

    result = _run_cli("code", str(plan_path))

    assert result.returncode == 1
    assert "Plan validation failed" in result.stderr
    assert "does not exist" in result.stderr
    assert result.stdout == ""
