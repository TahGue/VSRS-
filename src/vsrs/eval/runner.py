"""Benchmark runner: execute benchmark tasks and collect evaluation results.

The BenchmarkRunner coordinates:
- Loading benchmark tasks from a BenchmarkSet
- Running each task through the VSRS pipeline (or a mock runner)
- Scoring each task result
- Aggregating into an EvaluationReport
- Exporting results (JSON, CSV)
"""

from __future__ import annotations

import time
from typing import Any, Callable, Protocol

from vsrs.core.schemas import FinalStatus, PatchCandidate, VerificationReport
from vsrs.eval.reports import EvaluationReport
from vsrs.eval.scorer import ScoreResult, score_task
from vsrs.eval.tasks import BenchmarkSet, BenchmarkTask


class TaskRunner(Protocol):
    """Protocol for running a single benchmark task."""

    def run(
        self,
        task: BenchmarkTask,
    ) -> tuple[list[PatchCandidate], list[VerificationReport], FinalStatus, dict[str, Any]]:
        """Run a benchmark task and return results.

        Returns:
            Tuple of (patches, verification_reports, final_status, extra_metrics).
            extra_metrics may include: hidden_tests_passed, hidden_tests_total,
            hidden_tests_failed, regression_tests_passed, invented_symbols,
            new_tests_written, duration_seconds.
        """
        ...


class BenchmarkRunner:
    """Runs benchmark tasks and collects evaluation results.

    Args:
        benchmark_set: The set of benchmark tasks to run.
        task_runner: A callable that runs a single BenchmarkTask and returns
                     (patches, reports, final_status, extra_metrics).
    """

    def __init__(
        self,
        benchmark_set: BenchmarkSet,
        task_runner: Callable[
            [BenchmarkTask],
            tuple[list[PatchCandidate], list[VerificationReport], FinalStatus, dict[str, Any]],
        ],
    ) -> None:
        self.benchmark_set = benchmark_set
        self.task_runner = task_runner
        self.report: EvaluationReport = EvaluationReport()
        self._results: dict[str, ScoreResult] = {}

    def run_all(self) -> EvaluationReport:
        """Run all benchmark tasks and return the aggregate report."""
        self.report = EvaluationReport()

        for task in self.benchmark_set.all():
            result = self.run_single(task)
            category = task.task_type.value
            self.report.add_result(result, category=category)

        return self.report

    def run_single(self, task: BenchmarkTask) -> ScoreResult:
        """Run a single benchmark task and return its score."""
        start_time = time.time()

        patches, reports, final_status, extra = self.task_runner(task)

        duration = time.time() - start_time
        extra.setdefault("duration_seconds", duration)

        result = score_task(
            patches=patches,
            reports=reports,
            final_status=final_status,
            hidden_tests_passed=extra.get("hidden_tests_passed", False),
            hidden_tests_total=extra.get("hidden_tests_total", len(task.hidden_tests)),
            hidden_tests_failed=extra.get("hidden_tests_failed", 0),
            regression_tests_passed=extra.get("regression_tests_passed", True),
            invented_symbols=extra.get("invented_symbols", 0),
            new_tests_written=extra.get("new_tests_written", 0),
            duration_seconds=extra.get("duration_seconds", 0.0),
        )

        self._results[task.id] = result
        return result

    def get_result(self, task_id: str) -> ScoreResult | None:
        """Get the score result for a specific task."""
        return self._results.get(task_id)

    def export_json(self, output_path: str) -> None:
        """Export the report to a JSON file."""
        from pathlib import Path
        self.report.to_json(Path(output_path))

    def export_csv(self, output_path: str) -> None:
        """Export per-task results to a CSV file."""
        from pathlib import Path
        self.report.to_csv(Path(output_path))

    def summary(self) -> str:
        """Generate a text summary of the benchmark results."""
        return self.report.summary()
