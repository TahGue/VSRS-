"""Failure categorizer: convert verification results to structured summaries (Section 7.3).

Takes CheckResults from verification and produces categorized FailureSummary
objects that can be fed back to the reasoner for repair. Instead of raw logs,
the reasoner receives actionable, categorized failure information.
"""

from __future__ import annotations

import re

from vsrs.core.logging import get_logger
from vsrs.core.schemas import CheckResult, CheckStatus, VerificationReport
from vsrs.reasoning.protocol import FailureSummary

logger = get_logger("repair.categorizer")


# Error category keywords mapped to categories
_CATEGORY_PATTERNS: dict[str, list[str]] = {
    "syntax": ["SyntaxError", "syntax error", "unexpected indent", "unexpected token", "EOL", "invalid syntax"],
    "test_failure": ["AssertionError", "assert", "FAILED", "test_", "pytest"],
    "type_error": ["mypy", "type:", "incompatible type", "Argument", "return type", "no_match"],
    "import_error": ["ImportError", "ModuleNotFoundError", "cannot import", "No module named"],
    "lint": ["ruff", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "F", "W", "C", "D", "N", "B", "UP", "SIM", "RUF"],
    "security": ["bandit", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "injection", "vulnerability"],
    "config": ["config", "pyproject", "setup.cfg", "tox.ini", "pytest.ini", "NoFile"],
    "other": [],
}


def categorize_error(check_type: str, error_message: str) -> str:
    """Categorize an error message into a standard category.

    Args:
        check_type: The type of check (syntax, existing_tests, lint, etc.).
        error_message: The error message from the check.

    Returns:
        One of: syntax, test_failure, type_error, import_error, lint, security, config, other
    """
    # Direct mapping from check type
    if check_type == "syntax":
        return "syntax"
    if check_type in ("existing_tests", "new_targeted_tests"):
        # Could be test failure or import error
        msg_lower = error_message.lower()
        if any(kw.lower() in msg_lower for kw in _CATEGORY_PATTERNS["import_error"]):
            return "import_error"
        return "test_failure"
    if check_type == "type_check":
        return "type_error"
    if check_type == "lint":
        return "lint"
    if check_type in ("security_scan", "static_analysis"):
        return "security"
    if check_type == "dependency_validation":
        if any(kw.lower() in error_message.lower() for kw in _CATEGORY_PATTERNS["import_error"]):
            return "import_error"
        return "other"
    if check_type == "build":
        if any(kw in error_message.lower() for kw in _CATEGORY_PATTERNS["config"]):
            return "config"
        return "other"

    # Fall back to pattern matching
    msg_lower = error_message.lower()
    for category, keywords in _CATEGORY_PATTERNS.items():
        if category == "other":
            continue
        for kw in keywords:
            # Skip overly broad short patterns in fallback matching
            if len(kw) <= 2:
                continue
            if kw.lower() in msg_lower:
                return category

    return "other"


def extract_file_and_line(error_message: str) -> tuple[str, int | None]:
    """Extract file path and line number from an error message.

    Returns:
        Tuple of (file_path, line_number or None).
    """
    # Pattern: file.py:line:
    match = re.search(r"(\S+\.py):(\d+)", error_message)
    if match:
        return match.group(1), int(match.group(2))

    # Pattern: file.py line N
    match = re.search(r"(\S+\.py)\s+line\s+(\d+)", error_message, re.IGNORECASE)
    if match:
        return match.group(1), int(match.group(2))

    # Pattern: File "path", line N
    match = re.search(r'File\s+"([^"]+)",\s+line\s+(\d+)', error_message)
    if match:
        return match.group(1), int(match.group(2))

    return "", None


def extract_failed_test_names(error_message: str) -> list[str]:
    """Extract failed test names from an error message."""
    names: list[str] = []

    # Pattern: test_name: error_type
    for match in re.finditer(r"(\w+):\s+\w+Error", error_message):
        names.append(match.group(1))

    # Pattern: test_name in FAILED lines
    for match in re.finditer(r"FAILED.*?::(\S+?)(?:\s|$)", error_message):
        names.append(match.group(1))

    # Pattern: test_name FAILED
    for match in re.finditer(r"(\S+?)\s+FAILED", error_message):
        name = match.group(1)
        if "::" in name:
            names.append(name.split("::")[-1])

    return list(dict.fromkeys(names))


