"""Worker process for distributed task execution.

A worker fetches jobs from a task queue, executes them, and reports
results. Supports graceful shutdown, concurrent execution, and
configurable job handlers.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from vsrs.core.logging import get_logger
from vsrs.distributed.base import JobResult, TaskJob, TaskQueue

logger = get_logger("distributed.worker")

# Type for job handler functions
JobHandler = Callable[[TaskJob], dict[str, Any]]


class Worker:
    """A worker that processes jobs from a task queue.

    Args:
        queue: The task queue to fetch jobs from.
        worker_id: Unique identifier for this worker.
        handlers: Dict mapping task_type to handler functions.
        poll_interval: Seconds to wait between queue polls when idle.
        max_jobs: Maximum number of jobs to process (None = unlimited).
    """

    def __init__(
        self,
        queue: TaskQueue,
        worker_id: str = "",
        handlers: dict[str, JobHandler] | None = None,
        poll_interval: float = 1.0,
        max_jobs: int | None = None,
    ) -> None:
        self.queue = queue
        self.worker_id = worker_id or f"worker_{id(self)}"
        self.handlers = handlers or {}
        self.poll_interval = poll_interval
        self.max_jobs = max_jobs
        self._running = False
        self._thread: threading.Thread | None = None
        self._jobs_processed = 0
        self._jobs_succeeded = 0
        self._jobs_failed = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def jobs_processed(self) -> int:
        return self._jobs_processed

    @property
    def jobs_succeeded(self) -> int:
        return self._jobs_succeeded

    @property
    def jobs_failed(self) -> int:
        return self._jobs_failed

    def register_handler(self, task_type: str, handler: JobHandler) -> None:
        """Register a handler for a specific job type.

        Args:
            task_type: The type of jobs this handler processes.
            handler: Function that takes a TaskJob and returns output dict.
        """
        self.handlers[task_type] = handler
        logger.info(f"Registered handler for task_type '{task_type}'")

    def process_one(self) -> JobResult | None:
        """Process a single job from the queue.

        Returns:
            The JobResult if a job was processed, None if queue was empty.
        """
        job = self.queue.fetch(self.worker_id)
        if job is None:
            return None

        return self._execute_job(job)

    def _execute_job(self, job: TaskJob) -> JobResult:
        """Execute a single job and report the result."""
        start = time.time()
        logger.info(f"Processing job {job.id} (type={job.task_type})")

        handler = self.handlers.get(job.task_type)
        if handler is None:
            result = JobResult(
                job_id=job.id,
                success=False,
                error=f"No handler registered for task_type '{job.task_type}'",
                duration_seconds=time.time() - start,
                worker_id=self.worker_id,
            )
            self.queue.complete(job.id, result)
            self._jobs_processed += 1
            self._jobs_failed += 1
            return result

        try:
            output = handler(job)
            result = JobResult(
                job_id=job.id,
                success=True,
                output=output,
                duration_seconds=time.time() - start,
                worker_id=self.worker_id,
            )
            self._jobs_processed += 1
            self._jobs_succeeded += 1
        except Exception as e:
            result = JobResult(
                job_id=job.id,
                success=False,
                error=str(e),
                duration_seconds=time.time() - start,
                worker_id=self.worker_id,
            )
            self._jobs_processed += 1
            self._jobs_failed += 1
            logger.error(f"Job {job.id} failed: {e}")

        self.queue.complete(job.id, result)
        return result

    def start(self) -> None:
        """Start the worker in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"Worker {self.worker_id} started")

    def stop(self) -> None:
        """Signal the worker to stop after current job."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info(f"Worker {self.worker_id} stopped")

    def _run_loop(self) -> None:
        """Main worker loop: fetch and process jobs until stopped."""
        while self._running:
            if self.max_jobs is not None and self._jobs_processed >= self.max_jobs:
                break
            result = self.process_one()
            if result is None:
                time.sleep(self.poll_interval)

    def stats(self) -> dict[str, Any]:
        """Get worker statistics."""
        return {
            "worker_id": self.worker_id,
            "is_running": self._running,
            "jobs_processed": self._jobs_processed,
            "jobs_succeeded": self._jobs_succeeded,
            "jobs_failed": self._jobs_failed,
            "handlers": list(self.handlers.keys()),
        }
