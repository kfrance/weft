"""Unit tests for the sandbox module.

Tests for the weft sandbox implementation including:
- SandboxConfig loading and validation
- Path expansion
- bwrap command generation
- Disallowed command pattern matching
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from weft.sandbox import (
    SandboxConfig,
    SandboxConfigError,
    build_bwrap_command,
    expand_path,
    find_claude_install_dir,
    get_disallowed_tools_args,
    load_sandbox_config,
    matches_disallowed_command,
    validate_config,
)


class TestExpandPath:
    """Tests for path expansion."""

    def test_expand_tilde_to_home(self) -> None:
        """Test that ~ is expanded to home directory."""
        result = expand_path("~/.weft/cache")
        # expand_path uses os.path.expanduser, so compare against that
        expected_home = os.path.expanduser("~")
        assert result == f"{expected_home}/.weft/cache"
        # Also verify it's an absolute path
        assert result.startswith("/")

    def test_expand_home_in_middle(self) -> None:
        """Test tilde expansion works at start of path."""
        result = expand_path("~/data/test")
        # Should be expanded to an absolute path
        assert result.startswith("/")
        assert result.endswith("data/test")
        # Verify ~ was actually expanded
        assert "~" not in result

    def test_absolute_path_unchanged(self) -> None:
        """Test that absolute paths without ~ are unchanged."""
        result = expand_path("/var/log/app")
        assert result == "/var/log/app"


class TestSandboxConfigValidation:
    """Tests for SandboxConfig validation."""

    def test_validate_config_no_collisions(self) -> None:
        """Test validation passes when paths are unique across lists."""
        config = SandboxConfig(
            read_paths=["/data/readonly"],
            write_paths=["/var/log"],
            read_write_paths=["~/.cache"],
        )
        # Should not raise
        validate_config(config)

    def test_validate_config_read_readwrite_collision(self) -> None:
        """Test validation fails when path in both read_paths and read_write_paths."""
        config = SandboxConfig(
            read_paths=["/data/shared"],
            read_write_paths=["/data/shared"],
        )
        with pytest.raises(SandboxConfigError) as exc_info:
            validate_config(config)
        assert "collision" in str(exc_info.value).lower()
        assert "/data/shared" in str(exc_info.value)

    def test_validate_config_tilde_expansion_collision(self) -> None:
        """Test validation detects collisions after ~ expansion."""
        home = os.path.expanduser("~")
        config = SandboxConfig(
            read_paths=["~/.config"],
            read_write_paths=[f"{home}/.config"],
        )
        with pytest.raises(SandboxConfigError) as exc_info:
            validate_config(config)
        assert "collision" in str(exc_info.value).lower()


class TestLoadSandboxConfig:
    """Tests for loading sandbox config from TOML files."""

    def test_load_config_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """Test that missing config file returns default empty config."""
        config_path = tmp_path / "nonexistent.toml"
        config = load_sandbox_config(config_path)

        assert config.read_paths == []
        assert config.write_paths == []
        assert config.read_write_paths == []
        assert config.disallowed_commands == []

    def test_load_config_valid_toml(self, tmp_path: Path) -> None:
        """Test loading valid sandbox configuration."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            """
[sandbox]
read_paths = ["/data/reference"]
read_write_paths = ["~/.weft/cache"]
disallowed_commands = ["git add:*", "git commit:*"]
""",
            encoding="utf-8",
        )

        config = load_sandbox_config(config_path)

        assert config.read_paths == ["/data/reference"]
        assert config.read_write_paths == ["~/.weft/cache"]
        assert config.disallowed_commands == ["git add:*", "git commit:*"]

    def test_load_config_missing_sandbox_section(self, tmp_path: Path) -> None:
        """Test that missing [sandbox] section returns defaults."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            """
[other_section]
key = "value"
""",
            encoding="utf-8",
        )

        config = load_sandbox_config(config_path)

        assert config.read_paths == []
        assert config.disallowed_commands == []

    def test_load_config_empty_lists(self, tmp_path: Path) -> None:
        """Test loading config with empty lists."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            """
