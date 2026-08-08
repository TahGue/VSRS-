"""Rust language adapter.

Uses:
- Syntax: cargo check
- Build: cargo build
- Tests: cargo test
- Lint: clippy
- Type check: cargo check (built-in type checking)
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.core.schemas import CheckResult, CheckStatus
from vsrs.languages.base import LanguageAdapter, LanguageInfo

logger = get_logger("languages.rust")


class RustAdapter(LanguageAdapter):
    """Language adapter for Rust.

    Uses:
    - Syntax: cargo check
    - Build: cargo build
    - Tests: cargo test
    - Lint: clippy
    - Type check: cargo check (built-in)
    """

    @property
    def info(self) -> LanguageInfo:
        return LanguageInfo(
            name="rust",
            file_extensions=[".rs"],
            display_name="Rust",
            build_tool="cargo build",
            test_framework="cargo test",
            linter="clippy",
            type_checker="cargo check",
        )

    def detect(self, repo_path: Path) -> bool:
        """Check if the repository contains Rust files or Cargo.toml."""
        if not repo_path.is_dir():
            return False
        if (repo_path / "Cargo.toml").exists():
            return True
        for entry in repo_path.rglob("*.rs"):
            if not any(part.startswith(".") for part in entry.parts):
                return True
        return False

    def _run_command(
        self,
        cmd_parts: list[str],
        worktree_path: Path,
        timeout: int,
        check_type: str,
    ) -> CheckResult:
        """Run a command and return a CheckResult."""
        command = " ".join(cmd_parts)
        start = time.time()
        try:
            result = subprocess.run(
                cmd_parts,
                cwd=str(worktree_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout + result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            return CheckResult(
                check_type=check_type,
                command=command,
                exit_code=-1,
                status=CheckStatus.error,
                duration_seconds=time.time() - start,
                error_message=f"command timed out: {command}",
            )
        except FileNotFoundError:
            return CheckResult(
                check_type=check_type,
                command=command,
                exit_code=-1,
                status=CheckStatus.error,
                error_message=f"command not found: {cmd_parts[0]}",
            )

        duration = time.time() - start
        status = CheckStatus.pass_ if exit_code == 0 else CheckStatus.fail

        return CheckResult(
            check_type=check_type,
            command=command,
            exit_code=exit_code,
            status=status,
            duration_seconds=duration,
            error_message="" if status == CheckStatus.pass_ else output[:500],
        )

    def syntax_check(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 60,
    ) -> CheckResult:
        """Check Rust syntax using cargo check."""
        rs_files = [f for f in files if f.endswith(".rs")]
        if not rs_files:
            return CheckResult(
                check_type="syntax",
                command="cargo check",
                status=CheckStatus.skip,
                error_message="No Rust files to check",
            )
        return self._run_command(
            ["cargo", "check", "--message-format=short"],
            worktree_path,
            timeout,
            "syntax",
        )

    def build(
        self,
        worktree_path: Path,
        timeout: int = 120,
    ) -> CheckResult:
        """Build Rust project using cargo build."""
        return self._run_command(
            ["cargo", "build", "--message-format=short"],
            worktree_path,
            timeout,
            "build",
        )

    def run_tests(
        self,
        worktree_path: Path,
        test_paths: list[str] | None = None,
        timeout: int = 120,
    ) -> CheckResult:
        """Run tests using cargo test."""
        cmd_parts = ["cargo", "test", "--", "--nocapture"]
        return self._run_command(cmd_parts, worktree_path, timeout, "existing_tests")

    def lint(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 60,
    ) -> CheckResult:
        """Run clippy linter."""
        rs_files = [f for f in files if f.endswith(".rs")]
        if not rs_files:
            return CheckResult(
                check_type="lint",
                command="clippy",
                status=CheckStatus.skip,
                error_message="No Rust files to lint",
            )
        return self._run_command(
            ["cargo", "clippy", "--", "-D", "warnings"],
            worktree_path,
            timeout,
            "lint",
        )

    def type_check(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 120,
    ) -> CheckResult:
        """Run cargo check for type checking."""
        rs_files = [f for f in files if f.endswith(".rs")]
        if not rs_files:
            return CheckResult(
                check_type="type_check",
                command="cargo check",
                status=CheckStatus.skip,
                error_message="No Rust files to type check",
            )
        return self._run_command(
            ["cargo", "check", "--message-format=short"],
            worktree_path,
            timeout,
            "type_check",
        )
