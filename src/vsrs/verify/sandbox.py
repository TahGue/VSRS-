"""Sandbox and worktree management for isolated task execution.

Implements Section 10: V1 isolation requirements.
- Disposable git worktree per task
- Command runner with resource limits
- Network disabled by default
- Every command logged with exit status
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from vsrs.core.config import SandboxConfig
from vsrs.core.logging import get_logger

logger = get_logger("sandbox")


class CommandClass(str, Enum):
    """Command policy classes (Section 10.2)."""

    safe = "safe"
    bounded = "bounded"
    package_install = "package_install"
    filesystem_destructive = "filesystem_destructive"
    network_service = "network_service"
    credential_cloud = "credential_cloud"


# Default policy: which command classes are allowed
DEFAULT_POLICY: dict[CommandClass, bool] = {
    CommandClass.safe: True,
    CommandClass.bounded: True,
    CommandClass.package_install: False,
    CommandClass.filesystem_destructive: False,
    CommandClass.network_service: False,
    CommandClass.credential_cloud: False,
}

# Patterns to classify commands
_DANGEROUS_PATTERNS = [
    "rm -rf", "chmod", "chown", "mkfs", "dd if=", "shutdown", "reboot",
    "> /dev/", ":(){", "fork bomb",
]

_NETWORK_PATTERNS = [
    "curl ", "wget ", "nc ", "netcat", "ssh ", "scp ", "rsync ",
    "aws ", "gcloud ", "kubectl ", "docker push", "docker pull",
]

_PACKAGE_PATTERNS = [
    "pip install", "npm install", "yarn add", "cargo add", "apt install",
    "brew install", "conda install",
]


def classify_command(command: str) -> CommandClass:
    """Classify a command into a policy class."""
    cmd_lower = command.lower().strip()
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in cmd_lower:
            return CommandClass.filesystem_destructive
    for pattern in _NETWORK_PATTERNS:
        if pattern in cmd_lower:
            return CommandClass.network_service
    for pattern in _PACKAGE_PATTERNS:
        if pattern in cmd_lower:
            return CommandClass.package_install
    return CommandClass.bounded


@dataclass
class CommandResult:
    """Result of a sandboxed command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    blocked: bool = False
    block_reason: str = ""


@dataclass
class Worktree:
    """An isolated git worktree for a task."""

    path: Path
    branch: str
    base_commit: str
    task_id: str
    created_at: float = field(default_factory=time.time)

    @property
    def exists(self) -> bool:
        return self.path.exists() and self.path.is_dir()

    def cleanup(self) -> None:
        """Remove the worktree directory."""
        if self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
            logger.info(f"Cleaned up worktree at {self.path}")


