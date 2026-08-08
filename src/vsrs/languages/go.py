"""Go language adapter.

Uses:
- Syntax: go vet
- Build: go build
- Tests: go test
- Lint: staticcheck (optional)
- Type check: go vet (built-in)
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.core.schemas import CheckResult, CheckStatus
from vsrs.languages.base import LanguageAdapter, LanguageInfo

logger = get_logger("languages.go")


class GoAdapter(LanguageAdapter):
    """Language adapter for Go.

    Uses:
    - Syntax: go vet
    - Build: go build ./...
    - Tests: go test ./...
    - Lint: staticcheck
    - Type check: go vet (built-in type checking)
    """

    @property
    def info(self) -> LanguageInfo:
        return LanguageInfo(
            name="go",
            file_extensions=[".go"],
            display_name="Go",
            build_tool="go build",
            test_framework="go test",
            linter="staticcheck",
            type_checker="go vet",
        )

    def detect(self, repo_path: Path) -> bool:
        """Check if the repository contains Go files or go.mod."""
        if not repo_path.is_dir():
            return False
        if (repo_path / "go.mod").exists():
            return True
        for entry in repo_path.rglob("*.go"):
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
        """Check Go syntax using go vet."""
        go_files = [f for f in files if f.endswith(".go")]
        if not go_files:
            return CheckResult(
                check_type="syntax",
                command="go vet",
                status=CheckStatus.skip,
                error_message="No Go files to check",
            )
        return self._run_command(
            ["go", "vet", "./..."],
            worktree_path,
            timeout,
            "syntax",
        )

    def build(
        self,
        worktree_path: Path,
        timeout: int = 120,
    ) -> CheckResult:
        """Build Go project using go build."""
        return self._run_command(
            ["go", "build", "./..."],
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
        """Run tests using go test."""
        cmd_parts = ["go", "test", "-v", "./..."]
        if test_paths:
            cmd_parts = ["go", "test", "-v"] + test_paths
        return self._run_command(cmd_parts, worktree_path, timeout, "existing_tests")

    def lint(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 60,
    ) -> CheckResult:
        """Run staticcheck linter."""
        go_files = [f for f in files if f.endswith(".go")]
        if not go_files:
            return CheckResult(
                check_type="lint",
                command="staticcheck",
                status=CheckStatus.skip,
                error_message="No Go files to lint",
            )
        return self._run_command(
            ["staticcheck", "./..."],
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
        """Run go vet for type checking."""
        go_files = [f for f in files if f.endswith(".go")]
        if not go_files:
            return CheckResult(
                check_type="type_check",
                command="go vet",
                status=CheckStatus.skip,
                error_message="No Go files to type check",
            )
        return self._run_command(
            ["go", "vet", "./..."],
            worktree_path,
            timeout,
            "type_check",
        )
