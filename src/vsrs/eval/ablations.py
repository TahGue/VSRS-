"""Ablation experiments: compare architecture variants (Section 14.3).

TODO: Phase 7 - full ablation harness implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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


# Predefined ablation experiments from Section 14.3
ABLATION_EXPERIMENTS: list[AblationConfig] = [
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
