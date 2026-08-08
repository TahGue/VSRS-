"""Lint adapter: ruff integration (Section 8).

Runs ruff check on changed files, parses output, and returns structured
results including individual lint findings.
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

logger = get_logger("verify.lint")


@dataclass
class LintFinding:
    """A single lint finding from ruff."""

    file: str
    line: int
    column: int = 0
    rule_code: str = ""
    message: str = ""
    fix_available: bool = False


@dataclass
class LintResult:
    """Parsed ruff check result."""

    exit_code: int
    findings: list[LintFinding] = field(default_factory=list)
    output: str = ""
    duration_seconds: float = 0.0
    error: str = ""

    @property
    def clean(self) -> bool:
        return self.exit_code == 0 and len(self.findings) == 0


class LintAdapter:
    """Adapter for running ruff lint checks.

    Implements Section 8: lint gate.
    """

    def __init__(self, sandbox: Sandbox | None = None) -> None:
        self.sandbox = sandbox

    def run(
        self,
        cwd: Path,
        paths: list[str] | None = None,
        timeout: int | None = None,
        select: list[str] | None = None,
    ) -> LintResult:
        """Run ruff check in the given directory.

        Args:
            cwd: Working directory (typically a worktree).
            paths: Specific files/dirs to check. None = all Python files.
            timeout: Wall-time limit in seconds.
            select: Optional list of rule codes to select.

        Returns:
            LintResult with parsed findings.
        """
        cmd_parts = ["ruff", "check", "--output-format=concise"]
        if select:
            cmd_parts.append(f"--select={','.join(select)}")
        if paths:
            cmd_parts.extend(paths)
        else:
            cmd_parts.append(".")

        command = " ".join(cmd_parts)
        logger.info(f"Running ruff: {command}")

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
                    timeout=timeout or 60,
                )
                output = result.stdout + result.stderr
                exit_code = result.returncode
                duration = time.time() - start
            except subprocess.TimeoutExpired:
                return LintResult(
                    exit_code=-1,
                    duration_seconds=time.time() - start,
                    error="ruff timed out",
                )
            except FileNotFoundError:
                return LintResult(
                    exit_code=-1,
                    error="ruff not found",
                )

        return self._parse_output(output, exit_code, duration)

    def _parse_output(self, output: str, exit_code: int, duration: float) -> LintResult:
        """Parse ruff concise output into structured findings.

        Ruff concise format: file:line:col: rule_code message
        """
        result = LintResult(
            exit_code=exit_code,
            output=output,
            duration_seconds=duration,
        )

        # Pattern: path:line:col: CODE message
        pattern = re.compile(
            r"^(.+?):(\d+):(\d+):\s+([A-Z]\d+)\s+(.+)$",
            re.MULTILINE,
        )

        for match in pattern.finditer(output):
            result.findings.append(LintFinding(
                file=match.group(1),
                line=int(match.group(2)),
                column=int(match.group(3)),
                rule_code=match.group(4),
                message=match.group(5).strip(),
            ))

        return result

    def to_check_result(self, result: LintResult) -> CheckResult:
        """Convert LintResult to a CheckResult schema."""
        if result.exit_code == 0:
            status = CheckStatus.pass_
        elif result.exit_code == -1:
            status = CheckStatus.error
        else:
            status = CheckStatus.fail

        error_msg = ""
        if result.findings:
            error_msg = "; ".join(
                f"{f.file}:{f.line} {f.rule_code}: {f.message}"
                for f in result.findings[:10]
            )
        elif result.error:
            error_msg = result.error

        return CheckResult(
            check_type="lint",
            command="ruff check",
            exit_code=result.exit_code,
            status=status,
            output_ref="",
            duration_seconds=result.duration_seconds,
            error_message=error_msg,
        )
