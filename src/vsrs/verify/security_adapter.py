"""Security adapter: bandit integration (Section 8).

Runs bandit on changed files, parses output, and returns structured results
including individual security findings with severity and confidence.
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

logger = get_logger("verify.security")


@dataclass
class SecurityFinding:
    """A single security finding from bandit."""

    file: str
    line: int
    test_id: str = ""
    test_name: str = ""
    severity: str = "LOW"  # LOW, MEDIUM, HIGH
    confidence: str = "LOW"  # LOW, MEDIUM, HIGH
    message: str = ""
    more_info: str = ""


@dataclass
class SecurityResult:
    """Parsed bandit scan result."""

    exit_code: int
    findings: list[SecurityFinding] = field(default_factory=list)
    output: str = ""
    duration_seconds: float = 0.0
    error: str = ""

    @property
    def clean(self) -> bool:
        return self.exit_code == 0 and len(self.findings) == 0

    @property
    def high_severity_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "HIGH")

    @property
    def medium_severity_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "MEDIUM")


class SecurityAdapter:
    """Adapter for running bandit security scans.

    Implements Section 8: security_scan and static_analysis gates.
    """

    def __init__(self, sandbox: Sandbox | None = None) -> None:
        self.sandbox = sandbox

    def run(
        self,
        cwd: Path,
        paths: list[str] | None = None,
        timeout: int | None = None,
        severity_level: str = "LOW",  # LOW, MEDIUM, HIGH
    ) -> SecurityResult:
        """Run bandit in the given directory.

        Args:
            cwd: Working directory (typically a worktree).
            paths: Specific files/dirs to scan. None = scan all .py files.
            timeout: Wall-time limit in seconds.
            severity_level: Minimum severity to report.

        Returns:
            SecurityResult with parsed findings.
        """
        cmd_parts = ["bandit", "-r", "-f", "txt"]
        if severity_level != "LOW":
            cmd_parts.extend(["-l", severity_level])
        if paths:
            cmd_parts.extend(paths)
        else:
            cmd_parts.append(".")

        command = " ".join(cmd_parts)
        logger.info(f"Running bandit: {command}")

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
                return SecurityResult(
                    exit_code=-1,
                    duration_seconds=time.time() - start,
                    error="bandit timed out",
                )
            except FileNotFoundError:
                return SecurityResult(
                    exit_code=-1,
                    error="bandit not found",
                )

        return self._parse_output(output, exit_code, duration)

    def _parse_output(self, output: str, exit_code: int, duration: float) -> SecurityResult:
        """Parse bandit text output into structured findings.

        Bandit text format:
        >> Issue: [Bxxx:test_name] severity level confidence
        Location: file:line
        """
        result = SecurityResult(
            exit_code=exit_code,
            output=output,
            duration_seconds=duration,
        )

        # Parse issue blocks
        # Pattern: ">> Issue: [B101:hardcoded_password_string] Severity: High Confidence: High"
        issue_pattern = re.compile(
            r">>\s+Issue:\s+\[(\w+):([^\]]+)\]\s+"
            r"Severity:\s+(\w+)\s+Confidence:\s+(\w+)",
            re.IGNORECASE,
        )
        location_pattern = re.compile(
            r"Location:\s+(.+?):(\d+)",
        )
        more_info_pattern = re.compile(
            r"More Info:\s+(.+?)(?:\n|$)",
        )

        lines = output.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            issue_match = issue_pattern.search(line)
            if issue_match:
                test_id = issue_match.group(1)
                test_name = issue_match.group(2).strip()
                severity = issue_match.group(3).upper()
                confidence = issue_match.group(4).upper()

                # Look for location in next few lines
                file_path = ""
                line_no = 0
                more_info = ""
                for j in range(i + 1, min(i + 5, len(lines))):
                    loc_match = location_pattern.search(lines[j])
                    if loc_match:
                        file_path = loc_match.group(1).strip()
                        line_no = int(loc_match.group(2))
                    info_match = more_info_pattern.search(lines[j])
                    if info_match:
                        more_info = info_match.group(1).strip()

                # Extract issue description
                desc = ""
                if "Issue:" in line:
                    desc = line.split("Issue:", 1)[1].strip()
                    # Remove the bracket part
                    desc = re.sub(r"^\[[^\]]+\]\s*", "", desc)
                    desc = re.sub(r"\s+Severity:.*$", "", desc, flags=re.IGNORECASE)

                result.findings.append(SecurityFinding(
                    file=file_path,
                    line=line_no,
                    test_id=test_id,
                    test_name=test_name,
                    severity=severity,
                    confidence=confidence,
                    message=desc,
                    more_info=more_info,
                ))

            i += 1

        return result

    def to_check_result(
        self,
        result: SecurityResult,
        check_type: str = "security_scan",
    ) -> CheckResult:
        """Convert SecurityResult to a CheckResult schema."""
        if result.exit_code == 0:
            status = CheckStatus.pass_
        elif result.exit_code == -1:
            status = CheckStatus.error
        else:
            status = CheckStatus.fail

        error_msg = ""
        if result.findings:
            error_msg = "; ".join(
                f"{f.file}:{f.line} [{f.test_id}] {f.severity}: {f.message}"
                for f in result.findings[:10]
            )
        elif result.error:
            error_msg = result.error

        return CheckResult(
            check_type=check_type,
            command="bandit -r",
            exit_code=result.exit_code,
            status=status,
            output_ref="",
            duration_seconds=result.duration_seconds,
            error_message=error_msg,
        )
