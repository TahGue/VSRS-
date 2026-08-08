"""Java language adapter.

Uses:
- Syntax: javac
- Build: mvn compile or gradle build
- Tests: mvn test or gradle test
- Lint: checkstyle (optional)
- Type check: javac (built-in)
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.core.schemas import CheckResult, CheckStatus
from vsrs.languages.base import LanguageAdapter, LanguageInfo

logger = get_logger("languages.java")


class JavaAdapter(LanguageAdapter):
    """Language adapter for Java.

    Uses:
    - Syntax: javac
    - Build: mvn compile (or gradle compileJava)
    - Tests: mvn test (or gradle test)
    - Lint: checkstyle
    - Type check: javac (built-in)
    """

    @property
    def info(self) -> LanguageInfo:
        return LanguageInfo(
            name="java",
            file_extensions=[".java"],
            display_name="Java",
            build_tool="mvn / gradle",
            test_framework="JUnit",
            linter="checkstyle",
            type_checker="javac",
        )

    def detect(self, repo_path: Path) -> bool:
        """Check if the repository contains Java files or build files."""
        if not repo_path.is_dir():
            return False
        if (repo_path / "pom.xml").exists():
            return True
        if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
            return True
        for entry in repo_path.rglob("*.java"):
            if not any(part.startswith(".") for part in entry.parts):
                return True
        return False

    def _detect_build_tool(self, repo_path: Path) -> str:
        """Detect whether to use Maven or Gradle."""
        if (repo_path / "pom.xml").exists():
            return "maven"
        if (repo_path / "build.gradle").exists() or (repo_path / "build.gradle.kts").exists():
            return "gradle"
        return "maven"  # default

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
        """Check Java syntax using javac."""
        java_files = [f for f in files if f.endswith(".java")]
        if not java_files:
            return CheckResult(
                check_type="syntax",
                command="javac",
                status=CheckStatus.skip,
                error_message="No Java files to check",
            )
        # Use javac -Xlint to check syntax without full compilation
        cmd_parts = ["javac", "-Xlint", "-d", "/tmp"] + java_files
        return self._run_command(cmd_parts, worktree_path, timeout, "syntax")

    def build(
        self,
        worktree_path: Path,
        timeout: int = 120,
    ) -> CheckResult:
        """Build Java project using Maven or Gradle."""
        build_tool = self._detect_build_tool(worktree_path)
        if build_tool == "gradle":
            cmd_parts = ["./gradlew", "compileJava"]
        else:
            cmd_parts = ["mvn", "compile", "-q"]
        return self._run_command(cmd_parts, worktree_path, timeout, "build")

    def run_tests(
        self,
        worktree_path: Path,
        test_paths: list[str] | None = None,
        timeout: int = 120,
    ) -> CheckResult:
        """Run tests using Maven or Gradle."""
        build_tool = self._detect_build_tool(worktree_path)
        if build_tool == "gradle":
            cmd_parts = ["./gradlew", "test"]
        else:
            cmd_parts = ["mvn", "test"]
        return self._run_command(cmd_parts, worktree_path, timeout, "existing_tests")

    def lint(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 60,
    ) -> CheckResult:
        """Run checkstyle linter."""
        java_files = [f for f in files if f.endswith(".java")]
        if not java_files:
            return CheckResult(
                check_type="lint",
                command="checkstyle",
                status=CheckStatus.skip,
                error_message="No Java files to lint",
            )
        build_tool = self._detect_build_tool(worktree_path)
        if build_tool == "gradle":
            cmd_parts = ["./gradlew", "checkstyleMain"]
        else:
            cmd_parts = ["mvn", "checkstyle:check"]
        return self._run_command(cmd_parts, worktree_path, timeout, "lint")

    def type_check(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 120,
    ) -> CheckResult:
        """Run javac for type checking."""
        java_files = [f for f in files if f.endswith(".java")]
        if not java_files:
            return CheckResult(
                check_type="type_check",
                command="javac",
                status=CheckStatus.skip,
                error_message="No Java files to type check",
            )
        # Use the build tool's compile step for proper classpath
        build_tool = self._detect_build_tool(worktree_path)
        if build_tool == "gradle":
            cmd_parts = ["./gradlew", "compileJava"]
        else:
            cmd_parts = ["mvn", "compiler:compile", "-q"]
        return self._run_command(cmd_parts, worktree_path, timeout, "type_check")
