"""Python language adapter.

Wraps the existing Python verification tools (ast.parse, pytest, ruff, mypy)
into the unified LanguageAdapter interface.
"""

from __future__ import annotations

import ast
import subprocess
import time
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.core.schemas import CheckResult, CheckStatus
from vsrs.languages.base import LanguageAdapter, LanguageInfo

logger = get_logger("languages.python")


class PythonAdapter(LanguageAdapter):
    """Language adapter for Python.

    Uses:
    - Syntax: ast.parse
    - Build: py_compile
    - Tests: pytest
    - Lint: ruff
    - Type check: mypy
    """

    @property
    def info(self) -> LanguageInfo:
        return LanguageInfo(
            name="python",
            file_extensions=[".py"],
            display_name="Python",
            build_tool="py_compile",
            test_framework="pytest",
            linter="ruff",
            type_checker="mypy",
        )

    def detect(self, repo_path: Path) -> bool:
        """Check if the repository contains Python files."""
        if not repo_path.is_dir():
            return False
        for entry in repo_path.rglob("*.py"):
            if not any(part.startswith(".") for part in entry.parts):
                return True
        return False

    def syntax_check(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 60,
    ) -> CheckResult:
        """Check Python syntax using ast.parse."""
        start = time.time()
        errors: list[str] = []

        for file_path in files:
            if not file_path.endswith(".py"):
                continue
            full_path = worktree_path / file_path
            if not full_path.exists():
                errors.append(f"File not found: {file_path}")
                continue
            try:
                content = full_path.read_text()
                ast.parse(content, filename=file_path)
            except SyntaxError as e:
                errors.append(f"{file_path}:{e.lineno}: {e.msg}")
            except Exception as e:
                errors.append(f"{file_path}: {e}")

        duration = time.time() - start
        if errors:
            return CheckResult(
                check_type="syntax",
                command="ast.parse",
                exit_code=1,
                status=CheckStatus.fail,
                duration_seconds=duration,
                error_message="; ".join(errors[:10]),
            )
        return CheckResult(
            check_type="syntax",
            command="ast.parse",
            exit_code=0,
            status=CheckStatus.pass_,
            duration_seconds=duration,
        )

    def build(
        self,
        worktree_path: Path,
        timeout: int = 120,
    ) -> CheckResult:
        """Build Python project using py_compile."""
        start = time.time()
        errors: list[str] = []

        py_files = list(worktree_path.rglob("*.py"))
        for py_file in py_files:
            try:
                content = py_file.read_text()
                ast.parse(content, filename=str(py_file))
            except SyntaxError as e:
                errors.append(f"{py_file}:{e.lineno}: {e.msg}")
            except Exception as e:
                errors.append(f"{py_file}: {e}")

        duration = time.time() - start
        if errors:
            return CheckResult(
                check_type="build",
                command="py_compile",
                exit_code=1,
                status=CheckStatus.fail,
                duration_seconds=duration,
                error_message="; ".join(errors[:10]),
            )
        return CheckResult(
            check_type="build",
            command="py_compile",
            exit_code=0,
            status=CheckStatus.pass_,
            duration_seconds=duration,
        )

    def run_tests(
        self,
        worktree_path: Path,
        test_paths: list[str] | None = None,
        timeout: int = 120,
    ) -> CheckResult:
        """Run tests using pytest."""
        cmd_parts = ["python", "-m", "pytest", "-v", "--tb=short"]
        if test_paths:
            cmd_parts.extend(test_paths)
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
                check_type="existing_tests",
                command=command,
                exit_code=-1,
                status=CheckStatus.error,
                duration_seconds=time.time() - start,
                error_message="pytest timed out",
            )
        except FileNotFoundError:
            return CheckResult(
                check_type="existing_tests",
                command=command,
                exit_code=-1,
                status=CheckStatus.error,
                error_message="pytest not found",
            )

        duration = time.time() - start
        status = CheckStatus.pass_ if exit_code == 0 else CheckStatus.fail

        return CheckResult(
            check_type="existing_tests",
            command=command,
            exit_code=exit_code,
            status=status,
            duration_seconds=duration,
            error_message="" if status == CheckStatus.pass_ else output[:500],
        )

    def lint(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 60,
    ) -> CheckResult:
        """Run ruff linter on changed files."""
        py_files = [f for f in files if f.endswith(".py")]
        if not py_files:
            return CheckResult(
                check_type="lint",
                command="ruff check",
                status=CheckStatus.skip,
                error_message="No Python files to lint",
            )

        cmd_parts = ["ruff", "check", "--output-format=concise"]
        cmd_parts.extend(py_files)
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
                check_type="lint",
                command=command,
                exit_code=-1,
                status=CheckStatus.error,
                duration_seconds=time.time() - start,
                error_message="ruff timed out",
            )
        except FileNotFoundError:
            return CheckResult(
                check_type="lint",
                command=command,
                exit_code=-1,
                status=CheckStatus.error,
                error_message="ruff not found",
            )

        duration = time.time() - start
        status = CheckStatus.pass_ if exit_code == 0 else CheckStatus.fail

        return CheckResult(
            check_type="lint",
            command=command,
            exit_code=exit_code,
            status=status,
            duration_seconds=duration,
            error_message="" if status == CheckStatus.pass_ else output[:500],
        )

    def type_check(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 120,
    ) -> CheckResult:
        """Run mypy type checker on changed files."""
        py_files = [f for f in files if f.endswith(".py")]
        if not py_files:
            return CheckResult(
                check_type="type_check",
                command="mypy",
                status=CheckStatus.skip,
                error_message="No Python files to type check",
            )

        cmd_parts = ["mypy", "--no-error-summary"]
        cmd_parts.extend(py_files)
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
                check_type="type_check",
                command=command,
                exit_code=-1,
                status=CheckStatus.error,
                duration_seconds=time.time() - start,
                error_message="mypy timed out",
            )
        except FileNotFoundError:
            return CheckResult(
                check_type="type_check",
                command=command,
                exit_code=-1,
                status=CheckStatus.error,
                error_message="mypy not found",
            )

        duration = time.time() - start
        status = CheckStatus.pass_ if exit_code == 0 else CheckStatus.fail

        return CheckResult(
            check_type="type_check",
            command=command,
            exit_code=exit_code,
            status=status,
            duration_seconds=duration,
            error_message="" if status == CheckStatus.pass_ else output[:500],
        )
