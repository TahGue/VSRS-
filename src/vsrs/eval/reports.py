"""Reports: evaluation metrics and comparisons (Section 14).

Implements aggregate evaluation reporting with:
- Per-task scoring (via ScoreResult)
- Aggregate metrics (rates, averages)
- Per-category breakdowns (by task type, difficulty, tags)
- CSV and JSON export
- Report comparison (delta between two reports)
- Text summary generation
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vsrs.eval.scorer import ScoreResult


@dataclass
class CategoryBreakdown:
    """Metrics broken down by a category (task type, difficulty, etc.)."""

    category: str
    total_tasks: int = 0
    verified_success_count: int = 0
    pass_at_1_count: int = 0
    repair_success_count: int = 0
    regression_count: int = 0
    escalated_count: int = 0

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "total_tasks": self.total_tasks,
            "verified_success_count": self.verified_success_count,
            "verified_success_rate": round(self.verified_success_rate, 4),
            "pass_at_1_count": self.pass_at_1_count,
            "pass_at_1_rate": round(self.pass_at_1_rate, 4),
            "repair_success_count": self.repair_success_count,
            "repair_success_rate": round(self.repair_success_rate, 4),
            "regression_count": self.regression_count,
            "regression_rate": round(self.regression_rate, 4),
            "escalated_count": self.escalated_count,
        }


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
    _task_categories: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def from_scores(
        cls,
        scores: list[ScoreResult],
        categories: dict[str, str] | None = None,
    ) -> EvaluationReport:
        """Build an EvaluationReport from a list of ScoreResults.

        Args:
            scores: List of ScoreResult objects.
            categories: Optional mapping of task_id -> category label.

        Returns:
            EvaluationReport with all scores aggregated.
        """
        report = cls()
        for score in scores:
            cat = categories.get(score.task_id, "") if categories else ""
            report.add_result(score, category=cat)
        return report

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

    def add_result(self, result: ScoreResult, category: str = "") -> None:
        """Add a single task's score to the aggregate.

        Args:
            result: The ScoreResult for this task.
            category: Optional category label (e.g. task type, difficulty) for breakdowns.
        """
        self.total_tasks += 1
        self.per_task.append(result)
        if category:
            self._task_categories[result.task_id] = category
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

    def breakdown_by_category(self, categories: dict[str, str] | None = None) -> list[CategoryBreakdown]:
        """Break down results by category.

        Args:
            categories: Mapping of task_id -> category label.
                        If None, uses categories stored via add_result().

        Returns:
            List of CategoryBreakdown, one per unique category.
        """
        cat_map = categories or self._task_categories
        breakdowns: dict[str, CategoryBreakdown] = {}

        for result in self.per_task:
            cat = cat_map.get(result.task_id, "unknown")
            if cat not in breakdowns:
                breakdowns[cat] = CategoryBreakdown(category=cat)
            b = breakdowns[cat]
            b.total_tasks += 1
            if result.verified_success:
                b.verified_success_count += 1
            if result.pass_at_1:
                b.pass_at_1_count += 1
            if result.repair_success:
                b.repair_success_count += 1
            if result.regression:
                b.regression_count += 1
            if result.escalated:
                b.escalated_count += 1

        return list(breakdowns.values())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "total_tasks": self.total_tasks,
            "verified_success_count": self.verified_success_count,
            "verified_success_rate": round(self.verified_success_rate, 4),
            "pass_at_1_count": self.pass_at_1_count,
            "pass_at_1_rate": round(self.pass_at_1_rate, 4),
            "repair_success_count": self.repair_success_count,
            "repair_success_rate": round(self.repair_success_rate, 4),
            "regression_count": self.regression_count,
            "regression_rate": round(self.regression_rate, 4),
            "total_grounding_errors": self.total_grounding_errors,
            "grounding_error_rate": round(self.grounding_error_rate, 4),
            "evidence_complete_count": self.evidence_complete_count,
            "evidence_completeness_rate": round(self.evidence_completeness_rate, 4),
            "escalated_count": self.escalated_count,
            "total_tool_calls": self.total_tool_calls,
            "avg_tool_calls": round(self.avg_tool_calls, 2),
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "avg_duration_seconds": round(self.avg_duration_seconds, 2),
            "per_task": [r.to_dict() for r in self.per_task],
        }

    def to_json(self, output_path: Path | None = None) -> str:
        """Serialize to JSON. If output_path given, also writes to file."""
        data = self.to_dict()
        text = json.dumps(data, indent=2, default=str)
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text)
        return text

    def to_csv(self, output_path: Path | None = None) -> str:
        """Serialize per-task results to CSV. If output_path given, also writes to file."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "task_id", "verified_success", "pass_at_1", "repair_success",
            "regression", "grounding_errors", "evidence_complete",
            "patch_minimality", "test_adequacy", "tool_calls",
            "duration_seconds", "escalated", "hidden_tests_passed",
            "hidden_tests_total", "hidden_tests_failed", "new_tests_written",
        ])
        for r in self.per_task:
            writer.writerow([
                r.task_id, r.verified_success, r.pass_at_1, r.repair_success,
                r.regression, r.grounding_errors, r.evidence_complete,
                round(r.patch_minimality, 3), round(r.test_adequacy, 3),
                r.tool_calls, round(r.total_duration_seconds, 2),
                r.escalated, r.hidden_tests_passed,
                r.hidden_tests_total, r.hidden_tests_failed, r.new_tests_written,
            ])
        text = output.getvalue()
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text)
        return text

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

    @classmethod
    def compare(cls, baseline: EvaluationReport, experimental: EvaluationReport) -> dict[str, Any]:
        """Compare two reports and return deltas.

        Args:
            baseline: The baseline report.
            experimental: The experimental report.

        Returns:
            Dict with metric names and delta values (experimental - baseline).
        """
        return {
            "total_tasks_delta": experimental.total_tasks - baseline.total_tasks,
            "verified_success_rate_delta": round(
                experimental.verified_success_rate - baseline.verified_success_rate, 4
            ),
            "pass_at_1_rate_delta": round(
                experimental.pass_at_1_rate - baseline.pass_at_1_rate, 4
            ),
            "repair_success_rate_delta": round(
                experimental.repair_success_rate - baseline.repair_success_rate, 4
            ),
            "regression_rate_delta": round(
                experimental.regression_rate - baseline.regression_rate, 4
            ),
            "grounding_error_rate_delta": round(
                experimental.grounding_error_rate - baseline.grounding_error_rate, 4
            ),
            "evidence_completeness_rate_delta": round(
                experimental.evidence_completeness_rate - baseline.evidence_completeness_rate, 4
            ),
            "avg_tool_calls_delta": round(
                experimental.avg_tool_calls - baseline.avg_tool_calls, 2
            ),
            "avg_duration_seconds_delta": round(
                experimental.avg_duration_seconds - baseline.avg_duration_seconds, 2
            ),
        }