def suggest_fix(category: str, error_message: str, file: str = "", line: int | None = None) -> str:
    """Generate a suggested fix based on the error category.

    Args:
        category: Error category.
        error_message: The error message.
        file: Relevant file path.
        line: Relevant line number.

    Returns:
        A suggested fix string.
    """
    suggestions: dict[str, str] = {
        "syntax": "Fix the syntax error — check for missing colons, parentheses, or indentation",
        "test_failure": "Review the failing assertion and adjust the code to match expected behavior",
        "type_error": "Add or fix type annotations to resolve the type mismatch",
        "import_error": "Check that the imported module exists and is installed; verify the import path",
        "lint": "Fix the lint issue — follow the style rule indicated by the rule code",
        "security": "Address the security finding — remove the vulnerable pattern or use a safe alternative",
        "config": "Fix the configuration file — check for syntax errors or missing required fields",
        "other": "Review the error message and fix the underlying issue",
    }

    base = suggestions.get(category, suggestions["other"])

    if file:
        location = f" in {file}"
        if line:
            location += f":{line}"
        return f"{base} (at {location[1:]})"

    return base


class FailureCategorizer:
    """Categorizes verification failures into structured summaries.

    Implements Section 7.3: instead of feeding raw logs back to the reasoner,
    failures are categorized with actionable information.
    """

    def categorize(self, report: VerificationReport) -> list[FailureSummary]:
        """Convert a VerificationReport's failed checks into FailureSummary list.

        Args:
            report: The verification report from a patch attempt.

        Returns:
            List of FailureSummary objects for each failed/errored check.
        """
        summaries: list[FailureSummary] = []

        for check in report.checks:
            if check.status in (CheckStatus.pass_, CheckStatus.skip, CheckStatus.waived):
                continue

            category = categorize_error(check.check_type, check.error_message)
            file, line = extract_file_and_line(check.error_message)
            test_names = extract_failed_test_names(check.error_message) if check.check_type in ("existing_tests", "new_targeted_tests") else []

            summary = FailureSummary(
                check_type=check.check_type,
                status=check.status.value,
                error_category=category,
                error_message=check.error_message,
                failed_test_names=test_names,
                relevant_file=file,
                relevant_line=line,
                suggested_fix=suggest_fix(category, check.error_message, file, line),
            )
            summaries.append(summary)

        logger.info(
            f"Categorized {len(summaries)} failures from {len(report.checks)} checks "
            f"(categories: {[s.error_category for s in summaries]})"
        )

        return summaries

    def categorize_check(self, check: CheckResult) -> FailureSummary:
        """Categorize a single check result.

        Args:
            check: A single CheckResult.

        Returns:
            FailureSummary for the check.
        """
        category = categorize_error(check.check_type, check.error_message)
        file, line = extract_file_and_line(check.error_message)
        test_names = extract_failed_test_names(check.error_message) if check.check_type in ("existing_tests", "new_targeted_tests") else []

        return FailureSummary(
            check_type=check.check_type,
            status=check.status.value,
            error_category=category,
            error_message=check.error_message,
            failed_test_names=test_names,
            relevant_file=file,
            relevant_line=line,
            suggested_fix=suggest_fix(category, check.error_message, file, line),
        )

    def has_blocking_failures(self, report: VerificationReport) -> bool:
        """Check if a verification report has any blocking failures.

        Args:
            report: The verification report.

        Returns:
            True if there are any failed or errored checks.
        """
        return any(
            check.status in (CheckStatus.fail, CheckStatus.error)
            for check in report.checks
        )

    def failure_categories(self, report: VerificationReport) -> set[str]:
        """Get the set of error categories present in a report.

        Args:
            report: The verification report.

        Returns:
            Set of error category strings.
        """
        return {s.error_category for s in self.categorize(report)}
