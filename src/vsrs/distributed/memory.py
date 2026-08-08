"""In-memory task queue implementation.

Used for testing and single-process scenarios. No external dependencies
required. Thread-safe for basic concurrent access.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from vsrs.core.logging import get_logger
from vsrs.distributed.base import JobResult, JobStatus, TaskJob, TaskQueue

logger = get_logger("distributed.memory")


class InMemoryQueue(TaskQueue):
    """Thread-safe in-memory task queue.

    Stores jobs and results in memory. Suitable for testing and
    single-process usage. No persistence across restarts.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, TaskJob] = {}
        self._results: dict[str, JobResult] = {}
        self._pending: list[str] = []  # job IDs in priority order
        self._lock = threading.Lock()

    def submit(self, job: TaskJob) -> str:
        """Submit a job to the queue."""
        with self._lock:
            self._jobs[job.id] = job
            self._pending.append(job.id)
            # Sort by priority (lower = higher priority)
            self._pending.sort(
                key=lambda jid: self._jobs[jid].priority
            )
            logger.info(f"Submitted job {job.id} (type={job.task_type})")
        return job.id

    def fetch(self, worker_id: str) -> TaskJob | None:
        """Fetch the next available job for a worker."""
        with self._lock:
            if not self._pending:
                return None
            job_id = self._pending.pop(0)
            job = self._jobs[job_id]
            job.started_at = datetime.now(timezone.utc)
            logger.info(f"Worker {worker_id} fetched job {job_id}")
            return job

    def complete(self, job_id: str, result: JobResult) -> None:
        """Mark a job as completed and store its result."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                logger.warning(f"Cannot complete unknown job {job_id}")
                return
            job.completed_at = datetime.now(timezone.utc)
            self._results[job_id] = result
            logger.info(
                f"Job {job_id} completed: success={result.success}, "
                f"duration={result.duration_seconds:.2f}s"
            )

    def get_result(self, job_id: str) -> JobResult | None:
        """Get the result of a completed job."""
        with self._lock:
            return self._results.get(job_id)

    def get_status(self, job_id: str) -> JobStatus | None:
        """Get the current status of a job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return job.status

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.completed_at is not None:
                return False
            if job_id in self._pending:
                self._pending.remove(job_id)
            job.completed_at = datetime.now(timezone.utc)
            self._results[job_id] = JobResult(
                job_id=job_id,
                success=False,
                error="Job cancelled",
            )
            logger.info(f"Cancelled job {job_id}")
            return True

    def size(self) -> int:
        """Get the number of pending jobs."""
        with self._lock:
            return len(self._pending)

    def clear(self) -> None:
        """Remove all jobs and results."""
        with self._lock:
            self._jobs.clear()
            self._results.clear()
            self._pending.clear()

    def list_jobs(
        self,
        status: JobStatus | None = None,
        task_type: str | None = None,
    ) -> list[TaskJob]:
        """List jobs, optionally filtered."""
        with self._lock:
            jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        if task_type is not None:
            jobs = [j for j in jobs if j.task_type == task_type]
        return jobs