class Sandbox:
    """Sandboxed execution environment using git worktrees.

    Creates an isolated worktree per task, runs commands with resource limits,
    and enforces command policy. Every command is logged.
    """

    def __init__(
        self,
        config: SandboxConfig,
        policy: dict[CommandClass, bool] | None = None,
    ) -> None:
        self.config = config
        self.policy = policy or dict(DEFAULT_POLICY)
        self._worktrees: dict[str, Worktree] = {}

    def create_worktree(
        self,
        repo_root: Path,
        task_id: str,
        branch_name: str | None = None,
    ) -> Worktree:
        """Create an isolated git worktree for a task.

        Args:
            repo_root: Root of the source repository.
            task_id: Task identifier for naming.
            branch_name: Optional branch name. Defaults to vsrs/{task_id}.

        Returns:
            Worktree instance pointing to the isolated workspace.
        """
        if branch_name is None:
            branch_name = f"vsrs/{task_id}"

        worktree_path = self.config.worktree_dir / task_id
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        # Get current commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to get HEAD commit: {result.stderr}")
        base_commit = result.stdout.strip()

        # Remove existing worktree if present
        if worktree_path.exists():
            shutil.rmtree(worktree_path, ignore_errors=True)

        # Create worktree with a new branch
        result = subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path), base_commit],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {result.stderr}")

        worktree = Worktree(
            path=worktree_path,
            branch=branch_name,
            base_commit=base_commit,
            task_id=task_id,
        )
        self._worktrees[task_id] = worktree
        logger.info(f"Created worktree at {worktree_path} for task {task_id} (base: {base_commit[:8]})")
        return worktree

    def get_worktree(self, task_id: str) -> Worktree | None:
        """Get an existing worktree for a task."""
        return self._worktrees.get(task_id)

    def remove_worktree(self, task_id: str, repo_root: Path | None = None) -> None:
        """Remove a worktree and its branch.

        Args:
            task_id: Task identifier.
            repo_root: Repository root for git worktree removal. If None,
                       only the directory is removed.
        """
        worktree = self._worktrees.pop(task_id, None)
        if worktree is None:
            return

        if repo_root is not None:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree.path)],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "branch", "-D", worktree.branch],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )

        worktree.cleanup()

    def check_command(self, command: str) -> tuple[bool, str]:
        """Check if a command is allowed by policy.

        Returns:
            (allowed, reason) tuple.
        """
        cmd_class = classify_command(command)
        allowed = self.policy.get(cmd_class, False)
        if not allowed:
            reason = f"Command class '{cmd_class.value}' is not allowed by policy"
            logger.warning(f"Blocked command: {command} ({reason})")
            return False, reason
        return True, ""

    def run_command(
        self,
        command: str,
        cwd: Path,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
    ) -> CommandResult:
        """Run a command in the sandbox.

        Args:
            command: Shell command to execute.
            cwd: Working directory (should be inside the worktree).
            timeout: Wall-time limit in seconds. Defaults to config value.
            env: Optional environment variables. Host secrets are stripped.
            capture_output: Whether to capture stdout/stderr.

        Returns:
            CommandResult with exit code, output, and timing.
        """
        # Check policy
        allowed, reason = self.check_command(command)
        if not allowed:
            return CommandResult(
                command=command, exit_code=-1, stdout="", stderr="",
                duration_seconds=0.0, blocked=True, block_reason=reason,
            )

        effective_timeout = timeout or self.config.wall_time_limit_seconds

        # Build safe environment
        safe_env = self._build_safe_env(env)

        start = time.time()
        logger.info(f"Running command: {command} (cwd={cwd}, timeout={effective_timeout}s)")

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=capture_output,
                text=True,
                timeout=effective_timeout,
                env=safe_env,
            )
            duration = time.time() - start
            logger.info(
                f"Command finished: exit={result.returncode}, "
                f"duration={duration:.2f}s"
            )
            return CommandResult(
                command=command,
                exit_code=result.returncode,
                stdout=result.stdout if capture_output else "",
                stderr=result.stderr if capture_output else "",
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start
            logger.warning(f"Command timed out after {effective_timeout}s: {command}")
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Timed out after {effective_timeout}s",
                duration_seconds=duration,
                timed_out=True,
            )
        except Exception as e:
            duration = time.time() - start
            logger.error(f"Command failed with exception: {e}")
            return CommandResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=duration,
            )

    def _build_safe_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build a safe environment for command execution.

        Strips host secrets, SSH keys, cloud credentials, and production
        environment variables. Network-related env vars are removed when
        network is disabled.
        """
        # Start with minimal env
        safe_env = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": os.environ.get("LANG", "en_US.UTF-8"),
            "TERM": os.environ.get("TERM", "xterm-256color"),
        }

        # Add Python-specific paths
        if "PYTHONPATH" in os.environ:
            safe_env["PYTHONPATH"] = os.environ["PYTHONPATH"]

        # Add extra env if provided
        if extra:
            safe_env.update(extra)

        # Explicitly strip dangerous env vars
        dangerous_vars = [
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
            "GOOGLE_APPLICATION_CREDENTIALS", "GCLOUD_PROJECT",
            "SSH_AUTH_SOCK", "SSH_AGENT_PID",
            "KUBECONFIG", "DOCKER_HOST",
            "DATABASE_URL", "REDIS_URL",
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        ]
        for var in dangerous_vars:
            safe_env.pop(var, None)

        # Strip network-related env if network is disabled
        if self.config.network_disabled:
            for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY"]:
                safe_env.pop(var, None)

        return safe_env

    @staticmethod
    def hash_file(path: Path) -> str:
        """Compute SHA-256 hash of a file for provenance."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def hash_content(content: str) -> str:
        """Compute SHA-256 hash of a string for provenance."""
        return hashlib.sha256(content.encode()).hexdigest()
