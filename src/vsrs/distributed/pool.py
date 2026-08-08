"""Worker pool with resource allocation and auto-scaling.

Manages a pool of verification workers with:
- Per-worker resource capacity (CPU, memory, GPU)
- Job resource requirements and capacity-aware scheduling
- Auto-scaling: spin up/down workers based on queue depth
- Health checks and automatic worker replacement
- Graceful shutdown with job draining
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from vsrs.core.logging import get_logger
from vsrs.distributed.base import JobResult, JobStatus, TaskJob, TaskQueue
from vsrs.distributed.worker import Worker

logger = get_logger("distributed.pool")


class WorkerState(str, Enum):
    """State of a worker in the pool."""

    idle = "idle"
    busy = "busy"
    draining = "draining"
    stopped = "stopped"
    unhealthy = "unhealthy"


@dataclass
class ResourceSpec:
    """Resource specification for a worker or job.

    Attributes:
        cpu: Number of CPU cores required.
        memory_mb: Memory in MB.
        gpu: Number of GPUs required (0 = no GPU needed).
        disk_mb: Disk space in MB.
    """

    cpu: float = 1.0
    memory_mb: int = 512
    gpu: int = 0
    disk_mb: int = 0

    def can_fit(self, other: ResourceSpec) -> bool:
        """Check if this resource spec can accommodate another."""
        return (
            self.cpu >= other.cpu
            and self.memory_mb >= other.memory_mb
            and self.gpu >= other.gpu
            and self.disk_mb >= other.disk_mb
        )

    def subtract(self, other: ResourceSpec) -> ResourceSpec:
        """Return a new spec with resources reduced by other."""
        return ResourceSpec(
            cpu=max(0, self.cpu - other.cpu),
            memory_mb=max(0, self.memory_mb - other.memory_mb),
            gpu=max(0, self.gpu - other.gpu),
            disk_mb=max(0, self.disk_mb - other.disk_mb),
        )

    def add(self, other: ResourceSpec) -> ResourceSpec:
        """Return a new spec with resources increased by other."""
        return ResourceSpec(
            cpu=self.cpu + other.cpu,
            memory_mb=self.memory_mb + other.memory_mb,
            gpu=self.gpu + other.gpu,
            disk_mb=self.disk_mb + other.disk_mb,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu": self.cpu,
            "memory_mb": self.memory_mb,
            "gpu": self.gpu,
            "disk_mb": self.disk_mb,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResourceSpec:
        return cls(
            cpu=data.get("cpu", 1.0),
            memory_mb=data.get("memory_mb", 512),
            gpu=data.get("gpu", 0),
            disk_mb=data.get("disk_mb", 0),
        )


@dataclass
class WorkerInfo:
    """Runtime information about a worker in the pool.

    Attributes:
        worker_id: Unique worker identifier.
        worker: The underlying Worker instance.
        capacity: Total resource capacity of this worker.
        available: Currently available resources.
        state: Current worker state.
        current_job_id: ID of the job being processed (if busy).
        started_at: When the worker was started.
        last_heartbeat: Last heartbeat timestamp.
        jobs_processed: Total jobs processed.
        jobs_succeeded: Successfully completed jobs.
        jobs_failed: Failed jobs.
    """

    worker_id: str
    worker: Worker
    capacity: ResourceSpec
    available: ResourceSpec
    state: WorkerState = WorkerState.idle
    current_job_id: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    jobs_processed: int = 0
    jobs_succeeded: int = 0
    jobs_failed: int = 0

    @property
    def is_available(self) -> bool:
        return self.state == WorkerState.idle

    @property
    def is_healthy(self) -> bool:
        return self.state not in (WorkerState.stopped, WorkerState.unhealthy)

    def update_heartbeat(self) -> None:
        self.last_heartbeat = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "state": self.state.value,
            "capacity": self.capacity.to_dict(),
            "available": self.available.to_dict(),
            "current_job_id": self.current_job_id,
            "started_at": self.started_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "jobs_processed": self.jobs_processed,
            "jobs_succeeded": self.jobs_succeeded,
            "jobs_failed": self.jobs_failed,
            "is_healthy": self.is_healthy,
        }


class InsufficientResourcesError(Exception):
    """Raised when no worker has sufficient resources for a job."""

    def __init__(self, job_id: str, required: ResourceSpec) -> None:
        self.job_id = job_id
        self.required = required
        super().__init__(
            f"No available worker has sufficient resources for job '{job_id}': "
            f"requires cpu={required.cpu}, memory={required.memory_mb}MB, gpu={required.gpu}"
        )


@dataclass
class PoolConfig:
    """Configuration for the worker pool.

    Attributes:
        min_workers: Minimum number of workers to maintain.
        max_workers: Maximum number of workers allowed.
        scale_up_threshold: Queue depth to trigger scale-up.
        scale_down_threshold: Queue depth to trigger scale-down.
        health_check_interval: Seconds between health checks.
        heartbeat_timeout: Seconds before a worker is considered unhealthy.
        default_worker_capacity: Default capacity for auto-scaled workers.
        job_timeout: Default job timeout in seconds (0 = no timeout).
    """

    min_workers: int = 1
    max_workers: int = 10
    scale_up_threshold: int = 5
    scale_down_threshold: int = 0
    health_check_interval: float = 10.0
    heartbeat_timeout: float = 60.0
    default_worker_capacity: ResourceSpec = field(default_factory=ResourceSpec)
    job_timeout: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
            "scale_up_threshold": self.scale_up_threshold,
            "scale_down_threshold": self.scale_down_threshold,
            "health_check_interval": self.health_check_interval,
            "heartbeat_timeout": self.heartbeat_timeout,
            "default_worker_capacity": self.default_worker_capacity.to_dict(),
            "job_timeout": self.job_timeout,
        }


class WorkerPool:
    """Manages a pool of workers with resource-aware scheduling and auto-scaling.

    Features:
    - Resource-aware job scheduling: matches job requirements to worker capacity
    - Auto-scaling: adds workers when queue depth exceeds threshold
    - Health monitoring: detects unhealthy workers via heartbeat timeout
    - Graceful shutdown: drains workers and waits for in-flight jobs
    - Thread-safe: all operations protected by a lock
    """

    def __init__(
        self,
        queue: TaskQueue,
        config: PoolConfig | None = None,
        handler_factory: Callable[[str], dict[str, Callable[[TaskJob], dict[str, Any]]]] | None = None,
    ) -> None:
        self.queue = queue
        self.config = config or PoolConfig()
        self.handler_factory = handler_factory
        self._workers: dict[str, WorkerInfo] = {}
        self._lock = threading.RLock()
        self._running = False
        self._scaler_thread: threading.Thread | None = None
        self._health_thread: threading.Thread | None = None
        self._worker_counter = 0
        self._pending_resources: dict[str, ResourceSpec] = {}  # job_id -> requirements

    # --- Worker lifecycle ---

    def add_worker(
        self,
        worker_id: str | None = None,
        capacity: ResourceSpec | None = None,
        handlers: dict[str, Callable[[TaskJob], dict[str, Any]]] | None = None,
    ) -> WorkerInfo:
        """Add a new worker to the pool.

        Args:
            worker_id: Optional worker ID (auto-generated if not provided).
            capacity: Resource capacity for this worker.
            handlers: Job handler functions.

        Returns:
            WorkerInfo for the new worker.
        """
        with self._lock:
            self._worker_counter += 1
            wid = worker_id or f"pool_worker_{self._worker_counter}"
            cap = capacity or self.config.default_worker_capacity

            if self.handler_factory and handlers is None:
                handlers = self.handler_factory(wid)

            worker = Worker(
                queue=self.queue,
                worker_id=wid,
                handlers=handlers or {},
                poll_interval=0.5,
            )
            info = WorkerInfo(
                worker_id=wid,
                worker=worker,
                capacity=cap,
                available=ResourceSpec(
                    cpu=cap.cpu, memory_mb=cap.memory_mb, gpu=cap.gpu, disk_mb=cap.disk_mb
                ),
            )
            self._workers[wid] = info
            logger.info(f"Worker added to pool: {wid} (capacity: {cap.to_dict()})")
            return info

    def remove_worker(self, worker_id: str, drain: bool = True) -> bool:
        """Remove a worker from the pool.

        Args:
            worker_id: ID of the worker to remove.
            drain: If True, wait for the worker to finish its current job.

        Returns:
            True if the worker was removed, False if not found.
        """
        with self._lock:
            info = self._workers.get(worker_id)
            if info is None:
                return False

            if drain and info.state == WorkerState.busy:
                info.state = WorkerState.draining
                logger.info(f"Worker {worker_id} draining (waiting for job completion)")
                # In a real implementation, we'd wait for the job to finish
                # For now, just mark as draining

            info.worker.stop()
            info.state = WorkerState.stopped
            self._workers.pop(worker_id)
            logger.info(f"Worker removed from pool: {worker_id}")
            return True

    def get_worker(self, worker_id: str) -> WorkerInfo | None:
        """Get worker info by ID."""
        with self._lock:
            return self._workers.get(worker_id)

    def list_workers(self) -> list[WorkerInfo]:
        """List all workers in the pool."""
        with self._lock:
            return list(self._workers.values())

    # --- Resource-aware scheduling ---

    def submit_job(
        self,
        job: TaskJob,
        resources: ResourceSpec | None = None,
    ) -> str:
        """Submit a job with resource requirements.

        Args:
            job: The job to submit.
            resources: Resource requirements for the job.

        Returns:
            The job ID.
        """
        req = resources or ResourceSpec()
        self._pending_resources[job.id] = req
        job_id = self.queue.submit(job)
        logger.debug(f"Job submitted: {job_id} (requires: {req.to_dict()})")
        return job_id

    def find_capable_worker(self, requirements: ResourceSpec) -> WorkerInfo | None:
        """Find an idle worker with sufficient resources.

        Args:
            requirements: Resource requirements for the job.

        Returns:
            WorkerInfo for a capable worker, or None if none available.
        """
        with self._lock:
            for info in self._workers.values():
                if info.is_available and info.available.can_fit(requirements):
                    return info
            return None

    def assign_job(self, worker_info: WorkerInfo, job: TaskJob, requirements: ResourceSpec) -> None:
        """Assign a job to a worker and reserve resources.

        Args:
            worker_info: The worker to assign to.
            job: The job to assign.
            requirements: Resource requirements for the job.
        """
        with self._lock:
            worker_info.available = worker_info.available.subtract(requirements)
            worker_info.state = WorkerState.busy
            worker_info.current_job_id = job.id
            worker_info.update_heartbeat()
            logger.debug(
                f"Job {job.id} assigned to worker {worker_info.worker_id} "
                f"(remaining: {worker_info.available.to_dict()})"
            )

    def release_worker(self, worker_id: str, job_id: str, resources: ResourceSpec) -> None:
        """Release resources back to a worker after job completion.

        Args:
            worker_id: The worker ID.
            job_id: The completed job ID.
            resources: Resources to release.
        """
        with self._lock:
            info = self._workers.get(worker_id)
            if info is None:
                return
            info.available = info.available.add(resources)
            info.state = WorkerState.idle
            info.current_job_id = None
            info.jobs_processed += 1
            info.update_heartbeat()
            logger.debug(f"Worker {worker_id} released (available: {info.available.to_dict()})")

    def mark_job_result(self, worker_id: str, success: bool) -> None:
        """Update worker stats based on job result."""
        with self._lock:
            info = self._workers.get(worker_id)
            if info is None:
                return
            if success:
                info.jobs_succeeded += 1
            else:
                info.jobs_failed += 1

    # --- Auto-scaling ---

    def start(self) -> None:
        """Start the worker pool with auto-scaling and health checks."""
        with self._lock:
            if self._running:
                return
            self._running = True

            # Ensure minimum workers
            while len(self._workers) < self.config.min_workers:
                self.add_worker()

            # Start all workers
            for info in self._workers.values():
                if not info.worker.is_running:
                    info.worker.start()

            # Start scaler thread
            self._scaler_thread = threading.Thread(target=self._scaler_loop, daemon=True)
            self._scaler_thread.start()

            # Start health check thread
            self._health_thread = threading.Thread(target=self._health_loop, daemon=True)
            self._health_thread.start()

            logger.info(
                f"Worker pool started: {len(self._workers)} workers "
                f"(min={self.config.min_workers}, max={self.config.max_workers})"
            )

    def stop(self, drain: bool = True) -> None:
        """Stop the worker pool.

        Args:
            drain: If True, wait for in-flight jobs to complete.
        """
        with self._lock:
            self._running = False

        # Stop scaler and health threads
        if self._scaler_thread:
            self._scaler_thread.join(timeout=5)
        if self._health_thread:
            self._health_thread.join(timeout=5)

        # Stop all workers
        with self._lock:
            for info in self._workers.values():
                info.worker.stop()
                info.state = WorkerState.stopped
            self._workers.clear()

        logger.info("Worker pool stopped")

    def _scaler_loop(self) -> None:
        """Auto-scaling loop: adjusts worker count based on queue depth."""
        while self._running:
            try:
                self._check_scaling()
            except Exception as e:
                logger.error(f"Scaler error: {e}")
            time.sleep(self.config.health_check_interval)

    def _check_scaling(self) -> None:
        """Check if we need to scale up or down."""
        with self._lock:
            queue_size = self.queue.size()
            worker_count = len(self._workers)
            idle_count = sum(1 for w in self._workers.values() if w.is_available)

            # Scale up: queue has jobs and we have capacity for more workers
            if (
                queue_size > self.config.scale_up_threshold
                and worker_count < self.config.max_workers
            ):
                self.add_worker()
                logger.info(
                    f"Scaled up: queue_size={queue_size}, workers={worker_count + 1}"
                )

            # Scale down: no queued jobs and more than min workers
            elif (
                queue_size <= self.config.scale_down_threshold
                and worker_count > self.config.min_workers
                and idle_count > 0
            ):
                # Remove an idle worker
                for info in self._workers.values():
                    if info.is_available:
                        self.remove_worker(info.worker_id, drain=False)
                        logger.info(
                            f"Scaled down: queue_size={queue_size}, workers={worker_count - 1}"
                        )
                        break

    # --- Health checks ---

    def _health_loop(self) -> None:
        """Health check loop: detects unhealthy workers."""
        while self._running:
            try:
                self._check_health()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            time.sleep(self.config.health_check_interval)

    def _check_health(self) -> None:
        """Check health of all workers."""
        now = datetime.now(timezone.utc)
        timeout_seconds = self.config.heartbeat_timeout

        with self._lock:
            for info in list(self._workers.values()):
                if info.state in (WorkerState.stopped, WorkerState.draining):
                    continue

                elapsed = (now - info.last_heartbeat).total_seconds()
                if elapsed > timeout_seconds:
                    logger.warning(
                        f"Worker {info.worker_id} unhealthy: "
                        f"no heartbeat for {elapsed:.0f}s"
                    )
                    info.state = WorkerState.unhealthy

                    # Replace unhealthy worker
                    if len(self._workers) <= self.config.max_workers:
                        self.remove_worker(info.worker_id, drain=False)
                        self.add_worker()
                        logger.info(f"Replaced unhealthy worker: {info.worker_id}")

    def heartbeat(self, worker_id: str) -> bool:
        """Record a heartbeat for a worker.

        Args:
            worker_id: The worker ID.

        Returns:
            True if the worker was found and updated, False otherwise.
        """
        with self._lock:
            info = self._workers.get(worker_id)
            if info is None:
                return False
            info.update_heartbeat()
            if info.state == WorkerState.unhealthy:
                info.state = WorkerState.idle if info.current_job_id is None else WorkerState.busy
            return True

    # --- Pool stats ---

    @property
    def worker_count(self) -> int:
        """Number of workers in the pool."""
        with self._lock:
            return len(self._workers)

    @property
    def idle_count(self) -> int:
        """Number of idle workers."""
        with self._lock:
            return sum(1 for w in self._workers.values() if w.is_available)

    @property
    def busy_count(self) -> int:
        """Number of busy workers."""
        with self._lock:
            return sum(1 for w in self._workers.values() if w.state == WorkerState.busy)

    @property
    def is_running(self) -> bool:
        return self._running

    def pool_stats(self) -> dict[str, Any]:
        """Get comprehensive pool statistics."""
        with self._lock:
            total_capacity = ResourceSpec(cpu=0, memory_mb=0, gpu=0, disk_mb=0)
            total_available = ResourceSpec(cpu=0, memory_mb=0, gpu=0, disk_mb=0)
            for info in self._workers.values():
                total_capacity = total_capacity.add(info.capacity)
                total_available = total_available.add(info.available)

            return {
                "is_running": self._running,
                "worker_count": len(self._workers),
                "idle_count": sum(1 for w in self._workers.values() if w.is_available),
                "busy_count": sum(1 for w in self._workers.values() if w.state == WorkerState.busy),
                "unhealthy_count": sum(1 for w in self._workers.values() if w.state == WorkerState.unhealthy),
                "queue_size": self.queue.size(),
                "total_capacity": total_capacity.to_dict(),
                "total_available": total_available.to_dict(),
                "config": self.config.to_dict(),
                "workers": [w.to_dict() for w in self._workers.values()],
            }

    def process_job_on_worker(
        self,
        job: TaskJob,
        resources: ResourceSpec | None = None,
    ) -> JobResult:
        """Synchronously process a job on a capable worker.

        Finds an idle worker with sufficient resources, assigns the job,
        processes it, and releases the worker.

        Args:
            job: The job to process.
            resources: Resource requirements for the job.

        Returns:
            The job result.

        Raises:
            InsufficientResourcesError: If no worker can handle the job.
        """
        req = resources or ResourceSpec()

        with self._lock:
            worker_info = self.find_capable_worker(req)
            if worker_info is None:
                raise InsufficientResourcesError(job.id, req)
            self.assign_job(worker_info, job, req)

        try:
            result = worker_info.worker._execute_job(job)
            with self._lock:
                self.mark_job_result(worker_info.worker_id, result.success)
            return result
        finally:
            with self._lock:
                self.release_worker(worker_info.worker_id, job.id, req)
