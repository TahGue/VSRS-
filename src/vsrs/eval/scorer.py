"""Scorer: compute verified task success, hallucination, regression metrics (Section 14.2).

Implements scoring for:
- Verified success (final status + hidden tests + regression tests)
- Pass@1 (first-attempt success)
- Repair success (multi-attempt success)
- Regression detection
- Grounding error detection (invented symbols)
- Evidence completeness
- Patch minimality
- Test adequacy (new targeted tests)
- Tool call counting
- Escalation tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vsrs.core.schemas import CheckStatus, FinalStatus, PatchCandidate, VerificationReport


@dataclass
class ScoreResult:
    """Result of scoring a single task."""

    task_id: str
    verified_success: bool = False
    pass_at_1: bool = False
    repair_success: bool = False
    regression: bool = False
    grounding_errors: int = 0
    evidence_complete: bool = False
    patch_minimality: float = 1.0
    test_adequacy: float = 0.0
    tool_calls: int = 0
    total_duration_seconds: float = 0.0
    escalated: bool = False
    hidden_tests_passed: bool = False
    hidden_tests_total: int = 0
    hidden_tests_failed: int = 0
    new_tests_written: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "task_id": self.task_id,
            "verified_success": self.verified_success,
            "pass_at_1": self.pass_at_1,
            "repair_success": self.repair_success,
            "regression": self.regression,
            "grounding_errors": self.grounding_errors,
            "evidence_complete": self.evidence_complete,
            "patch_minimality": self.patch_minimality,
            "test_adequacy": self.test_adequacy,
            "tool_calls": self.tool_calls,
            "total_duration_seconds": self.total_duration_seconds,
            "escalated": self.escalated,
            "hidden_tests_passed": self.hidden_tests_passed,
            "hidden_tests_total": self.hidden_tests_total,
            "hidden_tests_failed": self.hidden_tests_failed,
            "new_tests_written": self.new_tests_written,
            "metadata": dict(self.metadata) if self.metadata else {},
        }


def score_task(
    patches: list[PatchCandidate],
    reports: list[VerificationReport],
    final_status: FinalStatus,
    hidden_tests_passed: bool = False,
    hidden_tests_total: int = 0,
    hidden_tests_failed: int = 0,
    regression_tests_passed: bool = True,
    invented_symbols: int = 0,
    new_tests_written: int = 0,
    duration_seconds: float = 0.0,
) -> ScoreResult:
    """Score a single task's outcome.

    Implements the primary metrics from Section 14.2.

    Args:
        patches: All patch attempts for the task.
        reports: All verification reports for the task.
        final_status: The final decision status.
        hidden_tests_passed: Whether all hidden acceptance tests passed.
        hidden_tests_total: Total number of hidden tests.
        hidden_tests_failed: Number of hidden tests that failed.
        regression_tests_passed: Whether existing tests still pass.
        invented_symbols: Number of invented symbols (grounding errors).
        new_tests_written: Number of new targeted tests written by the model.
        duration_seconds: Total execution time.

    Returns:
        ScoreResult with all computed metrics.
    """
    task_id = patches[0].task_id if patches else ""

    verified_success = (
        final_status == FinalStatus.verified_candidate
        and hidden_tests_passed
        and regression_tests_passed
    )

    pass_at_1 = verified_success and len(patches) == 1

    repair_success = (
        len(patches) > 1
        and verified_success
        and not pass_at_1
    )

    regression = not regression_tests_passed

    # Check evidence completeness from latest report
    latest_report = reports[-1] if reports else None
    evidence_complete = (
        latest_report is not None
        and latest_report.required_passed
        and len(latest_report.unresolved_unknowns) == 0
    )

    # Count tool calls from reports
    tool_calls = sum(len(r.checks) for r in reports)

    # Patch minimality: fewer changed files is better
    if patches:
        latest_patch = patches[-1]
        patch_minimality = max(0.0, 1.0 - len(latest_patch.changed_files) * 0.1)
    else:
        patch_minimality = 0.0

    # Test adequacy: did the model write new targeted tests?
    if hidden_tests_total > 0:
        test_adequacy = min(1.0, new_tests_written / max(1, hidden_tests_total))
    elif new_tests_written > 0:
        test_adequacy = 0.5
    else:
        test_adequacy = 0.0

    return ScoreResult(
        task_id=task_id,
        verified_success=verified_success,
        pass_at_1=pass_at_1,
        repair_success=repair_success,
        regression=regression,
        grounding_errors=invented_symbols,
        evidence_complete=evidence_complete,
        patch_minimality=patch_minimality,
        test_adequacy=test_adequacy,
        tool_calls=tool_calls,
        total_duration_seconds=duration_seconds,
        escalated=final_status == FinalStatus.needs_review,
        hidden_tests_passed=hidden_tests_passed,
        hidden_tests_total=hidden_tests_total,
        hidden_tests_failed=hidden_tests_failed,
        new_tests_written=new_tests_written,
    )


def detect_grounding_errors(
    patch: PatchCandidate,
    known_symbols: set[str] | None = None,
) -> int:
    """Detect invented symbols in a patch diff.

    Scans the diff for added imports or references to symbols that don't
    exist in the known symbol set.

    Args:
        patch: The patch candidate to check.
        known_symbols: Set of known symbol names in the repository.

    Returns:
        Number of potentially invented symbols.
    """
    if not known_symbols:
        return 0

    invented = 0
    for line in patch.diff.split("\n"):
        if not line.startswith("+"):
            continue
        # Check import statements
        stripped = line[1:].strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            # Extract imported names
            parts = stripped.split()
            for part in parts:
                # Clean up the part
                clean = part.strip(",();")
                if clean and clean not in known_symbols and clean not in (
                    "import", "from", "as", "*", "typing", "os", "sys",
                    "pathlib", "json", "abc", "dataclasses", "functools",
                    "collections", "itertools", "re", "io",
                ):
                    # Only count if it looks like a symbol reference
                    if clean[0].isupper() or "_" in clean:
                        invented += 1
    return invented
