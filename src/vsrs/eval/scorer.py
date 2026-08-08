"""Scorer: compute verified task success, hallucination, regression metrics (Section 14.2).

TODO: Phase 0/7 - full scoring implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
    metadata: dict[str, object] = field(default_factory=dict)


def score_task(
    patches: list[PatchCandidate],
    reports: list[VerificationReport],
    final_status: FinalStatus,
    hidden_tests_passed: bool = False,
    regression_tests_passed: bool = True,
    invented_symbols: int = 0,
) -> ScoreResult:
    """Score a single task's outcome.

    Implements the primary metrics from Section 14.2.
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

    return ScoreResult(
        task_id=task_id,
        verified_success=verified_success,
        pass_at_1=pass_at_1,
        repair_success=repair_success,
        regression=regression,
        grounding_errors=invented_symbols,
        evidence_complete=evidence_complete,
        patch_minimality=patch_minimality,
        tool_calls=tool_calls,
        escalated=final_status == FinalStatus.needs_review,
    )
