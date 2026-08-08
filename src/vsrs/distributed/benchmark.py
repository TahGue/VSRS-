"""Distributed benchmark runner.

Submits benchmark tasks to a task queue, processes them with workers,
and collects results into an evaluation report. Supports parallel
execution across multiple workers.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from vsrs.core.logging import get_logger
from vsrs.distributed.base import JobResult, TaskJob
from vsrs.distributed.memory import InMemoryQueue
from vsrs.distributed.worker import Worker
from vsrs.eval.reports import EvaluationReport
from vsrs.eval.runner import BenchmarkRunner
from vsrs.eval.scorer import ScoreResult
from vsrs.eval.tasks import BenchmarkSet, BenchmarkTask

logger = get_logger("distributed.benchmark")


class DistributedBenchmarkRunner:
    """Runs benchmarks in parallel using a task queue and workers.

    Submits each benchmark task as a job to the queue, launches workers
    to process them, and collects results into an EvaluationReport.

    Args:
        benchmark_set: The set of benchmark tasks to run.
        task_handler: Function that processes a benchmark task and returns
            a ScoreResult dict.
        num_workers: Number of parallel workers to launch.
        queue: Optional task queue (defaults to InMemoryQueue).
    """

    def __init__(
        self,
        benchmark_set: BenchmarkSet,
        task_handler: Callable[[BenchmarkTask], dict[str, Any]],
        num_workers: int = 4,
        queue: InMemoryQueue | None = None,
    ) -> None:
        self.benchmark_set = benchmark_set
        self.task_handler = task_handler
        self.num_workers = num_workers
        self.queue = queue or InMemoryQueue()
        self.workers: list[Worker] = []
        self._job_ids: list[str] = []

    def _make_handler(self) -> Callable[[TaskJob], dict[str, Any]]:
        """Create a job handler that wraps the task handler."""
        def handler(job: TaskJob) -> dict[str, Any]:
            task_id = job.payload.get("task_id", "")
            task = self.benchmark_set.get(task_id)
            if task is None:
                raise ValueError(f"Unknown benchmark task: {task_id}")
            return self.task_handler(task)
        return handler

    def submit_all(self) -> list[str]:
        """Submit all benchmark tasks as jobs to the queue.

        Returns:
            List of job IDs.
        """
        self._job_ids = []
        for task in self.benchmark_set.all():
            job_id = f"bench_{task.id}_{uuid.uuid4().hex[:8]}"
            job = TaskJob(
                id=job_id,
                task_type="benchmark",
                payload={"task_id": task.id},
                priority=0,
                tags=["benchmark", task.task_type.value if hasattr(task.task_type, 'value') else str(task.task_type)],
            )
            self.queue.submit(job)
            self._job_ids.append(job_id)
        logger.info(f"Submitted {len(self._job_ids)} benchmark jobs to queue")
        return self._job_ids

    def run(self) -> EvaluationReport:
        """Run all benchmarks in parallel and collect results.

        Submits jobs, launches workers, waits for completion, and
        assembles the results into an EvaluationReport.

        Returns:
            EvaluationReport with results from all benchmark tasks.
        """
        start_time = time.time()

        # Submit all jobs
        self.submit_all()

        # Create and start workers
        handler = self._make_handler()
        self.workers = []
        for i in range(self.num_workers):
            worker = Worker(
                queue=self.queue,
                worker_id=f"bench-worker-{i}",
                handlers={"benchmark": handler},
                poll_interval=0.1,
            )
            self.workers.append(worker)
            worker.start()

        # Wait for all jobs to complete
        results: dict[str, ScoreResult] = {}
        pending = set(self._job_ids)
        while pending:
            for job_id in list(pending):
                result = self.queue.get_result(job_id)
                if result is not None:
                    pending.discard(job_id)
                    if result.success:
                        score = ScoreResult.from_dict(result.output)
                        results[job_id] = score
                    else:
                        logger.warning(
                            f"Job {job_id} failed: {result.error}"
                        )
            if pending:
                time.sleep(0.1)

        # Stop workers
        for worker in self.workers:
            worker.stop()

        elapsed = time.time() - start_time
        logger.info(
            f"Distributed benchmark run complete: "
            f"{len(results)}/{len(self._job_ids)} succeeded, "
            f"duration={elapsed:.2f}s"
        )

        # Build evaluation report
        scores = list(results.values())
        return EvaluationReport.from_scores(scores)

    def get_job_status(self) -> dict[str, str]:
        """Get the status of all submitted jobs.

        Returns:
            Dict mapping job_id to status string.
        """
        statuses: dict[str, str] = {}
        for job_id in self._job_ids:
            status = self.queue.get_status(job_id)
            statuses[job_id] = status.value if status else "unknown"
        return statuses

    def get_worker_stats(self) -> list[dict[str, Any]]:
        """Get statistics for all workers.

        Returns:
            List of worker stat dicts.
        """
        return [w.stats() for w in self.workers]
