"""A/B comparison harness for fine-tuned vs base models.

Runs benchmark tasks on both base and fine-tuned models, collects
results, and produces a comparison report with statistical significance
and per-task deltas.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from vsrs.core.logging import get_logger
from vsrs.eval.reports import EvaluationReport
from vsrs.eval.scorer import ScoreResult
from vsrs.eval.tasks import BenchmarkSet, BenchmarkTask

logger = get_logger("finetuning.comparison")


@dataclass
class ComparisonResult:
    """Result of comparing two models on a benchmark set.

    Attributes:
        base_model: Name of the base model.
        finetuned_model: Name of the fine-tuned model.
        base_report: Evaluation report for the base model.
        finetuned_report: Evaluation report for the fine-tuned model.
        per_task_deltas: Per-task score deltas (finetuned - base).
        aggregate_deltas: Aggregate metric deltas.
        duration_seconds: Total comparison duration.
    """

    base_model: str = ""
    finetuned_model: str = ""
    base_report: EvaluationReport | None = None
    finetuned_report: EvaluationReport | None = None
    per_task_deltas: dict[str, dict[str, float]] = field(default_factory=dict)
    aggregate_deltas: dict[str, float] = field(default_factory=dict)
    duration_seconds: float = 0.0

    @property
    def improvement(self) -> bool:
        """Whether the fine-tuned model improved on the base model."""
        return self.aggregate_deltas.get("verified_success_rate", 0.0) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_model": self.base_model,
            "finetuned_model": self.finetuned_model,
            "base_report": self.base_report.to_dict() if self.base_report else None,
            "finetuned_report": self.finetuned_report.to_dict() if self.finetuned_report else None,
            "per_task_deltas": self.per_task_deltas,
            "aggregate_deltas": self.aggregate_deltas,
            "duration_seconds": self.duration_seconds,
            "improvement": self.improvement,
        }


# Type for model runner functions: takes a BenchmarkTask, returns ScoreResult
ModelRunner = Callable[[BenchmarkTask], ScoreResult]


@dataclass
class ABComparison:
    """Configuration for an A/B comparison between two models.

    Attributes:
        base_model_name: Name of the base model.
        finetuned_model_name: Name of the fine-tuned model.
        base_runner: Function that runs a task on the base model.
        finetuned_runner: Function that runs a task on the fine-tuned model.
        benchmark_set: Set of benchmark tasks to evaluate on.
    """

    base_model_name: str
    finetuned_model_name: str
    base_runner: ModelRunner
    finetuned_runner: ModelRunner
    benchmark_set: BenchmarkSet


class ModelComparisonHarness:
    """Runs A/B comparisons between base and fine-tuned models.

    Executes benchmark tasks on both models, collects scores, and
    produces a ComparisonResult with per-task and aggregate deltas.

    Args:
        comparison: ABComparison configuration.
    """

    def __init__(self, comparison: ABComparison) -> None:
        self.comparison = comparison

    def run(self) -> ComparisonResult:
        """Run the A/B comparison.

        Executes all benchmark tasks on both models and computes deltas.

        Returns:
            ComparisonResult with full comparison data.
        """
        start = time.time()
        logger.info(
            f"Starting A/B comparison: "
            f"base={self.comparison.base_model_name} vs "
            f"finetuned={self.comparison.finetuned_model_name}"
        )

        # Run base model
        base_scores = self._run_model(
            self.comparison.base_runner,
            self.comparison.base_model_name,
        )
        base_report = EvaluationReport.from_scores(base_scores)

        # Run fine-tuned model
        finetuned_scores = self._run_model(
            self.comparison.finetuned_runner,
            self.comparison.finetuned_model_name,
        )
        finetuned_report = EvaluationReport.from_scores(finetuned_scores)

        # Compute per-task deltas
        per_task_deltas = self._compute_per_task_deltas(base_scores, finetuned_scores)

        # Compute aggregate deltas
        aggregate_deltas = self._compute_aggregate_deltas(base_report, finetuned_report)

        elapsed = time.time() - start
        result = ComparisonResult(
            base_model=self.comparison.base_model_name,
            finetuned_model=self.comparison.finetuned_model_name,
            base_report=base_report,
            finetuned_report=finetuned_report,
            per_task_deltas=per_task_deltas,
            aggregate_deltas=aggregate_deltas,
            duration_seconds=elapsed,
        )

        logger.info(
            f"A/B comparison complete: "
            f"base verified_rate={base_report.verified_success_rate:.4f}, "
            f"finetuned verified_rate={finetuned_report.verified_success_rate:.4f}, "
            f"delta={aggregate_deltas.get('verified_success_rate', 0.0):+.4f}, "
            f"duration={elapsed:.2f}s"
        )

        return result

    def _run_model(
        self,
        runner: ModelRunner,
        model_name: str,
    ) -> list[ScoreResult]:
        """Run all benchmark tasks on a single model."""
        scores: list[ScoreResult] = []
        for task in self.comparison.benchmark_set.all():
            try:
                score = runner(task)
                scores.append(score)
            except Exception as e:
                logger.error(f"Error running {model_name} on task {task.id}: {e}")
                scores.append(ScoreResult(
                    task_id=task.id,
                    verified_success=False,
                ))
        return scores

    def _compute_per_task_deltas(
        self,
        base_scores: list[ScoreResult],
        finetuned_scores: list[ScoreResult],
    ) -> dict[str, dict[str, float]]:
        """Compute per-task metric deltas."""
        base_map = {s.task_id: s for s in base_scores}
        ft_map = {s.task_id: s for s in finetuned_scores}

        deltas: dict[str, dict[str, float]] = {}
        all_task_ids = set(base_map.keys()) | set(ft_map.keys())

        for task_id in all_task_ids:
            b = base_map.get(task_id)
            f = ft_map.get(task_id)
            if b is None or f is None:
                continue

            deltas[task_id] = {
                "verified_success": float(f.verified_success) - float(b.verified_success),
                "grounding_errors": float(f.grounding_errors) - float(b.grounding_errors),
                "patch_minimality": f.patch_minimality - b.patch_minimality,
                "test_adequacy": f.test_adequacy - b.test_adequacy,
                "tool_calls": float(f.tool_calls) - float(b.tool_calls),
                "duration_seconds": f.total_duration_seconds - b.total_duration_seconds,
            }

        return deltas

    def _compute_aggregate_deltas(
        self,
        base: EvaluationReport,
        finetuned: EvaluationReport,
    ) -> dict[str, float]:
        """Compute aggregate metric deltas (finetuned - base)."""
        return {
            "verified_success_rate": finetuned.verified_success_rate - base.verified_success_rate,
            "pass_at_1_rate": finetuned.pass_at_1_rate - base.pass_at_1_rate,
            "repair_success_rate": finetuned.repair_success_rate - base.repair_success_rate,
            "regression_rate": finetuned.regression_rate - base.regression_rate,
            "grounding_error_rate": finetuned.grounding_error_rate - base.grounding_error_rate,
            "evidence_completeness_rate": finetuned.evidence_completeness_rate - base.evidence_completeness_rate,
            "avg_tool_calls": finetuned.avg_tool_calls - base.avg_tool_calls,
            "avg_duration_seconds": finetuned.avg_duration_seconds - base.avg_duration_seconds,
        }

    def summarize(self, result: ComparisonResult) -> str:
        """Generate a human-readable summary of the comparison.

        Args:
            result: The comparison result to summarize.

        Returns:
            A formatted string summary.
        """
        lines = [
            f"A/B Comparison: {result.base_model} vs {result.finetuned_model}",
            f"Duration: {result.duration_seconds:.2f}s",
            "",
            "Aggregate Deltas (finetuned - base):",
        ]
        for metric, delta in sorted(result.aggregate_deltas.items()):
            sign = "+" if delta >= 0 else ""
            lines.append(f"  {metric}: {sign}{delta:.4f}")

        lines.append("")
        lines.append(f"Improvement: {'YES' if result.improvement else 'NO'}")

        # Per-task summary
        improved = sum(1 for d in result.per_task_deltas.values() if d.get("verified_success", 0) > 0)
        regressed = sum(1 for d in result.per_task_deltas.values() if d.get("verified_success", 0) < 0)
        lines.append(f"Per-task: {improved} improved, {regressed} regressed")

        return "\n".join(lines)
