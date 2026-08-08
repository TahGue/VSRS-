"""Ablation experiments: compare architecture variants (Section 14.3).

Implements an ablation harness that:
- Defines standard ablation configurations (disable specific components)
- Runs benchmarks with components disabled
- Collects results for comparison
- Generates comparison tables

Standard ablations from Section 14.3:
- no_repo_index: No repository index vs structural retrieval
- no_evidence_contract: No evidence contract vs evidence contract
- no_falsification: No falsification step vs explicit falsification planning
- no_repair_loop: One-shot generation vs repair loop
- no_critic: No critic vs independent critic
- no_structured_failures: Raw logs vs structured failure summaries
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from vsrs.eval.reports import EvaluationReport


@dataclass
class AblationConfig:
    """Configuration for an ablation experiment."""

    name: str
    description: str
    disable_components: list[str] = field(default_factory=list)
    # Examples: "repository_index", "evidence_contract", "falsification_step",
    #           "repair_loop", "critic", "structured_failures"


@dataclass
class AblationResult:
    """Result of an ablation experiment."""

    config: AblationConfig
    verified_success_rate: float = 0.0
    pass_at_1_rate: float = 0.0
    repair_success_rate: float = 0.0
    regression_rate: float = 0.0
    grounding_error_rate: float = 0.0
    evidence_completeness_rate: float = 0.0
    avg_tool_calls: float = 0.0
    avg_duration_seconds: float = 0.0
    total_tasks: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "config": {
                "name": self.config.name,
                "description": self.config.description,
                "disable_components": self.config.disable_components,
            },
            "verified_success_rate": self.verified_success_rate,
            "pass_at_1_rate": self.pass_at_1_rate,
            "repair_success_rate": self.repair_success_rate,
            "regression_rate": self.regression_rate,
            "grounding_error_rate": self.grounding_error_rate,
            "evidence_completeness_rate": self.evidence_completeness_rate,
            "avg_tool_calls": self.avg_tool_calls,
            "avg_duration_seconds": self.avg_duration_seconds,
            "total_tasks": self.total_tasks,
        }

    @classmethod
    def from_report(cls, config: AblationConfig, report: EvaluationReport) -> AblationResult:
        """Create an AblationResult from an EvaluationReport."""
        return cls(
            config=config,
            verified_success_rate=report.verified_success_rate,
            pass_at_1_rate=report.pass_at_1_rate,
            repair_success_rate=report.repair_success_rate,
            regression_rate=report.regression_rate,
            grounding_error_rate=report.grounding_error_rate,
            evidence_completeness_rate=report.evidence_completeness_rate,
            avg_tool_calls=report.avg_tool_calls,
            avg_duration_seconds=report.avg_duration_seconds,
            total_tasks=report.total_tasks,
        )


# Predefined ablation experiments from Section 14.3
ABLATION_EXPERIMENTS: list[AblationConfig] = [
    AblationConfig(
        name="baseline",
        description="Full pipeline with all components enabled",
        disable_components=[],
    ),
    AblationConfig(
        name="no_repo_index",
        description="No repository index vs structural retrieval",
        disable_components=["repository_index"],
    ),
    AblationConfig(
        name="no_evidence_contract",
        description="No evidence contract vs evidence contract",
        disable_components=["evidence_contract"],
    ),
    AblationConfig(
        name="no_falsification",
        description="No falsification step vs explicit falsification planning",
        disable_components=["falsification_step"],
    ),
    AblationConfig(
        name="no_repair_loop",
        description="One-shot generation vs repair loop",
        disable_components=["repair_loop"],
    ),
    AblationConfig(
        name="no_critic",
        description="No critic vs independent critic",
        disable_components=["critic"],
    ),
    AblationConfig(
        name="no_structured_failures",
        description="Raw logs vs structured failure summaries",
        disable_components=["structured_failures"],
    ),
]


class AblationHarness:
    """Runs ablation experiments and collects results for comparison.

    The harness takes a runner function that accepts an AblationConfig
    and returns an EvaluationReport. This allows the harness to be
    used with any execution backend (local, Docker, distributed).
    """

    def __init__(
        self,
        runner: Callable[[AblationConfig], EvaluationReport],
        configs: list[AblationConfig] | None = None,
    ) -> None:
        """Initialize the harness.

        Args:
            runner: Function that runs benchmarks with a given ablation config
                    and returns an EvaluationReport.
            configs: List of ablation configs to run. Defaults to ABLATION_EXPERIMENTS.
        """
        self.runner = runner
        self.configs = configs or list(ABLATION_EXPERIMENTS)
        self.results: list[AblationResult] = []

    def run_all(self) -> list[AblationResult]:
        """Run all ablation experiments and collect results."""
        self.results = []
        for config in self.configs:
            report = self.runner(config)
            result = AblationResult.from_report(config, report)
            self.results.append(result)
        return self.results

    def run_single(self, config: AblationConfig) -> AblationResult:
        """Run a single ablation experiment."""
        report = self.runner(config)
        result = AblationResult.from_report(config, report)
        self.results.append(result)
        return result

    def comparison_table(self) -> str:
        """Generate a text comparison table of all ablation results."""
        if not self.results:
            return "No ablation results available. Run run_all() first."

        headers = [
            "Experiment", "Verified%", "Pass@1%", "Repair%",
            "Regress%", "GroundErr", "Evidence%", "Tools", "Duration",
        ]
        rows = []
        for r in self.results:
            rows.append([
                r.config.name,
                f"{r.verified_success_rate:.1%}",
                f"{r.pass_at_1_rate:.1%}",
                f"{r.repair_success_rate:.1%}",
                f"{r.regression_rate:.1%}",
                f"{r.grounding_error_rate:.2f}",
                f"{r.evidence_completeness_rate:.1%}",
                f"{r.avg_tool_calls:.1f}",
                f"{r.avg_duration_seconds:.1f}s",
            ])

        # Calculate column widths
        col_widths = [max(len(str(h)), max((len(row[i]) for row in rows), default=0)) for i, h in enumerate(headers)]

        # Build table
        lines = []
        header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_widths, strict=False))
        separator = "-+-".join("-" * w for w in col_widths)
        lines.append(header_line)
        lines.append(separator)
        for row in rows:
            lines.append(" | ".join(c.ljust(w) for c, w in zip(row, col_widths, strict=False)))

        return "\n".join(lines)

    def to_dict(self) -> list[dict[str, Any]]:
        """Convert all results to a list of dicts for JSON serialization."""
        return [r.to_dict() for r in self.results]
