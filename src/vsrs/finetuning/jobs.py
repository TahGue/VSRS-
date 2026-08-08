"""Fine-tuning job models and orchestration.

Defines the data structures for fine-tuning jobs and an orchestrator
that manages job lifecycle: submission, execution, monitoring, and
result collection.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from vsrs.core.logging import get_logger

logger = get_logger("finetuning.jobs")


class FineTuningMethod(str, Enum):
    """Fine-tuning methods."""

    full = "full"
    lora = "lora"
    qlora = "qlora"
    dpo = "dpo"
    ppo = "ppo"


class FineTuningStatus(str, Enum):
    """Fine-tuning job lifecycle states."""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


@dataclass
class FineTuningJob:
    """A fine-tuning job specification.

    Attributes:
        id: Unique job identifier.
        model_name: Base model to fine-tune (e.g. "gpt-4o", "meta-llama/Llama-3-8B").
        method: Fine-tuning method (full, lora, qlora, dpo, ppo).
        dataset_path: Path to the training dataset (JSONL).
        validation_path: Path to the validation dataset (JSONL).
        output_model_name: Name for the fine-tuned model.
        hyperparameters: Training hyperparameters (lr, epochs, batch_size, etc.).
        status: Current job status.
        created_at: When the job was created.
        started_at: When training started.
        completed_at: When training completed.
        metrics: Training metrics (loss, eval_loss, etc.).
        error: Error message if the job failed.
        tags: Optional tags for grouping.
    """

    id: str = ""
    model_name: str = ""
    method: FineTuningMethod = FineTuningMethod.lora
    dataset_path: str = ""
    validation_path: str = ""
    output_model_name: str = ""
    hyperparameters: dict[str, Any] = field(default_factory=lambda: {
        "learning_rate": 2e-5,
        "num_epochs": 3,
        "batch_size": 8,
        "warmup_steps": 100,
        "weight_decay": 0.01,
    })
    status: FineTuningStatus = FineTuningStatus.pending
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"ftjob_{uuid.uuid4().hex[:12]}"
        if not self.output_model_name:
            self.output_model_name = f"{self.model_name}-finetuned-{self.id[-8:]}"

    @property
    def duration_seconds(self) -> float:
        """Calculate job duration if completed."""
        if self.started_at is None:
            return 0.0
        end = self.completed_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "model_name": self.model_name,
            "method": self.method.value,
            "dataset_path": self.dataset_path,
            "validation_path": self.validation_path,
            "output_model_name": self.output_model_name,
            "hyperparameters": self.hyperparameters,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metrics": self.metrics,
            "error": self.error,
            "tags": self.tags,
            "duration_seconds": self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FineTuningJob:
        return cls(
            id=data["id"],
            model_name=data.get("model_name", ""),
            method=FineTuningMethod(data.get("method", "lora")),
            dataset_path=data.get("dataset_path", ""),
            validation_path=data.get("validation_path", ""),
            output_model_name=data.get("output_model_name", ""),
            hyperparameters=data.get("hyperparameters", {}),
            status=FineTuningStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            metrics=data.get("metrics", {}),
            error=data.get("error", ""),
            tags=data.get("tags", []),
        )


# Type for training execution functions
TrainingExecutor = Callable[[FineTuningJob], dict[str, Any]]


class JobOrchestrator:
    """Orchestrates fine-tuning jobs.

    Manages job submission, execution, monitoring, and result collection.
    Supports custom training executors for different backends (local, cloud, etc.).

    Args:
        executor: Function that executes a training job and returns metrics dict.
    """

    def __init__(self, executor: TrainingExecutor | None = None) -> None:
        self._jobs: dict[str, FineTuningJob] = {}
        self._executor: TrainingExecutor | None = executor

    def submit(self, job: FineTuningJob) -> str:
        """Submit a fine-tuning job.

        Args:
            job: The job to submit.

        Returns:
            The job ID.
        """
        self._jobs[job.id] = job
        logger.info(f"Submitted fine-tuning job {job.id} (model={job.model_name}, method={job.method.value})")
        return job.id

    def execute(self, job_id: str) -> FineTuningJob:
        """Execute a fine-tuning job synchronously.

        Args:
            job_id: ID of the job to execute.

        Returns:
            The updated job with results.

        Raises:
            ValueError: If job not found or no executor configured.
        """
        job = self._jobs.get(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        if self._executor is None:
            raise ValueError("No executor configured")

        job.status = FineTuningStatus.running
        job.started_at = datetime.now(timezone.utc)
        logger.info(f"Starting execution of job {job_id}")

        try:
            metrics = self._executor(job)
            job.metrics = metrics
            job.status = FineTuningStatus.completed
            job.completed_at = datetime.now(timezone.utc)
            logger.info(
                f"Job {job_id} completed: {metrics}"
            )
        except Exception as e:
            job.status = FineTuningStatus.failed
            job.error = str(e)
            job.completed_at = datetime.now(timezone.utc)
            logger.error(f"Job {job_id} failed: {e}")

        return job

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending or running job.

        Returns:
            True if cancelled, False if not found or already completed.
        """
        job = self._jobs.get(job_id)
        if job is None or job.status in (FineTuningStatus.completed, FineTuningStatus.failed):
            return False
        job.status = FineTuningStatus.cancelled
        job.completed_at = datetime.now(timezone.utc)
        logger.info(f"Cancelled job {job_id}")
        return True

    def get(self, job_id: str) -> FineTuningJob | None:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def get_status(self, job_id: str) -> FineTuningStatus | None:
        """Get the status of a job."""
        job = self._jobs.get(job_id)
        return job.status if job else None

    def list_jobs(
        self,
        status: FineTuningStatus | None = None,
        model_name: str | None = None,
    ) -> list[FineTuningJob]:
        """List jobs, optionally filtered."""
        jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        if model_name is not None:
            jobs = [j for j in jobs if j.model_name == model_name]
        return jobs

    def set_executor(self, executor: TrainingExecutor) -> None:
        """Set the training executor function."""
        self._executor = executor

    def count(self) -> int:
        """Get total number of jobs."""
        return len(self._jobs)

    def clear(self) -> None:
        """Remove all jobs."""
        self._jobs.clear()