[sandbox]
read_paths = []
disallowed_commands = []
""",
            encoding="utf-8",
        )

        config = load_sandbox_config(config_path)

        assert config.read_paths == []
        assert config.disallowed_commands == []

    def test_load_config_invalid_toml(self, tmp_path: Path) -> None:
        """Test that invalid TOML raises SandboxConfigError."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            """
[sandbox
read_paths = "not closed
""",
            encoding="utf-8",
        )

        with pytest.raises(SandboxConfigError) as exc_info:
            load_sandbox_config(config_path)
        assert "Invalid TOML" in str(exc_info.value)

    def test_load_config_invalid_list_type(self, tmp_path: Path) -> None:
        """Test that non-list value for path list raises error."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            """
[sandbox]
read_paths = "/single/path"
""",
            encoding="utf-8",
        )

        with pytest.raises(SandboxConfigError) as exc_info:
            load_sandbox_config(config_path)
        assert "should be a list" in str(exc_info.value)

    def test_load_config_invalid_item_type(self, tmp_path: Path) -> None:
        """Test that non-string item in list raises error."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            """
[sandbox]
read_paths = [123, "/valid/path"]
""",
            encoding="utf-8",
        )

        with pytest.raises(SandboxConfigError) as exc_info:
            load_sandbox_config(config_path)
        assert "should be a string" in str(exc_info.value)

    def test_load_config_path_collision_raises_error(self, tmp_path: Path) -> None:
        """Test that path collisions in config file are detected."""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            """
[sandbox]
read_paths = ["/data/shared"]
read_write_paths = ["/data/shared"]
""",
            encoding="utf-8",
        )

        with pytest.raises(SandboxConfigError) as exc_info:
            load_sandbox_config(config_path)
        assert "collision" in str(exc_info.value).lower()


class TestFindClaudeInstallDir:
    """Tests for dynamically finding Claude Code installation."""

    def test_returns_none_when_claude_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that None is returned when claude command is not in PATH."""
        # Empty PATH ensures claude won't be found
        monkeypatch.setenv("PATH", "")
        result = find_claude_install_dir()
        assert result is None

    def test_finds_claude_install_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test finding Claude installation via symlink resolution."""
        # Create a fake Claude installation structure
        install_dir = tmp_path / "share" / "claude-code" / "cli"
        install_dir.mkdir(parents=True)
        real_executable = install_dir / "claude-code"
        real_executable.write_text("#!/bin/bash\necho 'claude'")
        real_executable.chmod(0o755)

        # Create a symlink in a bin directory
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        symlink = bin_dir / "claude"
        symlink.symlink_to(real_executable)

        # Set PATH to include our bin directory
        monkeypatch.setenv("PATH", str(bin_dir))

        result = find_claude_install_dir()

        # Should resolve the symlink and return the real directory
        assert result == str(install_dir)

    def test_handles_direct_executable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test finding Claude when it's a direct executable (not symlink)."""
        # Create a direct executable
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        executable = bin_dir / "claude"
        executable.write_text("#!/bin/bash\necho 'claude'")
        executable.chmod(0o755)

        monkeypatch.setenv("PATH", str(bin_dir))

        result = find_claude_install_dir()

        # Should return the bin directory directly
        assert result == str(bin_dir)


class TestBuildBwrapCommand:
    """Tests for bwrap command generation."""

    def test_build_bwrap_command_includes_system_paths(self, tmp_path: Path) -> None:
        """Test that system paths are mounted read-only."""
        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)

        # Check bwrap is first
        assert cmd[0] == "bwrap"

        # Check system paths are mounted read-only
        cmd_str = " ".join(cmd)
        assert "--ro-bind /usr /usr" in cmd_str
        assert "--ro-bind /bin /bin" in cmd_str
        assert "--ro-bind /etc /etc" in cmd_str

    def test_build_bwrap_command_includes_special_mounts(self, tmp_path: Path) -> None:
        """Test that proc, dev, tmpfs, and /tmp/claude are mounted."""
        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        assert "--proc /proc" in cmd_str
        assert "--dev /dev" in cmd_str
        assert "--tmpfs /tmp" in cmd_str
        # /tmp/claude is bind-mounted on top of tmpfs for weft temp files
        assert "--bind /tmp/claude /tmp/claude" in cmd_str
        assert "--share-net" in cmd_str

    def test_build_bwrap_command_mounts_systemd_resolve(self, tmp_path: Path) -> None:
        """Test that /run/systemd/resolve is mounted for DNS on systemd distros."""
        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        # On systemd distros with /run/systemd/resolve, it should be mounted
        # This is needed because /etc/resolv.conf is often a symlink to this directory
        if Path("/run/systemd/resolve").exists():
            assert "--ro-bind /run/systemd/resolve /run/systemd/resolve" in cmd_str

    def test_build_bwrap_command_mounts_worktree_readwrite(self, tmp_path: Path) -> None:
        """Test that worktree is mounted read-write."""
        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        # Worktree should be mounted with --bind (read-write)
        assert f"--bind {worktree}" in cmd_str

    def test_build_bwrap_command_mounts_repo_git_dir(self, tmp_path: Path) -> None:
        """Test that repo .git directory is mounted read-write for git worktree operations."""
        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        # Simulate a separate .git directory (as in git worktrees)
        repo_git_dir = tmp_path / "main-repo" / ".git"
        repo_git_dir.mkdir(parents=True)

        cmd = build_bwrap_command("echo hello", config, worktree, repo_git_dir=repo_git_dir)
        cmd_str = " ".join(cmd)

        # Repo .git dir should be mounted with --bind (read-write)
        assert f"--bind {repo_git_dir.resolve()}" in cmd_str

    def test_build_bwrap_command_without_repo_git_dir(self, tmp_path: Path) -> None:
        """Test that omitting repo_git_dir doesn't cause errors."""
        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        # Should work without repo_git_dir
        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        # Should still have worktree mounted
        assert f"--bind {worktree}" in cmd_str

    def test_build_bwrap_command_mounts_claude_directories(self, tmp_path: Path) -> None:
        """Test that Claude directories are mounted appropriately."""
        # Path.home() is mocked to return fake home in unit tests
        home = str(Path.home())
        # Create .claude.json file so the mount condition is met
        claude_json = Path(home) / ".claude.json"
        claude_json.write_text("{}")

        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        # ~/.claude should be read-write (config/sessions) - always created
        assert f"--bind {home}/.claude" in cmd_str
        # ~/.claude.json should be read-write (global config with onboarding state)
        assert f"--bind {home}/.claude.json" in cmd_str

    def test_build_bwrap_command_mounts_gitconfig(self, tmp_path: Path) -> None:
        """Test that ~/.gitconfig is mounted read-only for git identity."""
        home = str(Path.home())
        # Create .gitconfig file so the mount condition is met
        gitconfig = Path(home) / ".gitconfig"
        gitconfig.write_text("[user]\n\tname = Test User\n\temail = test@example.com\n")

        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        # ~/.gitconfig should be read-only (git user identity)
        assert f"--ro-bind {home}/.gitconfig" in cmd_str

    def test_build_bwrap_command_mounts_claude_install_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that Claude installation directory is dynamically mounted."""
        # Create a fake Claude installation
        install_dir = tmp_path / "share" / "claude-code" / "cli"
        install_dir.mkdir(parents=True)
        real_executable = install_dir / "claude-code"
        real_executable.write_text("#!/bin/bash\necho 'claude'")
        real_executable.chmod(0o755)

        # Create a symlink in a bin directory
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        symlink = bin_dir / "claude"
        symlink.symlink_to(real_executable)

        # Set PATH to include our bin directory
        monkeypatch.setenv("PATH", str(bin_dir))

        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        # The installation directory should be mounted read-only
        assert f"--ro-bind {install_dir}" in cmd_str

    def test_build_bwrap_command_mounts_path_directories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that exact PATH directories are mounted (not parent dirs for security)."""
        home = str(Path.home())
        # Create bin directories in the fake home
        local_bin = Path(home) / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        cargo_bin = Path(home) / ".cargo" / "bin"
        cargo_bin.mkdir(parents=True, exist_ok=True)
        # Create a non-home directory (like /opt/bin)
        opt_bin = tmp_path / "opt" / "bin"
        opt_bin.mkdir(parents=True, exist_ok=True)

        # Set PATH to include these directories plus system paths
        monkeypatch.setenv("PATH", f"{local_bin}:{cargo_bin}:{opt_bin}:/usr/bin:/bin")

        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        # PATH directories should be mounted exactly (not parents) to avoid credential exposure
        # ~/.local/bin should be mounted (not ~/.local parent)
        assert f"--ro-bind {local_bin}" in cmd_str
        # ~/.cargo/bin should be mounted (not ~/.cargo which has credentials.toml)
        assert f"--ro-bind {cargo_bin}" in cmd_str
        # Verify parent dirs are NOT mounted
        assert f"--ro-bind {home}/.cargo {home}/.cargo" not in cmd_str
        # Non-home directories from PATH should be mounted as-is
        assert f"--ro-bind {opt_bin}" in cmd_str
        # System paths like /usr/bin should NOT be separately mounted (covered by /usr)
        assert "--ro-bind /usr/bin" not in cmd_str

    def test_build_bwrap_command_mounts_xdg_runtime_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that XDG_RUNTIME_DIR is mounted when available."""
        # Create a fake XDG_RUNTIME_DIR
        xdg_runtime = tmp_path / "runtime"
        xdg_runtime.mkdir()
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg_runtime))
        monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", f"unix:path={xdg_runtime}/bus")

        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        # XDG_RUNTIME_DIR should be mounted read-write
        assert f"--bind {xdg_runtime}" in cmd_str
        # Environment variables should be set
        assert f"--setenv XDG_RUNTIME_DIR {xdg_runtime}" in cmd_str
        assert "--setenv DBUS_SESSION_BUS_ADDRESS" in cmd_str

    def test_build_bwrap_command_forwards_ssh_agent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that SSH agent socket is forwarded when available."""
        # Create a fake SSH agent socket directory
        ssh_agent_dir = tmp_path / "ssh-agent"
        ssh_agent_dir.mkdir()
        ssh_socket = ssh_agent_dir / "agent.12345"
        ssh_socket.touch()  # Create the socket file
        monkeypatch.setenv("SSH_AUTH_SOCK", str(ssh_socket))
        # Clear XDG_RUNTIME_DIR to test standalone SSH mount
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

        # Create ~/.ssh directory with config file in the fake home (conftest patches Path.home())
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir(exist_ok=True)
        ssh_dir = fake_home / ".ssh"
        ssh_dir.mkdir()
        ssh_config = ssh_dir / "config"
        ssh_config.touch()  # Create empty config file

        sandbox_config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("git push", sandbox_config, worktree)
        cmd_str = " ".join(cmd)

        # SSH agent socket directory should be mounted
        assert f"--bind {ssh_agent_dir}" in cmd_str
        # SSH_AUTH_SOCK should be set
        assert f"--setenv SSH_AUTH_SOCK {ssh_socket}" in cmd_str
        # ~/.ssh should be mounted read-only
        assert f"--ro-bind {ssh_dir}" in cmd_str
        # GIT_SSH_COMMAND should use user's config file
        assert f"--setenv GIT_SSH_COMMAND ssh -F {ssh_config}" in cmd_str

    def test_build_bwrap_command_ssh_agent_in_xdg_runtime(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test SSH agent socket already covered by XDG_RUNTIME_DIR is not double-mounted."""
        # Create XDG_RUNTIME_DIR containing SSH socket
        xdg_runtime = tmp_path / "runtime"
        xdg_runtime.mkdir()
        ssh_socket = xdg_runtime / "ssh-agent" / "agent.12345"
        ssh_socket.parent.mkdir()
        ssh_socket.touch()
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg_runtime))
        monkeypatch.setenv("SSH_AUTH_SOCK", str(ssh_socket))

        # Create ~/.ssh directory in the fake home (conftest patches Path.home())
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir(exist_ok=True)
        ssh_dir = fake_home / ".ssh"
        ssh_dir.mkdir()

        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("git push", config, worktree)
        cmd_str = " ".join(cmd)

        # XDG_RUNTIME_DIR is mounted, so SSH socket parent shouldn't be separately mounted
        # Count occurrences of the ssh-agent dir - should only appear once (from XDG mount)
        assert cmd_str.count(f"--bind {xdg_runtime}") == 1
        # But SSH_AUTH_SOCK should still be set
        assert f"--setenv SSH_AUTH_SOCK {ssh_socket}" in cmd_str

    def test_build_bwrap_command_ssh_config_symlink(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that symlinked SSH config has its target directory mounted."""
        # Create SSH agent socket
        ssh_agent_dir = tmp_path / "ssh-agent"
        ssh_agent_dir.mkdir()
        ssh_socket = ssh_agent_dir / "agent.12345"
        ssh_socket.touch()
        monkeypatch.setenv("SSH_AUTH_SOCK", str(ssh_socket))
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

        # Create fake home with ~/.ssh
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir(exist_ok=True)
        ssh_dir = fake_home / ".ssh"
        ssh_dir.mkdir()

        # Create dotfiles directory with actual config
        dotfiles_dir = tmp_path / "dotfiles"
        dotfiles_dir.mkdir()
        real_config = dotfiles_dir / "ssh_config"
        real_config.write_text("# SSH config")

        # Symlink ~/.ssh/config -> dotfiles/ssh_config
        ssh_config_link = ssh_dir / "config"
        ssh_config_link.symlink_to(real_config)

        sandbox_config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("git push", sandbox_config, worktree)
        cmd_str = " ".join(cmd)

        # Both ~/.ssh and dotfiles dir should be mounted
        assert f"--ro-bind {ssh_dir}" in cmd_str
        assert f"--ro-bind {dotfiles_dir}" in cmd_str
        # GIT_SSH_COMMAND should use the symlink path
        assert f"--setenv GIT_SSH_COMMAND ssh -F {ssh_config_link}" in cmd_str

    def test_build_bwrap_command_ssh_no_config_uses_dev_null(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that missing SSH config falls back to /dev/null."""
        # Create SSH agent socket
        ssh_agent_dir = tmp_path / "ssh-agent"
        ssh_agent_dir.mkdir()
        ssh_socket = ssh_agent_dir / "agent.12345"
        ssh_socket.touch()
        monkeypatch.setenv("SSH_AUTH_SOCK", str(ssh_socket))
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

        # Create fake home with ~/.ssh but NO config file
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir(exist_ok=True)
        ssh_dir = fake_home / ".ssh"
        ssh_dir.mkdir()
        # Note: not creating config file

        sandbox_config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("git push", sandbox_config, worktree)
        cmd_str = " ".join(cmd)

        # Should use /dev/null to skip system config
        assert "--setenv GIT_SSH_COMMAND ssh -F /dev/null" in cmd_str

    def test_build_bwrap_command_mounts_user_paths(self, tmp_path: Path) -> None:
        """Test that user-configured paths are mounted."""
        # Create paths to mount
        readonly_path = tmp_path / "readonly"
        readonly_path.mkdir()
        readwrite_path = tmp_path / "readwrite"
        # Note: readwrite paths are created automatically

        config = SandboxConfig(
            read_paths=[str(readonly_path)],
            read_write_paths=[str(readwrite_path)],
        )
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        # Read-only path should use --ro-bind
        assert f"--ro-bind {readonly_path}" in cmd_str
        # Read-write path should use --bind
        assert f"--bind {readwrite_path}" in cmd_str

    def test_build_bwrap_command_sets_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that HOME and PATH are set correctly."""
        # Set a known PATH for testing
        test_path = "/usr/bin:/bin:/custom/path"
        monkeypatch.setenv("PATH", test_path)

        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        home = str(Path.home())
        assert f"--setenv HOME {home}" in cmd_str
        # PATH should be passed through from the environment
        assert f"--setenv PATH {test_path}" in cmd_str

    def test_build_bwrap_command_sets_cwd(self, tmp_path: Path) -> None:
        """Test that working directory is set to worktree."""
        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("echo hello", config, worktree)
        cmd_str = " ".join(cmd)

        assert f"--chdir {worktree}" in cmd_str

    def test_build_bwrap_command_includes_command(self, tmp_path: Path) -> None:
        """Test that the actual command is appended after --."""
        config = SandboxConfig()
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        cmd = build_bwrap_command("my-command --flag arg", config, worktree)

        # Find position of "--"
        separator_idx = cmd.index("--")
        # After separator should be bash -c <command>
        assert cmd[separator_idx + 1] == "bash"
        assert cmd[separator_idx + 2] == "-c"
        assert cmd[separator_idx + 3] == "my-command --flag arg"


class TestGetDisallowedToolsArgs:
    """Tests for disallowed tools argument generation."""

    def test_empty_config_returns_empty_list(self) -> None:
        """Test that empty disallowed_commands returns empty list."""
        config = SandboxConfig(disallowed_commands=[])
        args = get_disallowed_tools_args(config)
        assert args == []

    def test_single_pattern(self) -> None:
        """Test generating args for single pattern."""
        config = SandboxConfig(disallowed_commands=["git add:*"])
        args = get_disallowed_tools_args(config)

        assert args[0] == "--disallowed-tools"
        assert "Bash(git add:*)" in args

    def test_multiple_patterns(self) -> None:
        """Test generating args for multiple patterns."""
        config = SandboxConfig(
            disallowed_commands=["git add:*", "git commit:*", "docker:*"]
        )
        args = get_disallowed_tools_args(config)

        assert args[0] == "--disallowed-tools"
        assert "Bash(git add:*)" in args
        assert "Bash(git commit:*)" in args
        assert "Bash(docker:*)" in args


class TestMatchesDisallowedCommand:
    """Tests for command pattern matching."""

    def test_prefix_pattern_matches_command(self) -> None:
        """Test that prefix:* pattern matches commands starting with prefix."""
        config = SandboxConfig(disallowed_commands=["git add:*"])

        is_blocked, pattern = matches_disallowed_command("git add file.txt", config)
        assert is_blocked is True
        assert pattern == "git add:*"

    def test_prefix_pattern_matches_with_flags(self) -> None:
        """Test that prefix matches commands with flags."""
        config = SandboxConfig(disallowed_commands=["git push:*"])

        is_blocked, _ = matches_disallowed_command("git push --force origin main", config)
        assert is_blocked is True

    def test_prefix_pattern_no_match(self) -> None:
        """Test that non-matching command is not blocked."""
        config = SandboxConfig(disallowed_commands=["git add:*"])

        is_blocked, pattern = matches_disallowed_command("git status", config)
        assert is_blocked is False
        assert pattern is None

    def test_multiple_patterns_first_match(self) -> None:
        """Test that first matching pattern is returned."""
        config = SandboxConfig(
            disallowed_commands=["git add:*", "git commit:*", "git push:*"]
        )

        is_blocked, pattern = matches_disallowed_command("git commit -m 'test'", config)
        assert is_blocked is True
        assert pattern == "git commit:*"

    def test_exact_match_pattern(self) -> None:
        """Test exact match patterns (no wildcard)."""
        config = SandboxConfig(disallowed_commands=["rm -rf /"])

        is_blocked, pattern = matches_disallowed_command("rm -rf /", config)
        assert is_blocked is True
        assert pattern == "rm -rf /"

        # Similar but not exact should not match
        is_blocked, _ = matches_disallowed_command("rm -rf /tmp", config)
        assert is_blocked is False

    def test_empty_config_allows_all(self) -> None:
        """Test that empty config allows all commands."""
        config = SandboxConfig(disallowed_commands=[])

        is_blocked, _ = matches_disallowed_command("git add file.txt", config)
        assert is_blocked is False

    def test_allowed_git_commands(self) -> None:
        """Test that git status, diff, log are allowed when only mutations blocked."""
        config = SandboxConfig(
            disallowed_commands=["git add:*", "git commit:*", "git push:*"]
        )

        # These should be allowed
        for cmd in ["git status", "git diff", "git log --oneline", "git branch -a"]:
            is_blocked, _ = matches_disallowed_command(cmd, config)
            assert is_blocked is False, f"Command should be allowed: {cmd}"
