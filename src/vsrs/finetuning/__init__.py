"""Model fine-tuning pipeline for VSRS.

Provides job orchestration for fine-tuning models on collected trajectories,
dataset versioning with deduplication, and A/B comparison between base
and fine-tuned models.
"""

from __future__ import annotations

from vsrs.finetuning.jobs import (
    FineTuningJob,
    FineTuningMethod,
    FineTuningStatus,
    JobOrchestrator,
)
from vsrs.finetuning.versioning import DatasetVersion, DatasetVersionManager
from vsrs.finetuning.comparison import ABComparison, ComparisonResult, ModelComparisonHarness

__all__ = [
    "ABComparison",
    "ComparisonResult",
    "DatasetVersion",
    "DatasetVersionManager",
    "FineTuningJob",
    "FineTuningMethod",
    "FineTuningStatus",
    "JobOrchestrator",
    "ModelComparisonHarness",
]
