"""Type check adapter: mypy integration (Section 8).

Runs mypy on changed files, parses output, and returns structured results
including individual type errors.
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

logger = get_logger("verify.type_check")


@dataclass
class TypeError:
    """A single type error from mypy."""

    file: str
    line: int
    column: int = 0
    severity: str = "error"  # error, note
    code: str = ""
    message: str = ""


@dataclass
class TypeCheckResult:
    """Parsed mypy check result."""

    exit_code: int
    errors: list[TypeError] = field(default_factory=list)
    notes: list[TypeError] = field(default_factory=list)
    output: str = ""
    duration_seconds: float = 0.0
    error: str = ""

    @property
    def clean(self) -> bool:
        return self.exit_code == 0 and len(self.errors) == 0

    @property
    def error_count(self) -> int:
        return len(self.errors)


class TypeCheckAdapter:
    """Adapter for running mypy type checks.

    Implements Section 8: type_check gate.
    """

    def __init__(self, sandbox: Sandbox | None = None) -> None:
        self.sandbox = sandbox

    def run(
        self,
        cwd: Path,
        paths: list[str] | None = None,
        timeout: int | None = None,
        strict: bool = False,
    ) -> TypeCheckResult:
        """Run mypy in the given directory.

        Args:
            cwd: Working directory (typically a worktree).
            paths: Specific files/packages to check. None = check package.
            timeout: Wall-time limit in seconds.
            strict: Whether to use --strict mode.

        Returns:
            TypeCheckResult with parsed errors.
        """
        cmd_parts = ["mypy", "--no-error-summary"]
        if strict:
            cmd_parts.append("--strict")
        if paths:
            cmd_parts.extend(paths)
        else:
            cmd_parts.append(".")

        command = " ".join(cmd_parts)
        logger.info(f"Running mypy: {command}")

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
                return TypeCheckResult(
                    exit_code=-1,
                    duration_seconds=time.time() - start,
                    error="mypy timed out",
                )
            except FileNotFoundError:
                return TypeCheckResult(
                    exit_code=-1,
                    error="mypy not found",
                )

        return self._parse_output(output, exit_code, duration)

    def _parse_output(self, output: str, exit_code: int, duration: float) -> TypeCheckResult:
        """Parse mypy output into structured errors.

        Mypy format: file:line: error: message  [error-code]
                     file:line: note: message
        """
        result = TypeCheckResult(
            exit_code=exit_code,
            output=output,
            duration_seconds=duration,
        )

        # Pattern: path:line: error: message  [code]
        # Also: path:line:col: error: message  [code]
        pattern = re.compile(
            r"^(.+?):(\d+)(?::(\d+))?:\s+(error|note):\s+(.+?)(?:\s+\[(\S+)\])?$",
            re.MULTILINE,
        )

        for match in pattern.finditer(output):
            finding = TypeError(
                file=match.group(1),
                line=int(match.group(2)),
                column=int(match.group(3)) if match.group(3) else 0,
                severity=match.group(4),
                message=match.group(5).strip(),
                code=match.group(6) or "",
            )
            if finding.severity == "error":
                result.errors.append(finding)
            else:
                result.notes.append(finding)

        return result

    def to_check_result(self, result: TypeCheckResult) -> CheckResult:
        """Convert TypeCheckResult to a CheckResult schema."""
        if result.exit_code == 0:
            status = CheckStatus.pass_
        elif result.exit_code == -1:
            status = CheckStatus.error
        else:
            status = CheckStatus.fail

        error_msg = ""
        if result.errors:
            error_msg = "; ".join(
                f"{e.file}:{e.line}: {e.message}"
                for e in result.errors[:10]
            )
        elif result.error:
            error_msg = result.error

        return CheckResult(
            check_type="type_check",
            command="mypy",
            exit_code=result.exit_code,
            status=status,
            output_ref="",
            duration_seconds=result.duration_seconds,
            error_message=error_msg,
        )
