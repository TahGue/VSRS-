"""Distributed execution for VSRS.

Provides a task queue abstraction for parallel benchmark runs and
verification workers. Supports in-memory (testing) and Redis (production)
backends. Includes a worker pool with resource allocation and auto-scaling.
"""

from __future__ import annotations

from vsrs.distributed.base import (
    JobResult,
    JobStatus,
    TaskJob,
    TaskQueue,
)
from vsrs.distributed.benchmark import DistributedBenchmarkRunner
from vsrs.distributed.memory import InMemoryQueue
from vsrs.distributed.pool import (
    InsufficientResourcesError,
    PoolConfig,
    ResourceSpec,
    WorkerInfo,
    WorkerPool,
    WorkerState,
)
from vsrs.distributed.redis_queue import RedisQueue
from vsrs.distributed.worker import Worker

__all__ = [
    "DistributedBenchmarkRunner",
    "InMemoryQueue",
    "InsufficientResourcesError",
    "JobResult",
    "JobStatus",
    "PoolConfig",
    "RedisQueue",
    "ResourceSpec",
    "TaskJob",
    "TaskQueue",
    "Worker",
    "WorkerInfo",
    "WorkerPool",
    "WorkerState",
]
