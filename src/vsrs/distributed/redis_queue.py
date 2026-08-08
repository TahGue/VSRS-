"""Redis-backed task queue implementation.

Uses Redis for distributed job coordination. Requires the `redis` package.
Falls back gracefully when Redis is not available.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from vsrs.core.logging import get_logger
from vsrs.distributed.base import JobResult, JobStatus, TaskJob, TaskQueue

logger = get_logger("distributed.redis")


class RedisQueue(TaskQueue):
    """Redis-backed task queue for distributed execution.

    Uses Redis lists for the pending queue and Redis hashes for job
    storage and results. Jobs are serialized as JSON.

    Args:
        redis_url: Redis connection URL (e.g. "redis://localhost:6379/0").
        queue_key: Redis key for the pending queue.
        jobs_key: Redis key prefix for job storage.
        results_key: Redis key prefix for results storage.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        queue_key: str = "vsrs:queue",
        jobs_key: str = "vsrs:jobs",
        results_key: str = "vsrs:results",
    ) -> None:
        self.redis_url = redis_url
        self.queue_key = queue_key
        self.jobs_key = jobs_key
        self.results_key = results_key
        self._redis: Any = None
        self._connect()

    def _connect(self) -> None:
        """Connect to Redis. Logs warning if unavailable."""
        try:
            import redis
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            self._redis.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")
        except ImportError:
            logger.warning("redis package not installed, RedisQueue will not function")
            self._redis = None
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}")
            self._redis = None

    @property
    def available(self) -> bool:
        """Check if Redis connection is available."""
        if self._redis is None:
            return False
        try:
            self._redis.ping()
            return True
        except Exception:
            return False

    def submit(self, job: TaskJob) -> str:
        """Submit a job to the queue."""
        if not self.available:
            raise RuntimeError("Redis is not available")
        self._redis.hset(self.jobs_key, job.id, json.dumps(job.to_dict()))
        self._redis.lpush(self.queue_key, job.id)
        logger.info(f"Submitted job {job.id} to Redis queue")
        return job.id

    def fetch(self, worker_id: str) -> TaskJob | None:
        """Fetch the next available job for a worker (blocking pop)."""
        if not self.available:
            return None
        # BRPOP returns (key, value) or None
        result = self._redis.brpop(self.queue_key, timeout=0)
        if result is None:
            return None
        _, job_id = result
        job_data = self._redis.hget(self.jobs_key, job_id)
        if job_data is None:
            return None
        job = TaskJob.from_dict(json.loads(job_data))
        job.started_at = datetime.now(timezone.utc)
        self._redis.hset(self.jobs_key, job_id, json.dumps(job.to_dict()))
        logger.info(f"Worker {worker_id} fetched job {job_id} from Redis")
        return job

    def complete(self, job_id: str, result: JobResult) -> None:
        """Mark a job as completed and store its result."""
        if not self.available:
            return
        job_data = self._redis.hget(self.jobs_key, job_id)
        if job_data is None:
            return
        job = TaskJob.from_dict(json.loads(job_data))
        job.completed_at = datetime.now(timezone.utc)
        self._redis.hset(self.jobs_key, job_id, json.dumps(job.to_dict()))
        self._redis.hset(self.results_key, job_id, json.dumps(result.to_dict()))
        logger.info(f"Job {job_id} completed in Redis")

    def get_result(self, job_id: str) -> JobResult | None:
        """Get the result of a completed job."""
        if not self.available:
            return None
        data = self._redis.hget(self.results_key, job_id)
        if data is None:
            return None
        return JobResult.from_dict(json.loads(data))

    def get_status(self, job_id: str) -> JobStatus | None:
        """Get the current status of a job."""
        if not self.available:
            return None
        data = self._redis.hget(self.jobs_key, job_id)
        if data is None:
            return None
        job = TaskJob.from_dict(json.loads(data))
        return job.status

    def cancel(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        if not self.available:
            return False
        data = self._redis.hget(self.jobs_key, job_id)
        if data is None:
            return False
        job = TaskJob.from_dict(json.loads(data))
        if job.completed_at is not None:
            return False
        job.completed_at = datetime.now(timezone.utc)
        self._redis.hset(self.jobs_key, job_id, json.dumps(job.to_dict()))
        self._redis.hset(self.results_key, job_id, json.dumps(JobResult(
            job_id=job_id,
            success=False,
            error="Job cancelled",
        ).to_dict()))
        # Remove from queue if present
        self._redis.lrem(self.queue_key, 0, job_id)
        return True

    def size(self) -> int:
        """Get the number of pending jobs."""
        if not self.available:
            return 0
        return self._redis.llen(self.queue_key)

    def clear(self) -> None:
        """Remove all jobs and results."""
        if not self.available:
            return
        self._redis.delete(self.queue_key, self.jobs_key, self.results_key)

    def list_jobs(
        self,
        status: JobStatus | None = None,
        task_type: str | None = None,
    ) -> list[TaskJob]:
        """List jobs, optionally filtered."""
        if not self.available:
            return []
        all_jobs = self._redis.hgetall(self.jobs_key)
        jobs: list[TaskJob] = []
        for data in all_jobs.values():
            job = TaskJob.from_dict(json.loads(data))
            if status is not None and job.status != status:
                continue
            if task_type is not None and job.task_type != task_type:
                continue
            jobs.append(job)
        return jobs
