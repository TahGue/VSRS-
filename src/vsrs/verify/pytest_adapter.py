"""pytest adapter: runs pytest and parses results (Section 8).

Runs pytest in a sandboxed worktree, captures exit code, output, and
parses structured results including test counts, failures, and errors.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.core.schemas import CheckResult, CheckStatus
from vsrs.verify.sandbox import Sandbox

logger = get_logger("verify.pytest")


@dataclass
class TestFailure:
    """A single test failure parsed from pytest output."""

    test_name: str
    file: str = ""
    line: int | None = None
    error_type: str = ""
    error_message: str = ""
    traceback: str = ""


@dataclass
class PytestResult:
    """Parsed pytest run result."""

    exit_code: int
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    warnings: int = 0
    duration_seconds: float = 0.0
    output: str = ""
    failures: list[TestFailure] = field(default_factory=list)
    collected: int = 0

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def all_passed(self) -> bool:
        return self.exit_code == 0 and self.failed == 0 and self.errors == 0


class PytestAdapter:
    """Adapter for running pytest and parsing results.

    Implements Section 8: existing_tests and new_targeted_tests gates.
    """

    def __init__(self, sandbox: Sandbox | None = None) -> None:
        self.sandbox = sandbox

    def run(
        self,
        cwd: Path,
        test_paths: list[str] | None = None,
        timeout: int | None = None,
        extra_args: list[str] | None = None,
    ) -> PytestResult:
        """Run pytest in the given directory.

        Args:
            cwd: Working directory (typically a worktree).
            test_paths: Specific test files/dirs to run. None = all tests.
            timeout: Wall-time limit in seconds.
            extra_args: Additional pytest arguments.

        Returns:
            PytestResult with parsed output.
        """
        cmd_parts = ["python", "-m", "pytest", "-v", "--tb=short"]
        if test_paths:
            cmd_parts.extend(test_paths)
        if extra_args:
            cmd_parts.extend(extra_args)

        command = " ".join(cmd_parts)
        logger.info(f"Running pytest: {command}")

        if self.sandbox:
            cmd_result = self.sandbox.run_command(command, cwd=cwd, timeout=timeout)
            output = cmd_result.stdout + cmd_result.stderr
            exit_code = cmd_result.exit_code
            duration = cmd_result.duration_seconds
        else:
            start = time.time()
            try:
                result = subprocess.run(
                    cmd_parts,
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    timeout=timeout or 120,
                )
                output = result.stdout + result.stderr
                exit_code = result.returncode
                duration = time.time() - start
            except subprocess.TimeoutExpired:
                return PytestResult(
                    exit_code=-1,
                    output="",
                    duration_seconds=time.time() - start,
                )
            except FileNotFoundError:
                return PytestResult(
                    exit_code=-1,
                    output="pytest not found",
                    duration_seconds=0.0,
                )

        return self._parse_output(output, exit_code, duration)

    def _parse_output(self, output: str, exit_code: int, duration: float) -> PytestResult:
        """Parse pytest verbose output into structured result."""
        result = PytestResult(
            exit_code=exit_code,
            duration_seconds=duration,
            output=output,
        )

        # Parse summary line: "N passed, M failed, E errors, S skipped"
        # Also handles "=== N passed in X.XXs ===" and similar variants
        summary_patterns = [
            r"(\d+) passed",
            r"(\d+) failed",
            r"(\d+) errors?",
            r"(\d+) skipped",
            r"(\d+) warnings?",
        ]

        passed_match = re.search(r"(\d+) passed", output)
        if passed_match:
            result.passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+) failed", output)
        if failed_match:
            result.failed = int(failed_match.group(1))

        errors_match = re.search(r"(\d+) errors?", output)
        if errors_match:
            result.errors = int(errors_match.group(1))

        skipped_match = re.search(r"(\d+) skipped", output)
        if skipped_match:
            result.skipped = int(skipped_match.group(1))

        warnings_match = re.search(r"(\d+) warnings?", output)
        if warnings_match:
            result.warnings = int(warnings_match.group(1))

        # Parse collected count
        collected_match = re.search(r"collected (\d+) items", output)
        if collected_match:
            result.collected = int(collected_match.group(1))

        # Parse individual failures
        result.failures = self._parse_failures(output)

        return result

    def _parse_failures(self, output: str) -> list[TestFailure]:
        """Parse individual test failures from verbose output."""
        failures: list[TestFailure] = []

        # Pattern: "FAILED tests/test_file.py::test_name - ErrorType: message"
        # Also: "tests/test_file.py::test_name FAILED [ 50%]"
        failed_pattern = re.compile(
            r"FAILED\s+(\S+?)::(\S+?)(?:\s+-\s+(.+?))?(?:$|\n)",
            re.MULTILINE,
        )
        for match in failed_pattern.finditer(output):
            file_path = match.group(1)
            test_name = match.group(2)
            error_info = match.group(3) or ""

            error_type = ""
            error_message = ""
            if ":" in error_info:
                parts = error_info.split(":", 1)
                error_type = parts[0].strip()
                error_message = parts[1].strip() if len(parts) > 1 else ""
            else:
                error_message = error_info

            failures.append(TestFailure(
                test_name=test_name,
                file=file_path,
                error_type=error_type,
                error_message=error_message,
            ))

        # Also match "path::name FAILED" format (verbose output)
        failed_pattern2 = re.compile(
            r"(\S+?)::(\S+?)\s+FAILED",
        )
        for match in failed_pattern2.finditer(output):
            file_path = match.group(1)
            test_name = match.group(2)
            # Avoid duplicates
            if any(f.test_name == test_name and f.file == file_path for f in failures):
                continue
            failures.append(TestFailure(
                test_name=test_name,
                file=file_path,
            ))

        # Also parse "ERROR" lines for collection errors
        error_pattern = re.compile(
            r"ERROR\s+(\S+?)(?:\s+-\s+(.+?))?(?:$|\n)",
            re.MULTILINE,
        )
        for match in error_pattern.finditer(output):
            file_path = match.group(1)
            error_info = match.group(2) or ""
            failures.append(TestFailure(
                test_name="<collection>",
                file=file_path,
                error_type="collection_error",
                error_message=error_info,
            ))

        return failures

    def to_check_result(
        self,
        result: PytestResult,
        check_type: str = "existing_tests",
    ) -> CheckResult:
        """Convert PytestResult to a CheckResult schema."""
        if result.exit_code == 0:
            status = CheckStatus.pass_
        elif result.exit_code == -1:
            status = CheckStatus.error
        else:
            status = CheckStatus.fail

        error_msg = ""
        if result.failures:
            failure_summary = "; ".join(
                f"{f.test_name}: {f.error_type or f.error_message}"
                for f in result.failures[:5]
            )
            error_msg = f"{result.failed} failed, {result.errors} errors: {failure_summary}"

        return CheckResult(
            check_type=check_type,
            command="python -m pytest",
            exit_code=result.exit_code,
            status=status,
            output_ref="",
            duration_seconds=result.duration_seconds,
            error_message=error_msg,
        )
