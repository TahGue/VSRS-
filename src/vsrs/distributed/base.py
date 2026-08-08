"""Base classes for distributed task execution.

Defines the core abstractions:
- TaskJob: A unit of work (benchmark task, verification run, etc.)
- JobResult: The outcome of a job
- JobStatus: Lifecycle states for jobs
- TaskQueue: Abstract queue for submitting and tracking jobs
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class JobStatus(str, Enum):
    """Lifecycle states for a job."""

    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


@dataclass
class TaskJob:
    """A unit of work for distributed execution.

    Attributes:
        id: Unique job identifier.
        task_type: Type of job (e.g. "benchmark", "verify", "repair").
        payload: Job-specific data (e.g. task definition, patch, config).
        priority: Job priority (lower = higher priority, default 0).
        created_at: When the job was created.
        started_at: When a worker started processing the job.
        completed_at: When the job finished (success or failure).
        max_retries: Maximum number of retry attempts on failure.
        retry_count: Current retry count.
        tags: Optional tags for filtering and grouping.
    """

    id: str
    task_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    max_retries: int = 0
    retry_count: int = 0
    tags: list[str] = field(default_factory=list)

    @property
    def status(self) -> JobStatus:
        """Derive current status from timestamps."""
        if self.completed_at is not None:
            return JobStatus.completed
        if self.started_at is not None:
            return JobStatus.running
        return JobStatus.pending

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage/transmission."""
        return {
            "id": self.id,
            "task_type": self.task_type,
            "payload": self.payload,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "tags": self.tags,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskJob:
        """Deserialize from dict."""
        return cls(
            id=data["id"],
            task_type=data["task_type"],
            payload=data.get("payload", {}),
            priority=data.get("priority", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            max_retries=data.get("max_retries", 0),
            retry_count=data.get("retry_count", 0),
            tags=data.get("tags", []),
        )


@dataclass
class JobResult:
    """The outcome of a completed job.

    Attributes:
        job_id: ID of the job this result belongs to.
        success: Whether the job completed successfully.
        output: Job output data (e.g. scores, verification report).
        error: Error message if the job failed.
        duration_seconds: How long the job took to execute.
        worker_id: ID of the worker that processed the job.
    """

    job_id: str
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_seconds: float = 0.0
    worker_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "worker_id": self.worker_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobResult:
        return cls(
            job_id=data["job_id"],
            success=data["success"],
            output=data.get("output", {}),
            error=data.get("error", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
            worker_id=data.get("worker_id", ""),
        )


class TaskQueue(ABC):
    """Abstract task queue for submitting and tracking jobs.

    Implementations:
    - InMemoryQueue: For testing and single-process usage
    - RedisQueue: For production distributed execution
    """

    @abstractmethod
    def submit(self, job: TaskJob) -> str:
        """Submit a job to the queue.

        Args:
            job: The job to submit.

        Returns:
            The job ID.
        """
        ...

    @abstractmethod
    def fetch(self, worker_id: str) -> TaskJob | None:
        """Fetch the next available job for a worker.

        Args:
            worker_id: ID of the worker requesting work.

        Returns:
            The next job to process, or None if queue is empty.
        """
        ...

    @abstractmethod
    def complete(self, job_id: str, result: JobResult) -> None:
        """Mark a job as completed and store its result.

        Args:
            job_id: ID of the completed job.
            result: The job result.
        """
        ...

    @abstractmethod
    def get_result(self, job_id: str) -> JobResult | None:
        """Get the result of a completed job.

        Args:
            job_id: ID of the job.

        Returns:
            The job result, or None if not completed.
        """
        ...

    @abstractmethod
    def get_status(self, job_id: str) -> JobStatus | None:
        """Get the current status of a job.

        Args:
            job_id: ID of the job.

        Returns:
            The job status, or None if not found.
        """
        ...

    @abstractmethod
    def cancel(self, job_id: str) -> bool:
        """Cancel a pending or running job.

        Args:
            job_id: ID of the job to cancel.

        Returns:
            True if the job was cancelled, False if not found or already completed.
        """
        ...

    @abstractmethod
    def size(self) -> int:
        """Get the number of pending jobs in the queue."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Remove all jobs and results from the queue."""
        ...

    @abstractmethod
    def list_jobs(
        self,
        status: JobStatus | None = None,
        task_type: str | None = None,
    ) -> list[TaskJob]:
        """List jobs, optionally filtered by status or type.

        Args:
            status: Filter by job status.
            task_type: Filter by job type.

        Returns:
            List of matching jobs.
        """
        ...
