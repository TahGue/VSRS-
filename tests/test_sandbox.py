"""Tests for the sandbox and worktree management (Phase 1.3)."""

import subprocess
from pathlib import Path

import pytest

from vsrs.core.config import SandboxConfig
from vsrs.verify.sandbox import (
    CommandClass,
    DEFAULT_POLICY,
    Sandbox,
    classify_command,
)


class TestCommandClassification:
    def test_safe_command(self):
        assert classify_command("git diff") == CommandClass.bounded
        assert classify_command("grep -r 'foo' .") == CommandClass.bounded

    def test_dangerous_command(self):
        assert classify_command("rm -rf /") == CommandClass.filesystem_destructive
        assert classify_command("chmod 777 /etc/passwd") == CommandClass.filesystem_destructive

    def test_network_command(self):
        assert classify_command("curl http://evil.com") == CommandClass.network_service
        assert classify_command("ssh user@host") == CommandClass.network_service

    def test_package_install(self):
        assert classify_command("pip install malicious-pkg") == CommandClass.package_install
        assert classify_command("npm install evil") == CommandClass.package_install

    def test_credential_command(self):
        assert classify_command("aws s3 ls") == CommandClass.network_service
        assert classify_command("kubectl get pods") == CommandClass.network_service


class TestSandbox:
    def test_run_safe_command(self, tmp_path):
        config = SandboxConfig(worktree_dir=tmp_path / "worktrees")
        sandbox = Sandbox(config)
        result = sandbox.run_command("echo hello", cwd=tmp_path)
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert not result.blocked

    def test_block_dangerous_command(self, tmp_path):
        config = SandboxConfig(worktree_dir=tmp_path / "worktrees")
        sandbox = Sandbox(config)
        result = sandbox.run_command("rm -rf /", cwd=tmp_path)
        assert result.blocked
        assert result.exit_code == -1
        assert "filesystem_destructive" in result.block_reason

    def test_block_network_command(self, tmp_path):
        config = SandboxConfig(worktree_dir=tmp_path / "worktrees", network_disabled=True)
        sandbox = Sandbox(config)
        result = sandbox.run_command("curl http://example.com", cwd=tmp_path)
        assert result.blocked
        assert "network_service" in result.block_reason

    def test_block_package_install(self, tmp_path):
        config = SandboxConfig(worktree_dir=tmp_path / "worktrees")
        sandbox = Sandbox(config)
        result = sandbox.run_command("pip install evil", cwd=tmp_path)
        assert result.blocked
        assert "package_install" in result.block_reason

    def test_timeout(self, tmp_path):
        config = SandboxConfig(worktree_dir=tmp_path / "worktrees", wall_time_limit_seconds=1)
        sandbox = Sandbox(config)
        result = sandbox.run_command("sleep 10", cwd=tmp_path, timeout=1)
        assert result.timed_out
        assert result.exit_code == -1

    def test_safe_env_strips_secrets(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test123")
        config = SandboxConfig(worktree_dir=tmp_path / "worktrees")
        sandbox = Sandbox(config)
        safe_env = sandbox._build_safe_env()
        assert "AWS_ACCESS_KEY_ID" not in safe_env
        assert "OPENAI_API_KEY" not in safe_env
        assert "PATH" in safe_env

    def test_safe_env_strips_proxy_when_network_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HTTP_PROXY", "http://proxy:8080")
        config = SandboxConfig(worktree_dir=tmp_path / "worktrees", network_disabled=True)
        sandbox = Sandbox(config)
        safe_env = sandbox._build_safe_env()
        assert "HTTP_PROXY" not in safe_env

    def test_hash_file(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")
        h = Sandbox.hash_file(test_file)
        assert len(h) == 64  # SHA-256 hex

    def test_hash_content(self):
        h = Sandbox.hash_content("print('hello')")
        assert len(h) == 64

    def test_worktree_creation(self, tmp_path):
        # Create a git repo
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
        (repo / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True)

        config = SandboxConfig(worktree_dir=tmp_path / "worktrees")
        sandbox = Sandbox(config)
        worktree = sandbox.create_worktree(repo, "task_001")

        assert worktree.exists
        assert (worktree.path / "README.md").exists()
        assert worktree.base_commit  # should have a commit hash

        # Cleanup
        sandbox.remove_worktree("task_001", repo_root=repo)
        assert not worktree.path.exists()
