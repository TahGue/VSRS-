"""Reports: evaluation metrics and comparisons (Section 14).

TODO: Phase 7 - full report generation implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vsrs.eval.scorer import ScoreResult


@dataclass
class EvaluationReport:
    """Aggregate evaluation report across multiple tasks."""

    total_tasks: int = 0
    verified_success_count: int = 0
    pass_at_1_count: int = 0
    repair_success_count: int = 0
    regression_count: int = 0
    total_grounding_errors: int = 0
    evidence_complete_count: int = 0
    escalated_count: int = 0
    total_tool_calls: int = 0
    total_duration_seconds: float = 0.0
    per_task: list[ScoreResult] = field(default_factory=list)

    @property
    def verified_success_rate(self) -> float:
        return self.verified_success_count / self.total_tasks if self.total_tasks else 0.0

    @property
    def pass_at_1_rate(self) -> float:
        return self.pass_at_1_count / self.total_tasks if self.total_tasks else 0.0

    @property
    def repair_success_rate(self) -> float:
        return self.repair_success_count / self.total_tasks if self.total_tasks else 0.0

    @property
    def regression_rate(self) -> float:
        return self.regression_count / self.total_tasks if self.total_tasks else 0.0

    @property
    def grounding_error_rate(self) -> float:
        return self.total_grounding_errors / self.total_tasks if self.total_tasks else 0.0

    @property
    def evidence_completeness_rate(self) -> float:
        return self.evidence_complete_count / self.total_tasks if self.total_tasks else 0.0

    @property
    def avg_tool_calls(self) -> float:
        return self.total_tool_calls / self.total_tasks if self.total_tasks else 0.0

    @property
    def avg_duration_seconds(self) -> float:
        return self.total_duration_seconds / self.total_tasks if self.total_tasks else 0.0

    def add_result(self, result: ScoreResult) -> None:
        """Add a single task's score to the aggregate."""
        self.total_tasks += 1
        self.per_task.append(result)
        if result.verified_success:
            self.verified_success_count += 1
        if result.pass_at_1:
            self.pass_at_1_count += 1
        if result.repair_success:
            self.repair_success_count += 1
        if result.regression:
            self.regression_count += 1
        self.total_grounding_errors += result.grounding_errors
        if result.evidence_complete:
            self.evidence_complete_count += 1
        if result.escalated:
            self.escalated_count += 1
        self.total_tool_calls += result.tool_calls
        self.total_duration_seconds += result.total_duration_seconds

    def summary(self) -> str:
        """Generate a text summary of the report."""
        return (
            f"Tasks: {self.total_tasks}\n"
            f"Verified success: {self.verified_success_count} ({self.verified_success_rate:.1%})\n"
            f"Pass@1: {self.pass_at_1_count} ({self.pass_at_1_rate:.1%})\n"
            f"Repair success: {self.repair_success_count} ({self.repair_success_rate:.1%})\n"
            f"Regression: {self.regression_count} ({self.regression_rate:.1%})\n"
            f"Grounding errors: {self.total_grounding_errors} ({self.grounding_error_rate:.1%})\n"
            f"Evidence complete: {self.evidence_complete_count} ({self.evidence_completeness_rate:.1%})\n"
            f"Escalated: {self.escalated_count}\n"
            f"Avg tool calls: {self.avg_tool_calls:.1f}\n"
            f"Avg duration: {self.avg_duration_seconds:.1f}s"
        )
