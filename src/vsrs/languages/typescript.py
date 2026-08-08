"""TypeScript language adapter.

Uses:
- Syntax: tsc --noEmit
- Build: tsc or npm run build
- Tests: jest or npm test
- Lint: eslint
- Type check: tsc --noEmit
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.core.schemas import CheckResult, CheckStatus
from vsrs.languages.base import LanguageAdapter, LanguageInfo

logger = get_logger("languages.typescript")


class TypeScriptAdapter(LanguageAdapter):
    """Language adapter for TypeScript.

    Uses:
    - Syntax: tsc --noEmit
    - Build: npm run build (or tsc)
    - Tests: npm test (or jest)
    - Lint: eslint
    - Type check: tsc --noEmit
    """

    @property
    def info(self) -> LanguageInfo:
        return LanguageInfo(
            name="typescript",
            file_extensions=[".ts", ".tsx"],
            display_name="TypeScript",
            build_tool="tsc / npm run build",
            test_framework="jest",
            linter="eslint",
            type_checker="tsc",
        )

    def detect(self, repo_path: Path) -> bool:
        """Check if the repository contains TypeScript files or tsconfig.json."""
        if not repo_path.is_dir():
            return False
        if (repo_path / "tsconfig.json").exists():
            return True
        for entry in repo_path.rglob("*.ts"):
            if not any(part.startswith(".") or part == "node_modules" for part in entry.parts):
                return True
        for entry in repo_path.rglob("*.tsx"):
            if not any(part.startswith(".") or part == "node_modules" for part in entry.parts):
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
        """Check TypeScript syntax using tsc --noEmit."""
        ts_files = [f for f in files if f.endswith((".ts", ".tsx"))]
        if not ts_files:
            return CheckResult(
                check_type="syntax",
                command="tsc --noEmit",
                status=CheckStatus.skip,
                error_message="No TypeScript files to check",
            )
        return self._run_command(
            ["npx", "tsc", "--noEmit"],
            worktree_path,
            timeout,
            "syntax",
        )

    def build(
        self,
        worktree_path: Path,
        timeout: int = 120,
    ) -> CheckResult:
        """Build TypeScript project using npm run build."""
        return self._run_command(
            ["npm", "run", "build"],
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
        """Run tests using npm test."""
        cmd_parts = ["npm", "test"]
        if test_paths:
            cmd_parts = ["npx", "jest"] + test_paths
        return self._run_command(cmd_parts, worktree_path, timeout, "existing_tests")

    def lint(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 60,
    ) -> CheckResult:
        """Run eslint linter."""
        ts_files = [f for f in files if f.endswith((".ts", ".tsx"))]
        if not ts_files:
            return CheckResult(
                check_type="lint",
                command="eslint",
                status=CheckStatus.skip,
                error_message="No TypeScript files to lint",
            )
        cmd_parts = ["npx", "eslint"] + ts_files
        return self._run_command(cmd_parts, worktree_path, timeout, "lint")

    def type_check(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 120,
    ) -> CheckResult:
        """Run tsc for type checking."""
        ts_files = [f for f in files if f.endswith((".ts", ".tsx"))]
        if not ts_files:
            return CheckResult(
                check_type="type_check",
                command="tsc --noEmit",
                status=CheckStatus.skip,
                error_message="No TypeScript files to type check",
            )
        return self._run_command(
            ["npx", "tsc", "--noEmit"],
            worktree_path,
            timeout,
            "type_check",
        )
